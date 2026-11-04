"""Indices module — live benchmark/sectoral list, detail with constituents,
full 5-year history, performance ladder and internal breadth."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.data.adapters import yfinance_adapter as Y
from app.models.models import Instrument
from app.seed.universe import INDICES
from app.services import calc, live_quote as LQ
from app.services.contextual import reported, source_issue

router = APIRouter(prefix="/indices", tags=["indices"])

BENCHMARKS = [s["slug"] for s in INDICES if s["top6"]]
FNO_OK = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50",
          "SENSEX", "INDIAVIX"}


def spec_for_slug(slug: str) -> dict | None:
    return next((s for s in INDICES if s["slug"] == slug), None)


def slug_for(row: Instrument) -> str:
    return next((s["slug"] for s in INDICES if s["nse"] == row.symbol),
                row.symbol.lower().replace(" ", "-"))


def _fno_symbol(spec: dict) -> str | None:
    sym = spec.get("fno")
    return sym if sym in FNO_OK else None


def _clean(v, nd: int | None = None):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, nd) if nd is not None else f


def _ratio(v, nd: int = 2):
    """Valuation ratios: a reported 0 means 'not meaningful', so treat it as
    missing rather than printing a fake 0.00 P/E."""
    f = _clean(v, nd)
    return None if not f else f


def _member_pe(m: dict) -> float | None:
    """Aggregate P/E for indices whose provider ratio is unavailable.

    The index P/E of a market-cap-weighted basket is the harmonic,
    weight-weighted mean of member P/Es: PE = Σw / Σ(w ÷ pe). We only use
    members that actually report a positive P/E and say so in the UI.
    """
    num = den = 0.0
    for c in (m.get("constituents") or []):
        w, pe = c.get("weight") or 0, c.get("pe")
        try:
            w, pe = float(w), float(pe)
        except (TypeError, ValueError):
            continue
        if w > 0 and pe > 0:
            num += w
            den += w / pe
    return round(num / den, 2) if den else None


def _member_pb(m: dict, db: Session) -> float | None:
    """Weighted harmonic mean of member P/B for the SENSEX fallback."""
    num = den = 0.0
    for c in (m.get("constituents") or []):
        w = c.get("weight") or 0
        eq = (db.query(Instrument)
                .filter_by(kind="EQUITY", symbol=c.get("symbol")).one_or_none())
        x = ((eq.meta or {}).get("extra") or {}) if eq else {}
        pb = x.get("priceToBook") or c.get("pb")
        try:
            w, pb = float(w), float(pb)
        except (TypeError, ValueError):
            continue
        if w > 0 and pb > 0:
            num += w
            den += w / pb
    return round(num / den, 2) if den else None


def _member_dy(m: dict, db: Session) -> float | None:
    """Weight-weighted arithmetic mean of member dividend yields."""
    num = den = 0.0
    for c in (m.get("constituents") or []):
        w = c.get("weight") or 0
        eq = (db.query(Instrument)
                .filter_by(kind="EQUITY", symbol=c.get("symbol")).one_or_none())
        em = (eq.meta or {}) if eq else {}
        x = em.get("extra") or {}
        dy = c.get("dy")
        if dy is None:
            rate = x.get("dividendRate")
            price = em.get("lastPrice") or c.get("last")
            if rate and price:
                dy = float(rate) / float(price) * 100
            else:
                dy = x.get("dividendYield")
        try:
            w, dy = float(w), float(dy)
        except (TypeError, ValueError):
            continue
        if w > 0 and dy >= 0:
            num += w * dy
            den += w
    return round(num / den, 2) if den else None


def _valuation_source(m: dict) -> dict:
    """Where the valuation ratios came from, for the honesty note."""
    if m.get("pe") or m.get("pb") or m.get("dy"):
        return {"kind": "provider", "note": "Published by the exchange feed."}
    if _member_pe(m):
        return {"kind": "members",
                "note": ("Index P/E, P/B and Dividend Yield are computed by the "
                         "platform from the weighted member list: P/E and P/B "
                         "use the weighted harmonic mean of member ratios, "
                         "dividend yield uses the weight-weighted mean of "
                         "member yields. These are not exchange-published ratios.")}
    return {"kind": "none", "note": "No free source publishes this ratio."}


def _env(v, what: str = "metric", nd: int | None = None) -> dict:
    """Reported value or an explicit SOURCE-UNAVAILABLE envelope — never a
    bare null on the wire."""
    if isinstance(v, (list, tuple)):
        if all(x is None for x in v):
            return source_issue(what)
        return reported(list(v))
    v = _clean(v, nd) if nd is not None else v
    if v is None:
        return source_issue(what)
    return reported(v)


@router.get("")
def list_indices(expand: bool = Query(False), db: Session = Depends(get_db)):
    rows = (db.query(Instrument).filter(Instrument.kind == "INDEX").all())
    by_slug = {slug_for(r): r for r in rows}
    shown: list[Instrument] = []
    for spec in INDICES:
        slug = spec["slug"]
        if not expand and slug not in BENCHMARKS and slug != "india-vix":
            continue
        if slug in by_slug:
            shown.append(by_slug[slug])
    LQ.refresh_rows(db, shown)
    out = []
    for spec in INDICES:
        slug = spec["slug"]
        if not expand and slug not in BENCHMARKS and slug != "india-vix":
            continue
        r = by_slug.get(slug)
        if not r:
            continue
        m = r.meta or {}
        hist = r.history or []
        out.append({
            "slug": slug,
            "symbol": r.symbol,
            "name": spec.get("display") or r.name,
            "full_name": r.name,
            "group": spec.get("group"),
            "last": _env(m.get("last"), "index level"),
            "change": _env(m.get("change"), "day change"),
            "changepct": _env(m.get("changepct"), "day change"),
            "prev_close": _env(m.get("prevClose"), "previous close"),
            "day_range": _env([m.get("low"), m.get("high")], "day range"),
            "year_range": _env([m.get("yearLow"), m.get("yearHigh")], "52-week range"),
            "pe": _env(_ratio(m.get("pe")) or _member_pe(m), "index P/E"),
            "pb": _env(_ratio(m.get("pb")) or _member_pb(m, db), "index P/B"),
            "dy": _env(_ratio(m.get("dy")) or _member_dy(m, db), "dividend yield"),
            "constituents_count": len(m.get("constituents") or []),
            "fno_available": bool(_fno_symbol(spec)),
            "fno_symbol": _fno_symbol(spec),
            "spark": [h.get("c") for h in hist[-40:] if h.get("c") is not None],
            "live_source": m.get("live_source"),
            "asof": m.get("live_asof"),
            "fetched_at": m.get("fetched_at"),
        })
    return {"indices": out, "expanded": expand, "expandable": True}


@router.get("/{slug}")
def index_detail(slug: str, db: Session = Depends(get_db)):
    spec = spec_for_slug(slug)
    if not spec:
        raise HTTPException(404, "Unknown index slug")
    row = (db.query(Instrument).filter_by(kind="INDEX", symbol=spec["nse"]).one_or_none())
    if not row:
        raise HTTPException(404, "Index not seeded yet")
    LQ.refresh_one(db, row, sync_history=True)
    m = row.meta or {}
    history = row.history or []
    closes = [h["c"] for h in history if h.get("c") is not None]

    # -------- performance ladder (simple return <= 1Y, CAGR > 1Y) --------
    ladder = {
        "1w": _ret(closes, 5, False),
        "1m": _ret(closes, 21, False),
        "3m": _ret(closes, 63, False),
        "6m": _ret(closes, 126, False),
        "1y": _ret(closes, 252, False),
        "3y": _ret(closes, 756, True),
        "5y": _ret(closes, len(closes) - 1, True),
    }
    returns = {k: (reported(v) if v is not None else source_issue("return series"))
               for k, v in ladder.items()}

    # -------- risk / valuation stats -------------------------------------
    stats = {
        "vol_1y": calc.annual_volatility(closes[-252:]) if len(closes) >= 252 else None,
        "vol_3y": calc.annual_volatility(closes[-756:]) if len(closes) >= 756 else None,
        "max_dd_1y": calc.max_drawdown(closes[-252:]) if len(closes) >= 60 else None,
        "max_dd_5y": calc.max_drawdown(closes) if len(closes) >= 60 else None,
    }
    stat_env = {k: (reported(v) if v is not None else source_issue("technical stat"))
                for k, v in stats.items()}

    year_high = _clean(m.get("yearHigh"))
    year_low = _clean(m.get("yearLow"))
    if (year_high is None or year_low is None) and history:
        tail = history[-252:]
        year_high = max((h.get("h") or h["c"]) for h in tail)
        year_low = min((h.get("l") or h["c"]) for h in tail)

    # -------- constituents (enriched from the equity universe) -----------
    constituents = []
    for c in (m.get("constituents") or []):
        sym = c.get("symbol")
        if not sym:
            continue
        eq = (db.query(Instrument).filter_by(kind="EQUITY", symbol=sym).one_or_none())
        em = (eq.meta or {}) if eq else {}
        last = em.get("lastPrice") if em.get("lastPrice") is not None else c.get("last")
        ch = em.get("changepct") if em.get("changepct") is not None else c.get("changepct")
        constituents.append({
            "symbol": sym,
            "name": (eq.name if eq else None) or c.get("name") or sym,
            "sector": c.get("sector") or em.get("sector") or (eq.sector if eq else None),
            "weight": c.get("weight"),
            "last": last,
            "changepct": ch,
            "year_high": c.get("yearHigh") or em.get("yearHigh"),
            "year_low": c.get("yearLow") or em.get("yearLow"),
            "pe": c.get("pe") or em.get("pe"),
            "market_cap": c.get("marketCap") or em.get("marketCap"),
            "href": f"/stocks/{sym}",
        })
    constituents.sort(key=lambda x: (x["weight"] is None, -(x["weight"] or 0),
                                     -(x["market_cap"] or 0)))

    fno_symbol = _fno_symbol(spec)
    return {
        "symbol": row.symbol,
        "name": spec.get("display") or row.name,
        "full_name": row.name,
        "slug": slug,
        "group": spec.get("group"),
        "about": spec.get("about") or "Reference index published by the National Stock Exchange of India / BSE.",
        "last": _env(m.get("last"), "index level"),
        "change": _env(m.get("change"), "day change"),
        "changepct": _env(m.get("changepct"), "day change"),
        "open": _env(m.get("open"), "day open"),
        "prev_close": _env(m.get("prevClose"), "previous close"),
        "day_range": _env([m.get("low"), m.get("high")], "day range"),
        "day_high": _env(m.get("high"), "day high"),
        "day_low": _env(m.get("low"), "day low"),
        "year_range": _env([year_low, year_high], "52-week range"),
        "high_52w": _env(year_high, "52-week high"),
        "low_52w": _env(year_low, "52-week low"),
        "pe": _env(_ratio(m.get("pe")) or _member_pe(m), "index P/E"),
        "pb": _env(_ratio(m.get("pb")) or _member_pb(m, db), "index P/B"),
        "dy": _env(_ratio(m.get("dy")) or _member_dy(m, db), "dividend yield"),
        "level_date": m.get("live_asof") or (history[-1]["date"] if history else None),
        "live_time": m.get("live_time"),
        "fetched_at": m.get("fetched_at"),
        "valuation_source": _valuation_source(m),
        "breadth": {
            "advances": _env(m.get("advances"), "advance count"),
            "declines": _env(m.get("declines"), "decline count"),
        },
        "returns": returns,
        "stats": stat_env,
        "fno_tab_available": bool(fno_symbol),
        "fno_symbol": fno_symbol,
        "constituents": constituents,
        "constituents_count": len(constituents),
        "weight_basis": m.get("weight_basis"),
        "constituents_source": m.get("constituents_source"),
        "history": [{"date": h["date"], "close": h["c"], "open": h.get("o"),
                     "high": h.get("h"), "low": h.get("l")} for h in history],
        "history_points": len(history),
        "history_source": m.get("history_source"),
        "live_source": m.get("live_source"),
        "source_note": m.get("source_note"),
        "asof": m.get("live_asof"),
        "data_note": reported(
            "Prices are exchange EOD/delayed. Returns <= 1Y are simple price "
            "returns; 3Y and 5Y are CAGR. Weights are free-float estimates, "
            "not official index-provider weights. Not a buy/sell recommendation."),
    }


@router.get("/{slug}/intraday")
def index_intraday(slug: str, interval: str = "5m", db: Session = Depends(get_db)):
    spec = spec_for_slug(slug)
    if not spec:
        raise HTTPException(404, "Unknown index slug")
    row = (db.query(Instrument).filter_by(kind="INDEX", symbol=spec["nse"]).one_or_none())
    if not row:
        raise HTTPException(404, "Index not seeded yet")
    quote = LQ.refresh_one(db, row)
    ticker = spec.get("yahoo")
    if ticker:
        try:
            data = Y.intraday(ticker, interval=interval, period="5d")
            if data["points"]:
                last = data["points"][-1]
                data["last"] = last["c"]
                if quote:
                    data["prevClose"] = quote.get("prevClose")
                    data["change"] = quote.get("change")
                    data["changepct"] = quote.get("changepct")
                    data["asof"] = quote.get("asof")
                    data["session_date"] = quote.get("session")
                    data["live_source"] = quote.get("source")
                else:
                    first = data["points"][0]
                    data["changepct"] = (round((last["c"] / first["o"] - 1) * 100, 2)
                                         if first.get("o") else None)
                return data
        except Exception:  # noqa: BLE001
            pass
    hist = row.history or []
    if len(hist) >= 2:
        tail = hist[-60:]
        points = [{"datetime": h["date"], "date": h["date"], "time": "15:30",
                   "o": h.get("o"), "h": h.get("h"), "l": h.get("l"),
                   "c": h["c"], "v": h.get("v")} for h in tail]
        change = round(hist[-1]["c"] - hist[-2]["c"], 2)
        return {
            "ticker": ticker, "interval": "1d", "session": hist[-1]["date"],
            "source": "Yahoo Finance daily candles (intraday feed unavailable)",
            "points": points,
            "last": hist[-1]["c"],
            "prevClose": hist[-2]["c"],
            "change": change,
            "changepct": round((hist[-1]["c"] / hist[-2]["c"] - 1) * 100, 2),
            "asof": (quote or {}).get("asof"),
            "note": "The intraday feed did not answer; the last 60 daily closes "
                    "are shown instead of fabricating candles.",
        }
    raise HTTPException(503, "No price history available for this index yet.")


def _ret(closes: list[float], lookback: int, cagr: bool) -> float | None:
    if len(closes) < 3:
        return None
    lookback = max(1, min(lookback, len(closes) - 1))
    first, last = closes[-1 - lookback], closes[-1]
    if not first:
        return None
    if cagr:
        years = lookback / 252
        return calc.cagr(first, last, years)
    return round((last / first - 1) * 100, 2)
