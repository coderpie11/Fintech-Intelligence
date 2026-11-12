"""F&O module — live NSE option chains plus platform-side models where the
exchange feed does not apply:
  * SENSEX: BSE chain synthesised with our own Black-Scholes engine around the
    live SENSEX spot and INDIA VIX (BSE OI is not on any free feed here).
  * INDIA VIX: expected-move / swing calculator instead of an error panel.
Everything model-derived is explicitly labelled — never passed off as OI."""
from __future__ import annotations

import datetime as dt
import math

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, defer

from app.core.db import get_db
from app.data.adapters import nse_adapter as N
from app.models.models import Instrument
from app.services import calc
from app.services.contextual import source_issue, reported

router = APIRouter(prefix="/fno", tags=["derivatives"])

RISK_FREE = 0.065  # proxy for India short-term risk-free; documented assumption

FNO_INDICES = {"NIFTY": "NIFTY 50", "BANKNIFTY": "NIFTY BANK",
               "FINNIFTY": "NIFTY FIN SERVICE", "MIDCPNIFTY": "NIFTY MIDCAP 100",
               "NIFTYNXT50": "NIFTY NEXT 50"}
VIX_KEYS = {"INDIAVIX", "INDIA VIX", "VIX"}
SENSEX_KEYS = {"SENSEX", "BSESENSEX", "BSE SENSEX"}

# NSE contract lot sizes for index derivatives (reviewed 2025-26). Equity lots
# are company-specific and must be supplied by the caller/broker.
LOT_SIZES = {"NIFTY": 75, "BANKNIFTY": 35, "FINNIFTY": 65,
             "MIDCPNIFTY": 120, "NIFTYNXT50": 25, "SENSEX": 20}


def _parse_expiry(exp: str) -> float:
    d = dt.datetime.strptime(exp, "%d-%b-%Y")
    return max((d - dt.datetime.now()).total_seconds() / (365 * 24 * 3600), 1 / 365)


def _expiry_key(exp) -> dt.date:
    try:
        return dt.datetime.strptime(str(exp), "%d-%b-%Y").date()
    except (TypeError, ValueError):
        return dt.date.max


def _index_row(db: Session, nse_name: str) -> Instrument | None:
    return (db.query(Instrument)
              .filter_by(kind="INDEX", symbol=nse_name).one_or_none())


def _index_spot(db: Session, nse_name: str) -> float | None:
    row = _index_row(db, nse_name)
    if not row:
        return None
    m = row.meta or {}
    v = m.get("last")
    if v is None and row.history:
        v = row.history[-1].get("c")
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _transform_chain(raw: dict, underlying: str = "", selected_expiry: str | None = None) -> dict:
    """NSE chain → rows enhanced with our own BSM values where IV exists."""
    records = raw.get("records", {})
    expiry = records.get("expiryDates") or []
    active = (raw.get("filtered") or {}).get("data") or []
    lot = LOT_SIZES.get(underlying.upper(), 1)
    rows = []
    for leg in active:
        strike = leg.get("strikePrice")
        row = {
            "strike": strike,
            "expiry": leg.get("expiryDate"),
            "lot_size": lot,
            "ce_oi": (leg.get("CE") or {}).get("openInterest"),
            "ce_chg_oi": (leg.get("CE") or {}).get("changeinOpenInterest"),
            "ce_volume": (leg.get("CE") or {}).get("totalTradedVolume"),
            "ce_iv": (leg.get("CE") or {}).get("impliedVolatility"),
            "ce_ltp": (leg.get("CE") or {}).get("lastPrice"),
            "pe_oi": (leg.get("PE") or {}).get("openInterest"),
            "pe_chg_oi": (leg.get("PE") or {}).get("changeinOpenInterest"),
            "pe_volume": (leg.get("PE") or {}).get("totalTradedVolume"),
            "pe_iv": (leg.get("PE") or {}).get("impliedVolatility"),
            "pe_ltp": (leg.get("PE") or {}).get("lastPrice"),
        }
        spot = records.get("underlyingValue")
        t = _parse_expiry(row["expiry"]) if row["expiry"] else 7 / 365
        row["dte"] = round(t * 365, 1)
        if spot and row["ce_iv"] and row["ce_iv"] > 0:
            g = calc.bsm(spot, strike, t, RISK_FREE, float(row["ce_iv"]) / 100)
            row["ce_greeks"] = {
                "delta": g["delta_call"], "gamma": g["gamma"],
                "theta": round(g["theta_call"] * lot, 2),
                "theta_per_unit": g["theta_call"], "vega": g["vega"],
                "pop": g["pop_call"],
            }
        if spot and row["pe_iv"] and row["pe_iv"] > 0:
            g = calc.bsm(spot, strike, t, RISK_FREE, float(row["pe_iv"]) / 100)
            row["pe_greeks"] = {
                "delta": g["delta_put"], "gamma": g["gamma"],
                "theta": round(g["theta_put"] * lot, 2),
                "theta_per_unit": g["theta_put"], "vega": g["vega"],
                "pop": g["pop_put"],
            }
        rows.append(row)

    support = max(((r["pe_oi"] or 0, r["strike"]) for r in rows
                   if r["strike"] and r["pe_oi"] and r["strike"] < (records.get("underlyingValue") or 0)),
                  default=(0, None))
    resist = max(((r["ce_oi"] or 0, r["strike"]) for r in rows
                  if r["strike"] and r["ce_oi"] and r["strike"] > (records.get("underlyingValue") or 0)),
                 default=(0, None))
    pcr = (sum(r["pe_oi"] or 0 for r in rows) /
           max(sum(r["ce_oi"] or 0 for r in rows), 1))
    return _attach_max_pain({
        "mode": "live",
        "underlying": records.get("underlying"),
        "underlyingValue": records.get("underlyingValue"),
        "expiries": expiry,
        "active_expiry": (selected_expiry
                          if selected_expiry and selected_expiry in expiry
                          else (raw.get("filtered", {}) or {}).get("CE", {}).get("expiryDate")
                          or (expiry[0] if expiry else None)),
        "spot": reported(records.get("underlyingValue")),
        "pcr": reported(round(pcr, 3),
                        note="Put/Call OI ratio from the live chain's open interest."),
        "max_oi_support": reported(support[1], note="Strike with highest PUT OI below spot — classic support proxy."),
        "max_oi_resistance": reported(resist[1], note="Strike with highest CALL OI above spot — classic resistance proxy."),
        "rows": rows,
        "greeks_note": ("Greeks and POP are computed by the platform's own "
                        "Black-Scholes engine from exchange IVs; risk-free assumed 6.5%."),
    })


def _next_tuesdays(count: int = 4) -> list[dt.date]:
    """BSE SENSEX weekly options expire on Tuesday (current BSE cadence)."""
    today = dt.date.today()
    days_ahead = (1 - today.weekday()) % 7  # Tuesday = 1
    first = today + dt.timedelta(days=days_ahead)
    return [first + dt.timedelta(days=7 * i) for i in range(count)]


def _model_sensex_chain(db: Session, expiry: str | None = None) -> dict:
    spot = _index_spot(db, "SENSEX")
    vix = _index_spot(db, "INDIA VIX") or 15.0
    if not spot:
        raise HTTPException(503, "SENSEX spot is not seeded yet — refresh the indices stage.")
    expiries = [d.strftime("%d-%b-%Y") for d in _next_tuesdays(4)]
    active = expiry if expiry and expiry in expiries else expiries[0]
    t = _parse_expiry(active)
    sigma = max(vix, 1.0) / 100

    step = 100
    atm = round(spot / step) * step
    strikes = [atm + step * i for i in range(-12, 13)]
    rows = []
    for k in strikes:
        g = calc.bsm(spot, k, t, RISK_FREE, sigma)
        rows.append({
            "strike": k, "expiry": active, "dte": round(t * 365, 1),
            "lot_size": LOT_SIZES.get("SENSEX", 1),
            "ce_oi": None, "ce_chg_oi": None, "ce_volume": None,
            "ce_iv": round(vix, 2), "ce_ltp": g["call"],
            "pe_oi": None, "pe_chg_oi": None, "pe_volume": None,
            "pe_iv": round(vix, 2), "pe_ltp": g["put"],
            "ce_greeks": {"delta": g["delta_call"], "gamma": g["gamma"],
                          "theta": round(g["theta_call"] * LOT_SIZES.get("SENSEX", 1), 2),
                          "theta_per_unit": g["theta_call"], "vega": g["vega"],
                          "pop": g["pop_call"]},
            "pe_greeks": {"delta": g["delta_put"], "gamma": g["gamma"],
                          "theta": round(g["theta_put"] * LOT_SIZES.get("SENSEX", 1), 2),
                          "theta_per_unit": g["theta_put"], "vega": g["vega"],
                          "pop": g["pop_put"]},
        })
    return _attach_max_pain({
        "mode": "model",
        "underlying": "SENSEX",
        "underlyingValue": spot,
        "expiries": expiries,
        "active_expiry": active,
        "spot": reported(spot, note="SENSEX last close from the BSE series."),
        "pcr": source_issue("BSE open interest"),
        "max_oi_support": source_issue("BSE open interest"),
        "max_oi_resistance": source_issue("BSE open interest"),
        "rows": rows,
        "lot_size": LOT_SIZES.get("SENSEX", 1),
        "dte": round(t * 365, 1),
        "model_note": ("BSE does not expose a free option-chain endpoint here, so "
                       "this is a model-derived BSM chain: premiums and Greeks are "
                       "computed by the platform around the live SENSEX spot using "
                       "INDIA VIX as the volatility input. Open interest is left "
                       "blank — it is not fabricated."),
        "greeks_note": (f"Black-Scholes model · spot {spot:,.2f} · IV = INDIA VIX "
                        f"{vix:.2f}% · risk-free 6.5% · expiry {active}. "
                        "Model output, not an exchange quote."),
    })


def _vix_payload(db: Session) -> dict:
    spot = _index_spot(db, "NIFTY 50")
    vix = _index_spot(db, "INDIA VIX")
    if not spot or not vix:
        raise HTTPException(503, "NIFTY 50 / INDIA VIX are not seeded yet — refresh the indices stage.")
    row = _index_row(db, "INDIA VIX")
    hist = [h["c"] for h in (row.history or []) if h.get("c") is not None] if row else []
    tail = hist[-252:]
    percentile = None
    if tail:
        percentile = round(sum(1 for x in tail if x <= vix) / len(tail) * 100, 1)

    horizons = []
    for label, days in (("1D", 1), ("1W", 5), ("1M", 21)):
        move = spot * (vix / 100) * math.sqrt(days / 252)
        horizons.append({
            "label": label,
            "days": days,
            "move_points": round(move, 2),
            "move_pct": round(move / spot * 100, 2),
            "lower": round(spot - move, 2),
            "upper": round(spot + move, 2),
        })
    regime = ("Calm" if vix < 12 else "Normal" if vix < 18 else
              "Elevated" if vix < 25 else "Fear")
    return {
        "mode": "vix",
        "underlying": "INDIA VIX",
        "underlyingValue": vix,
        "spot": reported(spot, note="NIFTY 50 last close."),
        "vix": reported(vix, note="INDIA VIX last close."),
        "regime": reported(regime),
        "percentile_1y": reported(percentile) if percentile is not None else source_issue("VIX percentile"),
        "vix_52w_high": reported(max(tail)) if tail else source_issue("VIX 52-week high"),
        "vix_52w_low": reported(min(tail)) if tail else source_issue("VIX 52-week low"),
        "horizons": horizons,
        "formula": "Expected 1σ move = Spot × (VIX / 100) × √(T / 252)",
        "note": ("INDIA VIX is an implied-volatility index, not a tradable equity "
                 "index — NSE does not publish an option chain on VIX itself. "
                 "This calculator converts the VIX reading into expected NIFTY "
                 "swing ranges. Model output, not a forecast or recommendation."),
    }


# ---------------------------------------------------------------------------
# Max pain
# ---------------------------------------------------------------------------
def _max_pain(rows: list[dict]) -> dict | None:
    """Strike at which option buyers lose the most / writers pay the least.

    Payout to holders at expiry = sum(CE_OI x max(0, K - strike)) +
    sum(PE_OI x max(0, strike - K)). The max-pain strike minimises that total.
    """
    strikes = sorted({float(r["strike"]) for r in rows if r.get("strike")})
    has_oi = any((r.get("ce_oi") or 0) + (r.get("pe_oi") or 0) > 0 for r in rows)
    if not strikes or not has_oi:
        return None
    curve, best = [], None
    for k in strikes:
        pain = 0.0
        for r in rows:
            s = float(r["strike"])
            pain += max(0.0, k - s) * (r.get("ce_oi") or 0)
            pain += max(0.0, s - k) * (r.get("pe_oi") or 0)
        curve.append({"strike": k, "payout": round(pain)})
        if best is None or pain < best[1]:
            best = (k, pain)
    if best is None:
        return None
    keep = curve if len(curve) <= 41 else curve[::max(len(curve) // 40, 1)]
    return {"strike": best[0], "total_payout": round(best[1]),
            "curve": keep}


def _attach_max_pain(payload: dict) -> dict:
    mp = _max_pain(payload.get("rows") or [])
    if mp:
        payload["max_pain"] = reported(
            mp["strike"],
            note=("Strike with the minimum total option-buyer payout at "
                  "expiry, computed from the chain's own open interest."))
        payload["max_pain_payout"] = mp["total_payout"]
        payload["max_pain_curve"] = mp["curve"]
    else:
        payload["max_pain"] = source_issue("option open interest")
        payload["max_pain_curve"] = []
    return payload


# ---------------------------------------------------------------------------
# Underlying universe, futures matrix and multi-leg payoff builder
# ---------------------------------------------------------------------------
def _fno_data(underlying: str) -> list[dict]:
    try:
        return (N.nse.fno_quote(underlying) or {}).get("data") or []
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"NSE F&O feed unavailable: {e}") from e


def _quadrant(price_pct, oi_change) -> str:
    if price_pct is None or oi_change is None:
        return "No read"
    up = price_pct >= 0
    add = oi_change >= 0
    if up and add:
        return "Long Buildup"
    if not up and add:
        return "Short Buildup"
    if not up and not add:
        return "Long Unwinding"
    return "Short Covering"


@router.get("/underlyings")
def underlyings(limit: int = Query(220, ge=1, le=400),
                db: Session = Depends(get_db)):
    """Index derivatives plus the ~200 most-liquid NSE F&O stocks.

    The stock list is the top of the local equity universe by market cap; the
    exchange F&O feed is the authority on whether a chain exists, so each row
    is verified lazily when opened rather than asserted here.
    """
    indices = [{"symbol": k, "name": v, "kind": "INDEX",
                "lot_size": LOT_SIZES.get(k)}
               for k, v in FNO_INDICES.items()]
    indices.append({"symbol": "SENSEX", "name": "SENSEX", "kind": "INDEX",
                    "lot_size": LOT_SIZES.get("SENSEX")})
    rows = (db.query(Instrument)
            .options(defer(Instrument.history))
            .filter(Instrument.kind == "EQUITY").all())

    def mc(r):
        try:
            return float((r.meta or {}).get("marketCap") or 0)
        except (TypeError, ValueError):
            return 0.0

    rows.sort(key=mc, reverse=True)
    stocks = [{"symbol": r.symbol, "name": r.name, "kind": "EQUITY",
               "sector": r.sector, "lot_size": None}
              for r in rows[:limit]]
    return {
        "indices": indices,
        "stocks": stocks,
        "stock_count": len(stocks),
        "note": ("Index list is the exchange F&O index set; the stock list is "
                 "the local top-liquidity universe. Chain availability is "
                 "confirmed from the live feed when a symbol is opened."),
    }


@router.get("/futures/{underlying}")
def futures_matrix(underlying: str, lot_size: int | None = Query(None, ge=1),
                   db: Session = Depends(get_db)):
    u = underlying.upper().replace(" ", "")
    data = _fno_data(u)
    futs = [r for r in data
            if r.get("instrumentType") in ("FUTIDX", "FUTSTK")
            and r.get("lastPrice") is not None]
    if not futs:
        raise HTTPException(404, f"No futures contracts returned for {u}.")
    futs.sort(key=lambda r: _expiry_key(r.get("expiryDate")))
    spot = next((r.get("underlyingValue") for r in futs
                 if r.get("underlyingValue") is not None), None)
    rows = []
    for r in futs:
        pct = r.get("pchange")
        chg_oi = r.get("changeinOpenInterest")
        last = float(r["lastPrice"])
        prev = float(r.get("prevClose") or last)
        rows.append({
            "expiry": r.get("expiryDate"),
            "last": round(last, 2),
            "change": round(last - prev, 2),
            "change_pct": round(float(pct), 3) if pct is not None else None,
            "open": r.get("openPrice"), "high": r.get("highPrice"),
            "low": r.get("lowPrice"),
            "oi": r.get("openInterest"), "chg_oi": chg_oi,
            "oi_change_pct": (round(float(r.get("pchangeinOpenInterest")), 2)
                              if r.get("pchangeinOpenInterest") is not None
                              else None),
            "volume": r.get("totalTradedVolume"),
            "turnover": r.get("totalTurnover"),
            "buildup": _quadrant(
                float(pct) if pct is not None else None,
                float(chg_oi) if chg_oi is not None else None),
        })

    near = rows[0]
    nxt = rows[1] if len(rows) > 1 else None
    rollover = None
    if nxt:
        total = (near.get("oi") or 0) + (nxt.get("oi") or 0)
        rollover = {
            "near_expiry": near["expiry"], "next_expiry": nxt["expiry"],
            "near_oi": near.get("oi"), "next_oi": nxt.get("oi"),
            "rollover_pct": (round((nxt.get("oi") or 0) / total * 100, 2)
                             if total else None),
            "next_premium": round(nxt["last"] - near["last"], 2),
            "next_premium_pct": (round((nxt["last"] / near["last"] - 1) * 100, 3)
                                 if near["last"] else None),
            "note": ("Share of open interest already in the next expiry. "
                     "Rollover cost is the next-minus-near futures spread."),
        }

    ban_list = N.nse.fno_ban_list()
    is_index = u in FNO_INDICES or u in SENSEX_KEYS
    banned = u in ban_list
    ban_meter = {
        "applicable": not is_index,
        "banned": banned if not is_index else None,
        "threshold_pct": 95,
        "utilization_pct": 100.0 if (banned and not is_index) else None,
        "state": ("INDEX - cash settled" if is_index else
                  "BANNED" if banned else "NOT IN BAN LIST"),
        "source": "NSE fo_secban.csv (official securities-in-ban feed)",
        "note": ("NSE does not publish contract-wise MWPL on the free feed, so "
                 "the 95% meter shows the authoritative ban-list state rather "
                 "than inventing a utilisation percentage."),
    }

    traps = {"applicable": not is_index, "alerts": [], "count": 0}
    if not is_index and spot:
        today = dt.date.today()
        lot = lot_size
        alerts: list[dict] = []
        for r in data:
            if r.get("instrumentType") != "OPTSTK":
                continue
            exp = _expiry_key(r.get("expiryDate"))
            dte = (exp - today).days
            if dte < 0 or dte > 4:
                continue
            try:
                k = float(r.get("strikePrice") or 0)
                last = float(r.get("lastPrice") or 0)
            except (TypeError, ValueError):
                continue
            ot = r.get("optionType")
            intrinsic = (max(spot - k, 0) if ot == "CE"
                         else max(k - spot, 0) if ot == "PE" else 0)
            if intrinsic <= 0:
                continue
            alerts.append({
                "strike": k, "option_type": ot, "expiry": r.get("expiryDate"),
                "days_to_expiry": dte, "last": last,
                "intrinsic": round(intrinsic, 2),
                "notional_per_unit": round(k, 2),
                "margin_per_lot": (round(k * lot, 2) if lot else None),
                "risk": ("ITM stock option inside the physical-delivery "
                         "window: delivery margin is charged on the full "
                         "contract value, not just the premium."),
            })
        alerts.sort(key=lambda a: (-a["intrinsic"], a["days_to_expiry"]))
        traps = {"applicable": True, "alerts": alerts[:8],
                 "count": len(alerts),
                 "note": ("Approaching expiry, ITM stock options can be "
                          "assigned for physical delivery. Margin is ~100% of "
                          "contract value from the delivery window.")}

    return {
        "underlying": u, "spot": spot, "futures": rows,
        "rollover": rollover, "ban_meter": ban_meter, "delivery_traps": traps,
        "lot_size": lot_size,
        "note": ("Futures rows come from the live NSE F&O feed. The 4-quadrant "
                 "read is price change x OI change; it is descriptive, not a "
                 "recommendation."),
    }


class StrategyLeg(BaseModel):
    side: str = "BUY"            # BUY / SELL
    option_type: str = "CE"      # CE / PE
    strike: float
    premium: float
    lots: float = 1
    lot_size: float = 1


class StrategyBody(BaseModel):
    underlying: str = "NIFTY"
    spot: float | None = None
    legs: list[StrategyLeg]
    points: int = 41
    span_pct: float = 10.0


def _leg_pnl(leg: StrategyLeg, s: float) -> float:
    k = float(leg.strike)
    intrinsic = max(s - k, 0) if leg.option_type.upper() == "CE" else max(k - s, 0)
    sign = 1 if leg.side.upper() == "BUY" else -1
    qty = max(float(leg.lots), 0) * max(float(leg.lot_size), 1)
    return sign * qty * (intrinsic - float(leg.premium))


@router.post("/strategy/payoff")
def strategy_payoff(body: StrategyBody):
    """Expiry payoff, net premium, max P/L and breakevens for up to 4 legs."""
    legs = body.legs[:6]
    if not legs:
        raise HTTPException(422, "At least one leg is required.")
    spot = float(body.spot or max(l.strike for l in legs) or 1.0)
    net_premium = sum(
        (1 if l.side.upper() == "BUY" else -1) * float(l.premium) *
        max(float(l.lots), 0) * max(float(l.lot_size), 1) for l in legs)

    def pnl(s: float) -> float:
        return sum(_leg_pnl(l, s) for l in legs)

    strikes = sorted({float(l.strike) for l in legs})
    lo = max(min(strikes + [spot]) * 0.5, 0.0)
    hi = max(strikes + [spot]) * 1.5
    probes = [lo] + strikes + [hi]
    vals = [(s, pnl(s)) for s in probes]
    max_profit = max(v for _, v in vals)
    max_loss = min(v for _, v in vals)
    # Unbounded tails: a net long call / net short call keeps moving.
    left_slope = pnl(lo + 1) - pnl(lo)
    right_slope = pnl(hi) - pnl(hi - 1)
    profit_unbounded = right_slope > 1e-6 or left_slope < -1e-6
    loss_unbounded = right_slope < -1e-6 or left_slope > 1e-6

    breakevens = []
    for (s0, p0), (s1, p1) in zip(vals, vals[1:]):
        if abs(p0) < 1e-6:
            breakevens.append(round(s0, 2))
        elif p0 * p1 < 0:
            x = s0 + (s1 - s0) * (-p0) / (p1 - p0)
            breakevens.append(round(x, 2))

    points = max(9, min(int(body.points), 121))
    span = max(float(body.span_pct), 1.0) / 100
    start, end = spot * (1 - span), spot * (1 + span)
    step = (end - start) / (points - 1)
    curve = [{"spot": round(start + step * i, 2),
              "pnl": round(pnl(start + step * i), 2)} for i in range(points)]

    return {
        "underlying": body.underlying.upper(),
        "spot_reference": round(spot, 2),
        "legs": [l.model_dump() for l in legs],
        "net_premium": round(net_premium, 2),
        "premium_side": "net debit" if net_premium > 0 else
                        "net credit" if net_premium < 0 else "flat",
        "max_profit": None if profit_unbounded else round(max_profit, 2),
        "max_profit_unbounded": profit_unbounded,
        "max_loss": None if loss_unbounded else round(max_loss, 2),
        "max_loss_unbounded": loss_unbounded,
        "breakevens": sorted(set(breakevens)),
        "curve": curve,
        "note": ("Expiry payoff from the entered legs only. Premiums are per "
                 "unit; lots x lot_size is the contract multiplier. No margin, "
                 "charges or assignment modelling."),
    }


@router.get("/max-pain/{underlying}")
def max_pain(underlying: str, expiry: str | None = Query(None),
             db: Session = Depends(get_db)):
    chain = option_chain(underlying, expiry, db)
    return {
        "underlying": underlying.upper(),
        "mode": chain.get("mode"),
        "spot": chain.get("underlyingValue"),
        "max_pain": chain.get("max_pain"),
        "total_payout": chain.get("max_pain_payout"),
        "curve": chain.get("max_pain_curve"),
        "note": ("Computed from the chain's open interest at every strike. "
                 "Model chains without exchange OI return unavailable, never "
                 "a fabricated level."),
    }


@router.get("/{underlying}")
def option_chain(underlying: str, expiry: str | None = Query(None),
                 db: Session = Depends(get_db)):
    u = underlying.upper().replace(" ", "")
    if u in VIX_KEYS:
        return _vix_payload(db)
    if u in SENSEX_KEYS:
        return _model_sensex_chain(db, expiry)
    try:
        if u in FNO_INDICES:
            raw = N.nse.index_option_chain(u, expiry)
        else:
            raw = N.nse.equity_option_chain(u, expiry)
        return _transform_chain(raw, u, expiry)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, detail=str(e)) from e


class ReplayBody(BaseModel):
    underlying: str
    option_type: str = "CE"
    strike: float
    spot: float | None = None
    entry_price: float
    lot_size: int = 1
    lots: int = 1
    sigma_pct: float | None = None
    expiry: str | None = None
    days_to_expiry: float | None = None
    horizon: str = "+30m"
    entry_time: str | None = None
    target_spot_move_pct: float = 0.0
    iv_shift_pct: float = 0.0


def _horizon_minutes(horizon: str, dte_days: float,
                     entry_time: str | None = None) -> tuple[float, str]:
    """Convert a human horizon into minutes forward and a readable label.

    When the caller supplies an entry time (HH:MM IST) the close/next-open
    horizons are measured from that entry, not from the wall clock.
    """
    h = (horizon or "+30m").strip().lower()
    now = dt.datetime.now()
    if entry_time:
        try:
            hh, mm = [int(x) for x in entry_time.split(":")[:2]]
            now = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        except Exception:  # noqa: BLE001
            pass
    if h in ("+10m", "10m", "10"):
        return 10, "10 minutes forward"
    if h in ("+30m", "30m", "30"):
        return 30, "30 minutes forward"
    if h in ("+1h", "1h", "60m", "60"):
        return 60, "1 hour forward"
    if h in ("15:15", "close", "market-close"):
        target = now.replace(hour=15, minute=15, second=0, microsecond=0)
        mins = (target - now).total_seconds() / 60
        return max(mins, 0), "today's 15:15 IST close"
    if h in ("next-open", "next_open", "next-day-0915", "next-day"):
        target = (now + dt.timedelta(days=1)).replace(hour=9, minute=15,
                                                      second=0, microsecond=0)
        mins = (target - now).total_seconds() / 60
        return max(mins, 0), "next session 09:15 IST"
    if h in ("expiry", "till-expiry", "till_expiry"):
        return max(dte_days, 0) * 24 * 60, "till expiry"
    try:
        return max(float(h.replace("+", "").replace("m", "")), 0), f"{h} forward"
    except ValueError:
        return 30, "30 minutes forward"


def _underlying_spot(db: Session, underlying: str) -> float | None:
    u = underlying.upper().replace(" ", "")
    if u in SENSEX_KEYS:
        return _index_spot(db, "SENSEX")
    if u in FNO_INDICES:
        return _index_spot(db, FNO_INDICES[u])
    row = (db.query(Instrument).filter_by(kind="EQUITY", symbol=u).one_or_none())
    if row:
        from app.services import instrument_engine as IE
        IE.ensure_instrument_ready(db, row)
        m = row.meta or {}
        v = m.get("lastPrice")
        if v is None and row.history:
            v = row.history[-1].get("c")
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    return None


@router.post("/replay")
def replay(body: ReplayBody, db: Session = Depends(get_db)):
    """Option time/theta 'what-if' replay — projects a position forward and
    decomposes P&L into delta/gamma gains, theta decay and vega, net of charges."""
    spot = body.spot or _underlying_spot(db, body.underlying)
    if not spot:
        raise HTTPException(422, "Spot price is required — pass it explicitly or "
                                 "open a seeded underlying.")
    u = body.underlying.upper().replace(" ", "")
    sigma = body.sigma_pct
    if sigma is None:
        if u in SENSEX_KEYS or u in FNO_INDICES:
            vix = _index_spot(db, "INDIA VIX")
            sigma = vix or 15.0
        else:
            sigma = 28.0
    dte = body.days_to_expiry
    if dte is None and body.expiry:
        try:
            dte = _parse_expiry(body.expiry) * 365
        except Exception:  # noqa: BLE001
            dte = 7.0
    dte = dte if dte is not None else 7.0
    minutes, label = _horizon_minutes(body.horizon, dte, body.entry_time)
    out = calc.option_replay(
        spot=spot, strike=body.strike, sigma_pct=sigma,
        days_to_expiry=dte, horizon_minutes=minutes,
        spot_move_pct=body.target_spot_move_pct,
        option_type=body.option_type, entry_price=body.entry_price,
        lot_size=max(body.lot_size, 1), lots=max(body.lots, 1),
        iv_shift_pct=body.iv_shift_pct, risk_free=RISK_FREE)
    out["underlying"] = body.underlying
    out["option_type"] = "CALL" if body.option_type.lower().startswith("c") else "PUT"
    out["strike"] = body.strike
    out["horizon"] = label
    out["horizon_minutes"] = round(minutes, 1)
    out["sigma_pct"] = round(sigma, 2)
    out["dte_days"] = round(dte, 2)
    out["lot_size"] = max(body.lot_size, 1)
    out["lots"] = max(body.lots, 1)
    out["charges_note"] = ("F&O charges: STT 0.1% on sell premium, exchange 0.03503% "
                           "of premium, SEBI, stamp duty and 18% GST; brokerage assumed "
                           "₹20 per order.")
    return out
