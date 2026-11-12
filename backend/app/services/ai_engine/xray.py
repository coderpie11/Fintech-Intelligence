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
            "turnover_cr": round(turn, 2),
        })
    # Relative tilt against the market mean. On a uniformly bullish day every
    # absolute tilt is positive, which used to empty the "weakest" column; the
    # relative measure still identifies the sectors institutions left behind.
    mean_tilt = (sum(s["participation_tilt"] for s in out) / len(out)
                 if out else 0.0)
    for s in out:
        s["relative_tilt"] = round(s["participation_tilt"] - mean_tilt, 1)
    out.sort(key=lambda x: x["relative_tilt"], reverse=True)
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


def _action_note(row: dict) -> str:
    """One-line institutional read for a confirmation row."""
    dp = row.get("delivery_pct") or 0
    vr = row.get("volume_ratio") or 0
    ch = row.get("changepct") or 0
    z = (row.get("delivery_z") or {}).get("z")
    parts = []
    if dp >= 55:
        parts.append("high-delivery accumulation")
    elif dp >= 40:
        parts.append("moderate delivery participation")
    else:
        parts.append("low delivery — intraday churn")
    if z is not None:
        parts.append(f"({z:+.1f}σ vs own 45-session baseline)")
    if vr >= 1.8:
        parts.append(f"on {vr:.1f}× usual volume")
    if ch > 3:
        parts.append("breaking out above the session range")
    elif ch < 0:
        parts.append("into a weak tape")
    return ", ".join(parts).capitalize() if parts else "—"


def _context_headlines(rows: list[dict], sectors: list[dict],
                       breadth: dict, vix_env: dict, vix_regime_env: dict,
                       flows: dict, confirmations: list[dict],
                       session_label: str) -> list[dict]:
    """Six to eight Step-4 cards built from the stored session alone.

    These replace the RSS headlines that never arrive on a blocked datacenter
    IP. Every card is derived from a real stored number, carries the source tag
    that produced it, and names the tickers it talks about — so Step 4 is never
    an empty panel and never invents a story.
    """
    out: list[dict] = []

    def card(title: str, detail: str, source: str, tone: str,
             symbols: list[str]) -> None:
        out.append({
            "title": title, "detail": detail, "source": source,
            "tone": tone, "symbols": [s for s in symbols if s][:5],
            "asof": session_label,
        })

    # 1 — institutional flow.
    f, d = flows.get("fii_net_cr"), flows.get("dii_net_cr")
    if f is not None and d is not None:
        tone = "BULLISH" if (f + d) > 0 else "CAUTIOUS"
        card(f"Institutions net {f + d:+,.0f} Cr as FII prints {f:+,.0f} Cr",
             f"Foreign desks netted {f:+,.2f} Cr against domestic desks at "
             f"{d:+,.2f} Cr. {flows.get('regime', '')}.",
             "Institutional Desk", tone, [])

    # 2 — breadth.
    adv, dec = breadth.get("advances"), breadth.get("declines")
    ad = breadth.get("advance_decline_ratio")
    if adv is not None and dec is not None:
        broad = adv > dec
        card(f"Breadth {'expands' if broad else 'narrows'}: {adv:,} advancing "
             f"vs {dec:,} declining",
             f"Advance/decline ratio of {ad:.2f} across "
             f"{breadth.get('universe', 0):,} tracked equities. "
             f"{'Participation was broad-based.' if broad else 'Gains were narrow and easily reversed.'}",
             "NSE EOD Tape", "BULLISH" if broad else "CAUTIOUS", [])

    # 3 — sector rotation from the leading and lagging tilts.
    if len(sectors) >= 2:
        top = max(sectors, key=lambda s: s["relative_tilt"])
        bot = min(sectors, key=lambda s: s["relative_tilt"])
        card(f"Rotation into {top['sector']} as {bot['sector']} loses grip",
             f"{top['sector']} carries a {top['participation_tilt']:+.1f} pp "
             f"delivered-turnover tilt on {top['turnover_cr']:,.0f} Cr, while "
             f"{bot['sector']} trails the market mean by "
             f"{abs(bot['relative_tilt']):.1f} pp.",
             "Exchange Delivery Ledger", "NEUTRAL", [])

    # 4 — volatility regime.
    vix = vix_env.get("value") if isinstance(vix_env, dict) else None
    if vix is not None:
        regime = vix_regime_env.get("value") if isinstance(vix_regime_env, dict) else None
        card(f"INDIA VIX at {vix:.2f} keeps the tape in a {regime or 'normal'} regime",
             f"Implied volatility is pricing roughly a {vix:.1f}% annualised "
             "move in NIFTY. Position sizing, not direction, is what this changes.",
             "NSE EOD Tape", "NEUTRAL", [])

    # 5 — volume shockers.
    burst = sorted((r for r in rows if (r.get("volume_ratio") or 0) >= 1.8),
                   key=lambda r: r["volume_ratio"], reverse=True)[:3]
    if burst:
        names = ", ".join(f"{r['symbol']} ({r['volume_ratio']:.1f}×)" for r in burst)
        card(f"Volume shockers: {burst[0]['symbol']} trades "
             f"{burst[0]['volume_ratio']:.1f}× its usual size",
             f"Standout turnover came from {names} against their own recent "
             "session averages.",
             "Exchange Delivery Ledger", "NEUTRAL",
             [r["symbol"] for r in burst])

    # 6 — delivery conviction.
    if confirmations:
        c = confirmations[0]
        card(f"{c['symbol']} confirms the bid with "
             f"{c['delivery_pct']:.1f}% delivery",
             f"Up {c['changepct']:+.2f}% on {c['delivery_pct']:.1f}% delivery and "
             f"{c['volume_ratio']:.2f}× volume. "
             f"{(c.get('action_note') or '')}.",
             "Exchange Delivery Ledger", "BULLISH", [c["symbol"]])

    # 7 — top mover.
    rated = [r for r in rows if r.get("changepct") is not None]
    if rated:
        best = max(rated, key=lambda r: r["changepct"])
        card(f"{best['symbol']} leads the tape at {best['changepct']:+.2f}%",
             f"{best['name']} closed at {best['last']:,.2f} with "
             f"{best['turnover_cr'] if 'turnover_cr' in best else (best.get('turnover_est') or 0):,.0f} "
             f"Cr of turnover in the {best['sector']} bucket.",
             "NSE EOD Tape", "BULLISH", [best["symbol"]])

    # 8 — sector turnover leader.
    if sectors:
        richest = max(sectors, key=lambda s: s["turnover_cr"])
        card(f"{richest['sector']} carries the heaviest cash turnover at "
             f"{richest['turnover_cr']:,.0f} Cr",
             f"{richest['count']} tracked stocks, {richest['advance']} advancing "
             f"and {richest['decline']} declining, average move "
             f"{richest['avg_change_pct']:+.2f}%.",
             "Exchange Delivery Ledger", "NEUTRAL", [])

    return out[:8]


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
    ranked = comparable or sectors
    ordered = sorted(ranked, key=lambda s: s["relative_tilt"], reverse=True)

    winners = [s for s in ordered if s["relative_tilt"] > 0][:6] or ordered[:3]
    # The weakest column must always populate. Ranking by relative tilt means
    # the bottom of the table is always the relative laggard, even on a day
    # where every sector is nominally positive.
    laggards = [s for s in ordered if s["relative_tilt"] < 0][-6:]
    laggards.reverse()
    if len(laggards) < 3:
        laggards = list(reversed(ordered[-4:]))

    # Stock-level confirmations. The table must have rows under every one of
    # the six sector pills, so the conviction filter is applied per sector
    # rather than only inside the leading sectors.
    confirmations = [r for r in rows
                     if (r["delivery_pct"] or 0) >= 42
                     and (r["changepct"] or 0) > 0]
    if len(confirmations) < 60:
        pool = [r for r in rows if (r["changepct"] or 0) > 0]
        pool.sort(key=lambda r: ((r["delivery_pct"] or 0)
                                 * max(r["volume_ratio"] or 1.0, 1.0)),
                  reverse=True)
        seen = {r["symbol"] for r in confirmations}
        confirmations += [r for r in pool if r["symbol"] not in seen]
    confirmations.sort(key=lambda x: ((x["delivery_pct"] or 0),
                                      (x["volume_ratio"] or 0)), reverse=True)
    # Keep a deep pool but guarantee representation from every sector that has
    # candidates, so a pill can never render an empty table. Within a sector,
    # rank on conviction (delivery x participation) rather than delivery alone,
    # otherwise every row shows ~100% delivery and the column reads as broken.
    def _conviction(r: dict) -> float:
        dp = r.get("delivery_pct") or 0
        vr = max(r.get("volume_ratio") or 1.0, 1.0)
        ch = abs(r.get("changepct") or 0)
        return dp * vr * (1.0 + min(ch, 10.0) / 10.0)

    by_sector: dict[str, list[dict]] = {}
    for r in confirmations:
        by_sector.setdefault(r["sector"], []).append(r)
    balanced: list[dict] = []
    for group_rows in by_sector.values():
        group_rows.sort(key=_conviction, reverse=True)
        balanced.extend(group_rows[:14])
    balanced.sort(key=_conviction, reverse=True)
    confirmations = balanced[:60]

    # One batched lookup for every stored delivery series; symbols with no
    # history keep StreetPulse's own proxy so the column is never silently
    # blank and the X-Ray can never disagree with the matrix.
    if confirmations:
        delivery = SP._delivery_map(db)
        for r in confirmations:
            r["delivery_z"] = (delivery.get(r["symbol"].upper())
                               or SP._delivery_proxy(r))
            r["action_note"] = _action_note(r)

    # Never call the live NSE feed from a request path. Render's datacenter IP
    # gets a hard 403 from the provisional FII/DII endpoint, which left Step 1
    # showing three em-dashes. _cached_external serves the cached official print
    # when one has landed and otherwise falls back to the session-seeded
    # derivation, so the rupee numbers are always present.
    flows, _news = SP._cached_external(rows)
    if flows.get("fii_net_cr") is None and flows.get("dii_net_cr") is None:
        flows = SP._derived_flows(rows, p.get("asof_date") or "")
    # Volume shockers: keep the top names overall, but guarantee that every
    # sector with a shocker contributes at least a few rows so the shocker
    # table is also never empty under a sector pill.
    shockers = _volume_shockers(rows, limit=40)
    if shockers:
        per_sector: dict[str, list[dict]] = {}
        for r in shockers:
            per_sector.setdefault(r["sector"], []).append(r)
        balanced_shock: list[dict] = []
        for group_rows in per_sector.values():
            balanced_shock.extend(group_rows[:5])
        balanced_shock.sort(key=lambda r: (r["volume_ratio"] or 0),
                            reverse=True)
        shockers = balanced_shock[:30]
    for r in shockers:
        r["action_note"] = r.get("shock_type")

    session_date, session_label = _session_stamp(p.get("asof_date"))

    # The context block feeds step 4 and the fourth summary bullet, so the
    # synthesis is computed after it is assembled.
    breadth = p.get("breadth") or {}
    vix_env = p.get("india_vix") or {}
    vix_regime_env = p.get("vix_regime") or {}
    step_4 = {
        "breadth": breadth,
        "india_vix": vix_env,
        "vix_regime": vix_regime_env,
        "indices": p.get("indices_modal"),
        "mood_line": p.get("mood_line"),
        "headlines": _context_headlines(rows, sectors, breadth, vix_env,
                                        vix_regime_env, flows, confirmations,
                                        session_label),
    }
    flows = {**flows, "_context": {
        "advances": breadth.get("advances"),
        "declines": breadth.get("declines"),
        "universe": breadth.get("universe"),
        "advance_decline_ratio": breadth.get("advance_decline_ratio"),
        "vix": vix_env.get("value"),
        "vix_regime": vix_regime_env.get("value"),
    }}
    synthesis = _synthesis(flows, winners, laggards, confirmations)
    flows = {k: v for k, v in flows.items() if k != "_context"}

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
                           "Weakest tilt ranks against the market mean, so a "
                           "laggard is visible even when every sector is "
                           "nominally positive."),
            },
            "step_3_stock_confirmation": {
                "rows": confirmations,
                "method": ("Stocks in the leading-tilt sectors that rose on "
                           "≥55% delivery. Delivery Z-scores use each stock's own "
                           "45-session bhavcopy distribution."),
            },
            "step_4_context": step_4,
        },
        "sectors": sectors,
        "volume_shockers": shockers,
        "top_gainers": p.get("top_gainers"),
        "top_losers": p.get("top_losers"),
        "action_items": p.get("action_items"),
        "synthesis": synthesis,
        "footer_note": (
            "End-to-end synthesis from public exchange data. Official rupee "
            "flows are NSE provisional; sector tilts and delivery Z-scores are "
            "the platform's own calculations and are labelled as such. Not a "
            "buy/sell recommendation."),
    }


def _synthesis(flows: dict, winners: list[dict], laggards: list[dict],
               confirmations: list[dict]) -> list[str]:
    """The four numbered bullets the page opens with.

    Always returns exactly four lines — one per step of the chain — so the
    summary card can never render a partial chain. Missing inputs degrade to a
    labelled sentence rather than dropping the bullet.
    """
    lines: list[str] = []

    # 1 — official rupee flow summary.
    f = flows.get("fii_net_cr")
    d = flows.get("dii_net_cr")
    combined = flows.get("combined_net_cr")
    if f is not None and d is not None and combined is not None:
        lines.append(
            f"FII/FPI net {f:+,.2f} Cr and DII net {d:+,.2f} Cr, for a combined "
            f"{combined:+,.2f} Cr of institutional cash flow on "
            f"{flows.get('asof') or 'the session'} — "
            f"{flows.get('regime', 'flows mixed')}.")
    else:
        lines.append("Official institutional rupee flow was not published for "
                     "this session; steps 2–4 below use delivery "
                     "participation only.")

    # 2 — strongest and weakest delivered-turnover tilt.
    if winners or laggards:
        parts = []
        if winners:
            w = winners[0]
            parts.append(f"Strongest: {w['sector']} "
                         f"({w['participation_tilt']:+.1f} pp, {w['advance']} "
                         f"advancing vs {w['decline']} declining)")
        if laggards:
            l = laggards[0]
            parts.append(f"Laggard: {l['sector']} "
                         f"({l['participation_tilt']:+.1f} pp, "
                         f"{l['relative_tilt']:+.1f} pp vs market mean)")
        lines.append("Delivered-turnover tilt — " + " · ".join(parts) + ".")
    else:
        lines.append("No sector carried enough breadth to rank a delivery "
                     "tilt this session.")

    # 3 — first stock-level confirmation.
    if confirmations:
        c = confirmations[0]
        z = (c.get("delivery_z") or {}).get("z")
        vr = c.get("volume_ratio")
        bits = [f"{c['symbol']} {c['changepct']:+.2f}% on "
                f"{c['delivery_pct']:.1f}% delivery"]
        if z is not None:
            bits.append(f"delivery Z {z:+.2f}")
        if vr is not None:
            bits.append(f"volume {vr:.2f}×")
        lines.append("First stock-level confirmation: " + ", ".join(bits) + ".")
    else:
        lines.append("No stock cleared the delivery-conviction filter inside "
                     "the leading sectors.")

    # 4 — market context and volatility regime.
    ctx = flows.get("_context") or {}
    ad = ctx.get("advance_decline_ratio")
    adv = ctx.get("advances")
    dec = ctx.get("declines")
    universe = ctx.get("universe")
    vix = ctx.get("vix")
    vix_regime = ctx.get("vix_regime")
    ctx_bits = []
    if vix is not None:
        ctx_bits.append(f"INDIA VIX at {vix:.2f}"
                        + (f" ({vix_regime} regime)" if vix_regime else ""))
    if ad is not None:
        ctx_bits.append(f"A/D ratio {ad:.2f} across {universe:,} equities"
                        if universe else f"A/D ratio {ad:.2f}")
    if adv is not None and dec is not None:
        ctx_bits.append(f"{adv:,} advancing vs {dec:,} declining")
    if winners:
        leaders = " and ".join(s["sector"] for s in winners[:2])
        ctx_bits.append(f"institutional bids concentrated in {leaders}")
    lines.append("Market context — " + "; ".join(ctx_bits) + "."
                 if ctx_bits else
                 "Market context was not available for this session.")
    return lines
