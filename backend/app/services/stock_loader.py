"""On-demand Indian equity loader.

The curated seed covers the index constituents, but India has roughly two
thousand active NSE listings. The NSE master is stored locally; this module
covers the long tail: when a user searches for or opens a company that is not
yet enriched, we ask Yahoo's Indian-listing search, create the instrument on
the fly, and attach a real 5-year history. The normal deep-dive endpoint then
fills fundamentals from the same source.

Nothing here invents a price. If Yahoo cannot answer, the row is returned with
an explicit null and the caller's normal unavailable envelope applies.
"""
from __future__ import annotations

import datetime as dt
import re

from sqlalchemy.orm import Session

from app.data.adapters import yfinance_adapter as Y
from app.models.models import Instrument


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or "equity"


def _num(v) -> float | None:
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _quote_from_history(hist: list[dict]) -> dict:
    if not hist:
        return {}
    last = hist[-1]
    prev = hist[-2] if len(hist) > 1 else last
    change = (round(last["c"] - prev["c"], 2)
              if last.get("c") is not None and prev.get("c") is not None else None)
    pct = (round((last["c"] / prev["c"] - 1) * 100, 2)
           if last.get("c") and prev.get("c") else None)
    tail = hist[-252:]
    return {
        "lastPrice": last.get("c"),
        "prevClose": prev.get("c"),
        "open": last.get("o"),
        "high": last.get("h"),
        "low": last.get("l"),
        "change": change,
        "changepct": pct,
        "yearHigh": max((h.get("h") or h["c"]) for h in tail),
        "yearLow": min((h.get("l") or h["c"]) for h in tail),
        "asof": last.get("date"),
        "fetched_at": dt.datetime.utcnow().isoformat() + "Z",
        "price_source": "Yahoo Finance history",
    }


def best_yahoo_match(query: str) -> dict | None:
    """Best Indian listing for a ticker or company name."""
    results = Y.search(query, 15)
    if not results:
        return None
    # Prefer an exact ticker match, then NSE over BSE, then the first equity.
    want = (query or "").strip().upper()
    exact = [r for r in results if r["symbol"].upper() == want]
    pool = exact or results
    pool = sorted(pool, key=lambda r: (r.get("exchange") != "NSE",
                                       r.get("type") != "EQUITY"))
    return pool[0] if pool else None


def ensure_from_yahoo(db: Session, query: str, with_history: bool = True,
                      commit: bool = True) -> Instrument | None:
    """Find or create an equity row from a live Yahoo Indian-listing match."""
    match = best_yahoo_match(query)
    if not match:
        return None
    symbol = match["symbol"].upper()
    exchange = match.get("exchange") or "NSE"
    row = (db.query(Instrument)
             .filter_by(kind="EQUITY", symbol=symbol)
             .one_or_none())
    if row is None:
        row = Instrument(
            symbol=symbol, name=match.get("name") or symbol, kind="EQUITY",
            exchange=exchange, slug=_slug(f"{symbol}-equity-{exchange}"),
            sector=match.get("sector"), industry=match.get("industry"),
            meta={},
        )
        db.add(row)
        db.flush()
    meta = dict(row.meta or {})
    meta["yahoo"] = match.get("yahoo")
    meta["price_source"] = "Yahoo Finance Indian listing search"
    meta["auto_loaded"] = True
    if match.get("name") and (not row.name or row.name == symbol):
        row.name = match["name"]
    if match.get("sector") and not row.sector:
        row.sector = match["sector"]
    if match.get("industry") and not row.industry:
        row.industry = match["industry"]
    if match.get("price") is not None:
        meta["lastPrice"] = match["price"]
    if match.get("changepct") is not None:
        meta["changepct"] = match["changepct"]

    if with_history and not row.history:
        try:
            hist = Y.history(match.get("yahoo") or f"{symbol}.NS", "5y")
            if hist:
                row.history = hist
                meta.update({k: v for k, v in _quote_from_history(hist).items()
                             if v is not None})
        except Exception:  # noqa: BLE001
            pass
    row.meta = meta
    db.add(row)
    if commit:
        try:
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
    return row


def ensure_by_symbol(db: Session, symbol: str,
                     with_history: bool = True) -> Instrument | None:
    """Resolve a ticker, using NSE first and then Yahoo's live search."""
    want = (symbol or "").strip().upper()
    if not want:
        return None
    row = (db.query(Instrument)
             .filter_by(kind="EQUITY", symbol=want).one_or_none())
    if row is not None:
        return row
    # Try the direct NSE ticker first: this avoids a search round-trip when the
    # user typed the exact symbol and the master has not been seeded yet.
    for exchange, suffix in (("NSE", ".NS"), ("BSE", ".BO")):
        try:
            hist = Y.history(f"{want}{suffix}", "5y")
        except Exception:  # noqa: BLE001
            hist = []
        if not hist:
            continue
        row = Instrument(
            symbol=want, name=want, kind="EQUITY", exchange=exchange,
            slug=_slug(f"{want}-equity-{exchange}"),
            history=hist if with_history else None,
            meta={"yahoo": f"{want}{suffix}", "auto_loaded": True,
                  **_quote_from_history(hist)},
        )
        db.add(row)
        try:
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        return row
    return ensure_from_yahoo(db, want, with_history=with_history)
