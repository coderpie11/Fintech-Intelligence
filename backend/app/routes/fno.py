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
from sqlalchemy.orm import Session

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
    return {
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
    }


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
    return {
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
    }


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
