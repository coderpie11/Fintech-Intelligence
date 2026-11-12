"""4 PM Market Pulse — breadth, VIX regime, movers, volume/delivery shockers,
clickable sector money-flow and a full sector constituent drawer."""
from __future__ import annotations

import os
import threading
import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, defer

from app.core.db import get_db
from app.data.adapters import nse_adapter as N
from app.models.models import CorporateEvent, Instrument
from app.services import calc
from app.services import live_quote as LQ
from app.services.contextual import reported, source_issue
from app.routes.equities import _loaded_history, _snap

router = APIRouter(prefix="/pulse", tags=["market pulse"])

# The slim hosted seed precomputes each row's return ladder in ``meta``, so the
# pulse pass never needs the multi-year JSON column there. A local full store
# has no such cache and still computes the ladder from history as before.
_DEFER_HISTORY = bool(os.getenv("RENDER"))


def _history_opts(query):
    return query.options(defer(Instrument.history)) if _DEFER_HISTORY else query

# Quote refresh runs off the request path. A 5-minute guard keeps a burst of
# page loads from stacking up 120-symbol downloads, and the HTTP response is
# always built from whatever is already in SQLite.
_REFRESH_LOCK = threading.Lock()
_LAST_REFRESH = 0.0
_REFRESH_INTERVAL = 300.0
_STATUS: dict = {"value": None, "trade_date": None, "at": 0.0}
_STATUS_INTERVAL = 180.0
_STATUS_LOCK = threading.Lock()

# The computed payload is pure read-only arithmetic over the stored snapshot.
# A short in-process cache keeps repeat loads in the low milliseconds while the
# daemon thread above keeps the underlying quotes moving.
_PAYLOAD: dict = {"at": 0.0, "data": None}
_PAYLOAD_LOCK = threading.Lock()
_PAYLOAD_TTL = 120.0


def _background_refresh() -> None:
    global _LAST_REFRESH
    with _REFRESH_LOCK:
        if time.time() - _LAST_REFRESH < _REFRESH_INTERVAL:
            return
        _LAST_REFRESH = time.time()

    def work() -> None:
        from app.core.db import SessionLocal

        s = SessionLocal()
        try:
            candidates = _history_opts(
                s.query(Instrument).filter(Instrument.kind == "EQUITY")).all()

            def _mcap(r: Instrument) -> float:
                try:
                    return float((r.meta or {}).get("marketCap") or 0)
                except (TypeError, ValueError):
                    return 0.0

            candidates.sort(key=_mcap, reverse=True)
            LQ.list_rows(s, candidates[:120], cap=120)
            idx_rows = _history_opts(
                s.query(Instrument).filter(Instrument.kind == "INDEX")).all()
            LQ.list_rows(s, idx_rows)
        except Exception:  # noqa: BLE001
            pass
        finally:
            s.close()

    threading.Thread(target=work, name="pulse-quote-refresh", daemon=True).start()


def _background_status() -> None:
    with _STATUS_LOCK:
        if time.time() - _STATUS["at"] < _STATUS_INTERVAL:
            return
        _STATUS["at"] = time.time()

    def work() -> None:
        try:
            raw = N.nse.market_status()
            cm = next((m for m in raw.get("marketState", [])
                       if m.get("market") == "Capital Market"), {})
            _STATUS["value"] = cm.get("marketStatus") or "Unknown"
            _STATUS["trade_date"] = cm.get("tradeDate")
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=work, name="pulse-status-refresh", daemon=True).start()



def _returns(hist: list[dict]) -> dict:
    return calc.nav_returns([{"date": h["date"], "nav": h["c"]} for h in hist or []])


def _delivery_speed(r: Instrument) -> float | None:
    hist = _loaded_history(r)
    vols = [h.get("v") for h in hist[-21:] if h.get("v")]
    if len(vols) < 5:
        return None
    avg = sum(vols[:-1]) / max(len(vols) - 1, 1)
    return round(vols[-1] / avg, 2) if avg else None


def _sector_rows(db: Session, sector: str | None = None) -> list[dict]:
    q = _history_opts(
        db.query(Instrument).filter(Instrument.kind == "EQUITY"))
    rows = q.all()
    out = []
    for r in rows:
        m = r.meta or {}
        # Skip unpriced rows before doing any history maths; the long tail of
        # 2,000+ NSE names would otherwise dominate the request.
        if m.get("lastPrice") is None:
            continue
        snap = _snap(r)
        sec = snap["sector"] or "Unclassified"
        if sector and sec.lower() != sector.lower():
            continue
        # The seed precomputes the ladder and volume ratio. Only a row without
        # the cache pays for its (already loaded) history.
        rets = m.get("returns")
        if not isinstance(rets, dict):
            rets = _returns(_loaded_history(r))
        vol_ratio = m.get("volume_ratio")
        if vol_ratio is None:
            vol_ratio = _delivery_speed(r)
        out.append({
            "symbol": r.symbol, "name": r.name, "sector": sec,
            "last": snap["last"]["value"], "changepct": snap["changepct"]["value"],
            "return_1w": rets.get("1w"), "return_1m": rets.get("1m"),
            "return_1y": rets.get("1y"),
            "market_cap": snap["market_cap"]["value"],
            "pe": snap["pe"]["value"], "pb": snap["pb"]["value"],
            "roe": (m.get("fundamentals") or {}).get("profitability", {}).get("roe"),
            "delivery_pct": m.get("deliveryPct"),
            "volume_ratio": vol_ratio,
            "href": f"/stocks/{r.symbol}",
        })
    return out


@router.get("")
def pulse(db: Session = Depends(get_db)):
    now = time.time()
    with _PAYLOAD_LOCK:
        cached = _PAYLOAD["data"]
        age = now - _PAYLOAD["at"]
    if cached is not None:
        # Stale-while-revalidate: a page view never pays the arithmetic pass.
        # Serve the last payload immediately and rebuild it in a daemon thread.
        if age >= _PAYLOAD_TTL:
            _recompute_payload()
        return cached
    payload = _compute_pulse(db)
    with _PAYLOAD_LOCK:
        _PAYLOAD["data"] = payload
        _PAYLOAD["at"] = time.time()
    return payload


_RECOMPUTE_LOCK = threading.Lock()
_RECOMPUTING: dict = {"on": False}


def _recompute_payload() -> None:
    with _RECOMPUTE_LOCK:
        if _RECOMPUTING["on"]:
            return
        _RECOMPUTING["on"] = True

    def work() -> None:
        from app.core.db import SessionLocal

        s = SessionLocal()
        try:
            payload = _compute_pulse(s)
            with _PAYLOAD_LOCK:
                _PAYLOAD["data"] = payload
                _PAYLOAD["at"] = time.time()
        except Exception:  # noqa: BLE001
            pass
        finally:
            s.close()
            with _RECOMPUTE_LOCK:
                _RECOMPUTING["on"] = False

    threading.Thread(target=work, name="pulse-payload-refresh", daemon=True).start()


def _compute_pulse(db: Session) -> dict:
    # Never block the response on a quote refresh: serve the stored snapshot
    # immediately and let a daemon thread update the 120 largest names.
    _background_refresh()
    _background_status()
    snaps = _sector_rows(db)
    snaps = [s for s in snaps if s["last"] is not None]
    gainers = sorted(snaps, key=lambda s: s["changepct"] or 0, reverse=True)[:8]
    losers = sorted(snaps, key=lambda s: s["changepct"] or 0)[:8]

    sector_agg: dict[str, dict] = {}
    for s in snaps:
        sec = s["sector"] or "Unclassified"
        ch = s["changepct"] or 0
        agg = sector_agg.setdefault(sec, {"sector": sec, "advance": 0, "decline": 0,
                                          "sum_change": 0.0, "count": 0})
        agg["count"] += 1
        agg["advance" if ch >= 0 else "decline"] += 1
        agg["sum_change"] += ch
    sectors = []
    for sec in sector_agg.values():
        sectors.append({"sector": sec["sector"],
                        "avg_change": round(sec["sum_change"] / max(sec["count"], 1), 2),
                        "advance": sec["advance"], "decline": sec["decline"],
                        "count": sec["count"]})
    sectors.sort(key=lambda x: x["avg_change"], reverse=True)

    idx_rows = _history_opts(
        db.query(Instrument).filter(Instrument.kind == "INDEX")).all()
    indices = [{"slug": (r.meta or {}).get("slug") or r.slug, "name": r.name,
                "last": (r.meta or {}).get("last"),
                "changepct": (r.meta or {}).get("changepct")}
               for r in idx_rows if (r.meta or {}).get("top6")]
    indices = [i for i in indices if i["changepct"] is not None]

    advances = sum(1 for s in snaps if (s["changepct"] or 0) > 0)
    declines = sum(1 for s in snaps if (s["changepct"] or 0) < 0)
    unchanged = len(snaps) - advances - declines
    mood = ("Risk-positive breadth" if advances > declines * 1.2 else
            "Defensive breadth" if declines > advances * 1.2 else "Balanced breadth")

    # VIX regime from the seeded index.
    vix_row = (db.query(Instrument).filter_by(kind="INDEX", symbol="INDIA VIX")
                 .one_or_none())
    vix = (vix_row.meta or {}).get("last") if vix_row else None
    vix_regime = (None if vix is None else
                  "Calm" if vix < 12 else "Normal" if vix < 18 else
                  "Elevated" if vix < 25 else "Fear")

    volume_shockers = sorted(
        [s for s in snaps if (s["volume_ratio"] or 0) >= 1.8],
        key=lambda s: s["volume_ratio"], reverse=True)[:8]
    delivery_shockers = sorted(
        [s for s in snaps if (s["delivery_pct"] or 0) >= 55 and (s["changepct"] or 0) > 0],
        key=lambda s: (s["delivery_pct"] or 0), reverse=True)[:8]

    events = (db.query(CorporateEvent)
                .order_by(CorporateEvent.ex_date.desc().nullslast()).limit(10).all())
    try:
        if _STATUS["value"] is not None:
            status = reported(_STATUS["value"])
            trade_date = _STATUS["trade_date"]
        else:
            status = reported("Warming up", note="Market status refreshes in the background.")
            trade_date = LQ.latest_completed_session().isoformat()
    except Exception:  # noqa: BLE001
        status = source_issue("market status")
        trade_date = LQ.latest_completed_session().isoformat()

    payload = {
        "asof_date": trade_date, "market_status": status,
        "breadth": {"advances": advances, "declines": declines, "unchanged": unchanged,
                    "universe": len(snaps),
                    "advance_decline_ratio": round(advances / max(declines, 1), 2)},
        "mood_line": reported(mood, note="Derived from the advance/decline spread."),
        "india_vix": reported(vix, note="INDIA VIX last close."),
        "vix_regime": reported(vix_regime) if vix_regime else source_issue("VIX regime"),
        "indices_modal": indices,
        "top_gainers": [{"symbol": g["symbol"], "name": g["name"],
                         "last": g["last"], "changepct": g["changepct"],
                         "href": g["href"]} for g in gainers],
        "top_losers": [{"symbol": g["symbol"], "name": g["name"],
                        "last": g["last"], "changepct": g["changepct"],
                        "href": g["href"]} for g in losers],
        "sector_flows": sectors[:12],
        "volume_shockers": volume_shockers,
        "delivery_shockers": delivery_shockers,
        "action_items": [{"symbol": e.symbol, "company": e.company,
                          "purpose": e.purpose,
                          "ex_date": e.ex_date.isoformat() if e.ex_date else None}
                         for e in events],
        "footer_note": reported(
            "Computed locally from EOD free-feed data by the platform's own engine. "
            "Not a buy/sell recommendation."),
    }
    return payload


@router.get("/sector/{sector}")
def sector_detail(sector: str, db: Session = Depends(get_db)):
    rows = _sector_rows(db, sector)
    if not rows:
        raise HTTPException(404, f"No tracked constituents for sector '{sector}'.")
    rows.sort(key=lambda x: x["market_cap"] or 0, reverse=True)
    advances = sum(1 for r in rows if (r["changepct"] or 0) > 0)
    declines = sum(1 for r in rows if (r["changepct"] or 0) < 0)
    return {"sector": sector, "count": len(rows),
            "advances": advances, "declines": declines,
            "avg_change": round(sum((r["changepct"] or 0) for r in rows) / len(rows), 2),
            "constituents": rows}
