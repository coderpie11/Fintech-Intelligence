"""Corpus builder — turns the platform's own verified extracts into RAG text.

Nothing here is scraped prose or invented narrative. Each paragraph is a
deterministic sentence built from numbers already stored in the instrument
record (annual statements, shareholding, corporate actions). That means every
retrieved chunk can be traced back to a real field, which is exactly what a
research copilot needs.

Operator-supplied annual reports / DRHPs dropped into `backend/data/corpus/`
are ingested as-is by `rag.ingest_external_corpus()` when Docling or pypdf can
extract them.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.models import CorporateEvent, Instrument
from app.services.ai_engine import rag


def _newest_indices(periods: list[str]) -> list[int]:
    """Stored series are oldest-first; index them newest-first."""
    from app.services.ai_engine.askdalal import _period_sort_key
    return sorted(range(len(periods)),
                  key=lambda i: _period_sort_key(periods[i]), reverse=True)


def _crore(x: float | None) -> str:
    if x is None:
        return "not reported"
    return f"₹{x:,.0f} crore"


def _pct(x: float | None) -> str:
    return "not reported" if x is None else f"{x:.2f}%"


def _statement_paragraphs(row: Instrument) -> list[str]:
    meta = row.meta or {}
    cons = meta.get("statements_consolidated") or {}
    annual = cons.get("annual") or {}
    periods = annual.get("periods") or []
    sections = annual.get("sections") or {}
    if not sections:
        sections = {k: (annual.get(k) or {})
                    for k in ("income", "balance", "cashflow")}
    income = sections.get("income") or {}
    balance = sections.get("balance") or {}
    cash = sections.get("cashflow") or {}

    def val(bucket, key, i):
        seq = bucket.get(key)
        if isinstance(seq, list) and i < len(seq) and seq[i] is not None:
            try:
                return float(seq[i])
            except (TypeError, ValueError):
                return None
        return None

    out = []
    for i in _newest_indices(periods)[:5]:
        period = periods[i]
        rev = val(income, "revenue", i) or val(income, "operating_income", i)
        op = val(income, "operating_profit", i)
        opm = val(income, "opm_pct", i)
        ni = val(income, "net_income", i)
        eps = val(income, "eps", i)
        debt = val(balance, "borrowings", i) or val(balance, "total_debt", i)
        reserves = val(balance, "reserves", i)
        cfo = val(cash, "cfo", i)
        fcf = val(cash, "fcf", i)
        payout = val(income, "dividend_payout_pct", i)
        parts = [f"{row.name} ({row.symbol}) — {period} consolidated results."]
        if rev is not None:
            parts.append(f"Revenue was {_crore(rev)}.")
        if op is not None:
            parts.append(f"Operating profit was {_crore(op)} at an operating "
                         f"margin of {_pct(opm)}.")
        if ni is not None:
            parts.append(f"Net income was {_pct(ni) and _crore(ni)}.")
        if eps is not None:
            parts.append(f"Reported EPS was ₹{eps:,.2f} per share.")
        if debt is not None:
            parts.append(f"Total borrowings stood at {_crore(debt)}.")
        if reserves is not None:
            parts.append(f"Reserves were {_crore(reserves)}.")
        if cfo is not None:
            parts.append(f"Cash flow from operations was {_crore(cfo)}.")
        if fcf is not None:
            parts.append(f"Free cash flow was {_crore(fcf)}.")
        if payout is not None:
            parts.append(f"Dividend payout was {_pct(payout)} of profit.")
        if len(parts) > 1:
            out.append(" ".join(parts))
    return out


def _shareholding_paragraph(row: Instrument) -> str | None:
    sh = (row.meta or {}).get("shareholding") or {}
    periods = sh.get("periods") or []
    series = sh.get("series") or sh.get("sections") or {}
    if not periods or not series:
        return None

    def latest(key):
        seq = series.get(key)
        if isinstance(seq, list) and seq:
            # Stored oldest → newest; take the last numeric value.
            for v in reversed(seq):
                if v is not None:
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        continue
        return None

    bits = []
    for label, keys in (("Promoter", ("Promoters", "promoter")),
                        ("FII", ("FIIs", "fii")),
                        ("DII", ("DIIs", "dii")),
                        ("Public", ("Public", "public"))):
        v = next((latest(k) for k in keys if latest(k) is not None), None)
        if v is not None:
            bits.append(f"{label} {v:.2f}%")
    if not bits:
        return None
    return (f"{row.name} shareholding pattern for {periods[-1]}: "
            + ", ".join(bits) + ".")


def _corporate_paragraphs(db: Session, row: Instrument) -> list[str]:
    events = (db.query(CorporateEvent)
                .filter(CorporateEvent.symbol == row.symbol)
                .order_by(CorporateEvent.ex_date.desc().nullslast())
                .limit(12).all())
    if not events:
        return []
    lines = [f"{row.name} corporate actions: " + "; ".join(
        f"{e.kind} — {e.purpose}"
        + (f" (ex-date {e.ex_date.isoformat()})" if e.ex_date else "")
        for e in events[:8]) + "."]
    return lines


def build(db: Session, symbols: list[str] | None = None,
          max_symbols: int | None = None) -> dict:
    rag.CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    q = db.query(Instrument).filter(Instrument.kind == "EQUITY")
    if symbols:
        q = q.filter(Instrument.symbol.in_([s.upper() for s in symbols]))
    rows = q.all()
    if max_symbols:
        rows = rows[:max_symbols]
    stats = {"documents": 0, "chunks": 0, "symbols": 0, "skipped": []}
    for row in rows:
        paras = _statement_paragraphs(row)
        sh = _shareholding_paragraph(row)
        if sh:
            paras.append(sh)
        paras.extend(_corporate_paragraphs(db, row))
        if not paras:
            stats["skipped"].append(row.symbol)
            continue
        n = rag.upsert_document(
            db, doc_id=f"platform:{row.symbol}", symbol=row.symbol,
            doc_kind="ANNUAL", title=f"{row.name} — annual statement extracts",
            asof=(row.meta or {}).get("asof"), paragraphs=paras,
            source_url=f"/stocks/{row.symbol}")
        stats["documents"] += 1
        stats["chunks"] += n
        stats["symbols"] += 1
    external = rag.ingest_external_corpus(db)
    return {**stats, "external": external, **rag.corpus_stats(db)}
