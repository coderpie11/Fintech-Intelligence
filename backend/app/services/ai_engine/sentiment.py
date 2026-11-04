"""Local sentiment engine for the StreetPulse matrix.

Two layers, both free and offline-first:

1. **FinBERT** (`ProsusAI/finbert`) on CPU — a financial-domain classifier, so
   "profit warning" and "beats estimates" are scored by a model trained on
   filings and market copy rather than by a keyword count. Loaded lazily once
   and kept warm; if torch/transformers or the weights are unavailable the
   engine degrades to layer 2 and says so.
2. **Domain lexicon** — a deterministic fallback that also handles
   Hinglish/market-slang tokens FinBERT was not trained on ("upper circuit",
   "short covering", "bhaav").

Feeds are public RSS (Google News India markets, ET Markets, Business
Standard, Moneycontrol, Mint). Only headlines and links are stored; the
platform never reproduces article bodies.
"""
from __future__ import annotations

import re
import threading
import time

import httpx

from app.core.config import cache_get, cache_set

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")

FEEDS = [
    ("Google News · Indian markets",
     "https://news.google.com/rss/search?q=NSE+Nifty+stock+market&hl=en-IN&gl=IN&ceid=IN:en"),
    ("Google News · FII DII flows",
     "https://news.google.com/rss/search?q=FII+DII+flows+NSE&hl=en-IN&gl=IN&ceid=IN:en"),
    ("Economic Times · Markets",
     "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("Business Standard · Markets",
     "https://www.business-standard.com/rss/markets-106.rss"),
    ("Mint · Markets", "https://www.livemint.com/rss/markets"),
    ("Moneycontrol · Market reports",
     "https://www.moneycontrol.com/rss/marketreports.xml"),
]

POSITIVE = {
    "beat", "beats", "surge", "surges", "rally", "rallies", "jump", "jumps",
    "gain", "gains", "record", "profit", "profits", "upgrade", "upgraded",
    "buy", "outperform", "strong", "growth", "grows", "expands", "wins",
    "order win", "bonus", "dividend", "buyback", "approval", "approved",
    "inflow", "inflows", "higher", "rise", "rises", "soar", "soars", "bullish",
    "positive", "boost", "expands margins", "margin expansion", "all-time high",
    "upper circuit", "short covering", "upgrade to buy",
}
NEGATIVE = {
    "fall", "falls", "drop", "drops", "slide", "slides", "plunge", "plunges",
    "crash", "decline", "declines", "loss", "losses", "downgrade", "downgraded",
    "sell", "underperform", "weak", "warning", "profit warning", "cut", "cuts",
    "miss", "misses", "probe", "fraud", "penalty", "fine", "default", "downgrade",
    "outflow", "outflows", "lower", "bearish", "negative", "slump", "tumble",
    "resign", "resignation", "lower circuit", "selloff", "sell-off", "recall",
}
HINGLISH_POS = {"tezi", "bhaari", "upar", "mazboot", "tijori"}
HINGLISH_NEG = {"mandi", "giravat", "neeche", "kamzor", "gir"}

# Ticker → aliases used in Indian market copy.
SYMBOL_ALIASES = {
    "RELIANCE": ["reliance", "ril"],
    "TCS": ["tcs", "tata consultancy"],
    "HDFCBANK": ["hdfc bank", "hdfcbank"],
    "ICICIBANK": ["icici bank", "icicibank"],
    "INFY": ["infosys", "infy"],
    "SBIN": ["state bank", "sbi", "sbin"],
    "BHARTIARTL": ["bharti airtel", "airtel"],
    "ITC": ["itc"],
    "LT": ["larsen", "l&t", "lt "],
    "AXISBANK": ["axis bank"],
    "KOTAKBANK": ["kotak"],
    "BAJFINANCE": ["bajaj finance"],
    "MARUTI": ["maruti", "suzuki"],
    "TATAMOTORS": ["tata motors"],
    "TMPV": ["tata motors passenger", "tmpv"],
    "SUNPHARMA": ["sun pharma"],
    "WIPRO": ["wipro"],
    "HINDUNILVR": ["hindustan unilever", "hul"],
    "ADANIENT": ["adani enterprises"],
    "TATASTEEL": ["tata steel"],
    "NIFTY": ["nifty"],
    "SENSEX": ["sensex"],
}

_cleaned: dict = {"model": None, "tokenizer": None, "state": "idle",
                  "error": None, "loaded_ms": None}
_lock = threading.Lock()


def _load_finbert() -> bool:
    """Load FinBERT once. Returns True when the model is usable."""
    global _cleaned
    with _lock:
        if _cleaned["state"] == "ready":
            return True
        if _cleaned["state"] == "failed":
            return False
        t0 = time.time()
        try:
            from transformers import (AutoModelForSequenceClassification,
                                      AutoTokenizer)
            name = "ProsusAI/finbert"
            _cleaned["tokenizer"] = AutoTokenizer.from_pretrained(name)
            _cleaned["model"] = AutoModelForSequenceClassification.from_pretrained(name)
            _cleaned["model"].eval()
            _cleaned["state"] = "ready"
            _cleaned["loaded_ms"] = int((time.time() - t0) * 1000)
            return True
        except Exception as e:  # noqa: BLE001
            _cleaned["state"] = "failed"
            _cleaned["error"] = f"{type(e).__name__}: {e}"[:240]
            return False


def finbert_status() -> dict:
    return {"engine": "ProsusAI/finbert (CPU)",
            "state": _cleaned["state"],
            "loaded_ms": _cleaned["loaded_ms"],
            "error": _cleaned["error"],
            "note": ("A general financial-sentiment classifier applied to news "
                     "headlines. It is a descriptive reading of public copy, "
                     "not a recommendation.")}


def score_finbert(texts: list[str]) -> list[dict] | None:
    """FinBERT probabilities per headline, or None when unavailable."""
    if not texts:
        return []
    if not _load_finbert():
        return None
    try:
        import torch
        tok, mdl = _cleaned["tokenizer"], _cleaned["model"]
        enc = tok(texts, return_tensors="pt", truncation=True,
                  padding=True, max_length=96)
        with torch.no_grad():
            logits = mdl(**enc).logits
        probs = torch.softmax(logits, dim=1).tolist()
        id2 = mdl.config.id2label
        out = []
        for p in probs:
            scores = {id2[i].lower(): round(p[i], 4) for i in range(len(p))}
            pos, neg, neu = (scores.get("positive", 0.0),
                             scores.get("negative", 0.0),
                             scores.get("neutral", 0.0))
            label = ("positive" if pos >= max(neg, neu)
                     else "negative" if neg >= max(pos, neu) else "neutral")
            out.append({"label": label, "positive": pos, "negative": neg,
                        "neutral": neu,
                        "score": round(pos - neg, 4)})
        return out
    except Exception as e:  # noqa: BLE001
        _cleaned["error"] = f"{type(e).__name__}: {e}"[:240]
        return None


def score_lexicon(text: str) -> dict:
    low = f" {text.lower()} "
    pos = sum(1 for w in POSITIVE if w in low)
    neg = sum(1 for w in NEGATIVE if w in low)
    pos += sum(1 for w in HINGLISH_POS if w in low)
    neg += sum(1 for w in HINGLISH_NEG if w in low)
    total = pos + neg
    if total == 0:
        return {"label": "neutral", "positive": 0.0, "negative": 0.0,
                "neutral": 1.0, "score": 0.0, "hits": {"positive": 0, "negative": 0}}
    p = pos / total
    n = neg / total
    return {"label": "positive" if pos > neg else "negative" if neg > pos else "neutral",
            "positive": round(p, 4), "negative": round(n, 4),
            "neutral": 0.0, "score": round(p - n, 4),
            "hits": {"positive": pos, "negative": neg}}


_TAG = re.compile(r"<[^>]+>")


def _clean_html(s: str) -> str:
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s or "", flags=re.S)
    s = _TAG.sub("", s)
    for a, b in (("&amp;", "&"), ("&quot;", '"'), ("&#39;", "'"),
                 ("&nbsp;", " "), ("&lt;", "<"), ("&gt;", ">")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def _parse_feed(xml: str, source: str) -> list[dict]:
    items = []
    for block in re.findall(r"<item[\s>].*?</item>", xml or "", flags=re.S)[:40]:
        title = re.search(r"<title>(.*?)</title>", block, re.S)
        link = re.search(r"<link>(.*?)</link>", block, re.S)
        pub = re.search(r"<pubDate>(.*?)</pubDate>", block, re.S)
        if not title:
            continue
        t = _clean_html(title.group(1))
        if len(t) < 18 or t.lower() in ("google news", "markets", "economic times"):
            continue
        items.append({
            "title": t,
            "link": _clean_html(link.group(1)) if link else None,
            "published": _clean_html(pub.group(1)) if pub else None,
            "source": source,
        })
    return items


def fetch_headlines(limit_per_feed: int = 18, ttl: int = 600) -> dict:
    """Pull and score the current public market headlines."""
    hit = cache_get("sentiment:headlines")
    if hit is not None:
        return hit
    heads: list[dict] = []
    errors = []
    with httpx.Client(headers={"User-Agent": UA}, timeout=18,
                      follow_redirects=True) as c:
        for name, url in FEEDS:
            try:
                r = c.get(url)
                if r.status_code != 200:
                    errors.append(f"{name}: HTTP {r.status_code}")
                    continue
                heads.extend(_parse_feed(r.text, name)[:limit_per_feed])
            except Exception as e:  # noqa: BLE001
                errors.append(f"{name}: {type(e).__name__}")
    # De-duplicate by normalised title.
    seen, unique = set(), []
    for h in heads:
        key = re.sub(r"[^a-z0-9]", "", h["title"].lower())[:90]
        if key in seen:
            continue
        seen.add(key)
        unique.append(h)
    unique = unique[:90]

    fb = score_finbert([h["title"] for h in unique]) if unique else []
    engine = "finbert" if fb is not None else "lexicon"
    for i, h in enumerate(unique):
        sc = fb[i] if fb is not None and i < len(fb) else score_lexicon(h["title"])
        h["sentiment"] = sc
        h["matched"] = _match_symbols(h["title"])
    out = {"engine": engine, "count": len(unique), "headlines": unique,
           "feed_errors": errors,
           "asof": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "note": ("Headlines are public RSS titles, scored for tone only. "
                    "A positive headline is not a buy signal.")}
    cache_set("sentiment:headlines", out, ttl=ttl)
    return out


def _match_symbols(title: str) -> list[str]:
    low = f" {title.lower()} "
    hits = []
    for sym, aliases in SYMBOL_ALIASES.items():
        if any(a in low for a in aliases):
            hits.append(sym)
    return hits[:4]


def symbol_sentiment(symbol: str, headlines: dict | None = None) -> dict:
    """Aggregate the tone of headlines that mention a ticker."""
    data = headlines or fetch_headlines()
    sym = symbol.upper()
    rel = [h for h in data["headlines"] if sym in h.get("matched", [])]
    if not rel:
        return {"symbol": sym, "count": 0, "sentiment_score": None,
                "label": "no-coverage",
                "note": "No current headline mentions this ticker in the free feeds."}
    scores = [h["sentiment"]["score"] for h in rel]
    avg = sum(scores) / len(scores)
    pos = sum(1 for s in scores if s > 0.15)
    neg = sum(1 for s in scores if s < -0.15)
    return {
        "symbol": sym, "count": len(rel),
        "sentiment_score": round(avg, 4),
        "label": ("positive" if avg > 0.15 else "negative" if avg < -0.15 else "mixed"),
        "positive_headlines": pos, "negative_headlines": neg,
        "headlines": [{"title": h["title"], "source": h["source"],
                       "link": h["link"], "label": h["sentiment"]["label"],
                       "score": h["sentiment"]["score"]} for h in rel[:8]],
        "engine": data["engine"],
    }
