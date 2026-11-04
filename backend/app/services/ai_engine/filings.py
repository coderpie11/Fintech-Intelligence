"""Filing text extraction for the CEO Say-vs-Do credibility tracker.

NSE's corporate-announcement *subjects* are one-line notices ("Investor
Presentation") and contain no guidance. The guidance lives in the attached
PDFs: earnings-call transcripts, investor presentations and results press
releases. This module downloads those attachments, extracts the text with
pypdf, and returns sentences that state a measurable forward-looking target.

Everything is cached on disk under `backend/data/filings/` so a repeat request
is a file read, not another download. Only public NSE attachments are read.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

from app.core.config import DATA_DIR
from app.data.adapters import nse_adapter as N

FILINGS_DIR = DATA_DIR / "filings"
FILINGS_DIR.mkdir(parents=True, exist_ok=True)

# Categories whose attachments are documents with management commentary.
_DOC_CATEGORIES = (
    "analysts/institutional investor meet",
    "investor presentation",
    "press release",
    "earnings call",
    "con. call",
    "transcript",
)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0 Safari/537.36"
MAX_PDF_BYTES = 12 * 1024 * 1024
MAX_PAGES = 45


def _is_document(ann: dict) -> bool:
    url = (ann.get("attchmntFile") or "").lower()
    if not url.endswith(".pdf"):
        return False
    desc = (ann.get("desc") or "").lower()
    return any(c in desc for c in _DOC_CATEGORIES)


def _download_pdf(url: str, dest: Path) -> bytes | None:
    import requests
    try:
        r = requests.get(url, timeout=60, headers={
            "User-Agent": _UA, "Accept": "application/pdf,*/*",
            "Referer": "https://www.nseindia.com/"})
        if r.status_code != 200 or not r.content:
            return None
        if len(r.content) > MAX_PDF_BYTES:
            return None
        dest.write_bytes(r.content)
        return r.content
    except Exception:  # noqa: BLE001
        return None


def _pdf_text(raw: bytes) -> str | None:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        chunks = []
        for page in reader.pages[:MAX_PAGES]:
            try:
                chunks.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001
                continue
        text = "\n".join(chunks).strip()
        return text or None
    except Exception:  # noqa: BLE001
        return None


def document_text(symbol: str, ann: dict) -> tuple[str | None, str]:
    """Return (text, source) for one announcement attachment, cached on disk."""
    url = ann.get("attchmntFile") or ""
    seq = str(ann.get("seq_id") or abs(hash(url)) % 10**10)
    dest = FILINGS_DIR / f"{symbol.upper()}_{seq}.pdf"
    txt_dest = dest.with_suffix(".txt")
    if txt_dest.exists():
        try:
            return txt_dest.read_text(encoding="utf-8", errors="ignore"), "cache"
        except Exception:  # noqa: BLE001
            pass
    raw = dest.read_bytes() if dest.exists() else _download_pdf(url, dest)
    if not raw:
        return None, "download-failed"
    text = _pdf_text(raw)
    if not text:
        return None, "no-text-layer"
    try:
        txt_dest.write_text(text, encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return text, "extracted"


_METRIC_CUES = {
    "revenue_growth": ("revenue", "top line", "turnover", "sales growth",
                       "income growth", "total income"),
    "margin": ("margin", "nim", "net interest margin", "ebitda margin", "opm",
               "casa ratio"),
    "debt_reduction": ("net debt", "debt reduction", "deleverag", "leverage",
                       "gnpa", "gross npa", "npa ratio"),
    "capex": ("capex", "capital expenditure", "capacity addition", "capacity",
              "stores", " gigawatt", " gw ", "order book"),
    "dividend": ("dividend", "payout"),
    "volume_growth": ("volume growth", "subscribers", "disbursement",
                      "loan growth", "credit growth", "deposit growth",
                      "aum", "premium growth"),
}

_FILLER = re.compile(
    r"(not spend too much time|you can see|thank you|good morning|good evening|"
    r"moderator|ladies and gentlemen|let me take|first question|next question|"
    r"operator|conference call|page \d+ of)", re.I)

_COMMIT_CUE = re.compile(
    r"\b(will|expect|expects|expected|guidance|guide|target|plan|plans|intend|"
    r"intends|aim|aims|commit|commits|forecast|outlook|going forward|confident|"
    r"on track|trajectory|visibility)\b", re.I)

# Only an explicit guidance phrase counts as a commitment. Generic future
# tense ("I will not spend too much time") is not guidance.
_STRONG = re.compile(
    r"(we (?:expect|expects|target|targets|aim|aims|plan|plans|intend|intends|"
    r"guide|are confident|remain confident|anticipate)|guidance|our target|"
    r"target of|expect to|aim to|plan to|intend to|will grow|will expand|"
    r"will improve|will be around|will be in the range|going forward|"
    r"on track to|outlook for|visibility of|confident of|committed to)",
    re.I)


def _clean(text: str) -> str:
    text = text.replace("\u00ad", "")
    text = re.sub(r"[ \t]+", " ", text)
    return text.replace("\n", " ")


def _sentences(text: str) -> list[str]:
    flat = _clean(text)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(])", flat)
    return [p.strip() for p in parts if 25 <= len(p.strip()) <= 520]


def _target_pct(sentence: str) -> float | None:
    """A stated percentage, normalised from basis points where needed."""
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:%|percent|per cent|pc\b)", sentence, re.I)
    if m:
        return float(m.group(1))
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:bps|basis points?)", sentence, re.I)
    if m:
        return round(float(m.group(1)) / 100, 2)
    return None


def _metric(sentence: str) -> tuple[str, str] | None:
    low = sentence.lower()
    for name, cues in _METRIC_CUES.items():
        for c in cues:
            if c in low:
                return name, c.strip()
    return None


def _number_phrase(sentence: str) -> str | None:
    """The first explicit quantity in the sentence, for display."""
    m = re.search(
        r"(?:Rs\.?|₹|INR)\s?[\d,]+(?:\.\d+)?\s*(?:crore|cr|billion|million|bn|mn)?"
        r"|\d+(?:\.\d+)?\s*(?:%|percent|per cent|pc\b|bps|basis points?|GW|MW|MT|"
        r"million|billion|crore|stores?|years?)",
        sentence, re.I)
    return m.group(0).strip() if m else None


def _explicit_target(sentence: str) -> float | None:
    """A percentage stated *as* a target, e.g. 'credit growth guidance of
    14% to 15%' or 'we expect margins around 18%'. A percentage that merely
    appears elsewhere in the sentence is not a target."""
    patterns = (
        r"(?:guidance|target|expect|expects|expected|will|should|aim|aims|plan|"
        r"plans|intend|intends)\b[^.%]{0,70}?(-?\d+(?:\.\d+)?)\s*"
        r"(?:%|percent|per cent|pc\b)",
        r"(-?\d+(?:\.\d+)?)\s*(?:%|percent|per cent)\s*(?:to|-|–)?\s*"
        r"(?:\d+(?:\.\d+)?\s*(?:%|percent|per cent))?\s*[^.]{0,40}?"
        r"\b(?:guidance|target)\b",
    )
    for pat in patterns:
        m = re.search(pat, sentence, re.I)
        if m:
            return float(m.group(1))
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:bps|basis points?)\s*"
                  r"(?:of\s+)?(?:guidance|target|expansion)", sentence, re.I)
    return round(float(m.group(1)) / 100, 2) if m else None


def extract_commitments(symbol: str, limit_docs: int = 4,
                        min_chars: int = 6000, max_candidates: int = 14) -> dict:
    """Guidance sentences from the latest substantive transcript/presentation
    PDFs. Short notices and intimation letters are skipped, not scored."""
    try:
        anns = N.nse.corporate_announcements(symbol=symbol.upper(), days=730)
    except Exception as e:  # noqa: BLE001
        return {"available": False, "error": f"{type(e).__name__}: {e}"[:180],
                "items": [], "documents": [], "announcements": 0}

    candidates = [a for a in anns if _is_document(a)]
    # Newest first; NSE returns them most-recent-first already.
    seen_urls: set[str] = set()
    docs = []
    skipped = []
    for a in candidates:
        url = a.get("attchmntFile") or ""
        if url in seen_urls:
            continue
        seen_urls.add(url)
        text, how = document_text(symbol, a)
        if not text or len(text) < min_chars:
            skipped.append({"category": a.get("desc"), "chars": len(text or ""),
                            "status": how})
            continue
        docs.append((a, text))
        if len(docs) >= max_candidates:
            break

    # Keep the newest documents plus at least two older ones, so guidance from
    # a prior year can actually be checked against the annual statements that
    # followed it.
    def _doc_year(item):
        m = re.search(r"(19|20)\d{2}", (item[0].get("an_dt") or ""))
        return int(m.group(0)) if m else 0

    docs.sort(key=_doc_year, reverse=True)
    newest = docs[:max(1, limit_docs - 2)]
    older = [d for d in docs if d not in newest][-2:]
    docs = newest + older

    items: list[dict] = []
    used = []
    seen_sent: set[str] = set()
    for ann, text in docs:
        used.append({"category": ann.get("desc"),
                     "announced": ann.get("an_dt"),
                     "characters": len(text),
                     "url": ann.get("attchmntFile"), "status": "read"})
        for sent in _sentences(text):
            if not _COMMIT_CUE.search(sent) or not re.search(r"\d", sent):
                continue
            if _FILLER.search(sent) or "?" in sent:
                continue
            # Analyst questions and greetings are not management guidance.
            if re.match(r"^(moderator|management|[A-Z][a-z]+ [A-Z][a-z]+)\s*:", sent):
                continue
            if re.search(r"\b(my question|your question|I think|just wanted to|"
                         r"could you|can you|would you)\b", sent, re.I):
                continue
            # Explicit guidance, or clear future framing tied to a named period.
            future = (re.search(r"\b(will|should|expect|expects|likely to|"
                                r"going to|target|guide)\b", sent, re.I)
                      and re.search(r"\b(next|coming|ahead|FY\s?2\d|by 20\d\d|"
                                    r"over the next|second half|H[12])\b", sent, re.I))
            if not (_STRONG.search(sent) or future):
                continue
            metric = _metric(sent)
            if metric is None:
                continue
            metric_name, cue = metric
            pct = _explicit_target(sent)
            phrase = _number_phrase(sent)
            if pct is None and phrase is None:
                continue
            # Without an explicit target, require the metric word and the figure
            # to sit close together, so unrelated numbers are not attached to it.
            if pct is None:
                low = sent.lower()
                anchor = low.find(cue) if cue else -1
                if anchor < 0 or phrase is None:
                    continue
                num_at = low.find(phrase.lower())
                if num_at < 0 or abs(num_at - anchor) > 110:
                    continue
            key = re.sub(r"\W+", " ", sent.lower())[:160]
            if key in seen_sent:
                continue
            seen_sent.add(key)
            items.append({
                "quote": sent[:420],
                "metric_guess": metric_name,
                "metric_cue": cue,
                "target_pct": pct,
                "target_text": phrase,
                "scorable": pct is not None,
                "level_target": metric_name == "margin" and "margin" in sent.lower()
                                and not re.search(r"expan|improv|contract|declin|"
                                                  r"bps|basis point", sent, re.I),
                "announced": ann.get("an_dt"),
                "category": ann.get("desc"),
                "source_url": ann.get("attchmntFile"),
            })
    return {"available": True, "announcements": len(anns),
            "documents": used, "skipped": skipped[:8], "items": items[:40]}
