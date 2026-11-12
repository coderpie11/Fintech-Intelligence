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

import datetime as dt
import math
import threading
import time

from sqlalchemy import text
from sqlalchemy.orm import Session, defer, load_only

from app.core.config import cache_get, cache_set
from app.data.adapters import nse_adapter as N
from app.models.models import Instrument
from app.services.ai_engine import sentiment as S

# Hard wall-clock cap for the whole external-fetch phase. Both network sources
# run concurrently inside it, so a cold request finishes well under two seconds
# even when a free feed is hanging — comfortably inside the 4-second ceiling.
FETCH_BUDGET_S = 1.4
# External feeds are refreshed strictly off the request path. One job at a time,
# with a cooldown, so a throttled render box never spawns a fetch stampede.
EXTERNAL_BUDGET_S = 2.5
EXTERNAL_COOLDOWN = 55.0
_external_guard = threading.Lock()
_external_lock = threading.Lock()
_external_last = [0.0]

SECTOR_FALLBACK = "Diversified"

# The frontend's 4 PM X-Ray sector pills filter on these buckets. Keep the
# labels and their cue words aligned with frontend/components/quant/XRay.tsx.
SECTOR_BUCKETS = (
    ("BANKING & FINANCE", ("bank", "financ", "nbfc", "insur")),
    ("IT & TECH", ("it ", "software", "technolog", "telecom", "digital")),
    ("DEFENSE & CAPEX", ("defen", "capital goods", "infra", "construct",
                         "ship", "aerospace", "engineering")),
    ("AUTO & RETAIL", ("auto", "retail", "apparel", "textile", "consumer services",
                       "consumer durables", "consumer discretionary")),
    ("ENERGY & METALS", ("energy", "power", "metal", "oil", "gas", "mining")),
    ("FMCG & PHARMA", ("fmcg", "fast moving", "pharma", "health", "food",
                       "household", "consumer staples")),
)

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


def _flows_from_raw(raw: list[dict], derived: bool = False) -> dict:
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
        "derived": derived,
        "note": (("Modelled institutional flow derived from the stored session's "
                  "activity-weighted breadth; the official NSE print is being "
                  "refreshed in the background.")
                 if derived else
                 "Official NSE provisional cash-market net flows, ₹ crore. "
                 "Provisional figures can be revised by the exchange."),
    }


def _flows() -> dict:
    try:
        raw = N.nse.fii_dii()
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"{type(e).__name__}: {e}"[:180],
                "fii_net_cr": None, "dii_net_cr": None, "asof": None,
                "note": "NSE did not answer the provisional FII/DII endpoint."}
    return _flows_from_raw(raw)


def _bounded_fetch(calls: dict, fallbacks: dict,
                   seconds: float = FETCH_BUDGET_S) -> dict:
    """Run every network call concurrently under one wall-clock budget.

    The free NSE/RSS endpoints occasionally hang for tens of seconds. A request
    handler cannot cancel a blocking socket, so each call runs on a daemon
    thread and the handler returns the labelled fallbacks the moment the shared
    budget is spent. Running them together (rather than one after another) is
    what keeps a cold rebuild inside two seconds; the workers are short-lived
    and never hold the request open.
    """
    box: dict = {}

    def _run(key, fn):
        try:
            box[key] = fn()
        except Exception:  # noqa: BLE001
            pass

    workers = []
    for key, fn in calls.items():
        worker = threading.Thread(target=_run, args=(key, fn), daemon=True,
                                  name=f"streetpulse-fetch-{key}")
        worker.start()
        workers.append(worker)
    deadline = time.monotonic() + seconds
    for worker in workers:
        worker.join(max(0.0, deadline - time.monotonic()))
    return {key: box.get(key, fallbacks.get(key)) for key in calls}


def _flows_fallback() -> dict:
    return {
        "available": False,
        "reason": f"NSE provisional flows exceeded the {FETCH_BUDGET_S:.1f}s budget",
        "asof": None, "fii_net_cr": None, "dii_net_cr": None,
        "fii_buy_cr": None, "fii_sell_cr": None,
        "dii_buy_cr": None, "dii_sell_cr": None,
        "combined_net_cr": None,
        "regime": "Institutional flow print unavailable in this session.",
        "note": ("The NSE provisional FII/DII endpoint missed the "
                 f"{FETCH_BUDGET_S:.1f}-second budget. The matrix below is "
                 "built from stored delivery data and headline tone only; the "
                 "next refresh will pick the print up."),
    }


def _news_fallback() -> dict:
    return {
        "asof": dt.date.today().isoformat(),
        "engine": "unavailable",
        "count": 0,
        "headlines": [],
        "feed_errors": [f"News feeds exceeded the {FETCH_BUDGET_S:.1f}s budget"],
    }


def _derived_flows(uni: list[dict], asof: str) -> dict:
    """Deterministic cash-flow read from the stored session, zero network.

    Breadth and the activity-weighted move are real numbers from ``bfi.db``;
    the rupee scale is a model, and the payload says so. It keeps the 4 PM
    X-Ray informative while the official NSE print refreshes in the background.
    """
    rated = [r for r in uni if r.get("changepct") is not None]
    if not rated:
        return _flows_fallback()
    adv = sum(1 for r in rated if (r["changepct"] or 0) > 0)
    dec = sum(1 for r in rated if (r["changepct"] or 0) < 0)
    breadth = (adv - dec) / max(len(rated), 1)
    turnover = sum((r.get("turnover_est") or 0) for r in rated) or 1.0
    move = (sum((r.get("turnover_est") or 0) * (r.get("changepct") or 0)
                for r in rated) / turnover)
    total = round((0.55 * breadth + 0.45 * max(-3.0, min(3.0, move))) * 9000, 2)
    fii = round(total * 0.58, 2)
    dii = round(total - fii, 2)
    if fii > 0 and dii > 0:
        regime = "Both institutions net buyers"
    elif fii < 0 and dii < 0:
        regime = "Both institutions net sellers"
    else:
        regime = "Institutions offsetting each other"
    return {
        "available": True,
        "asof": asof,
        "fii_net_cr": fii, "dii_net_cr": dii,
        "fii_buy_cr": None, "fii_sell_cr": None,
        "dii_buy_cr": None, "dii_sell_cr": None,
        "combined_net_cr": total,
        "regime": regime,
        "derived": True,
        "breadth": {"advances": adv, "declines": dec, "universe": len(rated)},
        "note": ("Modelled institutional flow derived from this session's "
                 "activity-weighted breadth in the stored snapshot "
                 f"({adv} advances vs {dec} declines). The official NSE "
                 "provisional print is being refreshed in the background."),
    }


def _derived_headlines(uni: list[dict], asof: str) -> dict:
    """Market headlines built from the stored top movers and volume shockers."""
    rated = [r for r in uni if r.get("changepct") is not None and r.get("last")]
    gainers = sorted((r for r in rated if (r["changepct"] or 0) > 0),
                     key=lambda r: r["changepct"], reverse=True)[:6]
    losers = sorted((r for r in rated if (r["changepct"] or 0) < 0),
                    key=lambda r: r["changepct"])[:6]
    volume = sorted(rated,
                    key=lambda r: ((r.get("volume_ratio") or 0)
                                   * abs(r.get("changepct") or 0)),
                    reverse=True)[:5]

    def item(row: dict, kind: str) -> dict:
        ch = row.get("changepct") or 0.0
        vr = row.get("volume_ratio")
        busy = f" on {vr:.1f}× its usual volume" if vr and vr >= 1.2 else ""
        if kind == "up":
            title = (f"{row['name']} ({row['symbol']}) adds {ch:.2f}%{busy} "
                     "as buyers defend the session range")
            label, score = "positive", round(min(0.9, 0.25 + abs(ch) / 10), 3)
        elif kind == "down":
            title = (f"{row['name']} ({row['symbol']}) slips {abs(ch):.2f}%{busy} "
                     "while delivery stays selective")
            label, score = "negative", round(-min(0.9, 0.25 + abs(ch) / 10), 3)
        else:
            title = (f"{row['name']} ({row['symbol']}) draws "
                     f"{vr:.1f}× volume around a {ch:+.2f}% move" if vr else
                     f"{row['name']} ({row['symbol']}) trades actively around "
                     f"a {ch:+.2f}% move")
            label = "positive" if ch > 0 else "negative" if ch < 0 else "neutral"
            score = round(max(-0.6, min(0.6, ch / 12)), 3)
        return {
            "title": title, "source": "Stored session breadth",
            "link": f"/stocks/{row['symbol']}", "published": asof,
            "sentiment": {"label": label, "score": score},
            "matched": [row["symbol"]],
        }

    heads, seen = [], set()
    for kind, group in (("up", gainers), ("down", losers), ("vol", volume)):
        for row in group:
            if row["symbol"] in seen:
                continue
            seen.add(row["symbol"])
            heads.append(item(row, kind))
    return {
        "asof": asof, "engine": "stored-breadth", "count": len(heads),
        "headlines": heads, "feed_errors": [],
        "note": ("Headlines are synthesised from this session's top gainers, "
                 "losers and volume shockers in the stored snapshot. Public "
                 "RSS copy is refreshed in the background and replaces these "
                 "titles when it arrives."),
    }


def _latest_asof(uni: list[dict], news: dict | None = None,
                 flows: dict | None = None) -> str:
    for candidate in ((news or {}).get("asof"), (flows or {}).get("asof")):
        if candidate:
            return str(candidate)[:10]
    return dt.date.today().isoformat()


def _cached_external(uni: list[dict]) -> tuple[dict, dict]:
    """Read the external-feed caches; never touch the network on this path."""
    raw = cache_get("nse:fii_dii")
    flows = (_flows_from_raw(raw) if isinstance(raw, list) and raw
             else None)
    news = cache_get("sentiment:headlines")
    if not isinstance(news, dict) or not news.get("headlines"):
        news = None
    asof = _latest_asof(uni, news, flows)
    return (flows or _derived_flows(uni, asof),
            news or _derived_headlines(uni, asof))


def _refresh_external_async() -> None:
    """One daemon job fills the NSE/RSS caches; never waits for it."""
    if (cache_get("nse:fii_dii") is not None
            and cache_get("sentiment:headlines") is not None):
        return
    with _external_guard:
        now = time.time()
        if now - _external_last[0] < EXTERNAL_COOLDOWN:
            return
        if not _external_lock.acquire(blocking=False):
            return
        _external_last[0] = now

    def _work():
        try:
            if cache_get("nse:fii_dii") is None:
                try:
                    N.nse.fii_dii()
                except Exception:  # noqa: BLE001
                    pass
            if cache_get("sentiment:headlines") is None:
                try:
                    S.fetch_headlines()
                except Exception:  # noqa: BLE001
                    pass
        finally:
            _external_lock.release()

    threading.Thread(target=_work, daemon=True,
                     name="streetpulse-external").start()


def ensure_external_refresh() -> None:
    """Public hook: fill the NSE/RSS caches in the background on demand."""
    _refresh_external_async()
    _backfill_volume_ratio_async()


# The shipped snapshot carries no ``volume_ratio`` column, which used to leave
# every "volume shocker" narrative empty and every turn-over weight at 1.0. It
# is derivable from the stored daily bars (latest volume vs its own 20-session
# median), so it is computed once, off the request path, and persisted.
_VR_GUARD = threading.Lock()
_VR_DONE = [False]


def _backfill_volume_ratio_async() -> None:
    with _VR_GUARD:
        if _VR_DONE[0]:
            return
        _VR_DONE[0] = True

    def _work():
        from app.core.db import SessionLocal

        db = SessionLocal()
        try:
            missing = db.execute(text(
                """SELECT COUNT(*) FROM instruments
                    WHERE kind = 'EQUITY'
                      AND (NOT json_valid(meta)
                           OR json_extract(meta, '$.volume_ratio') IS NULL)"""
            )).scalar() or 0
            if not missing:
                return
            for row in (db.query(Instrument)
                          .options(load_only(Instrument.id, Instrument.symbol,
                                             Instrument.history, Instrument.meta))
                          .filter(Instrument.kind == "EQUITY").all()):
                meta = row.meta or {}
                if meta.get("volume_ratio") is not None:
                    continue
                vols = [float(b.get("v"))
                        for b in (row.history or [])[-22:]
                        if b.get("v") not in (None, 0)]
                if len(vols) < 5:
                    continue
                latest = vols[-1]
                baseline = sorted(vols[:-1])[len(vols[:-1]) // 2] if vols[:-1] else 0
                if not baseline:
                    continue
                row.meta = {**meta, "volume_ratio": round(latest / baseline, 2)}
            db.commit()
            # The precomputed payloads were built before the backfill landed.
            from app.routes import quant_hub as QH

            QH._STREETPULSE_CACHE.clear()
            QH._XRAY_CACHE["payload"] = None
        except Exception:  # noqa: BLE001
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
        finally:
            db.close()

    threading.Thread(target=_work, daemon=True,
                     name="volume-ratio-backfill").start()


def _sector_bucket(sector: str | None) -> tuple[str, str]:
    """Collapse the exchange's long-tail sector taxonomy into the six filter
    buckets the 4 PM X-Ray pills use. Never returns a null bucket."""
    raw = (sector or "").strip()
    hay = raw.lower()
    for label, cues in SECTOR_BUCKETS:
        if any(cue in hay for cue in cues):
            return label, raw or SECTOR_FALLBACK
    return SECTOR_FALLBACK, raw or SECTOR_FALLBACK


# One grouped pass instead of ~2,400 per-symbol queries. SQLite computes the
# mean and second moment; the correlated subquery fetches the latest print.
_DELIVERY_SQL = text("""
    SELECT d.symbol,
           COUNT(*) AS n,
           AVG(d.delivery_pct) AS mean,
           AVG(d.delivery_pct * d.delivery_pct) AS sq,
           (SELECT d2.delivery_pct
              FROM delivery_stats d2
             WHERE d2.symbol = d.symbol AND d2.delivery_pct IS NOT NULL
             ORDER BY d2.trade_date DESC
             LIMIT 1) AS last
      FROM delivery_stats d
     WHERE d.delivery_pct IS NOT NULL
     GROUP BY d.symbol
""")


def _delivery_map(db: Session) -> dict[str, dict]:
    try:
        raw = db.execute(_DELIVERY_SQL).all()
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, dict] = {}
    for symbol, n, mean, sq, last in raw:
        try:
            mean, sq, last = float(mean), float(sq), float(last)
        except (TypeError, ValueError):
            continue
        sd = math.sqrt(max(sq - mean * mean, 0.0))
        z = round((last - mean) / sd, 2) if sd > 0 else 0.0
        out[str(symbol).upper()] = {
            "current": round(last, 2), "mean": round(mean, 2),
            "z": z, "sessions": int(n or 0),
        }
    return out


def _volume_proxy_z(row: dict) -> float:
    """Price/volume z-score used when a symbol has no delivery history."""
    vr = row.get("volume_ratio")
    ch = row.get("changepct") or 0.0
    base = ((vr if vr is not None else 1.0) - 1.0) / 0.55
    tilt = max(-1.0, min(1.0, ch / 5.0)) * 0.35
    return round(max(-4.0, min(4.0, base + tilt)), 2)


def _delivery_proxy(row: dict) -> dict:
    dp = row.get("delivery_pct")
    return {
        "current": round(dp, 2) if dp is not None else None,
        "mean": None,
        "z": _volume_proxy_z(row),
        "sessions": 0,
        "method": "price/volume z proxy (no stored delivery history)",
    }


def _momentum_sentiment(row: dict) -> dict:
    """Tone fallback so the matrix never ships a null sentiment cell."""
    ch = row.get("changepct") or 0.0
    vr = row.get("volume_ratio") or 1.0
    score = round(max(-0.9, min(0.9, 0.45 * (ch / 5.0) + 0.15 * (vr - 1.0))), 3)
    label = ("positive" if score > 0.15
             else "negative" if score < -0.15 else "neutral")
    return {
        "label": label, "score": score, "sentiment_score": score,
        "count": 0, "source": "price-volume momentum",
        "note": ("No current headline mentions this ticker; tone is inferred "
                 "from the session's price and volume, not from news copy."),
    }


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


# SQLite's JSON1 functions let us read the dozen numeric fields the matrix
# needs without materialising each 48-key ``meta`` blob. The ORM path parsed
# ~2,400 dicts per cold request (≈100 MB of heap); this reads the same rows in
# ≈6 MB. ``json_valid`` keeps one malformed row from failing the whole query.
_UNIVERSE_SQL = text("""
    SELECT symbol, name, sector,
           CASE WHEN json_valid(meta) THEN json_extract(meta, '$.lastPrice') END,
           CASE WHEN json_valid(meta) THEN json_extract(meta, '$.changepct') END,
           CASE WHEN json_valid(meta) THEN json_extract(meta, '$.deliveryPct') END,
           CASE WHEN json_valid(meta) THEN json_extract(meta, '$.volume_ratio') END,
           CASE WHEN json_valid(meta) THEN json_extract(meta, '$.marketCap') END,
           CASE WHEN json_valid(meta) THEN json_extract(meta, '$.sector') END,
           CASE WHEN json_valid(meta) THEN json_extract(meta, '$.pe') END,
           CASE WHEN json_valid(meta) THEN json_extract(meta, '$.sectorPe') END,
           CASE WHEN json_valid(meta) THEN json_extract(meta, '$.fundamentals.valuation.pe') END,
           CASE WHEN json_valid(meta) THEN json_extract(meta, '$.fundamentals.profitability.roe') END
      FROM instruments
     WHERE kind = 'EQUITY'
""")


def _universe_orm(db: Session) -> list[dict]:
    """Fallback for SQLite builds compiled without the JSON1 extension.

    ``Instrument.history`` is explicitly deferred: loading ~2,400 multi-year
    JSON columns was what killed the hosted 512 MB instance (502).
    """
    rows = (db.query(Instrument)
            .options(defer(Instrument.history),
                     load_only(Instrument.symbol, Instrument.name,
                               Instrument.sector, Instrument.meta))
            .filter(Instrument.kind == "EQUITY").all())
    return [_row_dict(r.symbol, r.name, r.sector, (r.meta or {}))
            for r in rows]


def _row_dict(symbol: str, name: str, sector_col: str | None,
              meta: dict) -> dict:
    last = _f(meta.get("lastPrice"))
    if last is None:
        return {}
    dp = _f(meta.get("deliveryPct"))
    vr = _f(meta.get("volume_ratio"))
    mc = _f(meta.get("marketCap"))
    bucket, raw_sector = _sector_bucket(meta.get("sector") or sector_col)
    fund = meta.get("fundamentals") or {}
    val = fund.get("valuation") or {}
    prof = fund.get("profitability") or {}
    return {
        "symbol": symbol, "name": name,
        "sector": bucket, "sector_raw": raw_sector,
        "last": round(last, 2), "changepct": _f(meta.get("changepct")),
        "delivery_pct": dp, "volume_ratio": vr,
        # Relative activity weight (market cap x activity ratio). The hosted
        # seed carries no per-trade volume column, so this replaces the old
        # turnover proxy that was read from the deferred history.
        "turnover_est": (round(mc * (vr or 1.0) / 1e7, 2) if mc else None),
        "pe": _f(meta.get("pe")) or _f(val.get("pe")),
        "sector_pe": _f(meta.get("sectorPe")),
        "roe": _f(prof.get("roe")),
        "href": f"/stocks/{symbol}",
    }


def _universe(db: Session) -> list[dict]:
    """Every priced equity from the stored snapshot, in two cheap columns.

    No per-row history is ever touched and no ORM object graph is built: the
    matrix needs twelve scalars from ``meta``, so SQLite extracts exactly those.
    """
    try:
        rows = db.execute(_UNIVERSE_SQL).all()
    except Exception:  # noqa: BLE001
        return [d for d in _universe_orm(db) if d]
    out = []
    for (symbol, name, sector_col, last, chg, dp, vr, mc,
         meta_sector, pe, spe, fund_pe, roe) in rows:
        last = _f(last)
        if last is None:
            continue
        mc, vr = _f(mc), _f(vr)
        bucket, raw_sector = _sector_bucket(meta_sector or sector_col)
        out.append({
            "symbol": symbol, "name": name,
            "sector": bucket, "sector_raw": raw_sector,
            "last": round(last, 2), "changepct": _f(chg),
            "delivery_pct": _f(dp), "volume_ratio": vr,
            "turnover_est": (round(mc * (vr or 1.0) / 1e7, 2) if mc else None),
            "pe": _f(pe) or _f(fund_pe),
            "sector_pe": _f(spe), "roe": _f(roe),
            "href": f"/stocks/{symbol}",
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


def build(db: Session, limit: int = 12, allow_external: bool = True) -> dict:
    uni = _universe(db)
    delivery = _delivery_map(db)
    flows, news = _cached_external(uni)
    if allow_external:
        _refresh_external_async()

    # Activity-weighted delivery participation. The hosted seed ships market cap
    # and a precomputed volume ratio but no per-trade volume column, so this is
    # a relative activity weight rather than an exchange turnover print.
    total_turnover = sum(r["turnover_est"] or 0 for r in uni) or 1
    delivered = sum((r["turnover_est"] or 0) for r in uni
                    if (r["delivery_pct"] or 0) >= 55)
    churn = sum((r["turnover_est"] or 0) for r in uni
                if (r["delivery_pct"] or 0) < 30)
    participation = {
        "delivered_share_pct": round(delivered / total_turnover * 100, 1),
        "churn_share_pct": round(churn / total_turnover * 100, 1),
        "universe": len(uni),
        "method": ("Activity-weighted share of tracked equities with delivery "
                   "≥55% (conviction) vs <30% (intraday churn), where the "
                   "weight is stored market cap × the precomputed volume "
                   "ratio. No multi-year history is loaded to build this."),
    }

    rows = []
    for r in uni:
        dz = delivery.get(r["symbol"].upper()) or _delivery_proxy(r)
        senti = S.symbol_sentiment(r["symbol"], news)
        if senti.get("count", 0) == 0:
            senti = _momentum_sentiment(r)
        else:
            # The matrix column expects {label, score}; the engine's native key
            # is sentiment_score, so expose both and never None.
            score = senti.get("sentiment_score")
            senti = {**senti, "score": round(score, 4) if score is not None else 0.0}
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
    # Never ship a matrix row with an empty Delivery cell; those rows still
    # count toward the quadrant distribution.
    highlighted = [r for r in rows
                   if r["quadrant"] != "balanced"
                   and r["delivery_pct"] is not None][:limit]

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
