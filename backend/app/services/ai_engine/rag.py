"""Hybrid retrieval over Indian filing text.

Design notes
------------
* **Chunk store** — `knowledge_chunks` holds text plus a JSON float embedding.
  The column type is the only thing that changes when this moves to
  PostgreSQL + pgvector (`vector(384)`); the query code is already
  cosine-on-vectors, so no rewrite is needed there.
* **Encoder** — `sentence-transformers/all-MiniLM-L6-v2` on CPU (a local
  caching HF model, 384-d). If it cannot load, retrieval falls back to BM25-ish
  lexical scoring and reports `dense: false` so the UI can say so.
* **Docling** — when the `docling` package is installed it is used to convert
  PDFs to text; otherwise the platform ingests text/markdown and says PDF
  extraction was unavailable. Neither path fabricates content.
* **What is actually indexed** — the platform's own derived filing extracts
  (annual-statement rows, shareholding deltas, corporate-action purposes) plus
  any DRHP/annual-report text the operator drops into
  `backend/data/corpus/`. Nothing is invented to make the demo look full.
"""
from __future__ import annotations

import math
import re
import threading

from sqlalchemy import select

from app.core.config import DATA_DIR
from app.models.models import KnowledgeChunk

CORPUS_DIR = DATA_DIR / "corpus"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

_enc_state: dict = {"model": None, "state": "idle", "error": None}
_enc_lock = threading.Lock()


def _encoder_ready() -> bool:
    with _enc_lock:
        if _enc_state["state"] == "ready":
            return True
        if _enc_state["state"] == "failed":
            return False
        try:
            from sentence_transformers import SentenceTransformer
            _enc_state["model"] = SentenceTransformer(EMBED_MODEL)
            _enc_state["state"] = "ready"
            return True
        except Exception as e:  # noqa: BLE001
            _enc_state["state"] = "failed"
            _enc_state["error"] = f"{type(e).__name__}: {e}"[:240]
            return False


def encoder_status() -> dict:
    return {"engine": EMBED_MODEL, "state": _enc_state["state"],
            "dim": 384 if _enc_state["state"] == "ready" else None,
            "error": _enc_state["error"],
            "vector_store": "SQLite JSON column (pgvector-compatible schema)"}


def embed(texts: list[str]) -> list[list[float]] | None:
    if not texts or not _encoder_ready():
        return None
    try:
        vecs = _enc_state["model"].encode(texts, normalize_embeddings=True,
                                          show_progress_bar=False)
        return [list(map(float, v)) for v in vecs]
    except Exception as e:  # noqa: BLE001
        _enc_state["error"] = f"{type(e).__name__}: {e}"[:240]
        return None


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower())
            if len(t) > 2 and t not in _STOP}


_STOP = {
    "the", "and", "for", "was", "were", "has", "have", "had", "with", "from",
    "that", "this", "are", "its", "not", "but", "you", "our", "all", "any",
    "per", "net", "new", "year", "into", "over", "than", "then", "also",
}


def _chunk_id(doc_id: str, ordinal: int) -> str:
    return f"{doc_id}#{ordinal}"


def upsert_document(db, *, doc_id: str, symbol: str | None, doc_kind: str,
                    title: str, asof: str | None, paragraphs: list[str],
                    source_url: str | None = None) -> int:
    """Replace a document's chunks. Returns the number of chunks stored."""
    db.query(KnowledgeChunk).filter(KnowledgeChunk.doc_id == doc_id).delete()
    paras = [p.strip() for p in paragraphs if p and p.strip()]
    if not paras:
        db.commit()
        return 0
    vecs = embed(paras)
    for i, p in enumerate(paras):
        db.add(KnowledgeChunk(
            doc_id=doc_id, symbol=(symbol or "").upper() or None,
            doc_kind=doc_kind, title=title[:240], asof=asof, ordinal=i,
            text=p, embedding=(vecs[i] if vecs and i < len(vecs) else None),
            source_url=source_url,
        ))
    db.commit()
    return len(paras)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def search(db, query: str, *, symbol: str | None = None, k: int = 6,
           doc_kinds: list[str] | None = None) -> dict:
    """Hybrid search: dense cosine when embeddings exist, lexical always.

    The final score is 0.72·dense + 0.28·lexical so a strong keyword hit can
    still surface above a mushy vector match, which matters for ticker codes.
    A small newest-first prior is added on top: annual-statement chunks from
    different years are near-identical in wording, so without it "latest
    revenue" could surface FY2023 ahead of FY2026. The prior is deliberately
    smaller than any real relevance gap (max +0.02) and only breaks near-ties.
    """
    stmt = select(KnowledgeChunk)
    if symbol:
        stmt = stmt.where(KnowledgeChunk.symbol == symbol.upper())
    if doc_kinds:
        stmt = stmt.where(KnowledgeChunk.doc_kind.in_(doc_kinds))
    rows = db.execute(stmt).scalars().all()
    if not rows:
        return {"query": query, "hits": [], "dense": False, "scanned": 0,
                "note": ("No filed documents are indexed yet. Run the corpus "
                         "build to ingest annual-statement extracts.")}
    qvec = embed([query])
    qvec = qvec[0] if qvec else None
    qtok = _tokens(query)
    scored = []
    for r in rows:
        dense = _cosine(qvec, r.embedding) if qvec and r.embedding else 0.0
        rtok = _tokens(r.text) | _tokens(r.title)
        overlap = len(qtok & rtok) / max(len(qtok), 1)
        base = (0.72 * dense + 0.28 * overlap) if qvec else overlap
        recency = 1.0 / (1 + max(0, r.ordinal or 0))
        score = base + 0.02 * recency
        if score > 0.01:
            scored.append((score, dense, overlap, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return {
        "query": query,
        "dense": bool(qvec),
        "scanned": len(rows),
        "hits": [{
            "doc_id": r.doc_id, "symbol": r.symbol, "doc_kind": r.doc_kind,
            "title": r.title, "asof": r.asof, "ordinal": r.ordinal,
            "text": r.text, "score": round(s, 4),
            "dense_score": round(d, 4), "lexical_score": round(l, 4),
            "source_url": r.source_url or None,
        } for s, d, l, r in scored[:k]],
    }


def corpus_stats(db) -> dict:
    rows = db.execute(select(KnowledgeChunk)).scalars().all()
    docs = {r.doc_id for r in rows}
    with_emb = sum(1 for r in rows if r.embedding)
    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r.doc_kind] = kinds.get(r.doc_kind, 0) + 1
    return {"chunks": len(rows), "documents": len(docs),
            "embedded_chunks": with_emb, "by_kind": kinds,
            "encoder": encoder_status(),
            "external_corpus_dir": str(CORPUS_DIR)}


def ingest_external_corpus(db) -> dict:
    """Ingest operator-supplied .txt/.md files, and PDFs when Docling exists."""
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    stats = {"ingested": 0, "chunks": 0, "skipped": [], "docling": _docling_available()}
    for path in sorted(CORPUS_DIR.glob("*")):
        if path.suffix.lower() not in (".txt", ".md", ".pdf"):
            continue
        try:
            if path.suffix.lower() == ".pdf":
                text = _pdf_text(path)
                if text is None:
                    stats["skipped"].append(f"{path.name}: no PDF extractor")
                    continue
            else:
                text = path.read_text(encoding="utf-8", errors="ignore")
            paras = [p for p in re.split(r"\n\s*\n", text) if len(p.strip()) > 80]
            if not paras:
                stats["skipped"].append(f"{path.name}: no usable paragraphs")
                continue
            sym = None
            m = re.match(r"([A-Z0-9&\-]{2,20})[_\-. ]", path.stem.upper())
            if m:
                sym = m.group(1)
            n = upsert_document(db, doc_id=f"file:{path.stem}", symbol=sym,
                                doc_kind="EXTERNAL", title=path.stem,
                                asof=None, paragraphs=paras[:200])
            stats["ingested"] += 1
            stats["chunks"] += n
        except Exception as e:  # noqa: BLE001
            stats["skipped"].append(f"{path.name}: {type(e).__name__}")
    return stats


def _docling_available() -> bool:
    try:
        import docling  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _pdf_text(path) -> str | None:
    """Docling first (layout-aware), then pypdf, else None — never fake text."""
    if _docling_available():
        try:
            from docling.document_converter import DocumentConverter
            res = DocumentConverter().convert(str(path))
            return res.document.export_to_markdown()
        except Exception:  # noqa: BLE001
            pass
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return "\n\n".join((pg.extract_text() or "") for pg in reader.pages)
    except Exception:  # noqa: BLE001
        return None
