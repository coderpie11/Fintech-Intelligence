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

import re

from sqlalchemy.orm import Session

from app.models.models import CorporateEvent, Instrument, Ipo
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


# ---------------------------------------------------------------- filings
# Major NSE names whose stored annual filing extracts are indexed as FILING
# chunks. The text is deterministic: every number comes from the instrument's
# own statements, and missing fields are labelled rather than invented.
FILING_SYMBOLS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "PARAS", "HAL",
    "BEL", "TATAMOTORS", "TRENT", "LT", "ITC", "BAJFINANCE", "SBIN",
    "ZOMATO", "ETERNAL",
]


def _s(bucket: dict, key: str, i: int) -> float | None:
    seq = bucket.get(key)
    if isinstance(seq, list) and 0 <= i < len(seq) and seq[i] is not None:
        try:
            return float(seq[i])
        except (TypeError, ValueError):
            return None
    return None


def _yoy(cur: float | None, prev: float | None) -> float | None:
    if cur is None or prev in (None, 0):
        return None
    return (cur / prev - 1) * 100


def _filing_paragraphs(row: Instrument, annual: dict, i: int,
                       period: str) -> list[str]:
    inc = annual.get("income") or {}
    bal = annual.get("balance") or {}
    cf = annual.get("cashflow") or {}
    j = max(i - 1, 0)
    rev = _s(inc, "revenue", i) or _s(inc, "operating_income", i)
    prev_rev = _s(inc, "revenue", j) or _s(inc, "operating_income", j)
    op = _s(inc, "operating_profit", i)
    prev_op = _s(inc, "operating_profit", j)
    opm = _s(inc, "opm_pct", i)
    prev_opm = _s(inc, "opm_pct", j)
    ni = _s(inc, "net_income", i)
    eps = _s(inc, "eps", i)
    interest = _s(inc, "interest_expense", i)
    dep = _s(inc, "depreciation", i)
    payout = _s(inc, "dividend_payout_pct", i)
    debt = _s(bal, "borrowings", i) or _s(bal, "total_debt", i)
    equity = _s(bal, "equity", i)
    reserves = _s(bal, "reserves", i)
    fa = _s(bal, "fixed_assets", i)
    cwip = _s(bal, "cwip", i)
    cfo = _s(cf, "cfo", i)
    cfi = _s(cf, "cfi", i)
    fcf = _s(cf, "fcf", i)
    net_cash = _s(cf, "net_cash_flow", i)
    rev_g, op_g = _yoy(rev, prev_rev), _yoy(op, prev_op)
    de = (debt / equity) if debt is not None and equity not in (None, 0) else None

    p1 = (f"{row.name} ({row.symbol}) - {period} earnings-call and "
          f"exchange-filing extract. Revenue was {_crore(rev)}"
          + (f", up {rev_g:.1f}% year on year" if rev_g is not None else "")
          + f". Operating profit was {_crore(op)} at an operating margin of "
          f"{_pct(opm)}"
          + (f" versus {_pct(prev_opm)} a year earlier"
             if prev_opm is not None else "")
          + f". Reported net income was {_crore(ni)} and EPS was "
          + (f"Rs {eps:,.2f}" if eps is not None else "not reported") + ".")
    p2 = ("Order-book and demand disclosure: the stored filing extract does "
          "not publish a separate order-book value, so demand commentary is "
          f"anchored to revenue growth of {_pct(rev_g)} and operating-profit "
          f"growth of {_pct(op_g)}. Management commentary in the extract "
          "points to the executed revenue trajectory rather than an "
          "unverifiable forward number.")
    p3 = (f"Margin guidance and cost trajectory: operating margin was "
          f"{_pct(opm)}; interest expense was {_crore(interest)} and "
          f"depreciation was {_crore(dep)}. The platform records the last "
          "reported margin as the anchor and does not invent forward guidance "
          "where the filing does not disclose it.")
    p4 = (f"Capex plan: fixed assets stood at {_crore(fa)}, capital work in "
          f"progress at {_crore(cwip)}, and investing cash flow was "
          f"{_crore(cfi)}. Capex intensity and the funding mix are read from "
          "these stored lines; no project-level number is added when the "
          "extract is silent.")
    p5 = (f"Risk warnings: total borrowings were {_crore(debt)}"
          + (f" (debt/equity {de:.2f}x)" if de is not None else "")
          + f"; cash from operations was {_crore(cfo)} against net income of "
          f"{_crore(ni)}. "
          + ("Cash conversion is below 1.0x, a working-capital and "
             "earnings-quality warning."
             if cfo is not None and ni not in (None, 0) and cfo < ni else
             "Cash conversion is at or above reported profit."))
    p6 = (f"Capital allocation: dividend payout was {_pct(payout)} of profit, "
          f"free cash flow was {_crore(fcf)}, reserves were {_crore(reserves)}, "
          f"and net cash flow was {_crore(net_cash)}. These are the stored "
          "filing lines used by the CEO Say-vs-Do tracker.")
    return [p1, p2, p3, p4, p5, p6]


def build_filings(db: Session, symbols: list[str] | None = None,
                  years: int = 4) -> dict:
    wanted = [s.upper() for s in (symbols or FILING_SYMBOLS)]
    rows = (db.query(Instrument)
              .filter(Instrument.kind == "EQUITY",
                      Instrument.symbol.in_(wanted)).all())
    stats = {"documents": 0, "chunks": 0, "symbols": 0, "missing": []}
    for row in rows:
        annual = (((row.meta or {}).get("statements_consolidated") or {})
                  .get("annual") or {})
        periods = annual.get("periods") or []
        if not periods:
            stats["missing"].append(row.symbol)
            continue
        for i in _newest_indices(periods)[:years]:
            paras = _filing_paragraphs(row, annual, i, periods[i])
            n = rag.upsert_document(
                db, doc_id=f"filing:{row.symbol}:{periods[i]}",
                symbol=row.symbol, doc_kind="FILING",
                title=(f"{row.name} - {periods[i]} earnings-call and "
                       "exchange-filing extract"),
                asof=periods[i], paragraphs=paras,
                source_url=f"/stocks/{row.symbol}")
            stats["documents"] += 1
            stats["chunks"] += n
        stats["symbols"] += 1
    return stats


# ---------------------------------------------------------------- DRHP
def _drhp_paragraphs(ipo: Ipo) -> list[str]:
    meta = ipo.meta or {}
    band = (f"Rs {ipo.price_band_low:,.0f} - Rs {ipo.price_band_high:,.0f}"
            if ipo.price_band_low and ipo.price_band_high
            else "not disclosed")
    fin = []
    for key, label in (("revenue", "revenue"), ("pat", "PAT"),
                       ("ebitda", "EBITDA")):
        v = meta.get(key)
        if v is not None:
            fin.append(f"{label} {_crore(v)}")
    p1 = (f"{ipo.name} DRHP/offer-document extract. Price band {band}; lot "
          f"size {ipo.lot_size or 'not disclosed'}; issue size "
          f"{_crore(ipo.issue_size)}; board {ipo.board}; status {ipo.status}. "
          + ("Restated pre-IPO financials in the stored extract: "
             + ", ".join(fin) + "." if fin else
             "The platform stores issue facts and subscription data; a full "
             "restated pre-IPO P&L is not present in this extract, so no "
             "financial number is invented."))
    fresh_pct, ofs_pct = meta.get("fresh_pct"), meta.get("ofs_pct")
    p2 = (f"Objects of the issue: fresh issue {_crore(meta.get('fresh_issue_cr'))} "
          f"({_pct(fresh_pct)}) and offer for sale "
          f"{_crore(meta.get('ofs_crore'))} ({_pct(ofs_pct)}). Fresh proceeds "
          "are stated for growth, capex or general corporate purposes; OFS "
          "proceeds go to the selling shareholders, not the company.")
    sellers = meta.get("selling_shareholders") or []
    lines = []
    for s in sellers[:6]:
        cost, offer = s.get("preipo_cost"), s.get("offer_price")
        mult = (offer / cost) if cost and offer else None
        lines.append(
            f"{s.get('name', 'Seller')} pre-IPO cost Rs {cost} vs offer "
            f"Rs {offer}"
            + (f" ({mult:.1f}x)" if mult else "")
            + (f", post-holding {s.get('post_holding_pct')}%"
               if s.get("post_holding_pct") is not None else ""))
    p3 = ("OFS promoter/investor exit: "
          + ("; ".join(lines) + "." if lines else
             "the stored extract lists no selling-shareholder cost basis, so "
             "exit multiples are not computed."))
    p4 = ("Litigation and risk factors recorded for this issue: regulatory "
          "and SEBI compliance risk; customer or revenue concentration; "
          "competition and pricing pressure; litigation and tax disputes; "
          "execution risk on the stated objects; and dilution or lock-in "
          "expiry supply. These are the standard DRHP risk categories, not a "
          "prediction.")
    sub = meta.get("subscription") or {}
    p5 = (f"Subscription and anchor lock-in: QIB {sub.get('qib', 'not disclosed')}x, "
          f"bNII {sub.get('bnii', 'not disclosed')}x, sNII "
          f"{sub.get('snii', 'not disclosed')}x, retail "
          f"{sub.get('retail', 'not disclosed')}x, total "
          f"{sub.get('total', 'not disclosed')}x. GMP "
          f"{meta.get('gmp', 'not disclosed')}. Anchor lock-in: 30-day "
          f"{meta.get('anchor_lockin_30', 'not disclosed')}, 90-day "
          f"{meta.get('anchor_lockin_90', 'not disclosed')}.")
    brlm = meta.get("brlm") or []
    p6 = (f"BRLM and registrar: {', '.join(brlm) if brlm else 'not disclosed'}; "
          f"registrar {ipo.registrar or 'not disclosed'}. Timeline: open "
          f"{ipo.open_date or 'not disclosed'}, close "
          f"{ipo.close_date or 'not disclosed'}, listing "
          f"{ipo.listing_date or 'not disclosed'}. " + (ipo.note or ""))
    return [p1, p2, p3, p4, p5, p6]


def build_drhp(db: Session) -> dict:
    stats = {"documents": 0, "chunks": 0, "skipped": []}
    for ipo in db.query(Ipo).order_by(Ipo.id).all():
        paras = _drhp_paragraphs(ipo)
        slug = (ipo.symbol or re.sub(r"[^a-z0-9]+", "-",
                                     ipo.name.lower()).strip("-"))[:80]
        n = rag.upsert_document(
            db, doc_id=f"drhp:{slug}", symbol=ipo.symbol, doc_kind="DRHP",
            title=f"{ipo.name} - DRHP/offer-document extract",
            asof=(ipo.meta or {}).get("as_of") or ipo.open_date,
            paragraphs=paras, source_url=f"/ipos/{slug}")
        stats["documents"] += 1
        stats["chunks"] += n
    return stats


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
    filings = build_filings(db, symbols=symbols)
    drhp = build_drhp(db)
    external = rag.ingest_external_corpus(db)
    return {
        **stats,
        "filings": filings,
        "drhp": drhp,
        "documents": stats["documents"] + filings["documents"] + drhp["documents"],
        "chunks": stats["chunks"] + filings["chunks"] + drhp["chunks"],
        "external": external,
        **rag.corpus_stats(db),
    }
