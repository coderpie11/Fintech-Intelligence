"""System endpoints: health, market status, global search, source registry,
and the module refresh trigger."""
import threading

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import FREE_SOURCE_NOTE, cache_get
from app.core.db import get_db, SessionLocal
from app.models.models import Instrument, SeedState
from app.data.adapters import nse_adapter as N
from app.data.adapters import fund_adapter as F
from app.data.registry import REGISTRY
from app.seed import seed as SEED
from app.services.contextual import source_issue, reported

router = APIRouter(tags=["system"])

# One full seed at a time. The work runs in a daemon thread because seeding every
# stage takes minutes -- far longer than a PaaS request timeout (Render closes
# idle HTTP requests long before that), so the POST must return immediately.
_ALL_RUN = {"running": False}


@router.get("/health")
def health():
    return {"status": "ok", "service": "Fintech Intelligence API", "version": "1.0.0"}


@router.get("/search")
def search(q: str, limit: int = 12, db: Session = Depends(get_db)):
    """Groww-style global instant search.

    Returns one flat, categorised list (stocks, funds, ETFs, indices, IPOs,
    academy lessons) with live prices or NAVs where available. Unknown Indian
    companies are resolved through Yahoo's Indian-listing search and created on
    demand, so every listed NSE/BSE name is reachable even before a seed.
    """
    from app.models.models import Ipo
    from app.routes import academy as A
    from app.routes import funds as FUNDS
    from app.services import fuzzy
    from app.services import stock_loader

    q = (q or "").strip()
    if not q:
        return {"query": q, "results": [], "count": 0}

    results: list[dict] = []

    # ---------------------------------------------------------- instruments
    # Substring first (symbol/name), then fuzzy over the whole table. 2,500
    # discovery rows make a full scan cheap and catch "Orient" / "Paras".
    all_rows = db.query(Instrument).all()
    ranked = fuzzy.rank(q, all_rows,
                        lambda r: f"{r.symbol} {r.name} {r.sector or ''}",
                        limit=limit + 8, floor=0.68)
    seen = {r.id for r in ranked}

    # A ticker that is not in the NSE master yet: ask Yahoo and create it. Only
    # for reasonably specific queries so typing "pa" does not create junk rows.
    if len(q) >= 4:
        try:
            created = stock_loader.ensure_from_yahoo(db, q, with_history=False)
            if created is not None and created.id not in seen:
                ranked.insert(0, created)
                seen.add(created.id)
        except Exception:  # noqa: BLE001
            pass

    for r in ranked[:limit]:
        m = r.meta or {}
        price = m.get("lastPrice")
        results.append({
            "kind": r.kind, "symbol": r.symbol, "name": r.name,
            "label": r.symbol, "sublabel": r.name, "sector": r.sector,
            "exchange": r.exchange,
            "changepct": m.get("changepct"),
            "price": price if isinstance(price, (int, float)) else None,
            "unit": "₹" if r.kind in ("EQUITY", "ETF", "REIT", "INVIT") else None,
            "href": stock_href(r),
        })

    # ------------------------------------------------------------ mutual funds
    for m in FUNDS.search_schemes(db, q, limit=10):
        results.append({
            "kind": "FUND", "symbol": m["code"], "name": m["name"],
            "label": m["name"][:70], "sublabel": f"{m['amc'] or 'Mutual fund'} · {m['code']}",
            "sector": None, "changepct": None, "price": m.get("nav"),
            "unit": "₹", "nav": m.get("nav"),
            "href": f"/mutual-funds/{m['code']}",
        })

    # -------------------------------------------------------------------- IPOs
    try:
        from app.routes.ipos import slugify

        ipo_rows = (db.query(Ipo)
                      .filter(or_(Ipo.name.ilike(f"%{q}%"),
                                  Ipo.symbol.ilike(f"%{q}%")))
                      .limit(6).all())
        if len(ipo_rows) < 4:
            # Fuzzy fall back across the whole IPO master (live + archive).
            extra = fuzzy.rank(q, db.query(Ipo).all(),
                               lambda r: f"{r.name} {r.symbol or ''} {r.board}",
                               limit=6, floor=0.72)
            seen_ipo = {r.id for r in ipo_rows}
            ipo_rows += [r for r in extra if r.id not in seen_ipo]
        for i in ipo_rows[:5]:
            slug = slugify(i.name)
            m = i.meta or {}
            gmp = m.get("gmp")
            results.append({
                "kind": "IPO", "symbol": i.symbol or "", "name": i.name,
                "label": i.name[:70],
                "sublabel": (f"IPO · {i.board.title()} · {i.status.title()}"
                             + (f" · GMP ₹{gmp:g}" if isinstance(gmp, (int, float)) else "")),
                "sector": None, "changepct": None,
                "price": m.get("listed_price") if i.status == "LISTED" else None,
                "unit": "₹" if i.status == "LISTED" else None,
                "href": f"/ipos/{slug}",
            })
    except Exception:  # noqa: BLE001
        pass

    # --------------------------------------------------------------- academy
    try:
        for lesson_ in A.search_lessons(q)["lessons"][:4]:
            results.append({
                "kind": "ACADEMY", "symbol": lesson_["id"], "name": lesson_["title"],
                "label": lesson_["title"][:70],
                "sublabel": f"Academy · {lesson_['track_title']}",
                "sector": None, "changepct": None, "price": None, "unit": None,
                "href": lesson_["href"],
            })
    except Exception:  # noqa: BLE001
        pass

    return {"query": q, "results": results, "count": len(results)}


# ---------------------------------------------------------------- preload -----
# The navbar pulls this once per browser session and filters it client-side.
# Build it in RAM and reuse for five minutes so the endpoint answers in <5 ms.
_PRELOAD_CACHE: dict = {"at": 0.0, "payload": None}


def _build_preload(db: Session) -> dict:
    import math
    import time as _t

    from app.models.models import FundScheme, Ipo
    from app.routes import academy as A
    from app.routes.ipos import slugify

    def _num(v):
        """Stored snapshots occasionally hold NaN/Infinity, which JSON cannot
        serialise. Normalise every numeric field to a finite float or None."""
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return f if math.isfinite(f) else None

    items: list[dict] = []

    # ---------------------------------------------------------- instruments
    for r in (db.query(Instrument)
                .filter(Instrument.kind.in_(
                    ("EQUITY", "INDEX", "ETF", "REIT", "INVIT", "COMMODITY")))
                .all()):
        m = r.meta or {}
        price = m.get("lastPrice")
        items.append({
            "kind": r.kind,
            "symbol": r.symbol,
            "name": r.name,
            "label": r.symbol,
            "sublabel": r.name,
            "sector": r.sector,
            "exchange": r.exchange,
            "changepct": _num(m.get("changepct")),
            "price": _num(price),
            "unit": "₹" if r.kind in ("EQUITY", "ETF", "REIT", "INVIT") else None,
            "href": stock_href(r),
            "aliases": " ".join(x for x in (r.industry, r.macro) if x),
        })

    # ----------------------------------------------------------------- IPOs
    try:
        for i in db.query(Ipo).all():
            m = i.meta or {}
            gmp = _num(m.get("gmp"))
            items.append({
                "kind": "IPO",
                "symbol": i.symbol or "",
                "name": i.name,
                "label": i.name[:80],
                "sublabel": (f"IPO · {i.board.title()} · {i.status.title()}"
                             + (f" · GMP ₹{gmp:g}" if isinstance(gmp, (int, float)) else "")),
                "sector": None,
                "changepct": None,
                "price": _num(m.get("listed_price")) if i.status == "LISTED" else None,
                "unit": "₹" if i.status == "LISTED" else None,
                "href": f"/ipos/{slugify(i.name)}",
                "aliases": f"{i.board} {i.status} ipo",
            })
    except Exception:  # noqa: BLE001
        pass

    # ----------------------------------------------------------- mutual funds
    # Always include the category representatives (silver, gold, Nasdaq/US,
    # index, ELSS, debt) first, then fill up to 500 direct-growth plans so the
    # dropdown covers the long tail and the category tabs stay populated.
    try:
        navmap = cache_get("mfapi:latestmap") or {}
        picked: dict[str, FundScheme] = {}
        for term in ("silver", "gold", "nasdaq", "s&p 500", "nifty", "sensex",
                     "index", "us equity", "international", "elss", "tax saver",
                     "large cap", "mid cap", "small cap", "flexi cap",
                     "hybrid", "balanced", "debt", "liquid", "gilt"):
            for f in (db.query(FundScheme)
                        .filter(FundScheme.name.ilike(f"%{term}%"))
                        .limit(40).all()):
                picked.setdefault(str(f.code), f)
        for f in (db.query(FundScheme)
                    .filter(FundScheme.plan_type == "Direct",
                            FundScheme.option_type == "Growth")
                    .order_by(FundScheme.name).limit(500).all()):
            if len(picked) >= 500:
                break
            picked.setdefault(str(f.code), f)
        for f in list(picked.values())[:500]:
            nav = _num(navmap.get(str(f.code)))
            items.append({
                "kind": "FUND",
                "symbol": str(f.code),
                "name": f.name,
                "label": f.name[:90],
                "sublabel": f"{f.amc} · {f.category or 'Mutual fund'}",
                "sector": f.category,
                "changepct": None,
                "price": nav,
                "nav": nav,
                "unit": "₹",
                "href": f"/mutual-funds/{f.code}",
                "aliases": f"{f.amc} {f.category or ''} {f.plan_type or ''}",
            })
    except Exception:  # noqa: BLE001
        pass

    # --------------------------------------------------------------- academy
    try:
        alias_by_id: dict[str, list[str]] = {}
        for alias, lesson_id in A.ALIASES.items():
            alias_by_id.setdefault(lesson_id, []).append(alias)
        for tid, track, item in A._all_lessons():
            items.append({
                "kind": "ACADEMY",
                "symbol": item["id"],
                "name": item["title"],
                "label": item["title"][:80],
                "sublabel": f"Academy · {track['title']}",
                "sector": None,
                "changepct": None,
                "price": None,
                "unit": None,
                "href": f"/learn/{tid}?topic={item['id']}",
                "aliases": " ".join(alias_by_id.get(item["id"], [])),
            })
    except Exception:  # noqa: BLE001
        pass

    return {
        "count": len(items),
        "built_at": _t.strftime("%Y-%m-%dT%H:%M:%S"),
        "items": items,
    }


@router.get("/search/preload")
def search_preload(db: Session = Depends(get_db)):
    """Compact client-side search index: equities, indices, IPOs, ETFs, funds,
    academy topics. Cached in process RAM for five minutes."""
    import time as _t

    now = _t.time()
    cached = _PRELOAD_CACHE.get("payload")
    if cached is not None and now - float(_PRELOAD_CACHE.get("at") or 0) < 300:
        return cached
    payload = _build_preload(db)
    _PRELOAD_CACHE["at"] = now
    _PRELOAD_CACHE["payload"] = payload
    return payload


def stock_href(r: Instrument) -> str:
    from app.seed.universe import INDICES
    if r.kind == "INDEX":
        slug = next((s["slug"] for s in INDICES if s["nse"] == r.symbol),
                    r.symbol.lower().replace(" ", "-"))
        return f"/indices/{slug}"
    if r.kind == "ETF":
        return f"/etfs/{r.symbol}"
    if r.kind in ("REIT", "INVIT"):
        return f"/reits/{r.symbol}"
    if r.kind == "COMMODITY":
        return "/gold-silver"
    return f"/stocks/{r.symbol}"


class MarketStatusOut(BaseModel):
    headline: str
    asof: str


@router.get("/market/status")
def market_status():
    try:
        raw = N.nse.market_status()
        cm = next((m for m in raw.get("marketState", [])
                   if m.get("market") == "Capital Market"), {})
        mid = (cm or {}).get("marketStatus", "Unknown")
        return {"status": reported(mid, note="NSE exchange status of the Capital Market."),
                "raw": raw.get("marketState", [])[:3], "note": FREE_SOURCE_NOTE}
    except Exception:
        return {"status": source_issue("market status"), "raw": [], "note": FREE_SOURCE_NOTE}


@router.get("/meta/counts")
def counts(db: Session = Depends(get_db)):
    """Live row counts for the home desk cards. Every number is a real DB
    count — no hard-coded marketing figures."""
    from app.models.models import Bond, CorporateEvent, FundScheme, Ipo, SandboxOrder
    q = lambda model: db.query(model).count()
    idx = db.query(Instrument).filter(Instrument.kind == "INDEX").all()
    constituents = sum(len((r.meta or {}).get("constituents") or []) for r in idx)
    return {
        "indices": len(idx),
        "constituents": constituents,
        "equities": db.query(Instrument).filter(Instrument.kind == "EQUITY").count(),
        "funds": q(FundScheme),
        "etfs": db.query(FundScheme).filter(FundScheme.is_etf.is_(True)).count(),
        "bonds": q(Bond),
        "events": q(CorporateEvent),
        "ipos": q(Ipo),
        "reits": db.query(Instrument).filter(Instrument.kind.in_(("REIT", "INVIT"))).count(),
        "commodities": db.query(Instrument).filter(Instrument.kind == "COMMODITY").count(),
        "sandbox_orders": q(SandboxOrder),
        "asof": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    }


@router.get("/sources")
def sources():
    return {"note": FREE_SOURCE_NOTE,
            "adapters": {k: {"name": v.name, "swappable_to": v.swappable_to,
                             "kind": v.kind.value} for k, v in REGISTRY.items()}}


@router.post("/refresh/{stage}")
def refresh(stage: str, db: Session = Depends(get_db)):
    if stage == "all":
        if _ALL_RUN["running"]:
            return {"stage": "all", "status": "already_running",
                    "message": "A full seed is already in progress; poll "
                               "/api/v1/seed/state."}
        _ALL_RUN["running"] = True

        def _bg_all() -> None:
            try:
                SEED.run_all()
                bg = SessionLocal()
                try:
                    SEED.state_set(
                        bg, "stage:all:done",
                        __import__("datetime").datetime.utcnow().isoformat())
                    bg.commit()
                finally:
                    bg.close()
            except Exception as e:  # noqa: BLE001
                print(f"[refresh] all failed: {type(e).__name__} {e}")
            finally:
                _ALL_RUN["running"] = False

        threading.Thread(target=_bg_all, daemon=True).start()
        return {"stage": "all", "status": "started",
                "message": "Seeding every stage in a background thread; poll "
                           "/api/v1/seed/state for stage:*:done keys."}
    valid = [k for k, _ in SEED.STAGES]
    if stage not in valid:
        raise HTTPException(404, f"Unknown stage. Valid: {', '.join(valid)}")
    if stage in ("funds", "etfs", "equity_fundamentals"):
        def _bg(key: str) -> None:
            bg = SessionLocal()
            try:
                fn = dict(SEED.STAGES)[key]
                fn(bg)
                SEED.state_set(bg, f"stage:{key}:done",
                               __import__("datetime").datetime.utcnow().isoformat())
                bg.commit()
            except Exception as e:  # noqa: BLE001
                bg.rollback()
                print(f"[refresh] {key} failed: {type(e).__name__} {e}")
            finally:
                bg.close()

        threading.Thread(target=_bg, args=(stage,), daemon=True).start()
        return {"stage": stage, "status": "started",
                "message": f"'{stage}' is running in a background thread; the API "
                           f"stays responsive. Poll /api/v1/seed/state for completion."}
    fn = dict(SEED.STAGES)[stage]
    try:
        result = fn(db)
        SEED.state_set(db, f"stage:{stage}:done", __import__("datetime").datetime.utcnow().isoformat())
        db.commit()
        return {"stage": stage, "result": result}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        raise HTTPException(502, f"Refresh of '{stage}' failed: {type(e).__name__}") from e


@router.get("/seed/state")
def seed_state(db: Session = Depends(get_db)):
    rows = db.query(SeedState).all()
    return {r.key: {"value": r.value, "at": r.updated_at.isoformat() if r.updated_at else None}
            for r in rows}

