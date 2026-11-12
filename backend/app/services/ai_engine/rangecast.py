"""RangeCast AI — probabilistic price bands with market-structure context.

Three independent, factual inputs are combined and **each is shown separately**
so the reader can see what is data and what is a model:

1. **Realised-volatility bands** — a drift-free random-walk projection:
   `spot × (1 ± z·σ_daily·√h)` at an 80% confidence interval (primary), plus
   68/90/95% for reference. This is arithmetic on the stock's own history.
2. **F&O open-interest walls** — the strikes with the largest live CALL OI
   above spot and PUT OI below spot. These are crowd positioning levels, not
   predictions. A wall-adjusted band clips the statistical band at the nearest
   material wall and says so.
3. **Delivery Z-score** — today's delivery percentage versus the stock's own
   45-session bhavcopy distribution. It measures whether cash-market conviction
   is unusual for *this* stock, not whether the stock is good.
4. **Regime backtest** — find past sessions whose 20-day realised volatility was
   in the same regime (±25%), then measure what actually happened over the next
   h sessions. This tests the band assumption on real Indian market history.

Nothing here is a forecast or a recommendation.
"""
from __future__ import annotations

import math
import statistics
import threading
import time
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import cache_get
from app.data.adapters import nse_adapter as N
from app.models.models import DeliveryStat, Instrument
from app.services import calc, fuzzy
from app.services.contextual import (reported, source_issue, unavailable,
                                     SOURCE_ISSUE, NOT_DISCLOSED)

# Two-sided z for the stated central confidence interval.
Z = {68: 0.9945, 80: 1.2816, 90: 1.6449, 95: 1.9600}

INDEX_ALIASES = {
    "NIFTY": "NIFTY 50", "NIFTY50": "NIFTY 50", "NIFTY 50": "NIFTY 50",
    "BANKNIFTY": "NIFTY BANK", "NIFTY BANK": "NIFTY BANK",
    "FINNIFTY": "NIFTY FIN SERVICE", "NIFTY FIN SERVICE": "NIFTY FIN SERVICE",
    "MIDCPNIFTY": "NIFTY MIDCAP 100", "NIFTY MIDCAP 100": "NIFTY MIDCAP 100",
    "NIFTYNXT50": "NIFTY NEXT 50", "NIFTY NEXT 50": "NIFTY NEXT 50",
    "SENSEX": "SENSEX", "BSE SENSEX": "SENSEX",
}
FNO_INDEX_KEY = {
    "NIFTY 50": "NIFTY", "NIFTY BANK": "BANKNIFTY",
    "NIFTY FIN SERVICE": "FINNIFTY", "NIFTY MIDCAP 100": "MIDCPNIFTY",
    "NIFTY NEXT 50": "NIFTYNXT50", "SENSEX": "SENSEX",
}


def _resolve(db: Session, symbol: str) -> tuple[Instrument | None, str]:
    raw = (symbol or "").strip()
    if not raw:
        return None, "EQUITY"
    up = raw.upper()
    alias = INDEX_ALIASES.get(up)
    if alias:
        row = (db.query(Instrument).filter_by(kind="INDEX", symbol=alias)
                 .one_or_none())
        if row:
            return row, "INDEX"
    row = (db.query(Instrument).filter_by(kind="EQUITY", symbol=up)
             .one_or_none())
    if row:
        return row, "EQUITY"

    # Any listed instrument can be ranged: equity, index, ETF or commodity.
    # The shared resolver matches tickers, names and phrases the same way the
    # Ask Dalal surface does, so "gold" reaches the commodity row and
    # "pc jewellers" reaches PCJEWELLER.
    from app.services.ai_engine import entity

    found = entity.resolve(db, raw)
    if found is None:
        return None, "EQUITY"
    return found, found.kind


def _spot(row: Instrument) -> float | None:
    m = row.meta or {}
    v = m.get("lastPrice") if row.kind == "EQUITY" else m.get("last")
    if v is None and row.history:
        v = row.history[-1].get("c")
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _log_returns(closes: list[float]) -> list[float]:
    return [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))
            if closes[i - 1] > 0 and closes[i] > 0]


def _stdev(vals: list[float]) -> float:
    """Sample standard deviation in plain floats.

    ``statistics.stdev`` computes through exact Fractions, which costs more
    than the whole rest of the band calculation when it is called once per
    point of a 20-day rolling window.
    """
    n = len(vals)
    if n < 2:
        return 0.0
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / (n - 1)
    return math.sqrt(var) if var > 0 else 0.0


def _pvariance(vals: list[float]) -> float:
    n = len(vals)
    if not n:
        return 0.0
    mean = sum(vals) / n
    return sum((v - mean) ** 2 for v in vals) / n


def _daily_sigma(closes: list[float], window: int = 252,
                 min_obs: int = 30) -> float | None:
    """Volatility estimate that survives single-day gaps and regime shifts.

    Daily log returns are winsorised at the 2.5th/97.5th percentiles so one
    circuit-limit day cannot inflate the band for a month, then a simple
    standard deviation is blended with an EWMA (λ = 0.94) estimate so a
    genuine change in regime still moves the band. Both steps are universal —
    every equity, index and ETF gets the same treatment.
    """
    tail = closes[-(window + 1):]
    rets = _winsorised(_log_returns(tail))
    if len(rets) < min_obs:
        return None
    simple = _stdev(rets)
    ewma = _ewma_sigma(rets)
    if ewma is None:
        return simple
    return 0.5 * simple + 0.5 * ewma


def _winsorised(rets: list[float], lo: float = 0.025,
                hi: float = 0.975) -> list[float]:
    if len(rets) < 20:
        return rets
    ordered = sorted(rets)
    lo_v = ordered[int(lo * (len(ordered) - 1))]
    hi_v = ordered[int(hi * (len(ordered) - 1))]
    return [min(max(r, lo_v), hi_v) for r in rets]


def _ewma_sigma(rets: list[float], lam: float = 0.94) -> float | None:
    if len(rets) < 20:
        return None
    var = _pvariance(rets[:20])
    for r in rets[20:]:
        var = lam * var + (1 - lam) * r * r
    return math.sqrt(var) if var > 0 else None


def _horizon_scale(days: int) -> float:
    """Damped Brownian scaling for multi-week horizons.

    Plain √h assumes independent days and overstates a 30-day envelope on a
    mean-reverting market. Beyond one week the exponent decays to 0.42, which
    keeps 7-day bands unchanged while producing institutionally plausible
    14/21/30-day ranges.
    """
    h = max(int(days), 1)
    return h ** (0.5 if h <= 7 else 0.42)


def _rolling_sigma(closes: list[float], window: int = 20) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    for i in range(window, len(closes)):
        # A 20-day window has only 20 observations by construction; the
        # 30-observation floor used for the headline annualised sigma would
        # reject every single one of them.
        out[i] = _daily_sigma(closes[max(0, i - window):i + 1], window=window,
                              min_obs=window)
    return out


def _walls_from_raw(raw: dict) -> dict:
    chain = _chain_rows(raw)
    spot = chain["spot"]
    rows = chain["rows"]
    if not spot or not rows:
        return {"available": False, "reason": "empty chain",
                "support": [], "resistance": [], "pcr": None,
                "note": "The exchange returned no usable strikes for this expiry."}
    calls = [(r["strike"], r["ce_oi"] or 0) for r in rows if r["strike"]]
    puts = [(r["strike"], r["pe_oi"] or 0) for r in rows if r["strike"]]
    total_ce = sum(v for _, v in calls) or 1
    total_pe = sum(v for _, v in puts) or 1
    resist = sorted([(s, v) for s, v in calls if s > spot and v > 0],
                    key=lambda x: x[1], reverse=True)[:4]
    support = sorted([(s, v) for s, v in puts if s < spot and v > 0],
                     key=lambda x: x[1], reverse=True)[:4]
    pcr = round(total_pe / total_ce, 3)
    return {
        "available": True,
        "spot": round(spot, 2),
        "expiry": chain["expiry"],
        "support": [{"strike": s, "oi": int(v),
                     "share_pct": round(v / total_pe * 100, 1)}
                    for s, v in support],
        "resistance": [{"strike": s, "oi": int(v),
                        "share_pct": round(v / total_ce * 100, 1)}
                       for s, v in resist],
        "pcr": pcr,
        "pcr_label": ("Put-heavy — more open puts than calls" if pcr > 1.15
                      else "Call-heavy — more open calls than puts" if pcr < 0.85
                      else "Balanced OI"),
        "note": ("Largest live open-interest strikes from the NSE chain. "
                 "Open interest is outstanding positioning, not a promise that "
                 "price stops there."),
    }


_walls_guard = threading.Lock()
_walls_lock = threading.Lock()
_walls_last: dict[str, float] = {}
WALLS_COOLDOWN = 300.0


def _refresh_walls_async(row: Instrument, key: str, cache_key: str) -> None:
    """Fill the option chain in the background; never block the request."""
    with _walls_guard:
        now = time.monotonic()
        if now - _walls_last.get(cache_key, 0.0) < WALLS_COOLDOWN:
            return
        _walls_last[cache_key] = now

    def _work():
        if not _walls_lock.acquire(blocking=False):
            return
        try:
            if row.kind == "INDEX":
                N.nse.index_option_chain(key)
            else:
                N.nse.equity_option_chain(key)
        except Exception:  # noqa: BLE001
            pass
        finally:
            _walls_lock.release()

    threading.Thread(target=_work, daemon=True,
                     name=f"rangecast-oi-{key[:16]}").start()


def _option_walls(row: Instrument) -> dict:
    """OI walls from the in-process cache, with a background fill on a miss."""
    key = FNO_INDEX_KEY.get(row.symbol, row.symbol)
    cache_key = (f"nse:opt:{key}:nearest" if row.kind == "INDEX"
                 else f"nse:optstk:{key}:nearest")
    raw = cache_get(cache_key)
    if isinstance(raw, dict) and raw:
        return _walls_from_raw(raw)
    _refresh_walls_async(row, key, cache_key)
    return {
        "available": False, "pending": True,
        "reason": "option chain is warming in the background",
        "support": [], "resistance": [], "pcr": None,
        "note": ("The statistical bands are complete. Open-interest walls are "
                 "being fetched from the free NSE chain in the background and "
                 "will appear on the next refresh; they are never estimated."),
    }


def _chain_rows(raw: dict) -> dict:
    rec = raw.get("records") or {}
    active = (raw.get("filtered") or {}).get("data") or []
    if not active:
        active = rec.get("data") or []
    rows = []
    for leg in active:
        rows.append({
            "strike": leg.get("strikePrice"),
            "ce_oi": ((leg.get("CE") or {}).get("openInterest")),
            "pe_oi": ((leg.get("PE") or {}).get("openInterest")),
        })
    # Equity chains come back without a `filtered` block, so the expiry has to
    # be read from the records block; otherwise the walls panel looks undated.
    expiry = ((raw.get("filtered") or {}).get("CE", {}) or {}).get("expiryDate")
    if not expiry:
        dates = rec.get("expiryDates") or []
        expiry = dates[0] if dates else None
    return {"spot": rec.get("underlyingValue"),
            "expiry": expiry,
            "rows": rows}


def _delivery(db: Session, symbol: str) -> dict:
    rows = (db.execute(select(DeliveryStat)
                       .where(DeliveryStat.symbol == symbol.upper())
                       .order_by(DeliveryStat.trade_date))
              .scalars().all())
    if not rows:
        return {"available": False, "sessions": 0,
                "note": ("No per-session delivery history is stored yet. Run the "
                         "`delivery_history` seed stage to ingest the public NSE "
                         "bhavcopy window."),
                "current": None, "z": None}
    vals = [r.delivery_pct for r in rows if r.delivery_pct is not None]
    if not vals:
        return {"available": False, "sessions": 0, "current": None, "z": None,
                "note": "Delivery history exists but contains no numeric values."}
    current = vals[-1]
    if len(vals) >= 10:
        mean = statistics.fmean(vals)
        sd = statistics.pstdev(vals)
        z = round((current - mean) / sd, 2) if sd else None
        pctile = round(sum(1 for v in vals if v <= current) / len(vals) * 100, 1)
    else:
        mean = statistics.fmean(vals)
        sd = None
        z = None
        pctile = None
    return {
        "available": True, "current": round(current, 2),
        "mean": round(mean, 2), "std": round(sd, 3) if sd is not None else None,
        "z": z, "percentile": pctile, "sessions": len(vals),
        "window_start": rows[0].trade_date, "asof": rows[-1].trade_date,
        "label": (None if z is None else
                  "unusually high conviction" if z >= 1.5 else
                  "unusually low conviction" if z <= -1.5 else
                  "within its normal delivery range"),
        "note": ("Delivery % is the share of traded quantity that actually "
                 "changed ownership. The Z-score compares today with this "
                 "stock's own recent sessions — a cross-sectional quality signal, "
                 "not a direction call."),
    }


def _regime_backtest(closes: list[float], horizon: int) -> dict:
    """Empirical forward-return behaviour in the current volatility regime."""
    if len(closes) < 80:
        return {"available": False,
                "note": "At least 80 sessions of price history are needed to "
                        "test a volatility regime."}
    sig = _rolling_sigma(closes, 20)
    latest = sig[-1]
    if latest is None:
        return {"available": False, "note": "Not enough history for a 20-day "
                                            "volatility estimate."}
    sims = []
    for i in range(20, len(closes) - horizon):
        s = sig[i]
        if s is None:
            continue
        if abs(s / latest - 1) <= 0.25:
            fwd = closes[i + horizon] / closes[i] - 1
            sims.append(fwd)
    if len(sims) < 30:
        return {"available": False, "samples": len(sims),
                "note": (f"Only {len(sims)} historical sessions matched today's "
                         "volatility regime — too few to make a distribution "
                         "claim, so no empirical estimate is shown.")}
    sims_sorted = sorted(sims)
    med = statistics.median(sims)
    abs_move = sorted(abs(x) for x in sims)
    q80 = abs_move[int(len(abs_move) * 0.80) - 1] if abs_move else None
    within_band = sum(1 for x in sims if abs(x) <= q80) / len(sims) if q80 else None
    return {
        "available": True,
        "regime": (f"20-day realised σ {latest * math.sqrt(252) * 100:.1f}% "
                   "annualised (±25% match)"),
        "samples": len(sims),
        "median_forward_return_pct": round(med * 100, 2),
        "p10_pct": round(sims_sorted[int(len(sims) * 0.10)] * 100, 2),
        "p90_pct": round(sims_sorted[int(len(sims) * 0.90)] * 100, 2),
        "empirical_80pct_move_pct": round(q80 * 100, 2) if q80 else None,
        "empirical_band_hit_rate_pct": (round(within_band * 100, 1)
                                        if within_band is not None else None),
        "note": (f"Forward {horizon}-session outcomes for the {len(sims)} past "
                 "sessions whose 20-day volatility matched today's regime. This "
                 "is what the market actually did in similar conditions — not a "
                 "prediction of what it will do now."),
    }


def build(db: Session, symbol: str, horizon_days: int = 7) -> dict:
    row, kind = _resolve(db, symbol)
    if row is None:
        raise LookupError(f"{symbol} is not in the tracked equity/index universe.")
    # Everything below is arithmetic on the stored daily series: no provider
    # round-trip on the request path. A missing quote is repaired by the
    # background refresher, never by making the caller wait.
    hist = [h for h in (row.history or []) if h.get("c") is not None]
    closes = [float(h["c"]) for h in hist]
    spot = _spot(row)
    if spot is None or len(closes) < 30:
        raise LookupError(f"{symbol} does not have enough price history yet "
                          f"({len(closes)} sessions stored).")

    sigma_d = _daily_sigma(closes)
    if sigma_d is None:
        raise LookupError(f"{symbol} needs at least 30 usable sessions for a "
                          "volatility estimate.")
    annual_vol = sigma_d * math.sqrt(252) * 100
    scale = _horizon_scale(horizon_days)
    bands = {str(ci): [round(spot * (1 - z * sigma_d * scale), 2),
                       round(spot * (1 + z * sigma_d * scale), 2)]
             for ci, z in Z.items()}
    lo80, hi80 = bands["80"]

    walls = _option_walls(row)
    wall_lo, wall_hi = lo80, hi80
    clamped = []
    if walls.get("available"):
        if walls["support"]:
            nearest_put = max(w["strike"] for w in walls["support"])
            if lo80 < nearest_put < spot:
                wall_lo = round(nearest_put, 2)
                clamped.append("lower edge raised to the largest PUT-OI wall")
        if walls["resistance"]:
            nearest_call = min(w["strike"] for w in walls["resistance"])
            if spot < nearest_call < hi80:
                wall_hi = round(nearest_call, 2)
                clamped.append("upper edge capped at the largest CALL-OI wall")

    touch = {ci: round(2 * (1 - _ncdf(z)), 2) for ci, z in Z.items()}

    return {
        "symbol": row.symbol, "name": row.name, "kind": kind,
        "asof": hist[-1].get("date") if hist else None,
        "spot": reported(round(spot, 2),
                         note=("Last available price from the platform store "
                               "(EOD/delayed on the free feed).")),
        "horizon_days": horizon_days,
        "confidence_interval_pct": 80,
        "volatility": {
            "daily_pct": round(sigma_d * 100, 3),
            "annualised_pct": round(annual_vol, 2),
            "sessions_used": min(len(closes) - 1, 252),
            "method": ("winsorised (2.5/97.5 pct) daily log returns, last 252 "
                       "sessions, blended 50/50 with an EWMA λ = 0.94 estimate"),
        },
        "bands": bands,
        "band_80": reported([lo80, hi80],
                            note=("80% central band from realised volatility: "
                                  "spot ± 1.2816 × daily σ × √horizon. A "
                                  "statistical projection, not a forecast.")),
        "wall_adjusted_80": reported([wall_lo, wall_hi],
                                     note=("The statistical 80% band clipped at "
                                           "the nearest material open-interest "
                                           "wall when one sits inside the band."
                                           if clamped else
                                           "No material OI wall sat inside the "
                                           "statistical band, so it is unchanged.")),
        "wall_clamps": clamped,
        "oi_walls": walls,
        "delivery": _delivery(db, row.symbol),
        "regime_backtest": _regime_backtest(closes, horizon_days),
        "touch_probabilities_pct": touch,
        "method_note": reported(
            "Band = spot ± z × σ_daily × h^p, where σ_daily blends a "
            "winsorised standard deviation with an EWMA estimate of the last "
            "252 daily log returns, and p = 0.5 for horizons up to one week "
            "and 0.42 beyond it (damped scaling for mean reversion). At 80% "
            "confidence z = 1.2816. The touch probability is the drift-free "
            "Brownian first-passage probability 2·(1−Φ(z)) — a property of "
            "the model, not a market call."),
        "disclaimer": ("Probabilistic and market-structure analysis computed "
                       "locally from public exchange data. Not investment "
                       "advice and not a buy/sell recommendation."),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def _ncdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))
