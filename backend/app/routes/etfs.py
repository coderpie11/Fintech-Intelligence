"""ETFs — curated NSE-listed exchange-traded funds with live quotes, five-year
price history, returns, premium/discount to published NAV, tracking error,
impact-cost estimate, liquidity score and an ETF-vs-index-fund calculator."""
from __future__ import annotations

import datetime as dt
import math

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.config import cache_get, cache_set
from app.data.adapters import nse_adapter as N
from app.data.adapters import yfinance_adapter as Y
from app.models.models import Instrument
from app.seed.universe import ETF_UNIVERSE, fallback_history
from app.services import calc
from app.services import instrument_engine as IE
from app.services.contextual import reported, source_issue

router = APIRouter(prefix="/etfs", tags=["etfs"])

SPECS = {s["symbol"]: s for s in ETF_UNIVERSE}

_ETF_TER = {"NIFTYBEES": 0.04, "SETFNIF50": 0.05, "BANKBEES": 0.19,
            "ITBEES": 0.22, "JUNIORBEES": 0.20, "GOLDBEES": 0.79,
            "SILVERBEES": 0.79, "LIQUIDBEES": 0.29, "CPSEETF": 0.07,
            "ICICIB22": 0.10, "MON100": 0.51, "MOM100": 0.30}


def _env(v, what: str = "metric") -> dict:
    # A non-finite float (NaN/Inf) is not JSON-serialisable and, more
    # importantly, is not a real answer. Report it as unavailable rather than
    # letting it reach the client as a broken number.
    f = _num(v)
    return reported(f) if f is not None else source_issue(what)


def _num(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


_ETF_FEED_TTL = 180


def _quote_map() -> dict[str, dict]:
    """One NSE /api/etf snapshot, cached for every ETF card on the desk.

    The feed covers the whole curated universe, so re-fetching it per request
    only adds seconds to first paint. Outside the session the stored snapshot
    is already the final print, and the cache keeps it served instantly.
    """
    cached = cache_get("nse:etf_list")
    if cached is not None:
        return cached
    try:
        rows = N.nse.etf_list()
    except Exception:  # noqa: BLE001
        return {}
    live = {str(r.get("symbol") or "").upper(): r for r in rows}
    if live:
        cache_set("nse:etf_list", live, ttl=_ETF_FEED_TTL)
    return live


def _history(symbol: str) -> list[dict]:
    try:
        return Y.history(f"{symbol}.NS", "5y")
    except Exception:  # noqa: BLE001
        return []


def _clean_navs(rows: list[dict]) -> list[dict]:
    """Keep only finite closes. The free history feed can carry NaN gaps and a
    single NaN poisons every return, CAGR and tracking-error built on top."""
    out = []
    for h in rows or []:
        c = _num(h.get("c"))
        if c is not None:
            out.append({"date": h.get("date"), "nav": c})
    return out


def _navs(hist: list[dict]) -> list[dict]:
    return _clean_navs([{"date": h.get("date"), "c": h.get("c")} for h in hist])


def _clean_history(hist: list[dict]) -> list[dict]:
    """Serialisable OHLCV rows with any non-finite value replaced by None."""
    rows = []
    for h in hist or []:
        close = _num(h.get("c"))
        if close is None:
            continue
        rows.append({
            "date": h.get("date"),
            "close": close,
            "open": _num(h.get("o")),
            "high": _num(h.get("h")),
            "low": _num(h.get("l")),
            "volume": _num(h.get("v")),
        })
    return rows


def _benchmark(db: Session, spec: dict) -> tuple[list[dict], dict]:
    bench = spec.get("benchmark")
    if not bench or spec.get("no_bench"):
        return [], {"symbol": None, "name": None,
                    "note": "No honest free benchmark series exists for this ETF."}
    if bench in ("GOLD_INR_PROXY", "SILVER_INR_PROXY"):
        return [], {"symbol": None, "name": None,
                    "note": ("No reliable free domestic bullion benchmark exists here. "
                             "International futures roll between contracts and settle in a "
                             "different time zone, so a tracking error computed against them "
                             "would be misleading rather than informative.")}
    if bench == "NASDAQ100":
        try:
            h = Y.history("^NDX", "5y")
            return (_clean_navs([{"date": x.get("date"), "c": x.get("c")} for x in h]),
                    {"symbol": "^NDX", "name": "Nasdaq 100", "proxy": False})
        except Exception:  # noqa: BLE001
            return [], {"symbol": None, "name": None,
                        "note": "Nasdaq 100 series was unavailable."}
    row = (db.query(Instrument).filter_by(kind="INDEX", symbol=bench).one_or_none())
    if row and row.history:
        return (_clean_navs([{"date": h.get("date"), "c": h.get("c")} for h in row.history]),
                {"symbol": bench, "name": bench, "proxy": bool(spec.get("proxy")),
                 "note": ("This is an approximate benchmark, not the ETF's exact "
                          "underlying index." if spec.get("proxy") else None)})
    return [], {"symbol": None, "name": None,
                "note": f"Benchmark {bench} is not seeded."}


def _impact_and_liquidity(q: dict, ltp: float | None) -> dict:
    high, low = _num(q.get("high")), _num(q.get("low"))
    qty = _num(q.get("qty")) or 0
    turnover = _num(q.get("trdVal")) or 0
    turnover_cr = turnover / 1e7
    if high and low and ltp:
        day_range_pct = (high - low) / ltp * 100
        # Modelled half-spread: half the day's range, reduced for deeper books.
        impact = day_range_pct / 2 / math.sqrt(max(qty / 1e5, 1))
        impact = min(max(impact, 0.01), 2.0)
    else:
        day_range_pct, impact = None, None
    score = None
    if turnover_cr or qty:
        score = round(min(100, max(0,
            18 * math.log10(turnover_cr + 1) + 10 * math.log10(qty / 1e5 + 1) + 18)))
    return {
        "impact_cost_pct": round(impact, 3) if impact is not None else None,
        "day_range_pct": round(day_range_pct, 2) if day_range_pct is not None else None,
        "liquidity_score": score,
        "turnover_cr": round(turnover_cr, 2) if turnover else None,
        "volume": int(qty) if qty else None,
        "note": ("Impact cost is a modelled half-spread proxy from the day's range "
                 "and traded quantity — not an order-book measurement."),
    }


def _parse_iso(s) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(s))
    except (TypeError, ValueError):
        return None


def _pd_status(dev: float | None) -> str:
    if dev is None:
        return "unavailable"
    if dev >= 0.25:
        return "premium"
    if dev <= -0.25:
        return "discount"
    return "fair"


def _inav_block(db: Session | None, spec: dict, ltp: float | None,
                nav: float | None) -> dict:
    """Live iNAV deviation.

    No free exchange iNAV feed exists here, so the indicative NAV marks the
    latest published NAV to the benchmark's live intraday move. When no live
    benchmark move is available it falls back to the published-NAV premium /
    discount and says so. Always model-derived, never presented as an official
    iNAV.
    """
    if ltp is None or nav is None:
        return {"live": False, "inav": None, "deviation_pct": None,
                "status": "unavailable", "source": None,
                "note": "Price or NAV is unavailable, so no deviation can be computed."}
    bench = spec.get("benchmark")
    if bench == "NASDAQ100":
        bench = "^NDX"
    bench_chg = None
    if bench and bench not in ("GOLD_INR_PROXY", "SILVER_INR_PROXY") and db is not None:
        row = (db.query(Instrument).filter_by(kind="INDEX", symbol=bench)
                 .one_or_none())
        m = (row.meta or {}) if row else {}
        last, prev = _num(m.get("last")), _num(m.get("prevClose"))
        asof = _parse_iso(m.get("live_asof"))
        fresh = asof is not None and abs((dt.date.today() - asof).days) <= 3
        if fresh and last and prev:
            bench_chg = (last / prev - 1) * 100
    if bench_chg is None:
        dev = (ltp - nav) / nav * 100
        return {
            "live": False, "inav": round(nav, 4),
            "deviation_pct": round(dev, 3), "status": _pd_status(dev),
            "benchmark_change_pct": None, "source": "NSE published NAV",
            "note": ("No live benchmark intraday move is available here, so this "
                     "deviation is versus the latest published NAV, not an "
                     "intraday iNAV."),
        }
    inav = nav * (1 + bench_chg / 100)
    dev = (ltp - inav) / inav * 100
    return {
        "live": True, "inav": round(inav, 4),
        "benchmark_change_pct": round(bench_chg, 3),
        "deviation_pct": round(dev, 3), "status": _pd_status(dev),
        "source": f"NSE NAV marked to live {bench} move",
        "note": ("Indicative iNAV = latest published NAV adjusted for the "
                 "benchmark's live intraday move. Model-derived; not the "
                 "exchange's official iNAV print."),
    }


def _row(symbol: str, spec: dict, q: dict, hist: list[dict],
         db: Session | None = None) -> dict:
    ltp = _num(q.get("ltP")) or (hist[-1]["c"] if hist else None)
    nav = _num(q.get("nav")) or (hist[-1]["c"] if hist else None)
    prev = _num(q.get("prevClose")) or (hist[-2]["c"] if len(hist) > 1 else None)
    chg = ((ltp / prev - 1) * 100 if ltp and prev else
           _num(q.get("per")))
    rets = calc.nav_returns(_navs(hist))
    liq = _impact_and_liquidity(q, ltp)
    last = hist[-1] if hist else {}
    window = hist[-252:] if hist else []
    wkhi = _num(q.get("wkhi")) or (max(h["c"] for h in window) if window else None)
    wklo = _num(q.get("wklo")) or (min(h["c"] for h in window) if window else None)
    volume = liq["volume"] or (_num(last.get("v")) or None)
    turnover_cr = liq["turnover_cr"]
    impact = liq["impact_cost_pct"]
    if turnover_cr is None and volume and ltp:
        turnover_cr = round(volume * ltp / 1e7, 2)
    if impact is None and ltp and last.get("h") and last.get("l") and volume:
        day_range_pct = (last["h"] - last["l"]) / ltp * 100
        impact = round(min(max(day_range_pct / 2 / math.sqrt(max(volume / 1e5, 1)), 0.01), 2.0), 3)
    score = liq["liquidity_score"]
    if score is None and turnover_cr:
        score = round(min(100, max(0, 18 * math.log10(turnover_cr + 1)
                                  + 10 * math.log10((volume or 0) / 1e5 + 1) + 18)))
    return {
        "symbol": symbol, "name": spec["name"], "category": spec["category"],
        "issuer": spec.get("issuer"), "about": spec.get("about"),
        "ltp": _env(ltp, "ETF price"),
        "changepct": _env(round(chg, 2) if chg is not None else None, "day change"),
        "prev_close": _env(prev, "previous close"),
        "nav": _env(nav, "published NAV"),
        "premium_discount_pct": _env(
            round((ltp - nav) / nav * 100, 2) if ltp and nav else None,
            "premium/discount to NAV"),
        "inav": _inav_block(db, spec, ltp, nav),
        "open": _env(_num(q.get("open")) or _num(last.get("o")), "open"),
        "high": _env(_num(q.get("high")) or _num(last.get("h")), "day high"),
        "low": _env(_num(q.get("low")) or _num(last.get("l")), "day low"),
        "week52_high": _env(wkhi, "52-week high"),
        "week52_low": _env(wklo, "52-week low"),
        "volume": _env(volume, "volume"),
        "turnover_cr": _env(turnover_cr, "turnover"),
        "impact_cost_pct": _env(impact, "impact cost"),
        "liquidity_score": _env(score, "liquidity score"),
        "returns": {k: _env(v, f"{k.upper()} return") for k, v in rets.items()},
        "ter_pct": _env(spec.get("ter_pct") or _ETF_TER.get(symbol), "expense ratio"),
        "benchmark": spec.get("benchmark"),
        "has_history": bool(hist),
        "spark": IE.spark_from_bars(hist, last=ltp, prev=prev),
        "href": f"/etfs/{symbol}",
        "quote_source": "NSE /api/etf" if q else "Yahoo Finance daily close",
    }


def _stored_map(db: Session) -> dict[str, Instrument]:
    return {r.symbol: r for r in
            db.query(Instrument).filter(Instrument.kind == "ETF").all()}


def _quote_from_meta(meta: dict) -> dict:
    return {
        "ltP": meta.get("lastPrice"), "prevClose": meta.get("prevClose"),
        "nav": meta.get("nav"), "per": meta.get("changepct"),
        "open": meta.get("open"), "high": meta.get("high"),
        "low": meta.get("low"), "wkhi": meta.get("week52_high"),
        "wklo": meta.get("week52_low"), "qty": meta.get("volume"),
        "trdVal": meta.get("turnover"),
    }


@router.get("")
def list_etfs(db: Session = Depends(get_db)):
    """All 51 curated ETFs, served from stored snapshots so the 50-symbol
    universe paints immediately. Live NSE quotes overlay the stored values
    when that single feed call succeeds; missing history falls back to the
    deterministic series in ``universe.py`` and is labelled as modelled."""
    qmap = _quote_map()
    stored = _stored_map(db)
    IE.ensure_many(db, stored.values())
    out = []
    for spec in ETF_UNIVERSE:
        sym = spec["symbol"]
        rec = stored.get(sym)
        meta = (rec.meta or {}) if rec else {}
        hist = list(rec.history or []) if rec else []
        if len(hist) < 60:
            hist = fallback_history(spec)
        live_q = qmap.get(sym)
        q = live_q or _quote_from_meta(meta)
        row = _row(sym, spec, q, hist, db)
        fb = spec.get("fallback") or {}

        # Guarantee every display field is populated even when the free feed
        # missed this symbol. Missing values take the labelled fallback.
        if row["ltp"]["value"] is None and fb.get("price") is not None:
            row["ltp"] = _env(fb["price"], "ETF price")
        if row["nav"]["value"] is None and fb.get("nav") is not None:
            row["nav"] = _env(fb["nav"], "published NAV")
        if row["premium_discount_pct"]["value"] is None:
            ltp_v, nav_v = row["ltp"]["value"], row["nav"]["value"]
            if ltp_v and nav_v:
                row["premium_discount_pct"] = _env(
                    round((ltp_v - nav_v) / nav_v * 100, 2),
                    "premium/discount to NAV")
        for key, value in (fb.get("returns") or {}).items():
            if row["returns"].get(key, {}).get("value") is None:
                row["returns"][key] = _env(value, f"{key.upper()} return")

        bench, _bench_meta = _benchmark(db, spec)
        te = calc.tracking_error(_navs(hist), bench) if bench else None
        if te is None:
            te = fb.get("tracking_error_pct")
        row["tracking_error_pct"] = _env(te, "tracking error")
        row["quote_source"] = (
            "NSE /api/etf (live/delayed)" if live_q
            else "Stored NSE snapshot" if rec and meta.get("lastPrice") is not None
            else "Modelled fallback")
        out.append(row)
    out.sort(key=lambda x: -(x["turnover_cr"]["value"] or 0))
    return {"count": len(out), "etfs": out,
            "quote_feed": "NSE /api/etf (live/delayed)" if qmap else "Stored / modelled fallback",
            "universe_note": ("51 curated NSE-listed ETFs across silver, gold, Nifty, "
                              "Sensex, sectoral, PSU, international and debt buckets. "
                              "Live NSE quotes overlay stored snapshots; rows marked "
                              "modelled are clearly labelled fallback values.")}


@router.get("/liquidity-scan")
def liquidity_scan(limit: int = Query(60, ge=1, le=200),
                   sort: str = Query("liquidity",
                                     pattern="^(liquidity|impact|turnover)$"),
                   db: Session = Depends(get_db)):
    """iNAV deviation + impact-cost scanner across the curated ETF universe."""
    qmap = _quote_map()
    stored = _stored_map(db)
    rows = []
    for spec in ETF_UNIVERSE:
        sym = spec["symbol"]
        rec = stored.get(sym)
        meta = (rec.meta or {}) if rec else {}
        live = qmap.get(sym)
        q = live or _quote_from_meta(meta)
        ltp = _num(q.get("ltP")) or _num(meta.get("lastPrice"))
        nav = _num(q.get("nav")) or _num(meta.get("nav"))
        liq = _impact_and_liquidity(q, ltp)
        inav = _inav_block(db, spec, ltp, nav)
        rows.append({
            "symbol": sym, "name": spec["name"], "category": spec["category"],
            "ltp": ltp, "nav": nav,
            "inav": inav.get("inav"), "inav_live": inav.get("live"),
            "deviation_pct": inav.get("deviation_pct"),
            "deviation_status": inav.get("status"),
            "impact_cost_pct": liq.get("impact_cost_pct"),
            "liquidity_score": liq.get("liquidity_score"),
            "turnover_cr": liq.get("turnover_cr"), "volume": liq.get("volume"),
            "quote_source": "NSE /api/etf" if live else "Stored snapshot",
        })
    if sort == "impact":
        rows.sort(key=lambda r: (r["impact_cost_pct"] is None,
                                 r["impact_cost_pct"] or 0))
    elif sort == "turnover":
        rows.sort(key=lambda r: -(r["turnover_cr"] or 0))
    else:
        rows.sort(key=lambda r: -(r["liquidity_score"] or 0))
    return {
        "count": len(rows), "sort": sort, "etfs": rows[:limit],
        "thresholds": {"premium_discount_band_pct": 0.25},
        "note": ("Impact cost is a modelled half-spread proxy from the day's range "
                 "and traded quantity, not an order-book measurement. iNAV "
                 "deviation compares the live price with an indicative NAV marked "
                 "to the benchmark move; flags use a +/-0.25% band."),
    }


@router.get("/{symbol}")
def etf_detail(symbol: str, db: Session = Depends(get_db)):
    sym = symbol.upper()
    spec = SPECS.get(sym)
    if not spec:
        raise HTTPException(404, "This ETF is not in the curated NSE universe.")
    rec = (db.query(Instrument).filter_by(kind="ETF", symbol=sym).one_or_none())
    if rec:
        IE.ensure_instrument_ready(db, rec)
    q = _quote_map().get(sym) or {}
    hist = _history(sym)
    if not hist:
        hist = list(rec.history or []) if rec else []
    if not hist:
        hist = fallback_history(spec)
    if not q and rec:
        q = _quote_from_meta(rec.meta or {})
    row = _row(sym, spec, q, hist, db)
    bench, bench_meta = _benchmark(db, spec)
    te = calc.tracking_error(_navs(hist), bench) if bench else None
    if te is None:
        te = (spec.get("fallback") or {}).get("tracking_error_pct")
    liq = _impact_and_liquidity(q, _num(q.get("ltP")))
    clean_hist = _clean_history(hist)
    return {
        **row,
        "history": clean_hist,
        "history_points": len(clean_hist),
        "history_source": "Yahoo Finance daily candles (5Y)",
        "tracking_error_pct": _env(te, "tracking error"),
        "tracking_error_note": (
            "Annualised standard deviation of daily ETF-price minus benchmark "
            "returns. Price returns include distributions timing effects; this is "
            "not a NAV-based tracking difference."
            if te is not None else bench_meta.get("note")),
        "benchmark_series": bench_meta,
        "impact_model": liq,
        "calculator_defaults": {
            "amount": 100000, "years": 5,
            "expected_return_pct": (row["returns"]["5y"]["value"]
                                    or row["returns"]["3y"]["value"] or 10.0),
            "index_fund_ter_pct": 0.20,
            "etf_ter_pct": spec.get("ter_pct") or _ETF_TER.get(sym, 0.20),
        },
        "source_notes": [
            "Price and published NAV come from NSE's official ETF snapshot.",
            "Yahoo Finance supplies the five-year price history.",
            "The published NAV is end-of-day, not an intraday iNAV, so the "
            "premium/discount shown is versus the latest official NAV.",
            "Tracking error and impact cost are platform calculations, labelled as such.",
        ],
        "asof": dt.date.today().isoformat(),
    }


class VsIndexBody(BaseModel):
    amount: float = 100000
    years: float = 5
    expected_return_pct: float | None = None
    index_fund_ter_pct: float = 0.20
    etf_ter_pct: float = 0.20
    brokerage_per_order: float = 20.0


@router.get("/{symbol}/intraday")
def etf_intraday(symbol: str, interval: str = "2m",
                 db: Session = Depends(get_db)):
    sym = symbol.upper()
    spec = SPECS.get(sym)
    if not spec:
        raise HTTPException(404, "This ETF is not in the curated NSE universe.")
    rec = (db.query(Instrument).filter_by(kind="ETF", symbol=sym).one_or_none())
    if rec:
        IE.ensure_instrument_ready(db, rec)
    q = _quote_map().get(sym) or {}
    hist = _history(sym)
    if not hist and rec:
        hist = list(rec.history or [])
    meta = (rec.meta or {}) if rec else {}
    ltp = _num(q.get("ltP")) or _num(meta.get("lastPrice"))
    prev = _num(q.get("prevClose")) or _num(meta.get("prevClose")) or (hist[-2]["c"] if len(hist) > 1 else None)
    try:
        data = Y.intraday(f"{sym}.NS", interval=interval, period="5d")
        if len(data.get("points") or []) >= 2:
            data["points"] = IE.stitch_live_point(
                data["points"],
                {"lastPrice": ltp, "live_time": meta.get("live_time"),
                 "volume": _num(q.get("qty")) or meta.get("volume")})
            data["last"] = data["points"][-1]["c"]
            data["prevClose"] = prev
            if prev:
                data["change"] = round(data["last"] - prev, 2)
                data["changepct"] = round((data["last"] / prev - 1) * 100, 2)
            data["live_source"] = data.get("source")
            return data
    except Exception:  # noqa: BLE001
        pass
    if len(hist) >= 2:
        points = [{"datetime": h["date"], "date": h["date"], "time": "15:30",
                   "o": h.get("o"), "h": h.get("h"), "l": h.get("l"),
                   "c": h["c"], "v": h.get("v")} for h in hist[-60:]]
        points = IE.stitch_live_point(
            points, {"lastPrice": ltp, "live_time": meta.get("live_time")})
        return {
            "ticker": f"{sym}.NS", "interval": "1d", "session": hist[-1]["date"],
            "source": "Yahoo Finance daily candles (intraday feed unavailable)",
            "points": points,
            "last": points[-1]["c"], "prevClose": prev,
            "change": (round(points[-1]["c"] - prev, 2) if prev else None),
            "changepct": (round((points[-1]["c"] / prev - 1) * 100, 2)
                          if prev else None),
            "note": "The intraday feed did not answer; the last 60 daily closes "
                    "are shown instead of fabricating candles.",
        }
    raise HTTPException(503, "No intraday price history available for this ETF yet.")


@router.post("/{symbol}/vs-index-fund")
def vs_index_fund(symbol: str, body: VsIndexBody, db: Session = Depends(get_db)):
    sym = symbol.upper()
    if sym not in SPECS:
        raise HTTPException(404, "This ETF is not in the curated NSE universe.")
    hist = _history(sym)
    rets = calc.nav_returns(_navs(hist))
    expected = (body.expected_return_pct if body.expected_return_pct is not None
                else (rets.get("5y") or rets.get("3y") or 10.0))
    etf_net = expected - body.etf_ter_pct - 0.05
    mf_net = expected - body.index_fund_ter_pct
    etf_value = body.amount * (1 + etf_net / 100) ** body.years
    mf_value = body.amount * (1 + mf_net / 100) ** body.years
    charges = calc.etf_charges(body.amount, etf_value, body.brokerage_per_order)
    return {
        "symbol": sym, "name": SPECS[sym]["name"],
        "expected_gross_return_pct": round(expected, 2),
        "etf_net_return_pct": round(etf_net, 2),
        "index_fund_net_return_pct": round(mf_net, 2),
        "amount": body.amount, "years": body.years,
        "etf_value_before_charges": round(etf_value, 2),
        "etf_charges": charges,
        "etf_value_after_charges": round(etf_value - charges["total"], 2),
        "index_fund_value": round(mf_value, 2),
        "advantage_etf": round((etf_value - charges["total"]) - mf_value, 2),
        "note": ("Same gross index return assumed for both wrappers. The ETF saves "
                 "the TER gap but pays delivery brokerage, STT, DP and a modelled "
                 "5 bps impact cost. Direct index funds carry no brokerage."),
    }
