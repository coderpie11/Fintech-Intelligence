"""4 PM Market X-Ray — end-to-end synthesis of institutional money flow.

The chain the page walks, in order of certainty:

1. **Top of the funnel — official cash flows.** NSE's provisional FII/FPI and
   DII net rupee figures. This is the only step measured in rupees.
2. **Sector tilt — where the delivered turnover sat.** For every sector the
   platform computes the turnover-weighted share of stocks with delivery ≥55%
   minus the share with delivery <30%. That is a *participation tilt*, not a
   rupee flow; it is labelled as such.
3. **Stock-level confirmation — delivery Z-score and volume shock.** Which
   names inside those sectors actually changed hands with conviction, and which
   merely traded heavily.
4. **Breadth and volatility context.** Advance/decline, INDIA VIX regime and
   the corporate-action calendar.

Every step reports its own unit and its own limitation, so no modelled number is
mistaken for an exchange-reported one.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session


def _last_completed_session() -> dt.date:
    """Latest completed weekday session, using IST and the 4:30 PM close."""
    now_ist = dt.datetime.utcnow() + dt.timedelta(hours=5, minutes=30)
    day = now_ist.date()
    if now_ist.time() < dt.time(16, 30):
        day -= dt.timedelta(days=1)
    while day.weekday() >= 5:
        day -= dt.timedelta(days=1)
    return day


def _session_stamp(asof) -> tuple[str, str]:
    day = None
    if asof:
        try:
            day = dt.date.fromisoformat(str(asof)[:10])
        except (TypeError, ValueError):
            day = None
    day = day or _last_completed_session()
    return day.isoformat(), day.strftime("%A, %d %B %Y")

from app.services.ai_engine import streetpulse as SP


def _sectors(rows: list[dict]) -> list[dict]:
    agg: dict[str, dict] = {}
    for r in rows:
        sec = r["sector"] or "Unclassified"
        a = agg.setdefault(sec, {"sector": sec, "count": 0, "advance": 0,
                                 "decline": 0, "sum_change": 0.0,
                                 "turnover": 0.0, "delivered": 0.0, "churn": 0.0})
        a["count"] += 1
        ch = r["changepct"] or 0
        a["advance" if ch >= 0 else "decline"] += 1
        a["sum_change"] += ch
        t = r.get("turnover_est") or 0
        a["turnover"] += t
        if (r["delivery_pct"] or 0) >= 55:
            a["delivered"] += t
        elif (r["delivery_pct"] or 0) < 30:
            a["churn"] += t
    out = []
    for a in agg.values():
        turn = a["turnover"] or 1
        deliv_share = a["delivered"] / turn * 100
        churn_share = a["churn"] / turn * 100
        out.append({
            "sector": a["sector"], "count": a["count"],
            "advance": a["advance"], "decline": a["decline"],
            "avg_change_pct": round(a["sum_change"] / max(a["count"], 1), 2),
            "delivered_turnover_share_pct": round(deliv_share, 1),
            "churn_turnover_share_pct": round(churn_share, 1),
            "participation_tilt": round(deliv_share - churn_share, 1),
            "turnover_cr": round(turn / 1e7, 2),
        })
    out.sort(key=lambda x: x["participation_tilt"], reverse=True)
    return out


def _volume_shockers(rows: list[dict], limit: int = 10) -> list[dict]:
    shock = [r for r in rows if (r["volume_ratio"] or 0) >= 1.8]
    shock.sort(key=lambda x: (x["volume_ratio"] or 0), reverse=True)
    out = []
    for r in shock[:limit]:
        ch = r["changepct"] or 0
        dp = r["delivery_pct"] or 0
        if ch > 1 and dp >= 50:
            kind = "volume + price + delivery — conviction expansion"
        elif ch > 1 and dp < 30:
            kind = "volume + price, low delivery — intraday churn"
        elif ch < -1 and dp >= 50:
            kind = "volume + price fall + delivery — distribution"
        elif ch < -1:
            kind = "volume + price fall, low delivery — speculative exit"
        else:
            kind = "volume without a meaningful price move — two-sided battle"
        out.append({**r, "shock_type": kind})
    return out


def build(db: Session) -> dict:
    from app.routes.pulse import pulse

    p = pulse(db)
    # Reuse the StreetPulse universe builder so the X-Ray and the matrix can
    # never disagree about the same stock on the same day.
    rows = SP._universe(db)
    sectors = _sectors(rows)
    # A "sector" with one stock is that stock's own delivery print, not a
    # sector tilt. Require a minimum breadth before ranking a tilt.
    MIN_SECTOR_BREADTH = 3
    comparable = [s for s in sectors if s["count"] >= MIN_SECTOR_BREADTH]
    winners = [s for s in comparable if s["participation_tilt"] > 0][:6]
    laggards = [s for s in comparable if s["participation_tilt"] < 0][-6:]
    laggards.reverse()

    # Stock-level confirmations inside the strongest tilted sectors.
    strong_sectors = {s["sector"] for s in winners}
    confirmations = [r for r in rows
                     if (r["sector"] or "Unclassified") in strong_sectors
                     and (r["delivery_pct"] or 0) >= 55
                     and (r["changepct"] or 0) > 0]
    # One batched lookup for every stored delivery series; symbols with no
    # history keep StreetPulse's own proxy so the column is never silently
    # blank and the X-Ray can never disagree with the matrix.
    if confirmations:
        delivery = SP._delivery_map(db)
        for r in confirmations:
            r["delivery_z"] = (delivery.get(r["symbol"].upper())
                               or SP._delivery_proxy(r))
    confirmations.sort(key=lambda x: (x["delivery_pct"] or 0,
                                      x["volume_ratio"] or 0), reverse=True)

    flows = SP._flows()
    shockers = _volume_shockers(rows)
    session_date, session_label = _session_stamp(p.get("asof_date"))
    return {
        "asof": p.get("asof_date"),
        "session_date": session_date,
        "session_label": session_label,
        "market_status": p.get("market_status"),
        "chain": {
            "step_1_official_flows": flows,
            "step_2_sector_tilt": {
                "leaders": winners, "laggards": laggards,
                "method": ("Turnover-weighted share of each sector's stocks "
                           "with delivery ≥55% minus the share with delivery "
                           "<30%. A participation tilt in percentage points — "
                           "NOT a rupee flow. Rupee flows exist only at step 1. "
                           "Only sectors with at least 3 tracked stocks are "
                           "ranked, so a single-stock 'sector' cannot top the "
                           "table."),
            },
            "step_3_stock_confirmation": {
                "rows": confirmations[:10],
                "method": ("Stocks in the leading-tilt sectors that rose on "
                           "≥55% delivery. Delivery Z-scores use each stock's own "
                           "45-session bhavcopy distribution."),
            },
            "step_4_context": {
                "breadth": p.get("breadth"),
                "india_vix": p.get("india_vix"),
                "vix_regime": p.get("vix_regime"),
                "indices": p.get("indices_modal"),
                "mood_line": p.get("mood_line"),
            },
        },
        "sectors": sectors,
        "volume_shockers": shockers,
        "top_gainers": p.get("top_gainers"),
        "top_losers": p.get("top_losers"),
        "action_items": p.get("action_items"),
        "synthesis": _synthesis(flows, winners, laggards, confirmations),
        "footer_note": (
            "End-to-end synthesis from public exchange data. Official rupee "
            "flows are NSE provisional; sector tilts and delivery Z-scores are "
            "the platform's own calculations and are labelled as such. Not a "
            "buy/sell recommendation."),
    }


def _synthesis(flows: dict, winners: list[dict], laggards: list[dict],
               confirmations: list[dict]) -> list[str]:
    lines = []
    if flows.get("available"):
        f, d = flows.get("fii_net_cr"), flows.get("dii_net_cr")
        if f is not None and d is not None:
            lines.append(
                f"FII/FPI net {f:+,.2f} Cr and DII net {d:+,.2f} Cr on "
                f"{flows.get('asof')} — {flows.get('regime','flows mixed')}.")
    if winners:
        w = winners[0]
        lines.append(
            f"Strongest delivered-turnover tilt: {w['sector']} "
            f"({w['participation_tilt']:+.1f} pp, {w['advance']} advancing vs "
            f"{w['decline']} declining).")
    if laggards:
        l = laggards[0]
        lines.append(
            f"Weakest delivered-turnover tilt: {l['sector']} "
            f"({l['participation_tilt']:+.1f} pp).")
    if confirmations:
        c = confirmations[0]
        z = (c.get("delivery_z") or {}).get("z")
        z_txt = f", delivery Z {z:+.2f}" if z is not None else ""
        lines.append(
            f"First stock-level confirmation: {c['symbol']} +"
            f"{c['changepct']:.2f}% on {c['delivery_pct']:.1f}% delivery"
            f"{z_txt}.")
    if not lines:
        lines.append("No official flow or delivery-tilt signal was available "
                     "for this session. Nothing is inferred in its place.")
    return lines
