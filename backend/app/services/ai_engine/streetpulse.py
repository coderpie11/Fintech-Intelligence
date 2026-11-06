"""StreetPulse Matrix — institutional flow vs retail chatter.

The matrix is deliberately built from **different kinds of evidence** so the
divergences are meaningful:

* **Institutional cash flow** — NSE's official provisional FII/FPI and DII net
  figures for the cash market. This is the real rupee flow, published daily.
* **Delivery behaviour** — the volume-weighted share of the market that took
  actual delivery versus intraday churn, plus per-stock delivery Z-scores.
* **Public-news tone** — local FinBERT (CPU) or the deterministic lexicon
  fallback, applied to public RSS headlines. Tone is *descriptive*, never a
  trading signal.

A "retail hype" row is therefore not an opinion about retail investors: it is a
stock with strongly positive news tone, low delivery participation and a
valuation that is rich against its own fundamentals. The evidence for each flag
is returned alongside it.
"""
from __future__ import annotations

import statistics

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.adapters import nse_adapter as N
from app.models.models import DeliveryStat, Instrument
from app.services.ai_engine import sentiment as S

CATALYSTS = [
    {
        "theme": "🎆 Diwali, Festive & Wedding Apparel / Retail Boom",
        "symbols": ["RAYMOND", "ABFRL", "TRENT", "TITAN", "MANYAVAR"],
        "driver": "Festive footfall, wedding wardrobe and jewellery restocking drive Q3 revenue surge.",
        "tone": "up",
    },
    {
        "theme": "🛡️ Indigenous Defense & Space Order Book",
        "symbols": ["PARAS", "HAL", "BEL", "MAZDOCK", "BDL"],
        "driver": "Make-in-India defence electronics, optics and naval pipeline order execution.",
        "tone": "accent",
    },
    {
        "theme": "⚡ Power, Renewables & Infra Capex",
        "symbols": ["NTPC", "TATAPOWER", "LT", "IREDA"],
        "driver": "Peak power demand, grid expansion and renewable capacity addition.",
        "tone": "warn",
    },
    {
        "theme": "🌾 Rural Consumption & Monsoon Recovery",
        "symbols": ["ITC", "HINDUNILVR", "DABUR", "M&M"],
        "driver": "Rural demand pickup and monsoon-led agri cash-flow recovery.",
        "tone": "up",
    },
]

DIVERGENCE_NOTE = (
    "Divergence flags compare independent measurements — news tone, delivery "
    "participation and valuation — and report where they disagree. A flag is a "
    "research prompt, not a recommendation.")


def _flows() -> dict:
    try:
        raw = N.nse.fii_dii()
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"{type(e).__name__}: {e}"[:180],
                "fii_net_cr": None, "dii_net_cr": None, "asof": None,
                "note": "NSE did not answer the provisional FII/DII endpoint."}
    fii = next((r for r in raw if "FII" in (r.get("category") or "").upper()), None)
    dii = next((r for r in raw if "DII" in (r.get("category") or "").upper()), None)

    def num(x):
        try:
            return round(float(x), 2)
        except (TypeError, ValueError):
            return None

    fii_net = num(fii.get("netValue")) if fii else None
    dii_net = num(dii.get("netValue")) if dii else None
    combined = (round(fii_net + dii_net, 2)
                if fii_net is not None and dii_net is not None else None)
    # Either leg can be missing on a partial NSE print; never compare None.
    if fii_net is None or dii_net is None:
        regime = ("Only one institutional leg was published for this session."
                  if combined is None else None)
    elif fii_net > 0 and dii_net > 0:
        regime = "Both institutions net buyers"
    elif fii_net < 0 and dii_net < 0:
        regime = "Both institutions net sellers"
    else:
        regime = "Institutions offsetting each other"
    return {
        "available": bool(fii or dii),
        "asof": (fii or dii or {}).get("date"),
        "fii_net_cr": fii_net, "dii_net_cr": dii_net,
        "fii_buy_cr": num(fii.get("buyValue")) if fii else None,
        "fii_sell_cr": num(fii.get("sellValue")) if fii else None,
        "dii_buy_cr": num(dii.get("buyValue")) if dii else None,
        "dii_sell_cr": num(dii.get("sellValue")) if dii else None,
        "combined_net_cr": combined,
        "regime": regime,
        "note": ("Official NSE provisional cash-market net flows, ₹ crore. "
                 "Provisional figures can be revised by the exchange."),
    }


def _delivery_z(db: Session, symbol: str) -> dict | None:
    rows = (db.execute(select(DeliveryStat.delivery_pct)
                       .where(DeliveryStat.symbol == symbol)
                       .order_by(DeliveryStat.trade_date))
              .scalars().all())
    vals = [v for v in rows if v is not None]
    if len(vals) < 10:
        return None
    mean = statistics.fmean(vals)
    sd = statistics.pstdev(vals)
    z = round((vals[-1] - mean) / sd, 2) if sd else None
    return {"current": round(vals[-1], 2), "mean": round(mean, 2), "z": z,
            "sessions": len(vals)}


def _f(x) -> float | None:
    """Coerce a stored value to a finite float, or None.

    Free-feed refreshes occasionally leave a string or a dict fragment in a
    numeric meta field. One bad row must not break the whole matrix.
    """
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v and abs(v) != float("inf") else None


def _universe(db: Session) -> list[dict]:
    rows = db.query(Instrument).filter(Instrument.kind == "EQUITY").all()
    out = []
    for r in rows:
        m = r.meta or {}
        hist = [h for h in (r.history or []) if h.get("c") and h.get("v")]
        last = _f(m.get("lastPrice")) or (_f(hist[-1]["c"]) if hist else None)
        ch = _f(m.get("changepct"))
        dp = _f(m.get("deliveryPct"))
        if last is None or dp is None:
            continue
        vol = _f(hist[-1]["v"]) if hist else None
        avg_vol = (statistics.fmean([v for v in
                                     (_f(h["v"]) for h in hist[-21:-1])
                                     if v is not None])
                   if len(hist) > 5 else None)
        vol_ratio = round(vol / avg_vol, 2) if vol and avg_vol else None
        fund = m.get("fundamentals") or {}
        val = fund.get("valuation") or {}
        prof = fund.get("profitability") or {}
        out.append({
            "symbol": r.symbol, "name": r.name,
            "sector": m.get("sector") or r.sector,
            "last": round(last, 2), "changepct": ch,
            "delivery_pct": dp, "volume_ratio": vol_ratio,
            "turnover_est": round(vol * last, 2) if vol else None,
            "pe": _f(m.get("pe")) or _f(val.get("pe")),
            "sector_pe": _f(m.get("sectorPe")),
            "roe": _f(prof.get("roe")),
            "href": f"/stocks/{r.symbol}",
        })
    return out


def _quadrant(row: dict, dz: dict | None, senti: dict | None) -> str:
    dp = row["delivery_pct"] or 0
    ch = row["changepct"] or 0
    z = (dz or {}).get("z")
    score = (senti or {}).get("sentiment_score") or 0.0
    high_conviction = dp >= 55 or (z is not None and z >= 1.2)
    low_conviction = dp < 30 or (z is not None and z <= -1.0)
    if high_conviction and ch > 0:
        return "institutional-accumulation"
    if high_conviction and ch < 0:
        return "distribution-under-delivery"
    if score > 0.15 and low_conviction:
        return "retail-hype"
    if score < -0.15 and high_conviction and ch >= 0:
        return "quiet-accumulation-against-press"
    return "balanced"


def _valuation_flag(row: dict) -> str | None:
    pe, spe, roe = row.get("pe"), row.get("sector_pe"), row.get("roe")
    if pe and spe and pe > spe * 1.5:
        if roe is not None and roe < 10:
            return (f"P/E {pe:.1f}× vs sector {spe:.1f}× while ROE is only "
                    f"{roe:.1f}% — the price is paying for profitability the "
                    "accounts do not yet show.")
        return (f"P/E {pe:.1f}× is more than 1.5× its sector's {spe:.1f}× — "
                "valuation is stretched relative to peers.")
    return None


def build(db: Session, limit: int = 12) -> dict:
    flows = _flows()
    news = S.fetch_headlines()
    uni = _universe(db)

    # Volume-weighted delivery participation. This is a real aggregate from
    # stored session volumes, not a survey of investor intent.
    total_turnover = sum(r["turnover_est"] or 0 for r in uni) or 1
    delivered = sum((r["turnover_est"] or 0) for r in uni
                    if (r["delivery_pct"] or 0) >= 55)
    churn = sum((r["turnover_est"] or 0) for r in uni
                if (r["delivery_pct"] or 0) < 30)
    participation = {
        "delivered_share_pct": round(delivered / total_turnover * 100, 1),
        "churn_share_pct": round(churn / total_turnover * 100, 1),
        "universe": len(uni),
        "method": ("Turnover-weighted share of tracked equities with delivery "
                   "≥55% (conviction) vs <30% (intraday churn), using the last "
                   "stored session volume × close."),
    }

    rows = []
    for r in uni:
        dz = _delivery_z(db, r["symbol"])
        senti = S.symbol_sentiment(r["symbol"], news)
        if senti.get("count", 0) == 0:
            senti = None
        q = _quadrant(r, dz, senti)
        flags = []
        val_flag = _valuation_flag(r)
        if val_flag:
            flags.append(val_flag)
        if q == "retail-hype":
            flags.append("Positive news tone with low delivery participation — "
                         "chatter is running ahead of settled ownership.")
        if q == "distribution-under-delivery":
            flags.append("High delivery while price fell — shares changed hands "
                         "into weakness.")
        if q == "quiet-accumulation-against-press":
            flags.append("High delivery and stable/rising price despite negative "
                         "news tone — accumulation is not following the headlines.")
        rows.append({**r, "delivery_z": dz, "sentiment": senti,
                     "quadrant": q, "divergence_flags": flags})

    order = {"institutional-accumulation": 0, "retail-hype": 1,
             "distribution-under-delivery": 2,
             "quiet-accumulation-against-press": 3, "balanced": 4}
    rows.sort(key=lambda x: (order.get(x["quadrant"], 9),
                             -(x["volume_ratio"] or 0)))
    highlighted = [r for r in rows if r["quadrant"] != "balanced"][:limit]

    headline_out = [{
        "title": h["title"], "source": h["source"], "link": h["link"],
        "published": h.get("published"),
        "label": h["sentiment"]["label"],
        "score": h["sentiment"]["score"],
        "symbols": h.get("matched", []),
    } for h in news["headlines"][:14]]

    pos = sum(1 for h in news["headlines"] if h["sentiment"]["score"] > 0.15)
    neg = sum(1 for h in news["headlines"] if h["sentiment"]["score"] < -0.15)
    return {
        "asof": news.get("asof"),
        "flows": flows,
        "participation": participation,
        "news_tone": {
            "engine": news["engine"],
            "headlines_scored": news["count"],
            "positive": pos, "negative": neg,
            "neutral": news["count"] - pos - neg,
            "net_tone": round((pos - neg) / max(news["count"], 1), 3),
            "feed_errors": news.get("feed_errors", []),
            "engine_status": S.finbert_status(),
            "note": ("Headline tone from a financial-sentiment model applied to "
                     "public RSS titles. It measures language, not truth or "
                     "future returns."),
        },
        "matrix": highlighted,
        "counts": {q: sum(1 for r in rows if r["quadrant"] == q)
                   for q in order},
        "headlines": headline_out,
        "catalysts": CATALYSTS,
        "divergence_note": DIVERGENCE_NOTE,
        "disclaimer": ("Descriptive analysis of public flows, delivery data and "
                       "news tone. Not investment advice."),
    }
