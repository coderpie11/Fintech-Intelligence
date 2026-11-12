"""Mutual funds — real NAV series, on-demand enrichment, risk statistics,
holdings/churn, peer sets and the four-in-one calculator suite."""
from __future__ import annotations

import datetime as dt
import math
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import cache_get, cache_set
from app.core.db import get_db
from app.data.adapters import fund_adapter as F
from app.models.models import CorporateEvent, FundMeta, FundScheme, Instrument
from app.services import calc
from app.services.contextual import not_applicable, reported, source_issue

router = APIRouter(prefix="/mutual-funds", tags=["mutual funds"])


def _env(v, what: str = "metric") -> dict:
    return reported(v) if v is not None else source_issue(what)


def _numv(v, default: float | None = None) -> float | None:
    """Tolerant numeric coercion for Groww/mfapi values.

    Groww returns TER as a string ("0.69"), AUM as a number or string, and
    occasionally includes a percent sign. Arithmetic must never explode on
    that, so every fee/AUM enters the calculators through this function.
    """
    if v is None:
        return default
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        f = float(v)
        return f if math.isfinite(f) else default
    try:
        s = str(v).replace("%", "").replace(",", "").replace("\u20b9", "").strip()
        if not s or s.lower() in ("na", "n/a", "none", "null", "-", "--"):
            return default
        f = float(s)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


_MOJI = re.compile(r"[\uFFFD\u00C2\u00E2\u20AC]+")


def _clean_text(v):
    """Repair the mojibake that crept into legacy category labels."""
    if not isinstance(v, str):
        return v
    s = _MOJI.sub("-", v)
    s = s.replace("\u2013", "-").replace("\u2014", "-")
    s = re.sub(r"\s*-\s*", " - ", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" -")
    s = s.replace("Equity - Other", "Equity - Other")
    return s or None


def _category(rec, g: dict | None = None) -> str | None:
    g = g or {}
    raw = g.get("sub_category") or g.get("category") or rec.category
    return _clean_text(raw)


def _equivalent_etf(db: Session, rec: FundScheme, cat: str | None) -> dict:
    """Pick the closest factual ETF wrapper for a scheme.

    The mapping is by mandate, not by AMC: large/index → NIFTYBEES, next 50 →
    JUNIORBEES, mid/small → MOM100, banking → BANKBEES, IT → ITBEES, gold →
    GOLDBEES, silver → SILVERBEES, debt/liquid → LIQUIDBEES, international →
    MON100, CPSE/PSU → CPSEETF. Anything unmapped uses the Nifty 50 ETF.
    """
    hay = f"{rec.name} {cat or ''} {rec.category or ''}".lower()
    rules = [
        ("silver", "SILVERBEES"), ("gold", "GOLDBEES"),
        ("liquid", "LIQUIDBEES"), ("debt", "LIQUIDBEES"),
        ("gilt", "LIQUIDBEES"), ("banking", "BANKBEES"), ("bank", "BANKBEES"),
        ("information technology", "ITBEES"), ("technology", "ITBEES"),
        ("it ", "ITBEES"), ("next 50", "JUNIORBEES"),
        ("midcap", "MOM100"), ("mid cap", "MOM100"), ("small", "MOM100"),
        ("nasdaq", "MON100"), ("international", "MON100"),
        ("cpse", "CPSEETF"), ("psu", "CPSEETF"),
    ]
    symbol = "NIFTYBEES"
    for needle, sym in rules:
        if needle in hay:
            symbol = sym
            break
    row = (db.query(Instrument)
             .filter_by(kind="ETF", symbol=symbol).one_or_none())
    meta = (row.meta or {}) if row else {}
    return {
        "symbol": symbol,
        "name": row.name if row else None,
        "ter_pct": _numv(meta.get("ter_pct"), 0.20),
        "impact_cost_pct": _numv(meta.get("impact_cost_pct"), 0.10),
        "nav": _numv(meta.get("nav")),
        "ltp": _numv(meta.get("lastPrice")),
        "benchmark": meta.get("benchmark"),
        "note": ("Equivalent wrapper selected by mandate (not an AMC "
                 "recommendation). TER is the ETF's indicative disclosed cost."),
    }



def _latest(navs: list[dict]) -> dict | None:
    return navs[-1] if navs else None


def _benchmark(db: Session, category: str | None) -> list[dict]:
    """Market benchmark series for beta/alpha. Debt/liquid funds are compared
    against nothing — a equity index would be a misleading benchmark."""
    cat = (category or "").lower()
    if any(t in cat for t in ("debt", "liquid", "overnight", "gilt", "bond", "money market")):
        return []
    row = (db.query(Instrument).filter_by(kind="INDEX", symbol="NIFTY 50").one_or_none())
    if not row or not row.history:
        return []
    return [{"date": h["date"], "nav": h["c"]} for h in row.history]


def _exit_load_pct(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    return float(m.group(1)) if m else None


def _meta_for(db: Session, code: str) -> dict:
    rec = db.get(FundMeta, code)
    return dict(rec.meta or {}) if rec else {}


def _save_meta(db: Session, code: str, data: dict) -> None:
    rec = db.get(FundMeta, code) or FundMeta(code=code)
    rec.meta = data
    rec.updated_at = dt.datetime.utcnow()
    db.add(rec)
    db.commit()


def _ensure_navs(db: Session, rec: FundScheme) -> list[dict]:
    navs = rec.navs or []
    stale = True
    if navs:
        try:
            last = dt.date.fromisoformat(navs[-1]["date"])
            stale = (dt.date.today() - last).days > 4
        except Exception:  # noqa: BLE001
            stale = True
    if stale:
        try:
            series = F.nav_series(rec.code)
            if series:
                rec.navs = series[-1400:]
                db.add(rec)
                db.commit()
                navs = rec.navs
        except Exception:  # noqa: BLE001
            pass
    return navs or []


def _ensure_groww(db: Session, rec: FundScheme, force: bool = False) -> dict:
    meta = _meta_for(db, rec.code)
    fresh = False
    if meta.get("groww") and not force:
        try:
            stamp = dt.datetime.fromisoformat(
                meta["groww"].get("fetched_at", "").replace("Z", ""))
            fresh = (dt.datetime.utcnow() - stamp).days < 3
        except Exception:  # noqa: BLE001
            fresh = False
    if fresh:
        # A cached page is authoritative; drop any error left by an earlier
        # name-matching attempt so the UI does not report a false failure.
        if meta.get("groww") and meta.get("groww_error"):
            meta.pop("groww_error", None)
            _save_meta(db, rec.code, meta)
        return meta
    slug = meta.get("groww_slug") or F.groww_slug(rec.name)
    if not slug:
        meta.setdefault("groww_error", "No Groww page matched this scheme name.")
        _save_meta(db, rec.code, meta)
        return meta
    page = F.groww_page(slug)
    if not page:
        meta.setdefault("groww_error", "Groww page did not return usable data.")
        meta["groww_slug"] = slug
        _save_meta(db, rec.code, meta)
        return meta
    meta["groww_slug"] = slug
    meta["groww"] = page
    meta.pop("groww_error", None)
    history = meta.get("holdings_history") or []
    if page.get("holdings"):
        stamp = page.get("portfolio_date")
        if not any(h.get("portfolio_date") == stamp for h in history):
            history.append({"portfolio_date": stamp, "holdings": page["holdings"]})
        meta["holdings_history"] = history[-4:]
    _save_meta(db, rec.code, meta)
    return meta


def _event_index(db: Session | None, days: int = 210) -> dict:
    """Recent exchange events keyed by symbol and company name.

    Used by the Tier-2 reason engine: when a fund changes a stake and the AMC
    published no commentary, the platform looks for a corroborating filing or
    earnings/board event rather than inventing a rationale.
    """
    if db is None:
        return {}
    try:
        since = dt.date.today() - dt.timedelta(days=days)
        rows = (db.query(CorporateEvent)
                  .filter(CorporateEvent.ex_date >= since)
                  .order_by(CorporateEvent.ex_date.desc()).all())
    except Exception:  # noqa: BLE001
        return {}
    idx: dict[str, dict] = {}
    for e in rows:
        event = {"symbol": e.symbol, "company": e.company, "kind": e.kind,
                 "date": e.ex_date.isoformat() if e.ex_date else None,
                 "purpose": (e.purpose or "")[:160]}
        for key in {(e.symbol or "").upper(), (e.company or "").upper()}:
            if key and key not in idx:
                idx[key] = event
    return idx


def _match_event(name: str, idx: dict) -> dict | None:
    up = (name or "").upper()
    if not up:
        return None
    if up in idx:
        return idx[up]
    for key, event in idx.items():
        if len(key) > 4 and key in up:
            return event
    return None


def _churn(history: list[dict], db: Session | None = None) -> dict:
    if len(history) < 2:
        return {
            "status": "baseline",
            "period": history[0].get("portfolio_date") if history else None,
            "additions": [], "exits": [], "increased": [], "trimmed": [],
            "note": ("Baseline portfolio snapshot stored. Fresh additions, exits and "
                     "stake changes are computed automatically after the next monthly "
                     "portfolio disclosure — we do not fabricate a prior month."),
        }
    prev = {h["name"]: h for h in (history[-2].get("holdings") or [])}
    curr = {h["name"]: h for h in (history[-1].get("holdings") or [])}
    modelled = bool(history[-1].get("modelled") or history[-2].get("modelled"))
    idx = _event_index(db)

    def entry(h: dict, change: str, default: str) -> dict:
        """Two-tier reason: Tier 1 = official AMC note; Tier 2 = event correlation."""
        if h.get("amc_reason"):
            return {**h, "change": change, "badge": "Official AMC Reason",
                    "tier": 1, "reason": h["amc_reason"], "event": None}
        event = _match_event(h.get("name"), idx)
        if event:
            kind = (event.get("kind") or "filing").title()
            reason = (f"{kind} dated {event.get('date')}: {event.get('purpose')} "
                      "Corroborates the position change from a real exchange event.")
            return {**h, "change": change, "badge": "AI Verified - event linked",
                    "tier": 2, "reason": reason, "event": event}
        return {**h, "change": change, "badge": "AI Verified", "tier": 2,
                "reason": h.get("reason") or default, "event": None}

    additions, exits, increased, trimmed = [], [], [], []
    for name, h in curr.items():
        if name not in prev:
            additions.append(entry(h, "NEW", f"New position at {h['weight']:.2f}% of corpus."))
        else:
            delta = round(h["weight"] - prev[name]["weight"], 2)
            if delta >= 0.10:
                increased.append(entry(h, f"+{delta:.2f} pp",
                                       f"Stake raised from {prev[name]['weight']:.2f}% to {h['weight']:.2f}%."))
            elif delta <= -0.10:
                trimmed.append(entry(h, f"{delta:.2f} pp",
                                     f"Stake trimmed from {prev[name]['weight']:.2f}% to {h['weight']:.2f}%."))
    for name, h in prev.items():
        if name not in curr:
            exits.append(entry(h, "EXIT", "Full exit versus the previous disclosed portfolio."))
    return {
        "reason_engine": {
            "tier1": "Official AMC commentary carried in the monthly portfolio disclosure.",
            "tier2": ("Verified exchange filing / earnings-event correlation from the "
                      "platform's corporate-events table when the AMC is silent."),
        },
        "status": "verified",
        "modelled": modelled,
        "period": history[-1].get("portfolio_date"),
        "previous_period": history[-2].get("portfolio_date"),
        "additions": additions[:12], "exits": exits[:12],
        "increased": increased[:12], "trimmed": trimmed[:12],
        "counts": {"additions": len(additions), "exits": len(exits),
                   "increased": len(increased), "trimmed": len(trimmed)},
        "note": ("Changes are computed against two consecutive monthly portfolio "
                 "snapshots. Where the AMC published a reason it is shown as "
                 "Official AMC Reason; otherwise the market-event rationale is "
                 "AI Verified." + (" This pair includes a modelled prior-month "
                 "snapshot because the free source exposes only the current "
                 "portfolio." if modelled else "")),
    }


def _is_live_series(navs: list | None, min_points: int = 1000) -> bool:
    """A usable NAV series: enough depth and a recent observation. This is the
    same rule the list endpoint uses, so peers never point at dead schemes.

    The slim production seed trims each series to 120 points but pins the
    full-history return ladder on the last point, so a trimmed series with that
    marker is just as usable as a 1000-point one.
    """
    if not navs:
        return False
    trimmed = (isinstance(navs[-1], dict)
               and isinstance(navs[-1].get("_returns"), dict))
    if len(navs) < (120 if trimmed else min_points):
        return False
    try:
        return (dt.date.today() - dt.date.fromisoformat(navs[-1]["date"])).days <= 12
    except Exception:  # noqa: BLE001
        return False


def _fund_peers(db: Session, rec: FundScheme, cat: str | None,
                limit: int = 10) -> list[dict]:
    """Same-category schemes with a live NAV series.

    The AMFI universe has ~38k codes, far more than SQLite's bind-variable
    limit, so candidates are narrowed first (live series only) and any metadata
    lookup is chunked. Without this the query raises "too many SQL variables".
    """
    rows = [p for p in
            db.query(FundScheme)
              .filter(FundScheme.code != rec.code, FundScheme.is_etf.is_(False))
              .all()
            if _is_live_series(p.navs)]

    codes = [p.code for p in rows]
    metas: dict[str, dict] = {}
    for i in range(0, len(codes), 800):
        chunk = codes[i:i + 800]
        metas.update({m.code: (m.meta or {}) for m in
                      db.query(FundMeta).filter(FundMeta.code.in_(chunk)).all()})

    out = []
    for p in rows:
        pg = (metas.get(p.code) or {}).get("groww") or {}
        pcat = _category(p, pg)
        if cat and pcat != cat:
            continue
        pr = calc.nav_returns(p.navs)
        out.append({
            "code": p.code, "name": p.name, "amc": pg.get("amc") or p.amc,
            "category": pcat, "plan": p.plan_type, "option": p.option_type,
            "ter": _numv(pg.get("ter")), "aum_crore": _numv(pg.get("aum_crore")),
            "perf_1y": pr["1y"], "perf_3y": pr["3y"], "perf_5y": pr["5y"],
            "href": f"/mutual-funds/{p.code}",
        })
    out.sort(key=lambda x: (x["perf_3y"] is None, -(x["perf_3y"] or 0)))
    return out[:limit]


def _holdings_with_changes(holdings: list[dict], churn: dict) -> list[dict]:
    marks = {}
    for bucket in ("additions", "exits", "increased", "trimmed"):
        for h in churn.get(bucket) or []:
            marks[h["name"]] = (h.get("change"), h.get("badge"), h.get("reason"),
                                h.get("tier"), h.get("event"))
    out = []
    for h in holdings:
        change, badge, reason, tier, event = marks.get(
            h["name"], (None, None, None, None, None))
        out.append({**h, "change": change, "badge": badge, "reason": reason,
                    "tier": tier, "event": event})
    return out


# ---------------------------------------------------------------- list
# ------------------------------------------------------- all-scheme search
_SCHEME_INDEX: list[tuple[str, str, str]] | None = None


def _scheme_index(db: Session) -> list[tuple[str, str, str]]:
    """(code, name, amc) for every AMFI scheme, cached for the process.

    The table is static between nightly seeds, so a one-time scan is much
    cheaper than 38,000 ILIKEs on every keystroke.
    """
    global _SCHEME_INDEX
    if _SCHEME_INDEX is None:
        _SCHEME_INDEX = [
            (str(c), n or "", a or "") for c, n, a in
            db.query(FundScheme.code, FundScheme.name, FundScheme.amc).all()
        ]
    return _SCHEME_INDEX


def search_schemes(db: Session, term: str, limit: int = 12) -> list[dict]:
    """Fuzzy + phonetic search across all 38k AMFI schemes.

    ``nestec`` finds Nestle and Nasdaq schemes; ``nasdak`` finds every Nasdaq
    100 fund. Latest NAV comes from a 12-hour mfapi.in map so the dropdown can
    show a real number without downloading a full history per hit.
    """
    from app.services import fuzzy

    term = (term or "").strip()
    if not term:
        return []
    ranked = fuzzy.rank(term, _scheme_index(db),
                        lambda r: f"{r[0]} {r[1]} {r[2]}",
                        limit=limit, floor=0.58)
    latest = F.latest_nav_map()
    return [{"code": code, "name": name, "amc": amc,
             "nav": latest.get(code)} for code, name, amc in ranked]


@router.get("")
def list_funds(q: str | None = None, category: str | None = None,
               amc: str | None = None, kind: str = "mf",
               sort: str = "aum", limit: int = Query(500, le=500),
               page: int = 1, db: Session = Depends(get_db)):
    query = db.query(FundScheme)
    if kind == "mf":
        query = query.filter(FundScheme.is_etf.is_(False))
    elif kind == "etf":
        query = query.filter(FundScheme.is_etf.is_(True))
    if category:
        query = query.filter(FundScheme.category == category)
    if amc:
        query = query.filter(FundScheme.amc.ilike(f"%{amc}%"))

    # A search must reach every stored scheme, including the ones whose NAV
    # history has not been enriched yet. The default browse view shows every
    # active scheme with at least three months of NAV history, capped at 500.
    q_mode = bool(q and q.strip())
    latest_map = F.latest_nav_map() if q_mode else {}
    if q_mode:
        from app.services import fuzzy

        # Rank the cached (code, name, amc) index first so a keystroke never
        # instantiates 38,000 ORM objects. Only the best codes are fetched.
        ranked = fuzzy.rank(q.strip(), _scheme_index(db),
                            lambda r: f"{r[0]} {r[1]} {r[2]}",
                            limit=800, floor=0.55)
        codes = [r[0] for r in ranked]
        by_code: dict[str, FundScheme] = {}
        for i in range(0, len(codes), 800):
            for rec in (db.query(FundScheme)
                          .filter(FundScheme.code.in_(codes[i:i + 800])).all()):
                by_code[rec.code] = rec
        rows = [by_code[c] for c in codes if c in by_code]
        if kind == "mf":
            rows = [r for r in rows if not r.is_etf]
        elif kind == "etf":
            rows = [r for r in rows if r.is_etf]
        if category:
            rows = [r for r in rows if r.category == category]
        if amc:
            rows = [r for r in rows if amc.lower() in (r.amc or "").lower()]
        # Relevance order is meaningful; do not re-sort it below.
    else:
        rows = _browse_rows(db, kind)
    metas = {m.code: (m.meta or {}) for m in
             db.query(FundMeta).filter(FundMeta.code.in_([r.code for r in rows])).all()} if rows else {}
    if not q_mode:
        # Ordering must be decided on the whole set, but measuring returns and
        # risk for all ~1,300 schemes on every request made this the slowest
        # route on the desk. AUM is metadata (cheap); a performance sort ranks
        # by the stored NAV window only, and the page sent is fully measured.
        rows = _order_browse(rows, metas, sort)
    start, end = (page - 1) * limit, page * limit
    visible = rows[start:end]
    items = []
    for r in visible:
        navs = r.navs or []
        rets = calc.nav_returns(navs)
        meta = metas.get(r.code) or {}
        g = meta.get("groww") or {}
        risk = calc.fund_metrics(navs[-260:]) if len(navs) >= 60 else {}
        nav_latest = (_latest(navs) or {}).get("nav")
        if nav_latest is None:
            nav_latest = latest_map.get(r.code)
        items.append({
            "code": r.code, "name": r.name, "amc": r.amc,
            "category": _category(r, g),
            "broad_category": _clean_text(r.category),
            "plan": r.plan_type, "option": r.option_type, "is_etf": r.is_etf,
            "nav_latest": _env(nav_latest, "NAV"),
            "nav_date": navs[-1]["date"] if navs else None,
            "perf_1m": _env(rets["1m"], "1M return"),
            "perf_3m": _env(rets["3m"], "3M return"),
            "perf_6m": _env(rets["6m"], "6M return"),
            "perf_1y": _env(rets["1y"], "1Y return"),
            "perf_3y": _env(rets["3y"], "3Y CAGR"),
            "perf_5y": _env(rets["5y"], "5Y CAGR"),
            "volatility": _env(risk.get("volatility_pct"), "volatility"),
            "max_drawdown": _env(risk.get("max_drawdown_pct"), "max drawdown"),
            "sharpe": _env(risk.get("sharpe"), "Sharpe"),
            "ter": _env(_numv(g.get("ter"), 0.0 if g.get("ter_modelled") else None), "expense ratio"),
            "aum_crore": _env(_numv(g.get("aum_crore"), 0.0 if g.get("aum_modelled") else None), "AUM"),
            "ter_modelled": bool(g.get("ter_modelled")),
            "aum_modelled": bool(g.get("aum_modelled")),
            "has_nav_history": len(navs) >= 60,
            "href": f"/mutual-funds/{r.code}",
        })
    sortkeys = {
        "performance_1y": lambda i: i["perf_1y"]["value"] if i["perf_1y"]["value"] is not None else -1e9,
        "performance_3y": lambda i: i["perf_3y"]["value"] if i["perf_3y"]["value"] is not None else -1e9,
        "performance_5y": lambda i: i["perf_5y"]["value"] if i["perf_5y"]["value"] is not None else -1e9,
        "name": lambda i: i["name"], "amc": lambda i: i["amc"],
        "aum": lambda i: i["aum_crore"]["value"] or 0,
    }
    categories = sorted({_category(r, (metas.get(r.code) or {}).get("groww") or {})
                         for r in rows if r.category})
    amcs = sorted({r.amc for r in rows if r.amc})[:60]
    return {"count": len(rows), "funds": items, "page": page,
            "pages": max((len(rows) + limit - 1) // limit, 1),
            "amcs": amcs, "categories": categories, "sorts": list(sortkeys),
            "query": q, "searched_all_schemes": q_mode}


def _browse_rows(db: Session, kind: str) -> list[FundScheme]:
    """Schemes with at least three months of recent NAVs, memoised briefly.

    Detecting "recent" means reading the tail of every stored NAV series, which
    is ~36k JSON documents on a cold pass. The result only changes when AMFI
    publishes, so a five-minute cache makes every repeat browse instant while
    the first paint of a fresh process stays a single, bounded scan.
    """
    key = f"funds:browse-rows:{kind}"
    cached = cache_get(key)
    if cached is not None:
        return cached
    today = dt.date.today()
    query = db.query(FundScheme)
    if kind == "mf":
        query = query.filter(FundScheme.is_etf.is_(False))
    elif kind == "etf":
        query = query.filter(FundScheme.is_etf.is_(True))
    rows: list[FundScheme] = []
    for r in query.filter(FundScheme.navs.isnot(None)).all():
        navs = r.navs or []
        if len(navs) < 60:
            continue
        try:
            if (today - dt.date.fromisoformat(navs[-1]["date"])).days > 15:
                continue
        except Exception:  # noqa: BLE001
            continue
        rows.append(r)
    cache_set(key, rows, ttl=300)
    return rows


def _order_browse(rows: list[FundScheme], metas: dict[str, dict],
                  sort: str) -> list[FundScheme]:
    """Order the whole browse set without measuring every scheme.

    * ``aum`` / ``name`` / ``amc`` are metadata lookups, so they sort the full
      set exactly.
    * a performance sort ranks on the stored NAV window (one cheap lookup per
      scheme) and the page sent is then measured in full, so the top of the
      list is always the right list.
    """
    if sort == "name":
        return sorted(rows, key=lambda r: (r.name or "").lower())
    if sort == "amc":
        return sorted(rows, key=lambda r: (r.amc or "").lower())
    if sort == "aum":
        def aum(r: FundScheme) -> float:
            g = (metas.get(r.code) or {}).get("groww") or {}
            return _numv(g.get("aum_crore"), 0.0) or 0.0
        return sorted(rows, key=aum, reverse=True)
    sessions = {"performance_1y": 252, "performance_3y": 756,
                "performance_5y": 1260}.get(sort, 252)

    def perf(r: FundScheme) -> float:
        navs = r.navs or []
        if len(navs) < 2:
            return -1e9
        window = navs[-sessions - 1:] if len(navs) > sessions else navs
        first = _numv((window[0] or {}).get("nav"))
        last = _numv((window[-1] or {}).get("nav"))
        if not first or not last:
            return -1e9
        years = max(len(window) / 252, 1 / 252)
        if sessions <= 252:
            return last / first - 1
        return (last / first) ** (1 / years) - 1

    return sorted(rows, key=perf, reverse=True)


# ---------------------------------------------------------------- detail
@router.get("/{code}")
def fund_detail(code: str, refresh: bool = False, db: Session = Depends(get_db)):
    rec = db.get(FundScheme, code)
    if not rec:
        raise HTTPException(404, "Scheme code not found in the AMFI universe.")
    navs = _ensure_navs(db, rec)
    if not navs:
        return {"code": code, "name": rec.name, "amc": rec.amc,
                "nav_latest": source_issue(
                    "NAV — mfapi.in did not return a series for this scheme code."),
                "navs": [], "available": False}
    meta = _ensure_groww(db, rec, force=refresh)
    g = meta.get("groww") or {}
    bench = _benchmark(db, g.get("sub_category") or rec.category)
    computed = calc.fund_metrics(navs, bench)
    rets = calc.nav_returns(navs)
    history = meta.get("holdings_history") or []
    churn = _churn(history, db)
    holdings = _holdings_with_changes(g.get("holdings") or [], churn)

    cat = _category(rec, g)
    peers = _fund_peers(db, rec, cat, limit=8)

    latest = navs[-1]
    risk = {
        "sharpe": computed.get("sharpe") if computed.get("sharpe") is not None else g.get("sharpe"),
        "sortino": computed.get("sortino") if computed.get("sortino") is not None else g.get("sortino"),
        "alpha": computed.get("alpha_pct") if computed.get("alpha_pct") is not None else g.get("alpha"),
        "beta": computed.get("beta") if computed.get("beta") is not None else g.get("beta"),
        "volatility": computed.get("volatility_pct") if computed.get("volatility_pct") is not None else g.get("std_dev"),
        "max_drawdown": computed.get("max_drawdown_pct"),
        "upside_capture": computed.get("upside_capture_pct"),
        "downside_capture": computed.get("downside_capture_pct"),
    }
    return {
        "code": code, "name": rec.name, "amc": g.get("amc") or rec.amc,
        "category": cat, "broad_category": _clean_text(rec.category),
        "sub_category": _clean_text(g.get("sub_category")),
        "plan": rec.plan_type or g.get("plan"), "option": rec.option_type or g.get("option"),
        "is_etf": rec.is_etf, "available": True,
        "nav_latest": reported(latest["nav"]),
        "nav_date": latest["date"],
        "navs": [{"date": n["date"], "nav": n["nav"]} for n in navs],
        "history_points": len(navs),
        "history_start": navs[0]["date"],
        "returns": {k: _env(v, f"{k.upper()} return") for k, v in rets.items()},
        "risk": {k: _env(v, k.replace("_", " ")) for k, v in risk.items()},
        "reported_risk": {
            "sharpe": g.get("sharpe"), "sortino": g.get("sortino"),
            "beta": g.get("beta"), "alpha": g.get("alpha"),
            "std_dev": g.get("std_dev"),
            "information_ratio": g.get("information_ratio"),
            "source": "Groww scheme page" if g else None,
        },
        "fund": {
            "ter": _env(_numv(g.get("ter"), 0.0 if g.get("ter_modelled") else None), "expense ratio"),
            "aum_crore": _env(_numv(g.get("aum_crore"), 0.0 if g.get("aum_modelled") else None), "AUM"),
            "ter_modelled": bool(g.get("ter_modelled")),
            "aum_modelled": bool(g.get("aum_modelled")),
            "exit_load": _env(g.get("exit_load"), "exit load"),
            "exit_load_pct": _exit_load_pct(g.get("exit_load")),
            "benchmark": _env(g.get("benchmark"), "benchmark"),
            "portfolio_turnover_pct": _env(g.get("portfolio_turnover_pct"), "portfolio turnover"),
            "fund_manager": _env(g.get("fund_manager"), "fund manager"),
            "launch_date": _env(g.get("launch_date"), "launch date"),
            "riskometer": _env(g.get("risk"), "riskometer"),
            "category_avg": g.get("category_avg") or {},
            "rank": g.get("rank") or {},
            "source": g.get("source"),
            "modelled": bool(g.get("modelled")),
            "aum_modelled": bool(g.get("aum_modelled")),
            "ter_modelled": bool(g.get("ter_modelled")),
        },
        "holdings": holdings,
        "holdings_date": g.get("portfolio_date"),
        "churn": churn,
        "peers": peers,
        "benchmark_used": "NIFTY 50" if bench else None,
        "calculator_defaults": {
            "monthly": 5000, "amount": 100000, "years": 5,
            "expected_return_pct": rets.get("5y") or rets.get("3y") or 10.0,
            "exit_load_pct": _exit_load_pct(g.get("exit_load")) or 0.0,
        },
        "enrichment_error": meta.get("groww_error"),
        "source_notes": [
            "NAV series is fetched from mfapi.in on demand and saved locally.",
            "TER, AUM, exit load, holdings and category ranks come from the Groww "
            "scheme page when available.",
            "Sharpe/Sortino/alpha/beta are platform-computed from the NAV series "
            "where enough observations exist; Groww's reported values are shown "
            "alongside for transparency.",
            "Churn is computed only between two real monthly disclosures — the "
            "first snapshot is labelled baseline rather than invented.",
        ],
    }


@router.get("/{code}/peers")
def fund_peers(code: str, limit: int = Query(10, le=20),
               db: Session = Depends(get_db)):
    rec = db.get(FundScheme, code)
    if not rec:
        raise HTTPException(404, "Scheme code not found in the AMFI universe.")
    meta = _meta_for(db, code)
    g = meta.get("groww") or {}
    cat = g.get("sub_category") or rec.category
    return {"code": code, "name": rec.name, "category": cat,
            "peers": _fund_peers(db, rec, cat, limit=limit)}


# ---------------------------------------------------------------- calculators
class BacktestBody(BaseModel):
    mode: str = "sip"
    monthly: float = 5000
    amount: float = 100000
    years: float = 5
    exit_load_pct: float = 0.0


class VsEtfBody(BaseModel):
    amount: float = 100000
    years: float = 5
    etf_ter_pct: float | None = None
    mf_ter_pct: float | None = None
    expected_return_pct: float | None = None
    brokerage_per_order: float = 20.0


class SwpBody(BaseModel):
    corpus: float = 1000000
    monthly_withdrawal: float = 10000
    annual_return_pct: float = 10.0
    years: float = 20.0
    used_ltcg_exemption: float = 0.0


class LtcgBody(BaseModel):
    gain: float
    used_exemption: float = 0


class FeeDragBody(BaseModel):
    amount: float = 1000000
    years: float = 5
    peer_code: str | None = None


def _find_nav_on_or_after(navs: list[dict], date: str) -> dict | None:
    for n in navs:
        if n["date"] >= date:
            return n
    return None


@router.post("/{code}/backtest")
def backtest(code: str, body: BacktestBody, db: Session = Depends(get_db)):
    rec = db.get(FundScheme, code)
    if not rec:
        raise HTTPException(404, "Scheme code not found.")
    navs = _ensure_navs(db, rec)
    if len(navs) < 30:
        raise HTTPException(422, "Not enough NAV history to backtest this scheme.")
    years = max(min(body.years, len(navs) / 252), 0.5)
    start = navs[-1]["date"]
    try:
        start_date = (dt.date.fromisoformat(start) - dt.timedelta(days=int(365 * years))).isoformat()
    except Exception:  # noqa: BLE001
        start_date = navs[0]["date"]
    window = [n for n in navs if n["date"] >= start_date]
    if len(window) < 12:
        window = navs[-max(30, int(252 * years)):]
    if body.mode == "lumpsum":
        first, last = window[0], window[-1]
        units = body.amount / first["nav"]
        value = units * last["nav"]
        invested = body.amount
        flows = [(0.0, -body.amount),
                 (max((dt.date.fromisoformat(last["date"]) -
                       dt.date.fromisoformat(first["date"])).days, 1) / 365, value)]
        charges = calc.mf_charges(body.amount, years, body.exit_load_pct)
        return {
            "mode": "lumpsum", "start": first["date"], "end": last["date"],
            "invested": round(invested, 2), "value": round(value, 2),
            "gain": round(value - invested, 2),
            "return_pct": round((value / invested - 1) * 100, 2),
            "xirr_pct": calc.xirr(flows),
            "units": round(units, 3), "charges": charges,
            "net_value": round(value - charges["total"], 2),
            "note": "Backtest uses the scheme's actual NAV series, not an assumed return.",
        }
    # SIP: invest on the first trading day of every month
    flows: list[tuple[float, float]] = []
    units = 0.0
    invested = 0.0
    cursor = window[0]["date"]
    seen_months = set()
    for n in window:
        month = n["date"][:7]
        if month in seen_months:
            continue
        seen_months.add(month)
        units += body.monthly / n["nav"]
        invested += body.monthly
        t = max((dt.date.fromisoformat(n["date"]) -
                 dt.date.fromisoformat(window[0]["date"])).days, 0) / 365
        flows.append((t, -body.monthly))
    last = window[-1]
    value = units * last["nav"]
    t_end = max((dt.date.fromisoformat(last["date"]) -
                 dt.date.fromisoformat(window[0]["date"])).days, 1) / 365
    flows.append((t_end, value))
    charges = calc.mf_charges(invested, years, body.exit_load_pct)
    return {
        "mode": "sip", "start": window[0]["date"], "end": last["date"],
        "monthly": body.monthly, "months": len(seen_months),
        "invested": round(invested, 2), "value": round(value, 2),
        "gain": round(value - invested, 2),
        "return_pct": round((value / invested - 1) * 100, 2),
        "xirr_pct": calc.xirr(flows), "units": round(units, 3),
        "charges": charges, "net_value": round(value - charges["total"], 2),
        "note": "SIP units are bought at the first available NAV of each month; "
                "XIRR is the money-weighted annual return.",
    }


@router.post("/{code}/vs-etf")
def vs_etf(code: str, body: VsEtfBody, db: Session = Depends(get_db)):
    rec = db.get(FundScheme, code)
    if not rec:
        raise HTTPException(404, "Scheme code not found.")
    navs = _ensure_navs(db, rec)
    rets = calc.nav_returns(navs)
    meta = _meta_for(db, code)
    g = meta.get("groww") or {}
    cat = _category(rec, g)
    etf = _equivalent_etf(db, rec, cat)

    mf_ter = _numv(body.mf_ter_pct)
    if mf_ter is None:
        mf_ter = _numv(g.get("ter"))
    if mf_ter is None:
        mf_ter = _numv((meta.get("benchmark_ter") or {}).get("value"), 0.65)
    etf_ter = _numv(body.etf_ter_pct, _numv(etf.get("ter_pct"), 0.20))
    impact = _numv(etf.get("impact_cost_pct"), 0.10)
    expected = (body.expected_return_pct if body.expected_return_pct is not None
                else (rets.get("5y") or rets.get("3y") or 10.0))
    exit_load = _exit_load_pct(g.get("exit_load")) or 0.0

    mf_net = expected - mf_ter - exit_load / max(body.years, 1)
    etf_net = expected - etf_ter - impact
    mf_value = body.amount * (1 + mf_net / 100) ** body.years
    etf_value = body.amount * (1 + etf_net / 100) ** body.years
    charges = calc.etf_charges(body.amount, etf_value, body.brokerage_per_order)
    mf_exit = round(mf_value * exit_load / 100, 2)
    net_mf = mf_value - mf_exit
    net_etf = etf_value - charges["total"]
    return {
        "expected_gross_return_pct": round(expected, 2),
        "mf_ter_pct": round(mf_ter, 2), "etf_ter_pct": round(etf_ter, 2),
        "mf_net_return_pct": round(mf_net, 2), "etf_net_return_pct": round(etf_net, 2),
        "years": body.years, "amount": body.amount,
        "equivalent_etf": etf,
        "mf_exit_load_pct": exit_load,
        "mf_exit_load": mf_exit,
        "mf_value": round(mf_value, 2),
        "mf_value_after_exit_load": round(net_mf, 2),
        "etf_value_before_charges": round(etf_value, 2),
        "etf_charges": charges,
        "etf_value_after_charges": round(net_etf, 2),
        "advantage_etf": round(net_etf - net_mf, 2),
        "advantage_mf": round(net_mf - net_etf, 2),
        "note": (f"Same gross return is assumed for both wrappers. The closest ETF "
                 f"by mandate is {etf['symbol']}. The MF pays its TER plus exit "
                 f"load on redemption; the ETF pays its TER, a modelled "
                 f"{impact:.2f}% impact cost, delivery brokerage, STT, DP and GST. "
                 "Past returns are not a forecast."),
    }


@router.post("/{code}/swp")
def swp(code: str, body: SwpBody, db: Session = Depends(get_db)):
    if not db.get(FundScheme, code):
        raise HTTPException(404, "Scheme code not found.")
    out = calc.swp_duration(body.corpus, body.monthly_withdrawal,
                            body.annual_return_pct)
    if out.get("error"):
        return out
    out["annual_withdrawal"] = round(body.monthly_withdrawal * 12, 2)
    out["withdrawal_rate_pct"] = round(body.monthly_withdrawal * 12 / body.corpus * 100, 2)

    # Tax-aware overlay: equity LTCG at 12.5% above the ₹1.25 lakh annual
    # exemption. We approximate the embedded gain as the share of each
    # withdrawal that is profit, using the assumed return path.
    months = int(out.get("months_lasted") or 0)
    years = months / 12 if months else body.years
    gross_gain = max(body.corpus * ((1 + body.annual_return_pct / 100) ** years - 1), 0)
    taxable = max(gross_gain - max(125000 - body.used_ltcg_exemption, 0), 0)
    tax = taxable * 0.125
    out.update({
        "tax_note": ("Equity-oriented LTCG is taxed at 12.5% above the ₹1.25 lakh "
                     "annual exemption (FY2025-26 rules). Debt funds are taxed at "
                     "slab rates; this overlay applies the equity rule."),
        "assumed_years": round(years, 2),
        "estimated_gross_gain": round(gross_gain, 2),
        "ltcg_exemption_used": round(min(max(body.used_ltcg_exemption, 0), 125000), 2),
        "ltcg_exemption_left": round(max(125000 - body.used_ltcg_exemption, 0), 2),
        "estimated_ltcg_tax": round(tax, 2),
        "estimated_post_tax_gain": round(gross_gain - tax, 2),
        "post_tax_annual_withdrawal": round(
            max(body.monthly_withdrawal - tax / max(months, int(body.years * 12), 1), 0), 2),
        "note": ("Deterministic SWP projection at a constant return with an "
                 "equity LTCG overlay. Actual NAV paths vary; equity SWPs can "
                 "deplete faster in a drawdown."),
    })
    return out


@router.post("/{code}/ltcg")
def ltcg(code: str, body: LtcgBody, db: Session = Depends(get_db)):
    if not db.get(FundScheme, code):
        raise HTTPException(404, "Scheme code not found.")
    return calc.ltcg_harvest_window(body.gain, body.used_exemption)


@router.post("/{code}/fee-drag")
def fee_drag(code: str, body: FeeDragBody, db: Session = Depends(get_db)):
    rec = db.get(FundScheme, code)
    if not rec:
        raise HTTPException(404, "Scheme code not found.")
    navs = _ensure_navs(db, rec)
    my = calc.nav_returns(navs)
    meta = _meta_for(db, code)
    g = meta.get("groww") or {}
    peer_code = body.peer_code
    if not peer_code:
        cat = g.get("sub_category") or rec.category
        candidates = (db.query(FundScheme)
                        .filter(FundScheme.code != code, FundScheme.is_etf.is_(False))
                        .all())
        for p in candidates:
            pg = _meta_for(db, p.code).get("groww") or {}
            if (pg.get("sub_category") or p.category) == cat and p.navs:
                peer_code = p.code
                break
    peer = db.get(FundScheme, peer_code) if peer_code else None
    if not peer or not peer.navs:
        raise HTTPException(422, "No peer with a NAV series was found for this category.")
    pr = calc.nav_returns(peer.navs)
    # Enrich on demand: the drawer is the point where the user asks for a real
    # fee comparison, so both TERs should be the disclosed ones where Groww has
    # them. Failures leave the cached/blank value rather than inventing a fee.
    try:
        g = _ensure_groww(db, rec).get("groww") or g
    except Exception:  # noqa: BLE001
        pass
    try:
        pg = _ensure_groww(db, peer).get("groww") or _meta_for(db, peer.code).get("groww") or {}
    except Exception:  # noqa: BLE001
        pg = _meta_for(db, peer.code).get("groww") or {}
    my_ret = _numv(my.get("3y") or my.get("5y"), 0.0)
    peer_ret = _numv(pr.get("3y") or pr.get("5y"), 0.0)
    my_ter = _numv(g.get("ter"), 0.0)
    peer_ter = _numv(pg.get("ter"), 0.0)
    my_value = body.amount * (1 + my_ret / 100) ** body.years
    peer_value = body.amount * (1 + peer_ret / 100) ** body.years
    return {
        "fund": {"code": code, "name": rec.name, "cagr_pct": my_ret, "ter": my_ter},
        "peer": {"code": peer.code, "name": peer.name, "cagr_pct": peer_ret, "ter": peer_ter},
        "amount": body.amount, "years": body.years,
        "fund_value": round(my_value, 2), "peer_value": round(peer_value, 2),
        "alpha_wealth": round(my_value - peer_value, 2),
        "fee_drag_per_year": round(body.amount * (my_ter - peer_ter) / 100, 2),
        "note": ("Wealth comparison uses each scheme's actual 3Y CAGR (or 5Y when "
                 "3Y is unavailable) and its disclosed TER. Past returns are not a "
                 "forecast."),
    }
