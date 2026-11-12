"""Indices module — live benchmark/sectoral list, detail with constituents,
full 5-year history, performance ladder and internal breadth."""
from __future__ import annotations

import datetime as dt
import math
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, defer

from app.core.db import get_db
from app.data.adapters import nse_adapter as N
from app.data.adapters import yfinance_adapter as Y
from app.models.models import CorporateEvent, Instrument
from app.seed.universe import INDICES
from app.services import calc, live_quote as LQ
from app.services import instrument_engine as IE
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
    rows = (db.query(Instrument)
            .options(defer(Instrument.history))
            .filter(Instrument.kind == "INDEX").all())
    by_slug = {slug_for(r): r for r in rows}
    shown: list[Instrument] = []
    for spec in INDICES:
        slug = spec["slug"]
        if not expand and slug not in BENCHMARKS and slug != "india-vix":
            continue
        if slug in by_slug:
            shown.append(by_slug[slug])
    IE.ensure_many(db, shown)
    LQ.list_rows(db, shown)
    out = []
    for spec in INDICES:
        slug = spec["slug"]
        if not expand and slug not in BENCHMARKS and slug != "india-vix":
            continue
        r = by_slug.get(slug)
        if not r:
            continue
        m = r.meta or {}
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
            "spark": IE.sparkline(r),
            "live_source": m.get("live_source"),
            "asof": m.get("live_asof"),
            "fetched_at": m.get("fetched_at"),
        })
    return {"indices": out, "expanded": expand, "expandable": True}


# ---------------------------------------------------------------------------
# GIFT Nifty + overnight ADR 09:15 implied-gap engine
# ---------------------------------------------------------------------------
OVERSEAS_ADRS = [
    {"symbol": "HDB", "name": "HDFC Bank ADR", "sector": "Banking"},
    {"symbol": "IBN", "name": "ICICI Bank ADR", "sector": "Banking"},
    {"symbol": "INFY", "name": "Infosys ADR", "sector": "IT"},
    {"symbol": "WIT", "name": "Wipro ADR", "sector": "IT"},
    {"symbol": "RDY", "name": "Dr. Reddy's ADR", "sector": "Pharma"},
]
_GIFT_TICKERS = ("GIFTNIFTY", "NIFTY_GIFT")
_RF = 0.065      # India short-term risk-free proxy used elsewhere in the app
_DY = 0.012      # NIFTY dividend-yield proxy for cost-of-carry


def _expiry_key(exp) -> dt.date:
    try:
        return dt.datetime.strptime(str(exp), "%d-%b-%Y").date()
    except (TypeError, ValueError):
        return dt.date.max


def _yf_quote(ticker: str) -> dict | None:
    try:
        h = Y.history(ticker, "1mo")
    except Exception:  # noqa: BLE001
        return None
    rows = [x for x in (h or []) if x.get("c") is not None]
    if len(rows) < 2:
        return None
    last, prev = float(rows[-1]["c"]), float(rows[-2]["c"])
    return {"last": last, "prev_close": prev,
            "change_pct": round((last / prev - 1) * 100, 3) if prev else None,
            "date": rows[-1].get("date")}


def _nearest_nifty_expiry() -> dt.date | None:
    try:
        info = N.nse.fno_contract_info("NIFTY") or {}
        dates = sorted((d for d in (info.get("expiryDates") or [])
                        if _expiry_key(d) != dt.date.max), key=_expiry_key)
        return _expiry_key(dates[0]) if dates else None
    except Exception:  # noqa: BLE001
        return None


def _nifty_futures_proxy() -> dict | None:
    """Nearest NIFTY futures from the exchange F&O feed.

    GIFT Nifty itself has no free public feed reachable from this deployment,
    so the GIFT value is proxied by the nearest NSE NIFTY futures contract and
    labelled `futures_proxy` on the wire. Nothing is invented.
    """
    try:
        data = (N.nse.fno_quote("NIFTY") or {}).get("data") or []
    except Exception:  # noqa: BLE001
        return None
    futs = [r for r in data
            if r.get("instrumentType") == "FUTIDX" and r.get("lastPrice")]
    if not futs:
        return None
    futs.sort(key=lambda r: _expiry_key(r.get("expiryDate")))
    r = futs[0]
    try:
        last = float(r["lastPrice"])
        prev = float(r.get("prevClose") or last)
    except (TypeError, ValueError):
        return None
    return {"last": last, "prev_close": prev,
            "expiry": r.get("expiryDate"),
            "change_pct": round((last / prev - 1) * 100, 3) if prev else None,
            "oi": r.get("openInterest"),
            "volume": r.get("totalTradedVolume"),
            "underlying": r.get("underlyingValue")}


def _fair_futures(spot: float, days: int) -> float:
    return spot * (1 + (_RF - _DY) * max(days, 1) / 365)


def _sector_signal(changes: list[float]) -> str:
    vals = [c for c in changes if c is not None]
    if not vals:
        return "unavailable"
    avg = sum(vals) / len(vals)
    if avg >= 0.3:
        return "lead"
    if avg <= -0.3:
        return "drag"
    return "neutral"


@router.get("/gift-nifty")
def gift_nifty(db: Session = Depends(get_db)):
    """GIFT Nifty / NIFTY futures, overnight ADRs and the 09:15 gap.

    Priority chain: a live GIFT ticker if one is reachable -> nearest NSE
    NIFTY futures as a clearly labelled proxy -> cost-of-carry model. The gap
    is always measured against NIFTY 50's previous 3:30 PM close.
    """
    nifty = (db.query(Instrument)
               .filter_by(kind="INDEX", symbol="NIFTY 50").one_or_none())
    m = (nifty.meta or {}) if nifty else {}
    spot = _clean(m.get("last"))
    prev = _clean(m.get("prevClose"))

    tickers = [a["symbol"] for a in OVERSEAS_ADRS] + ["DX-Y.NYB", "BZ=F"]
    with ThreadPoolExecutor(max_workers=3) as pool:
        snaps = list(pool.map(_yf_quote, tickers))
        gift_live = list(pool.map(_yf_quote, _GIFT_TICKERS))
    adrs = list(zip(OVERSEAS_ADRS, snaps[:len(OVERSEAS_ADRS)]))
    dxy, brent = snaps[-2], snaps[-1]
    live = next((g for g in gift_live if g), None)

    mode, instrument, note = "model", "cost-of-carry fair value", None
    if live:
        gift, mode = live, "live"
        instrument = "GIFT Nifty front-month (Yahoo)"
    else:
        proxy = _nifty_futures_proxy()
        if proxy:
            gift, mode = proxy, "futures_proxy"
            instrument = "NSE NIFTY nearest futures (GIFT Nifty proxy)"
            note = ("GIFT Nifty has no free live feed reachable here, so the "
                    "front NSE NIFTY futures print stands in for it. Labelled "
                    "proxy, never presented as a GIFT quote.")
        else:
            gift = {"last": None, "prev_close": None, "change_pct": None}
            instrument = "cost-of-carry model"

    expiry = _expiry_key(gift.get("expiry")) if gift.get("expiry") else None
    if not expiry:
        expiry = _nearest_nifty_expiry() or (dt.date.today() + dt.timedelta(days=7))
    days = max((expiry - dt.date.today()).days, 1)
    base = spot or prev
    fair = _fair_futures(base, days) if base else None
    last = gift.get("last") if gift.get("last") is not None else fair

    gap_points = gap_pct = None
    if last is not None and prev:
        gap_points = round(last - prev, 2)
        gap_pct = round((last / prev - 1) * 100, 3)
    direction = ("flat" if gap_pct is None else
                 "gap-up" if gap_pct >= 0.15 else
                 "gap-down" if gap_pct <= -0.15 else "flat")
    basis = round(last - fair, 2) if (last is not None and fair) else None

    sector_rows = []
    for sector in ("Banking", "IT", "Pharma"):
        members = [(a, s) for a, s in adrs if a["sector"] == sector]
        changes = [s["change_pct"] for _, s in members if s]
        sector_rows.append({
            "sector": sector,
            "signal": _sector_signal(changes),
            "avg_change_pct": (round(sum(changes) / len(changes), 3)
                               if changes else None),
            "drivers": [{
                "symbol": a["symbol"], "name": a["name"],
                "last": s["last"] if s else None,
                "change_pct": s["change_pct"] if s else None,
            } for a, s in members],
        })

    return {
        "asof": m.get("live_asof"),
        "mode": mode,
        "instrument": instrument,
        "source_note": note,
        "nifty": {"prev_close": prev, "last": spot,
                  "session_close": "previous 15:30 IST close"},
        "gift_nifty": {
            "symbol": "GIFTNIFTY",
            "last": round(last, 2) if last is not None else None,
            "prev_close": gift.get("prev_close"),
            "change_pct": gift.get("change_pct"),
            "expiry": expiry.isoformat(),
            "days_to_expiry": days,
            "is_proxy": mode != "live",
        },
        "fair_value": {
            "risk_free": _RF, "dividend_yield": _DY,
            "fair_futures": round(fair, 2) if fair else None,
            "basis_points": basis,
            "basis_pct": (round(basis / fair * 100, 4)
                          if basis is not None and fair else None),
        },
        "opening_gap": {
            "points": gap_points, "pct": gap_pct, "direction": direction,
            "label": ("Flat / inside normal noise" if direction == "flat"
                      else "Implied gap-up" if direction == "gap-up"
                      else "Implied gap-down"),
            "note": ("Indicative 09:15 IST opening gap from the GIFT/futures "
                     "print versus NIFTY 50's prior close. Basis-adjusted; "
                     "not a forecast and not a recommendation."),
        },
        "sectors": sector_rows,
        "overnight": {
            "adrs": [{
                "symbol": a["symbol"], "name": a["name"], "sector": a["sector"],
                "last": s["last"] if s else None,
                "prev_close": s["prev_close"] if s else None,
                "change_pct": s["change_pct"] if s else None,
                "currency": "USD",
            } for a, s in adrs],
            "dxy": {"last": dxy["last"] if dxy else None,
                    "change_pct": dxy["change_pct"] if dxy else None,
                    "implication": ("Dollar strength is a headwind for FII "
                                    "flows and rupee-sensitive sectors."
                                    if dxy and (dxy.get("change_pct") or 0) > 0
                                    else "Dollar softness is a tailwind for "
                                         "FII flows and rupee-sensitive sectors.")
                    if dxy else None},
            "brent": {"last": brent["last"] if brent else None,
                      "change_pct": brent["change_pct"] if brent else None,
                      "implication": ("Higher crude is negative for OMCs, "
                                      "paints, aviation and the import bill."
                                      if brent and (brent.get("change_pct") or 0) > 0
                                      else "Softer crude eases the import bill "
                                           "and supports OMCs, paints and aviation.")
                      if brent else None},
        },
        "disclaimer": ("Opening-gap output is statistical/indicative. ADR "
                       "moves are overnight US closes, not Indian prices."),
    }


# ---------------------------------------------------------------------------
# India VIX stability + expected-range engine
# ---------------------------------------------------------------------------
def _vix_regime(vix: float) -> dict:
    if vix < 13:
        return {"label": "Low-Volatility", "band": "< 13", "tone": "calm",
                "note": "Cheap protection; ranges compress but complacency "
                        "risk rises."}
    if vix <= 18:
        return {"label": "Normal Regime", "band": "13 - 18", "tone": "normal",
                "note": "Standard two-sided risk; option premiums are near "
                        "their long-run average."}
    return {"label": "High-Fear", "band": "> 18", "tone": "fear",
            "note": "Elevated implied vol; wide expected ranges and fast "
                    "theta decay once the event passes."}


@router.get("/vix-stability")
def vix_stability(days_ahead: int = Query(10, ge=1, le=45),
                  db: Session = Depends(get_db)):
    nifty = (db.query(Instrument)
               .filter_by(kind="INDEX", symbol="NIFTY 50").one_or_none())
    vix_row = (db.query(Instrument)
                 .filter_by(kind="INDEX", symbol="INDIA VIX").one_or_none())
    if not nifty or not vix_row:
        raise HTTPException(503, "NIFTY 50 / INDIA VIX are not seeded yet.")
    spot = _clean((nifty.meta or {}).get("last"))
    vix = _clean((vix_row.meta or {}).get("last"))
    hist = [float(h["c"]) for h in (vix_row.history or [])
            if h.get("c") is not None]
    if spot is None or vix is None:
        raise HTTPException(503, "NIFTY 50 / INDIA VIX values are unavailable.")
    tail = hist[-252:]
    mean20 = round(sum(hist[-20:]) / len(hist[-20:]), 2) if hist else None
    percentile = (round(sum(1 for x in tail if x <= vix) / len(tail) * 100, 1)
                  if tail else None)

    ranges = []
    for label, denom, formula in (
        ("Daily", math.sqrt(252), "VIX / sqrt(252)"),
        ("Weekly", math.sqrt(52), "VIX / sqrt(52)"),
        ("Monthly", math.sqrt(12), "VIX / sqrt(12)"),
    ):
        move_pct = round(vix / denom, 3)
        move_pts = round(spot * move_pct / 100, 2)
        ranges.append({
            "period": label, "formula": f"+/- ({formula}) x 100",
            "move_pct": move_pct, "move_points": move_pts,
            "lower": round(spot - move_pts, 2),
            "upper": round(spot + move_pts, 2),
        })

    # Scheduled high-volatility events: results/board meetings of NIFTY 50
    # constituents plus the monthly F&O expiry.
    meta = nifty.meta or {}
    members = {c.get("symbol") for c in (meta.get("constituents") or [])
               if c.get("symbol")}
    today = dt.date.today()
    horizon = today + dt.timedelta(days=days_ahead)
    events = []
    q = (db.query(CorporateEvent)
           .filter(CorporateEvent.ex_date >= today,
                   CorporateEvent.ex_date <= horizon)
           .order_by(CorporateEvent.ex_date))
    for e in q:
        if members and (e.symbol or "").upper() not in members:
            continue
        purpose = (e.purpose or "")
        if not any(k in purpose.lower() for k in
                   ("result", "board", "agm", "earnings", "meeting")):
            continue
        events.append({
            "symbol": e.symbol, "company": e.company, "kind": e.kind,
            "date": e.ex_date.isoformat() if e.ex_date else None,
            "days_away": (e.ex_date - today).days if e.ex_date else None,
            "purpose": purpose[:160],
        })
    expiry = _nearest_nifty_expiry()
    if expiry and today <= expiry <= horizon:
        events.append({
            "symbol": "NIFTY", "company": "NIFTY monthly F&O expiry",
            "kind": "EXPIRY", "date": expiry.isoformat(),
            "days_away": (expiry - today).days,
            "purpose": "Monthly derivative expiry and rollover",
        })

    vix_vs_mean = (round((vix / mean20 - 1) * 100, 2)
                   if mean20 else None)
    hot = ((vix_vs_mean is not None and vix_vs_mean >= 8)
           or (percentile is not None and percentile >= 75))
    warning = bool(events) and hot
    severity = ("high" if warning and ((vix_vs_mean or 0) >= 15 or
                                       (percentile or 0) >= 85)
                else "moderate" if warning else "none")
    crush = {
        "warning": warning,
        "severity": severity,
        "vix_vs_20d_mean_pct": vix_vs_mean,
        "vix_percentile_1y": percentile,
        "events": events[:8],
        "window_days": days_ahead,
        "note": ("Option buyers pay for event vol; when VIX sits above its "
                 "20-day mean into a known event, implied vol often collapses "
                 "after the print and long-premium positions lose even when "
                 "the direction is right. This is a risk flag, not a trade.")
        if warning else
        ("No elevated-IV setup into a scheduled event in the next "
         f"{days_ahead} days."),
    }

    return {
        "asof": (nifty.meta or {}).get("live_asof"),
        "spot": spot,
        "vix": vix,
        "regime": _vix_regime(vix),
        "percentile_1y": percentile,
        "mean_20d": mean20,
        "vix_52w_high": round(max(tail), 2) if tail else None,
        "vix_52w_low": round(min(tail), 2) if tail else None,
        "ranges": ranges,
        "iv_crush": crush,
        "formula_note": ("Expected move = Spot x (VIX / 100) / sqrt(N), N = "
                         "252 daily, 52 weekly, 12 monthly. VIX is an implied "
                         "volatility index, so these are one-standard-deviation "
                         "ranges, not forecasts."),
    }


@router.get("/{slug}")
def index_detail(slug: str, db: Session = Depends(get_db)):
    spec = spec_for_slug(slug)
    if not spec:
        raise HTTPException(404, "Unknown index slug")
    row = (db.query(Instrument).filter_by(kind="INDEX", symbol=spec["nse"]).one_or_none())
    if not row:
        raise HTTPException(404, "Index not seeded yet")
    IE.ensure_instrument_ready(db, row)
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
def index_intraday(slug: str, interval: str = "2m", db: Session = Depends(get_db)):
    spec = spec_for_slug(slug)
    if not spec:
        raise HTTPException(404, "Unknown index slug")
    row = (db.query(Instrument).filter_by(kind="INDEX", symbol=spec["nse"]).one_or_none())
    if not row:
        raise HTTPException(404, "Index not seeded yet")
    IE.ensure_instrument_ready(db, row)
    quote = LQ.refresh_one(db, row)
    ticker = spec.get("yahoo")
    if ticker:
        try:
            data = Y.intraday(ticker, interval=interval, period="5d")
            if data["points"]:
                data["points"] = IE.stitch_live_point(data["points"], row.meta)
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
        points = IE.stitch_live_point(points, row.meta)
        change = round(hist[-1]["c"] - hist[-2]["c"], 2)
        return {
            "ticker": ticker, "interval": "1d", "session": hist[-1]["date"],
            "source": "Yahoo Finance daily candles (intraday feed unavailable)",
            "points": points,
            "last": points[-1]["c"],
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
