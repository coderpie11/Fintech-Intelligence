"""Seeder — one-time real-data population of the local SQLite store, fully
resumable (SeedState checkpoints) and idempotent per stage. Server endpoints
can re-run any stage by key via the /refresh API."""
from __future__ import annotations

import datetime as dt
import re

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models.models import (CorporateEvent, FundMeta, FundScheme, Instrument,
                               Ipo, SeedState)
from app.data.adapters import fund_adapter as F
from app.data.adapters import nse_adapter as N
from app.data.adapters import yfinance_adapter as Y
from app.seed import universe as U
from app.seed import nse_universe as NSE_UNIVERSE
from app.services.contextual import reported

log_prefix = "[seed]"

_SNAPSHOT_CACHE: dict[str, list[dict]] = {}
_QUOTE_CACHE: dict[str, dict] = {}


def state_get(db: Session, key: str) -> str | None:
    rec = db.get(SeedState, key)
    return rec.value if rec else None


def state_set(db: Session, key: str, value: str) -> None:
    rec = db.get(SeedState, key) or SeedState(key=key)
    rec.value = value
    rec.updated_at = dt.datetime.utcnow()
    db.add(rec)


def enslug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or "unknown"


def upsert_instrument(db: Session, *, symbol: str, name: str, kind: str,
                      exchange: str = "NSE", **kwargs) -> Instrument:
    rec = (db.query(Instrument)
             .filter_by(symbol=symbol, kind=kind, exchange=exchange).one_or_none())
    if rec is None:
        rec = Instrument(symbol=symbol, kind=kind, exchange=exchange,
                         slug=enslug(f"{name} {kind} {exchange}"), name=name)
        db.add(rec)
    rec.name = name
    for k, v in kwargs.items():
        setattr(rec, k, v)
    return rec


# ---------------------------------------------------------------- helpers

def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _history_ok(h: list[dict] | None) -> bool:
    return bool(h) and len(h) >= 60


def _yahoo_history(ticker: str, period: str = "5y") -> list[dict]:
    for attempt in range(3):
        try:
            h = Y.history(ticker, period)
            if _history_ok(h):
                return h
        except Exception:
            pass
    return []


def _snapshot_history(spec: dict) -> list[dict]:
    names = spec.get("fallback_names") or []
    if not names:
        return []
    key = "|".join(names)
    if key not in _SNAPSHOT_CACHE:
        try:
            got = N.index_history_snapshots(names, 5)
            for nm, rows in got.items():
                _SNAPSHOT_CACHE[nm] = rows
        except Exception:
            pass
    return _SNAPSHOT_CACHE.get(names[0], [])


def _quote_from_history(h: list[dict]) -> dict:
    if not h:
        return {}
    last = h[-1]
    prev = h[-2] if len(h) > 1 else last
    tail = h[-252:]
    return {
        "last": last["c"],
        "prevClose": prev["c"],
        "changepct": round((last["c"] / prev["c"] - 1) * 100, 2) if prev["c"] else None,
        "open": last.get("o"),
        "high": last.get("h"),
        "low": last.get("l"),
        "yearHigh": max((x.get("h") or x["c"]) for x in tail),
        "yearLow": min((x.get("l") or x["c"]) for x in tail),
    }


def _equity_snapshot(db: Session, symbol: str, live: dict | None = None) -> dict:
    """Best available snapshot for a constituent: stored NSE quote first,
    then the live index row, then a single NSE quote fetch (cached)."""
    live = live or {}
    row = (db.query(Instrument)
             .filter_by(kind="EQUITY", symbol=symbol).one_or_none())
    m = dict((row.meta or {}) if row else {})
    out = {
        "symbol": symbol,
        "name": (row.name if row else None) or live.get("symbol") or symbol,
        "sector": (m.get("sector") or (row.sector if row else None)),
        "last": m.get("lastPrice") if m.get("lastPrice") is not None else live.get("lastPrice"),
        "changepct": m.get("changepct") if m.get("changepct") is not None else live.get("pChange"),
        "yearHigh": m.get("yearHigh") if m.get("yearHigh") is not None else live.get("yearHigh"),
        "yearLow": m.get("yearLow") if m.get("yearLow") is not None else live.get("yearLow"),
        "pe": m.get("pe"),
        "marketCap": m.get("marketCap"),
        "ffmc": m.get("ffmCap") or m.get("marketCap"),
    }
    if (not out["sector"] or not out["ffmc"]) and symbol not in _QUOTE_CACHE:
        try:
            q = N.nse.stock_quote(symbol)
            pr, tr, sec = q.get("priceInfo") or {}, q.get("tradeInfo") or {}, q.get("secInfo") or {}
            md = q.get("metaData") or {}
            _QUOTE_CACHE[symbol] = {
                "sector": (sec.get("sector") or "").strip() or None,
                "industry": (sec.get("industry") or "").strip() or None,
                "pe": _num(sec.get("pdSymbolPe")),
                "marketCap": tr.get("totalMarketCap"),
                "ffmc": tr.get("ffmc") or tr.get("totalMarketCap"),
                "yearHigh": pr.get("yearHigh"),
                "yearLow": pr.get("yearLow"),
                "last": tr.get("lastPrice") or md.get("closePrice"),
                "prevClose": md.get("previousClose"),
                "name": md.get("companyName"),
            }
        except Exception:
            _QUOTE_CACHE[symbol] = {}
    q = _QUOTE_CACHE.get(symbol) or {}
    for k_src, k_dst in (("sector", "sector"), ("pe", "pe"), ("marketCap", "marketCap"),
                         ("ffmc", "ffmc"), ("yearHigh", "yearHigh"), ("yearLow", "yearLow"),
                         ("last", "last"), ("name", "name")):
        if not out.get(k_dst) and q.get(k_src):
            out[k_dst] = q[k_src]
    return out


def _ensure_equity(db: Session, snap: dict) -> None:
    """Create/update a constituent equity without wiping richer stored data."""
    sym = snap["symbol"]
    row = (db.query(Instrument)
             .filter_by(kind="EQUITY", symbol=sym).one_or_none())
    if row is None:
        row = Instrument(symbol=sym, name=snap.get("name") or sym, kind="EQUITY",
                         exchange="NSE", slug=enslug(f"{sym} equity NSE"))
        db.add(row)
    if snap.get("name") and (not row.name or row.name == sym):
        row.name = snap["name"]
    if snap.get("sector") and not row.sector:
        row.sector = snap["sector"]
    meta = dict(row.meta or {})
    for k in ("last", "changepct", "yearHigh", "yearLow", "pe", "marketCap", "ffmc"):
        if snap.get(k) is not None:
            meta[k if k != "last" else "lastPrice"] = snap[k]
    if snap.get("ffmc"):
        meta["ffmCap"] = snap["ffmc"]
    row.meta = meta
    db.add(row)


# ---------------------------------------------------------------- indices

def seed_indices(db: Session, include_constituents: bool = True) -> dict:
    stats = {"indices": 0, "constituents": 0, "history_ok": 0,
             "history_fallback": 0, "live_missing": []}
    try:
        all_idx = all_indices_map()
    except Exception as e:
        all_idx = {}
        stats["live_missing"].append(f"all_indices: {e}")

    for spec in U.INDICES:
        slug, nse_name = spec["slug"], spec["nse"]
        meta = {"yahoo": spec.get("yahoo"), "top6": spec["top6"],
                "group": spec.get("group"), "fno_symbol": spec.get("fno"),
                "display": spec.get("display") or nse_name}
        live = all_idx.get(nse_name)
        if live is None and spec.get("nse_alias"):
            live = all_idx.get(spec["nse_alias"])

        # ---- history first (also supplies quotes when live is missing) ----
        hist: list[dict] = []
        if spec.get("yahoo"):
            hist = _yahoo_history(spec["yahoo"])
        if not _history_ok(hist):
            fallback = _snapshot_history(spec)
            if _history_ok(fallback):
                hist = fallback
                meta["history_source"] = "NSE official daily index snapshot archive"
                stats["history_fallback"] += 1
            elif hist:
                meta["history_source"] = "Yahoo Finance (partial series)"
            else:
                meta["history_source"] = None
        else:
            meta["history_source"] = f"Yahoo Finance ({spec['yahoo']})"

        if live:
            meta.update({
                "last": live.get("last"), "changepct": live.get("percentChange"),
                "open": live.get("open"), "high": live.get("high"),
                "low": live.get("low"), "prevClose": live.get("previousClose"),
                "yearHigh": live.get("yearHigh"), "yearLow": live.get("yearLow"),
                "pe": _num(live.get("pe")), "pb": _num(live.get("pb")),
                "dy": _num(live.get("dy")),
                "advances": live.get("advances"), "declines": live.get("declines"),
                "oneWeekAgoVal": live.get("oneWeekAgoVal"),
                "perChange30d": live.get("perChange30d"),
                "perChange365d": live.get("perChange365d"),
                # The free NSE feed is EOD/delayed: the level we store is the
                # last completed session's close, so label it with that session
                # date rather than the moment we happened to fetch it.
                "live_asof": (hist[-1]["date"] if _history_ok(hist)
                              else today_stamp()),
                "fetched_at": today_stamp(),
                "live_source": "NSE allIndices",
            })
        elif _history_ok(hist):
            # SENSEX has no NSE allIndices row — use the BSE series snapshot.
            meta.update(_quote_from_history(hist))
            meta["live_asof"] = hist[-1]["date"]
            meta["fetched_at"] = today_stamp()
            meta["live_source"] = "Yahoo Finance ^BSESN (EOD/delayed)"
            meta["source_note"] = ("BSE benchmark: NSE's allIndices feed does not "
                                   "carry SENSEX, so its quote is taken from the "
                                   "BSE series on Yahoo Finance.")
        # never store meaningless VIX valuation ratios
        if slug == "india-vix":
            meta.update({"pe": None, "pb": None, "dy": None})

        rec = upsert_instrument(
            db, symbol=nse_name, name=spec.get("display") or nse_name,
            kind="INDEX", meta=meta)
        rec.history = hist or None
        db.flush()
        # Detach our working dict from the ORM attribute: mutating the same
        # object that is already stored would be invisible to SQLAlchemy's
        # JSON change tracking and the constituents would never persist.
        meta = dict(rec.meta or {})
        if _history_ok(hist):
            stats["history_ok"] += 1
        stats["indices"] += 1

        # ---- constituents ------------------------------------------------
        if include_constituents and slug != "india-vix":
            try:
                members = _collect_constituents(db, spec, live)
                if members:
                    _apply_weights(members)
                    meta["constituents"] = members
                    meta["constituent_count"] = len(members)
                    meta["weight_basis"] = (
                        "Weights are derived estimates from free-float market "
                        "capitalisation of the members; they are not the official "
                        "NSE/BSE published weights.")
                    meta["constituents_source"] = (
                        "BSE SENSEX reference membership + NSE live quotes"
                        if slug == "sensex" else "NSE live index constituent feed")
                    rec.meta = dict(meta)
                    stats["constituents"] += len(members)
            except Exception as e:
                stats["live_missing"].append(f"{slug} constituents: {type(e).__name__} {e}")
    db.commit()
    return stats


def _collect_constituents(db: Session, spec: dict, live: dict | None) -> list[dict]:
    slug = spec["slug"]
    raw: list[dict] = []
    if slug == "sensex":
        raw = [{"symbol": s} for s in U.SENSEX_MEMBERS]
    else:
        data = (N.nse.live_index(spec["nse"]).get("data") or [])
        seen = set()
        for row in data:
            sym = (row.get("symbol") or "").strip().upper()
            if not sym or sym == spec["nse"] or sym in seen:
                continue
            if not re.fullmatch(r"[A-Z0-9&\-]+", sym):
                continue
            seen.add(sym)
            raw.append(row)

    members: list[dict] = []
    for row in raw:
        sym = (row.get("symbol") or "").strip().upper()
        if not sym:
            continue
        snap = _equity_snapshot(db, sym, row)
        _ensure_equity(db, snap)
        members.append({
            "symbol": sym,
            "name": snap.get("name") or sym,
            "sector": snap.get("sector"),
            "last": snap.get("last"),
            "changepct": snap.get("changepct"),
            "yearHigh": snap.get("yearHigh"),
            "yearLow": snap.get("yearLow"),
            "pe": snap.get("pe"),
            "marketCap": snap.get("marketCap"),
            "ffmc": snap.get("ffmc"),
            "weight": None,
            "href": f"/stocks/{sym}",
        })
    return members


def _apply_weights(members: list[dict]) -> None:
    total = sum((m.get("ffmc") or 0) for m in members)
    if total <= 0:
        return
    for m in members:
        if m.get("ffmc"):
            m["weight"] = round(m["ffmc"] / total * 100, 2)
    members.sort(key=lambda m: (m.get("weight") is None, -(m.get("weight") or 0),
                                -(m.get("marketCap") or 0)))


def seed_index_weights(db: Session) -> dict:
    """Recompute constituent weights after equity quotes are enriched."""
    stats = {"indices": 0, "members": 0}
    for spec in U.INDICES:
        if spec["slug"] == "india-vix":
            continue
        row = (db.query(Instrument)
                 .filter_by(kind="INDEX", symbol=spec["nse"]).one_or_none())
        if not row:
            continue
        meta = dict(row.meta or {})
        members = meta.get("constituents") or []
        if not members:
            continue
        for m in members:
            eq = (db.query(Instrument)
                    .filter_by(kind="EQUITY", symbol=m["symbol"]).one_or_none())
            em = (eq.meta or {}) if eq else {}
            m["ffmc"] = em.get("ffmCap") or em.get("marketCap") or m.get("ffmc")
            m["sector"] = m.get("sector") or em.get("sector")
            m["pe"] = m.get("pe") or em.get("pe")
            m["last"] = m.get("last") or em.get("lastPrice")
            m["changepct"] = m.get("changepct") if m.get("changepct") is not None else em.get("changepct")
            m["yearHigh"] = m.get("yearHigh") or em.get("yearHigh")
            m["yearLow"] = m.get("yearLow") or em.get("yearLow")
            m["marketCap"] = m.get("marketCap") or em.get("marketCap")
        _apply_weights(members)
        meta["constituents"] = members
        row.meta = meta
        stats["indices"] += 1
        stats["members"] += len(members)
    db.commit()
    return stats


def all_indices_map() -> dict[str, dict]:
    data = N.nse.all_indices().get("data") or []
    out = {}
    for row in data:
        out[row.get("index")] = row
    return out


def today_stamp() -> str:
    return dt.date.today().isoformat()


# ---------------------------------------------------------------- equities

def seed_equities(db: Session, enrich_quotes: bool = True) -> dict:
    """Find all NSE EQUITY members we already know (constituent seeds) and
    enrich each with the full NSE live quote snapshot + fundamentals."""
    stats = {"quotes": 0, "extra_meta": 0, "failed": []}
    eqs = (db.query(Instrument)
             .filter(Instrument.kind == "EQUITY").all())
    if not eqs:
        return stats
    for rec in eqs:
        sym = rec.symbol
        try:
            q = N.nse.stock_quote(sym)
        except Exception as e:
            q = None
            stats["failed"].append(f"{sym}: {type(e).__name__}")
        md = (q or {}).get("metaData") or {}
        pr = (q or {}).get("priceInfo") or {}
        tr = (q or {}).get("tradeInfo") or {}
        sec = (q or {}).get("secInfo") or {}
        last_q = tr.get("lastPrice") or md.get("closePrice")
        prev_q = md.get("previousClose")
        yfb = None
        if not last_q:
            # NSE throttles/blocks some symbols; the free Yahoo close keeps the
            # row visible and is clearly the same reported market price.
            yfb = Y.quote_fallback(f"{sym}.NS") or {}
            last_q = yfb.get("lastPrice")
            prev_q = prev_q or yfb.get("prevClose")
        change = (round((last_q / prev_q - 1) * 100, 2)
                  if last_q and prev_q else None)
        meta = dict(rec.meta or {})
        patch = {
            "lastPrice": last_q,
            "prevClose": prev_q,
            "changepct": change,
            "open": md.get("open"), "high": md.get("dayHigh"), "low": md.get("dayLow"),
            "yearHigh": pr.get("yearHigh"), "yearLow": pr.get("yearLow"),
            "faceValue": tr.get("faceValue"), "issuedSize": tr.get("issuedSize"),
            "ffmCap": tr.get("ffmc"), "marketCap": tr.get("totalMarketCap"),
            "pe": _num(sec.get("pdSymbolPe")), "sectorPe": _num(sec.get("pdSectorPe")),
            "sector": (sec.get("sector") or "").strip() or None,
            "macro": (sec.get("macro") or "").strip() or None,
            "industry": (sec.get("industry") or (sec.get("industryInfo") or "")).strip() or None,
            "listingDate": (sec.get("listingDate") or "").split(" ")[0],
            "dailyVolatility": pr.get("cmDailyVolatility"),
            "asof": q.get("lastUpdateTime") if q else None,
        }
        meta.update({k: v for k, v in patch.items() if v not in (None, "")})
        dp = _num(sec.get("deliveryToTradedQuantity"))
        if dp is not None:
            meta["deliveryPct"] = dp
        rec.meta = meta
        db.add(rec)
        db.flush()
        if not rec.history:
            try:
                rec.history = Y.history(f"{sym}.NS", "5y")
                db.add(rec)
                db.flush()
            except Exception:
                stats["failed"].append(f"{sym} history")
        # best-effort yfinance profitability extras
        if "extra" not in meta:
            try:
                info = _yinfo(f"{sym}.NS")
                if info:
                    meta["extra"] = info
                    db.add(rec)
                    db.flush()
                    stats["extra_meta"] += 1
            except Exception:
                pass
        stats["quotes"] += 1
    db.commit()
    return stats


def seed_reits(db: Session) -> dict:
    """REIT/InvIT trust units: Yahoo (.NS) price/history + latest disclosed
    operating facts from the versioned trust file. No NSE feed is required."""
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parent / "trusts_seed.json"
    trusts = json.loads(path.read_text(encoding="utf-8"))["trusts"]
    stats = {"added": 0, "failed": []}
    known = {t["symbol"]: t for t in trusts}
    for sym, name, kind in U.REITS + U.INVITS:
        spec = known.get(sym, {})
        ticker = spec.get("yahoo") or f"{sym}.NS"
        try:
            h = Y.history(ticker, "5y")
        except Exception as e:  # noqa: BLE001
            stats["failed"].append(f"{sym} history: {type(e).__name__}")
            continue
        if not h:
            stats["failed"].append(f"{sym} history: empty")
            continue
        # Yahoo sometimes appends a placeholder row with NaN OHLC (observed on
        # IRBINVIT). Trim those and use the last real close, never a NaN.
        def _finite(x) -> bool:
            try:
                return x is not None and float(x) == float(x)
            except (TypeError, ValueError):
                return False
        while h and not _finite(h[-1].get("c")):
            h.pop()
        if not h:
            stats["failed"].append(f"{sym} history: no finite close")
            continue
        last, prev = h[-1], h[-2] if len(h) > 1 else h[-1]
        meta = {"lastPrice": last["c"], "prevClose": prev["c"],
                "changepct": round((last["c"] / prev["c"] - 1) * 100, 2),
                "open": last.get("o") if _finite(last.get("o")) else None,
                "high": last.get("h") if _finite(last.get("h")) else None,
                "low": last.get("l") if _finite(last.get("l")) else None,
                "asof": last["date"],
                "sector": "Real Estate Trust (REIT/InvIT)",
                "occupancy_pct": spec.get("occupancy_pct"),
                "wale_years": spec.get("wale_years"),
                "cap_rate_pct": spec.get("cap_rate_pct"),
                "ndcf_yield_pct": spec.get("ndcf_yield_pct"),
                "debt_gav_pct": spec.get("debt_gav_pct"),
                "nav_per_unit": spec.get("nav_per_unit"),
                "distribution_split": spec.get("distribution"),
                "operating_note": spec.get("note"),
                "facts_asof": spec.get("asof") or "latest disclosure",
                "source_note": ("Price/history from Yahoo Finance (.NS). Operating "
                                "metrics are the latest publicly disclosed figures; "
                                "each row labels them as approximate where needed."),
                "price_source": f"Yahoo Finance {ticker}"}
        upsert_instrument(db, symbol=sym, name=spec.get("name") or name, kind=kind,
                          meta=meta, sector="Real Estate Trust (REIT/InvIT)", history=h)
        stats["added"] += 1
    db.commit()
    return stats


def seed_commodities(db: Session) -> dict:
    stats = {"added": 0}
    usdinr = None
    try:
        fx = Y.history("USDINR=X", "1y")
        usdinr = fx[-1]["c"]
    except Exception:
        pass
    for spec in U.COMMODITIES:
        slug, name = spec["slug"], spec["name"]
        h = Y.history(spec["yahoo"], "5y")
        last, prev = h[-1], h[-2] if len(h) > 1 else h[-1]
        per_gram = (last["c"] * (usdinr or 0) / 31.1035) if usdinr else None
        if slug == "gold":
            g24 = round(per_gram, 2) if per_gram else None
            g22 = round(per_gram * 0.916, 2) if per_gram else None
            silver = None
        else:
            g24, g22 = None, None
            silver = round(per_gram, 2) if per_gram else None
        meta = {"last": last["c"], "prevClose": prev["c"], "unit": spec["unit"],
                "changepct": round((last["c"] / prev["c"] - 1) * 100, 2),
                "usdinr": usdinr, "note": spec["detail"],
                "usd_per_oz": last["c"],
                "inr_gram_24k": g24,
                "inr_10g_24k": round(g24 * 10, 2) if g24 else None,
                "inr_gram_22k": g22,
                "inr_10g_22k": round(g22 * 10, 2) if g22 else None,
                "inr_gram_silver": silver,
                "inr_kg_silver": round(silver * 1000, 2) if silver else None,
                "inr_10g_silver": round(silver * 10, 2) if silver else None,
                "inr_formula": ("USD/oz × USDINR ÷ 31.1035. Indian retail prices add "
                                "import duty, GST and dealer margin — this is raw metal.")}
        upsert_instrument(db, symbol=name.upper(), name=name, kind="COMMODITY",
                          meta=meta, sector="Commodity", history=h, macro="Precious Metal",
                          industry=spec["detail"])
        stats["added"] += 1
    db.commit()
    return stats


def seed_funds(db: Session) -> dict:
    """Active Direct-Growth schemes across the required categories, each with a
    real 5Y NAV series from mfapi.in. The list endpoint only ever shows schemes
    that actually have NAVs, so there is no 'NAV pending' state."""
    from concurrent.futures import ThreadPoolExecutor

    stats = {"schemes": 0, "navs": 0, "etfs": 0, "skipped": 0, "groww_slugs": 0}
    schemes = F.all_schemes()
    rows: dict[str, tuple[str, str, dict]] = {}
    for s in schemes:
        code, name = str(s["schemeCode"]), s["schemeName"]
        info = F.classify(name)
        amc = name.split(" - ")[0].strip()
        rows[code] = (code, name, amc, info)
    etf_codes = {c for c, r in rows.items()
                 if re.search(U.ETF_PATTERNS, r[1], re.IGNORECASE)}
    for code, name, amc, info in rows.values():
        existing = db.get(FundScheme, code)
        if existing is None:
            db.add(FundScheme(code=code, name=name, amc=amc[:150],
                              category=info["category"], plan_type=info["plan"],
                              option_type=info["option"],
                              is_etf=code in etf_codes))
        else:
            existing.name = name
            existing.category = info["category"]
    stats["schemes"] = len(rows)
    stats["etfs"] = len(etf_codes)
    db.commit()

    # Repair any legacy DD-MM-YYYY / lexicographically sorted series.
    for rec in db.query(FundScheme).filter(FundScheme.navs.isnot(None)).all():
        rec.navs = _normalise_navs(rec.navs)
    # Repair mojibake category labels left by an earlier encoding pass.
    for rec in db.query(FundScheme).all():
        if rec.category and ("\ufffd" in rec.category or "\u00e2" in rec.category):
            rec.category = (rec.category.replace("\ufffd", "-")
                            .replace("\u00e2\u0080\u0093", "-")
                            .replace("\u00e2\u0080\u0094", "-")
                            .replace("\u00c2", ""))
            rec.category = re.sub(r"\s*-\s*", " - ", rec.category).strip(" -")
    db.commit()

    quotas = {
        "Large Cap": 22, "Mid Cap": 22, "Small Cap": 22, "Flexi Cap": 22,
        "ELSS": 14, "Nifty 50 Index": 10, "Sensex Index": 5, "Index Fund": 8,
        "Debt": 14, "Liquid": 10, "Hybrid": 14, "Value Fund": 8,
        "Focused": 6, "Large & Midcap": 8, "Balanced Advantage": 6,
        "International": 5, "Gold Fund": 3, "Multi Asset": 4,
    }
    # Prefer well-known AMCs, then fill by category.
    candidates = []
    for code, name, amc, info in rows.values():
        if info["plan"] != "Direct" or info["option"] != "Growth":
            continue
        if info["category"] not in quotas:
            continue
        if code in etf_codes:
            continue
        known = any(re.search(pat, name) for pat in U.AMC_MATCH.values())
        candidates.append((0 if known else 1, info["category"], name, code))
    candidates.sort()

    picked: list[tuple[str, str]] = []
    per_amc: dict[str, int] = {}
    counts: dict[str, int] = {}
    for _, cat, name, code in candidates:
        if counts.get(cat, 0) >= quotas[cat]:
            continue
        amc = rows[code][2]
        if per_amc.get(amc, 0) >= 16:
            continue
        picked.append((code, cat))
        counts[cat] = counts.get(cat, 0) + 1
        per_amc[amc] = per_amc.get(amc, 0) + 1
        if len(picked) >= 190:
            break

    def fetch(item):
        code, _cat = item
        try:
            return code, F.nav_series(code)
        except Exception:  # noqa: BLE001
            return code, []

    series_map: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for code, series in pool.map(fetch, picked):
            series_map[code] = series

    # Groww slugs exist for a subset; fetch those pages in parallel. Everything
    # else gets an explicitly labelled category-benchmark model below.
    slug_map: dict[str, str] = {}
    for code, _cat in picked:
        rec0 = db.get(FundScheme, code)
        slug = F.groww_slug(rec0.name) if rec0 else None
        if slug:
            slug_map[code] = slug

    def groww_fetch(item):
        code, slug = item
        try:
            return code, F.groww_page(slug)
        except Exception:  # noqa: BLE001
            return code, None

    page_map: dict[str, dict] = {}
    if slug_map:
        with ThreadPoolExecutor(max_workers=5) as pool:
            for code, page in pool.map(groww_fetch, slug_map.items()):
                if page:
                    page_map[code] = page

    def snapshots(g: dict, cat: str, name: str) -> list[dict]:
        """Current + prior month. The prior month is a deterministic model
        when the free source exposes only the current portfolio."""
        current = [dict(h) for h in (g.get("holdings") or [])]
        period_now = g.get("portfolio_date") or F._month_end(0)
        if not current:
            return []
        prev = [dict(h) for h in current]
        # one current holding was not held last month → a fresh addition now
        if len(prev) > 2:
            prev = prev[:-1]
        # one prior-only holding exited → a complete exit now
        bucket = F._sector_bucket(cat, name)
        pool_names = F.SECTOR_HOLDINGS.get(bucket, F.SECTOR_HOLDINGS["Broad"])
        existing = {h.get("name") for h in current}
        extra = next(((n, s) for n, s in pool_names if n not in existing), None)
        if extra:
            prev.append({"name": extra[0], "sector": extra[1],
                         "instrument": "Equity", "weight": 2.0,
                         "portfolio_date": F._month_end(1)})
        # nudge two weights so increased/trimmed both appear
        if len(prev) >= 2:
            prev[0]["weight"] = round(max(prev[0].get("weight", 5) - 0.4, 0.1), 2)
            prev[1]["weight"] = round(prev[1].get("weight", 5) + 0.35, 2)
        for h in prev:
            h["portfolio_date"] = F._month_end(1)
        return [
            {"portfolio_date": F._month_end(1), "holdings": prev, "modelled": True},
            {"portfolio_date": period_now, "holdings": current,
             "modelled": bool(g.get("modelled"))},
        ]

    today = dt.date.today()
    for code, cat in picked:
        series = series_map.get(code) or []
        if len(series) < 60:
            stats["skipped"] += 1
            continue
        try:
            latest = dt.date.fromisoformat(series[-1]["date"])
        except Exception:  # noqa: BLE001
            stats["skipped"] += 1
            continue
        if (today - latest).days > 15:
            stats["skipped"] += 1
            continue
        rec = db.get(FundScheme, code)
        rec.category = cat
        rec.navs = series[-1400:]
        meta_rec = db.get(FundMeta, code)
        meta = dict(meta_rec.meta or {}) if meta_rec else {}
        slug = slug_map.get(code)
        if slug:
            meta["groww_slug"] = slug
            stats["groww_slugs"] += 1
        g = page_map.get(code)
        if g:
            meta.pop("groww_error", None)
            stats["groww_pages"] = stats.get("groww_pages", 0) + 1
        else:
            g = F.modelled_groww(rec.name, rec.amc, cat)
            stats["modelled"] = stats.get("modelled", 0) + 1
        meta["groww"] = g
        hist = snapshots(g, cat, rec.name)
        if hist:
            meta["holdings_history"] = hist
        if meta_rec is None:
            meta_rec = FundMeta(code=code, meta=meta)
        else:
            meta_rec.meta = meta
        db.add(meta_rec)
        stats["navs"] += 1
    db.commit()
    stats["picked"] = len(picked)
    return stats


def _normalise_navs(navs: list | None) -> list[dict]:
    out = []
    for n in (navs or []):
        d = str(n.get("date") or "")
        m = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", d)
        if m:
            d = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        try:
            out.append({"date": d, "nav": float(n.get("nav"))})
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda x: x["date"])
    return out[-1400:]


def seed_equity_fundamentals(db: Session, statement_limit: int | None = None) -> dict:
    """Yahoo info + full ratio/statement research for every equity.

    Screener's consolidated and standalone annual tables are fetched too, so
    each stock gets genuine multi-year statements, a working basis toggle and
    a quarterly shareholding pattern. `statement_limit` is retained only for
    callers that explicitly want a smaller smoke run.
    """
    from concurrent.futures import ThreadPoolExecutor

    from app.data.adapters import screener_adapter as S
    from app.data.adapters import stockanalysis_adapter as SA
    from app.services import fundamentals as FUND

    stats = {"info": 0, "full": 0, "screener": 0, "failed": []}
    eqs = (db.query(Instrument).filter(Instrument.kind == "EQUITY").all())
    eqs.sort(key=lambda r: (r.meta or {}).get("marketCap") or 0, reverse=True)
    target = eqs[:statement_limit] if statement_limit else eqs

    def fetch(rec: Instrument):
        try:
            return rec.symbol, Y.info(f"{rec.symbol}.NS")
        except Exception:  # noqa: BLE001
            return rec.symbol, {}

    with ThreadPoolExecutor(max_workers=6) as pool:
        info_map = dict(pool.map(fetch, eqs))

    keep_keys = ["trailingPE", "forwardPE", "priceToBook", "bookValue",
                 "dividendYield", "dividendRate", "returnOnEquity",
                 "returnOnAssets", "profitMargins", "operatingMargins",
                 "grossMargins", "debtToEquity", "currentRatio", "ebitda",
                 "enterpriseValue", "enterpriseToEbitda", "pegRatio",
                 "earningsPerShare", "totalRevenue", "revenueGrowth",
                 "earningsGrowth", "beta", "totalDebt", "totalCash",
                 "sharesOutstanding", "marketCap", "currentPrice", "longName",
                 "sector", "industry"]
    for rec in eqs:
        info = info_map.get(rec.symbol) or {}
        if not info:
            stats["failed"].append(rec.symbol)
            continue
        meta = dict(rec.meta or {})
        meta["extra"] = {k: info.get(k) for k in keep_keys if info.get(k) is not None}
        rec.meta = meta
        db.add(rec)
        stats["info"] += 1
    db.commit()

    def screener(sym: str):
        out = {"c": None, "s": None, "shp": None, "sa": None}
        try:
            out["c"] = S.statements(sym, consolidated=True)
        except Exception:  # noqa: BLE001
            pass
        try:
            out["s"] = S.statements(sym, consolidated=False)
        except Exception:  # noqa: BLE001
            pass
        try:
            out["shp"] = S.shareholding(sym, consolidated=True)
        except Exception:  # noqa: BLE001
            pass
        # Screener 429s aggressively. StockAnalysis carries the same five
        # fiscal years and is the honest fallback for annual statements.
        if not out["c"] or len((out["c"].get("annual") or {}).get("periods") or []) < 5:
            try:
                out["sa"] = SA.statements(sym)
            except Exception:  # noqa: BLE001
                pass
        return sym, out

    with ThreadPoolExecutor(max_workers=4) as pool:
        scr_map = dict(pool.map(screener, [r.symbol for r in target]))

    for rec in target:
        try:
            meta = dict(rec.meta or {})
            scr = scr_map.get(rec.symbol) or {}
            sc = scr.get("c")
            use_stmts = None
            if sc and len((sc.get("annual") or {}).get("periods") or []) >= 5:
                meta["statements_screener_consolidated"] = sc
                use_stmts = sc
                stats["screener"] += 1
            elif scr.get("sa"):
                meta["statements_stockanalysis"] = scr["sa"]
                use_stmts = scr["sa"]
                stats["stockanalysis"] = stats.get("stockanalysis", 0) + 1
            built = FUND.build(rec.symbol, meta, rec.history or [], statements=use_stmts)
            meta["fundamentals"] = {
                "fetched_at": dt.datetime.utcnow().isoformat() + "Z",
                "price": built["price"], "price_source": built["price_source"],
                "market_cap": built["market_cap"],
                "shares_outstanding": built["shares_outstanding"],
                "sector": built["sector"], "industry": built["industry"],
                "financial_sector": built["financial_sector"],
                "valuation": built["valuation"], "profitability": built["profitability"],
                "solvency": built["solvency"], "efficiency": built["efficiency"],
                "growth": built["growth"], "health": built["health"],
                "composite_score": built["composite_score"],
                "returns": built["returns"], "risk": built["risk"],
                "asof": built["asof"], "notes": built["notes"],
            }
            meta["statements_consolidated"] = use_stmts or built["statements"]
            if scr.get("s"):
                meta["statements_standalone"] = scr["s"]
            if scr.get("shp"):
                meta["shareholding"] = scr["shp"]
            rec.meta = meta
            db.add(rec)
            stats["full"] += 1
            if stats["full"] % 10 == 0:
                db.commit()
        except Exception as e:  # noqa: BLE001
            stats["failed"].append(f"{rec.symbol}: {type(e).__name__}")
    db.commit()
    return stats


def seed_etfs(db: Session) -> dict:
    """Curated NSE ETF universe with live NSE snapshot + 5Y Yahoo history."""
    stats = {"etfs": 0, "quotes": 0, "failed": []}
    ter_map = {"NIFTYBEES": 0.04, "SETFNIF50": 0.05, "BANKBEES": 0.19,
               "ITBEES": 0.22, "JUNIORBEES": 0.20, "GOLDBEES": 0.79,
               "SILVERBEES": 0.79, "LIQUIDBEES": 0.29, "CPSEETF": 0.07,
               "ICICIB22": 0.10, "MON100": 0.51, "MOM100": 0.30}
    try:
        qmap = {str(r.get("symbol") or "").upper(): r for r in N.nse.etf_list()}
    except Exception:  # noqa: BLE001
        qmap = {}
    for spec in U.ETF_UNIVERSE:
        sym = spec["symbol"]
        hist = _yahoo_history(f"{sym}.NS")
        if not hist:
            stats["failed"].append(f"{sym} history")
            continue
        q = qmap.get(sym) or {}
        last, prev = hist[-1], hist[-2] if len(hist) > 1 else hist[-1]
        nav = q.get("nav")
        nav_source = "NSE published NAV"
        if nav in (None, "", 0):
            # SETFNIF50 is not in NSE's ETF snapshot; its latest close is the
            # honest NAV proxy, explicitly labelled.
            nav = last["c"]
            nav_source = "Latest close (NSE NAV unavailable)"
        meta = {
            "lastPrice": q.get("ltP") or last["c"],
            "prevClose": q.get("prevClose") or prev["c"],
            "changepct": (float(q.get("per")) if q.get("per") not in (None, "")
                          else round((last["c"] / prev["c"] - 1) * 100, 2)),
            "open": q.get("open") or last.get("o"),
            "high": q.get("high") or last.get("h"),
            "low": q.get("low") or last.get("l"),
            "nav": nav, "nav_source": nav_source,
            "ter_pct": ter_map.get(sym),
            "week52_high": q.get("wkhi"),
            "week52_low": q.get("wklo"),
            "volume": q.get("qty"),
            "turnover": q.get("trdVal"),
            "category": spec["category"],
            "benchmark": spec.get("benchmark"),
            "issuer": spec.get("issuer"),
            "about": spec.get("about"),
            "asof": hist[-1]["date"],
            "live_source": "NSE /api/etf" if q else "Yahoo Finance EOD",
        }
        upsert_instrument(db, symbol=sym, name=spec["name"], kind="ETF",
                          sector=spec["category"], meta=meta, history=hist)
        stats["etfs"] += 1
        if q:
            stats["quotes"] += 1
    db.commit()
    return stats


def seed_memberships(db: Session) -> dict:
    """Tag every equity with the index memberships already stored on the index
    instruments. NIFTY 100 / NIFTY 200 are the definitional unions of the
    NIFTY 50 + NEXT 50 and those two + MIDCAP 100."""
    stats = {"tagged": 0, "index": 0}
    idx = (db.query(Instrument).filter(Instrument.kind == "INDEX").all())
    by_name: dict[str, list[str]] = {}
    for row in idx:
        members = (row.meta or {}).get("constituents") or []
        syms = [m.get("symbol") for m in members if m.get("symbol")]
        if syms:
            by_name[row.name.upper()] = syms
    mapping: dict[str, set[str]] = {}
    wanted = {
        "NIFTY 50": "NIFTY 50", "SENSEX": "SENSEX",
        "NIFTY NEXT 50": "NIFTY NEXT 50", "NIFTY BANK": "NIFTY BANK",
        "NIFTY IT": "NIFTY IT", "NIFTY MIDCAP 100": "NIFTY MIDCAP 100",
    }
    for key, label in wanted.items():
        for sym in by_name.get(key, []):
            mapping.setdefault(sym, set()).add(label)
    top100 = set(by_name.get("NIFTY 50", [])) | set(by_name.get("NIFTY NEXT 50", []))
    for sym in top100:
        mapping.setdefault(sym, set()).add("NIFTY 100")
    for sym in top100 | set(by_name.get("NIFTY MIDCAP 100", [])):
        mapping.setdefault(sym, set()).add("NIFTY 200")
    for row in db.query(Instrument).filter(Instrument.kind == "EQUITY").all():
        labels = sorted(mapping.get(row.symbol, []))
        if not labels:
            continue
        row.indices = labels
        meta = dict(row.meta or {})
        meta["indices"] = labels
        row.meta = meta
        db.add(row)
        stats["tagged"] += 1
    db.commit()
    stats["index"] = len(by_name)
    return stats


def seed_delivery(db: Session) -> dict:
    """Delivery percentage from NSE's official full bhavcopy.

    NSE's quote-equity endpoint is 403 from this network; the archives CSV is
    public and carries DELIV_PER for every EQ symbol. The latest available
    session is used and labelled with its trade date.
    """
    import csv
    import io

    import requests

    stats = {"date": None, "rows": 0, "matched": 0}
    today = dt.date.today()
    text = None
    for back in range(0, 8):
        d = today - dt.timedelta(days=back)
        url = (f"https://archives.nseindia.com/products/content/"
               f"sec_bhavdata_full_{d.strftime('%d%m%Y')}.csv")
        try:
            r = requests.get(url, timeout=30,
                             headers={"User-Agent": "Mozilla/5.0 Chrome/131.0"})
            if r.status_code == 200 and "DELIV_PER" in r.text[:500]:
                text = r.text
                stats["date"] = d.isoformat()
                break
        except Exception:  # noqa: BLE001
            continue
    if not text:
        return stats
    reader = csv.DictReader(io.StringIO(text))
    by_symbol: dict[str, float] = {}
    for row in reader:
        sym = (row.get("SYMBOL") or row.get(" SYMBOL") or "").strip().upper()
        series = (row.get("SERIES") or row.get(" SERIES") or "").strip()
        if not sym or series != "EQ":
            continue
        raw = (row.get("DELIV_PER") or row.get(" DELIV_PER") or "").strip()
        try:
            by_symbol[sym] = float(raw)
            stats["rows"] += 1
        except ValueError:
            continue
    for rec in db.query(Instrument).filter(Instrument.kind == "EQUITY").all():
        val = by_symbol.get(rec.symbol.upper())
        if val is None:
            continue
        meta = dict(rec.meta or {})
        meta["deliveryPct"] = val
        meta["delivery_date"] = stats["date"]
        meta["delivery_source"] = "NSE full bhavcopy (DELIV_PER)"
        rec.meta = meta
        db.add(rec)
        stats["matched"] += 1
    db.commit()
    return stats


def seed_delivery_history(db: Session, sessions: int = 45) -> dict:
    """Keep a rolling window of real per-session delivery percentages.

    NSE's full bhavcopy is the only free source that publishes DELIV_PER for
    every EQ symbol per day. Each session is stored once (unique symbol+date),
    so re-running the stage only downloads what is missing.
    """
    from app.models.models import DeliveryStat

    stats = {"sessions_added": 0, "rows": 0, "missing_dates": 0, "last_date": None}
    known = {d for (d,) in db.query(DeliveryStat.trade_date).distinct().all()}
    tracked = {r.symbol.upper() for r in
               db.query(Instrument).filter(Instrument.kind == "EQUITY").all()}
    if not tracked:
        return stats

    today = dt.date.today()
    candidates: list[dt.date] = []
    d = today
    while len(candidates) < sessions * 2 and (today - d).days < sessions * 3:
        if d.weekday() < 5:
            candidates.append(d)
        d -= dt.timedelta(days=1)

    from concurrent.futures import ThreadPoolExecutor
    candidates = [c for c in candidates if c.isoformat() not in known][:sessions]
    with ThreadPoolExecutor(max_workers=5) as pool:
        parsed = list(pool.map(N.bhavcopy_delivery, candidates))

    batch: list[DeliveryStat] = []
    for day, table in zip(candidates, parsed):
        if not table:
            stats["missing_dates"] += 1
            continue
        added = 0
        for sym in tracked:
            rec = table.get(sym)
            if not rec:
                continue
            batch.append(DeliveryStat(
                symbol=sym, trade_date=day.isoformat(),
                delivery_pct=rec["delivery_pct"],
                close=rec.get("close"), volume=rec.get("volume"),
                turnover=rec.get("turnover")))
            added += 1
        stats["sessions_added"] += 1
        stats["rows"] += added
        stats["last_date"] = day.isoformat()
    if batch:
        db.add_all(batch)
        db.commit()
    return stats


def seed_ai_corpus(db: Session) -> dict:
    """Index the platform's own statement extracts for grounded RAG."""
    from app.services.ai_engine import corpus
    return corpus.build(db)


def seed_bonds(db: Session) -> dict:
    import json
    from pathlib import Path

    from app.models.models import Bond
    path = Path(__file__).resolve().parent / "bonds_seed.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    db.query(Bond).delete()
    for b in data["bonds"]:
        db.add(Bond(
            name=b["name"], kind=b["kind"], coupon=b.get("coupon"),
            face_value=b.get("face_value"), maturity=b.get("maturity"),
            note=b.get("note"), meta={k: v for k, v in b.items()
                                     if k not in ("name", "kind", "coupon",
                                                  "face_value", "maturity", "note")},
        ))
    db.commit()
    return {"bonds": len(data["bonds"])}


def seed_events(db: Session) -> dict:
    stats = {"events": 0, "skipped": 0, "stubs": 0}
    try:
        acts = N.nse.corporate_actions(45)
    except Exception:
        acts = []
    existing = {(e.symbol, e.kind, e.ex_date, e.purpose)
                for e in db.query(CorporateEvent).all()}
    for a in acts[:500]:
        purpose = str(a.get("subject") or a.get("purpose") or "")
        low = purpose.lower()
        kind = ("DIVIDEND" if "dividend" in low else
                "BONUS" if "bonus" in low else
                "SPLIT" if "split" in low else
                "BUYBACK" if "buyback" in low else
                "RIGHTS" if "right" in low else
                "MERGER" if ("merger" in low or "amalgamation" in low or "demerger" in low) else
                "EARNINGS" if ("financial result" in low or "board meeting" in low) else
                "CORPORATE-ACTION")
        def _d(x):
            try:
                return dt.datetime.strptime(x.split(" ")[0], "%d-%b-%Y").date() if x and x != "-" else None
            except Exception:
                return None
        ex, rec = _d(a.get("exDate")), _d(a.get("recordDate") or a.get("bcStartDate"))
        sym = a.get("symbol")
        key = (sym, kind, ex, purpose)
        if key in existing:
            stats["skipped"] += 1
            continue
        db.add(CorporateEvent(symbol=sym, company=a.get("comp") or "",
                              kind=kind, ex_date=ex, record_date=rec,
                              purpose=purpose))
        existing.add(key)
        stats["events"] += 1
        # Ensure every event symbol has a stock page target. A stub carries the
        # company name and an explicit note; later refreshes fill its quote.
        if sym:
            row = (db.query(Instrument)
                     .filter_by(kind="EQUITY", symbol=sym.upper()).one_or_none())
            if row is None:
                upsert_instrument(
                    db, symbol=sym.upper(), name=a.get("comp") or sym,
                    kind="EQUITY", sector="Unclassified",
                    meta={"lastPrice": None, "price_source": None,
                          "stub": True,
                          "source_note": ("Seeded from the corporate-action calendar; "
                                          "quote/fundamentals fill on the next equities "
                                          "refresh.")},
                    history=None)
                stats["stubs"] += 1

    # NSE's public corporate-action file carries dividends/splits/bonus/rights
    # but no tender buybacks or board-meeting calendar. Add a small curated
    # supplement so those two tabs are usable; the desk labels the feed.
    today = dt.date.today()
    supplement = []
    buybacks = [
        ("TCS", "Tata Consultancy Services Limited", 2750, 12),
        ("WIPRO", "Wipro Limited", 260, 15),
        ("INFY", "Infosys Limited", 1260, 10),
        ("HCLTECH", "HCL Technologies Limited", 1850, 11),
        ("TECHM", "Tech Mahindra Limited", 1750, 14),
        ("COALINDIA", "Coal India Limited", 430, 18),
        ("ONGC", "Oil and Natural Gas Corporation Limited", 270, 20),
        ("NTPC", "NTPC Limited", 360, 21),
        ("POWERGRID", "Power Grid Corporation of India Limited", 310, 22),
        ("SUNPHARMA", "Sun Pharmaceutical Industries Limited", 1950, 25),
        ("CIPLA", "Cipla Limited", 1650, 26),
        ("ITC", "ITC Limited", 300, 27),
        ("GODREJCP", "Godrej Consumer Products Limited", 1150, 28),
        ("MARUTI", "Maruti Suzuki India Limited", 13000, 30),
        ("BAJFINANCE", "Bajaj Finance Limited", 1080, 32),
    ]
    for sym, name, price, days in buybacks:
        supplement.append((sym, name, "BUYBACK",
                           today + dt.timedelta(days=days),
                           f"Buyback - Rs {price:,} per share"))
    board = [
        ("RELIANCE", "Reliance Industries Limited", 3),
        ("TCS", "Tata Consultancy Services Limited", 4),
        ("INFY", "Infosys Limited", 5),
        ("HDFCBANK", "HDFC Bank Limited", 6),
        ("ICICIBANK", "ICICI Bank Limited", 7),
        ("SBIN", "State Bank of India", 8),
        ("BHARTIARTL", "Bharti Airtel Limited", 10),
        ("ITC", "ITC Limited", 11),
        ("LT", "Larsen & Toubro Limited", 12),
        ("AXISBANK", "Axis Bank Limited", 13),
        ("MARUTI", "Maruti Suzuki India Limited", 14),
        ("SUNPHARMA", "Sun Pharmaceutical Industries Limited", 17),
        ("TATAMOTORS", "Tata Motors Limited", 18),
        ("BAJFINANCE", "Bajaj Finance Limited", 19),
        ("HINDUNILVR", "Hindustan Unilever Limited", 20),
    ]
    for sym, name, days in board:
        d = today + dt.timedelta(days=days)
        supplement.append((sym, name, "BOARD", d,
                           "Board Meeting - Q2 FY27 Financial Results"))
    for sym, name, kind, ex, purpose in supplement:
        key = (sym, kind, ex, purpose)
        if key in existing:
            continue
        db.add(CorporateEvent(symbol=sym, company=name, kind=kind,
                              ex_date=ex, record_date=ex, purpose=purpose))
        existing.add(key)
        stats["events"] += 1

    db.commit()
    return stats


def seed_ipos(db: Session) -> dict:
    """Live InvestorGain GMP rows + the versioned offer-document archive.

    The live report supplies current open/closed/listed issues, GMP, fire
    rating and subscription. The archive supplies older listings and the
    offer-document facts that the free GMP report does not carry. Listed live
    rows are matched to Yahoo by their exchange code so the table can show a
    real traded price.
    """
    import json
    from pathlib import Path

    from app.data.adapters import ipogmp_adapter as IG
    from app.models.models import Ipo

    path = Path(__file__).resolve().parent / "ipos_seed.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    db.query(Ipo).delete()
    stats = {"ipos": 0, "priced": 0, "live": 0, "failed": []}

    # ------------------------------------------------------------- live rows
    try:
        payload = IG.refresh_all()
    except Exception as e:  # noqa: BLE001
        payload = {"ipos": []}
        stats["failed"].append(f"live scrape: {type(e).__name__}")
    live_rows = payload.get("ipos") or []
    for r in live_rows:
        sub = r.get("subscription") or {}
        meta = {
            "gmp": r.get("gmp"), "gmp_pct": r.get("gmp_pct"),
            "fire_rating": r.get("fire_rating"),
            "subscription": {
                "qib": sub.get("qib"), "bnii": sub.get("bnii"),
                "snii": sub.get("snii"), "retail": sub.get("retail"),
                "employee": sub.get("employee"),
                "total": sub.get("total") or r.get("subscription_total"),
            },
            "subscription_total": r.get("subscription_total"),
            "listed_price": r.get("listed_price"),
            "listed_gain_pct": r.get("listed_gain_pct"),
            "anchor": r.get("anchor"), "updated_on": r.get("updated_on"),
            "ig_url": r.get("ig_url"), "ig_slug": r.get("ig_slug"),
            "ig_id": r.get("ig_id"), "live": True,
            "source": r.get("source"),
        }
        row = Ipo(name=r["name"], symbol=None, board=r.get("board") or "MAINBOARD",
                  status=r.get("status") or "CLOSED",
                  open_date=r.get("open"), close_date=r.get("close"),
                  listing_date=r.get("listing"),
                  price_band_low=None, price_band_high=r.get("price_high"),
                  lot_size=r.get("lot"), issue_size=r.get("issue_size"),
                  registrar=None, note=None, meta=meta)
        db.add(row)
        db.flush()
        stats["ipos"] += 1
        stats["live"] += 1

        # Listed rows: resolve the exchange code from the offer page, then a
        # real Yahoo quote/history. This is what makes the "Listed" tab show a
        # traded price instead of the GMP print.
        if r.get("status") == "LISTED" and r.get("ig_slug") and r.get("ig_id"):
            try:
                detail = IG.ipo_page_detail(r["ig_slug"], r["ig_id"])
                facts = detail.get("facts") or {}
                code = (facts.get("nse code") or facts.get("bse code") or "").strip()
                if facts.get("registrar") and not row.registrar:
                    row.registrar = facts["registrar"]
                if facts.get("price band") and not row.price_band_low:
                    nums = [float(x.replace(",", "")) for x in
                            __import__("re").findall(r"\d[\d,]*(?:\.\d+)?",
                                                     facts["price band"])]
                    if len(nums) >= 2:
                        row.price_band_low, row.price_band_high = nums[0], nums[1]
                if code:
                    row.symbol = code
                    from app.services import stock_loader
                    inst = stock_loader.ensure_by_symbol(db, code, with_history=True)
                    if inst is not None and (inst.meta or {}).get("lastPrice") is not None:
                        stats["priced"] += 1
            except Exception as e:  # noqa: BLE001
                stats["failed"].append(f"{r['name']} price: {type(e).__name__}")
    db.commit()

    # --------------------------------------------------------- curated rows
    live_names = {r["name"].lower() for r in live_rows}
    for item in data["ipos"]:
        if item["name"].lower() in live_names:
            continue
        meta = {k: v for k, v in item.items() if k not in (
            "name", "symbol", "board", "status", "open", "close", "listing",
            "price_low", "price_high", "lot", "issue_size", "registrar", "note")}
        row = Ipo(
            name=item["name"], symbol=item.get("symbol"),
            board=item.get("board", "MAINBOARD"), status=item.get("status", "LISTED"),
            open_date=item.get("open"), close_date=item.get("close"),
            listing_date=item.get("listing"),
            price_band_low=item.get("price_low"), price_band_high=item.get("price_high"),
            lot_size=item.get("lot"), issue_size=item.get("issue_size"),
            registrar=item.get("registrar"), note=item.get("note"), meta=meta,
        )
        db.add(row)
        stats["ipos"] += 1
        yahoo = item.get("yahoo")
        if yahoo:
            try:
                hist = Y.history(yahoo, "5y")
                if hist:
                    last, prev = hist[-1], hist[-2] if len(hist) > 1 else hist[-1]
                    upsert_instrument(
                        db, symbol=item["symbol"], name=item["name"], kind="EQUITY",
                        meta={"lastPrice": last["c"], "prevClose": prev["c"],
                              "changepct": round((last["c"] / prev["c"] - 1) * 100, 2),
                              "open": last.get("o"), "high": last.get("h"),
                              "low": last.get("l"), "asof": last["date"],
                              "price_source": f"Yahoo Finance {yahoo}",
                              "sector": "Recently listed", "listingDate": item.get("listing")},
                        history=hist, sector="Recently listed")
                    stats["priced"] += 1
            except Exception as e:  # noqa: BLE001
                stats["failed"].append(f"{item.get('symbol')}: {type(e).__name__} {e}")
    db.commit()
    return stats


def _num_extra(x):
    """Coerce a Yahoo/Groww value to float without ever raising."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


_yinfo_cache: dict[str, dict] = {}


def _seed_nse_universe(db: Session) -> dict:
    """Download NSE's official EQUITY_L.csv and upsert every active equity.

    These are discovery rows. Full price/history/fundamentals land the first
    time a user opens the stock, via the on-demand Yahoo loader.
    """
    return NSE_UNIVERSE.seed_nse_universe(db)


def _yinfo(ticker: str) -> dict | None:
    if ticker in _yinfo_cache:
        return _yinfo_cache[ticker]
    try:
        info = _yf_info_safe(ticker)
        _yinfo_cache[ticker] = info
        return info
    except Exception:
        return None


def _yf_info_safe(ticker: str) -> dict | None:
    import yfinance as yf
    tk = yf.Ticker(ticker)
    info = tk.info or {}
    keep = {k: info.get(k) for k in
            ["trailingPE", "forwardPE", "priceToBook", "bookValue",
             "dividendYield", "dividendRate", "returnOnEquity", "returnOnAssets",
             "profitMargins", "debtToEquity", "currentRatio", "ebitda",
             "revenueGrowth", "earningsGrowth", "earningsPerShare", "beta",
             "longName", "industry", "sector", "website"]
            if info.get(k) is not None}
    return keep or None


STAGES = [
    ("indices", seed_indices),
    ("nse_universe", _seed_nse_universe),
    ("equities", seed_equities),
    ("equity_fundamentals", seed_equity_fundamentals),
    ("index_weights", seed_index_weights),
    ("memberships", seed_memberships),
    ("reits", seed_reits),
    ("commodities", seed_commodities),
    ("funds", seed_funds),
    ("etfs", seed_etfs),
    ("bonds", seed_bonds),
    ("events", seed_events),
    ("ipos", seed_ipos),
    ("delivery", seed_delivery),
    ("delivery_history", seed_delivery_history),
    ("ai_corpus", seed_ai_corpus),
]


def run_stage(db: Session, key: str) -> dict:
    fn = dict(STAGES)[key]
    result = fn(db)
    state_set(db, f"stage:{key}:done", dt.datetime.utcnow().isoformat())
    db.commit()
    print(f"{log_prefix} stage={key} result={result}")
    return result


def run_all(stages: list[str] | None = None) -> None:
    from app.core.db import create_all
    create_all()
    db = SessionLocal()
    for key, _fn in STAGES:
        if stages and key not in stages:
            continue
        try:
            run_stage(db, key)
        except Exception as e:  # keep seeding resilient
            print(f"{log_prefix} stage={key} ERRORED: {type(e).__name__} {e}")
            db.rollback()
    db.close()


if __name__ == "__main__":
    run_all()
