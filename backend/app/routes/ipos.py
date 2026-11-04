"""IPO Intelligence Hub — InvestorGain-style live GMP table.

The live report and each offer page are scraped with browser TLS
impersonation. Rows are merged into SQLite so the global search bar and the
detail pages work offline. When the scrape fails the versioned offer-document
seed is served instead, and the row says so. Nothing is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.data.adapters import ipogmp_adapter as IG
from app.models.models import Instrument, Ipo
from app.services.contextual import not_disclosed, reported, source_issue

router = APIRouter(prefix="/ipos", tags=["ipos"])

SEED = Path(__file__).resolve().parent.parent / "seed" / "ipos_seed.json"

REGISTRAR_LINKS = {
    "kfin": "https://kosmic.kfintech.com/ipostatus/",
    "link intime": "https://linkintime.co.in/IPO/ipo_status.html",
    "bigshare": "https://ipo.bigshareonline.com/ipo_status.html",
    "mufg": "https://linkintime.co.in/IPO/ipo_status.html",
    "cameo": "https://ipostatus.cameoindia.com/",
    "purva": "https://ipo.purvashare.com/ipo_status",
    "skyline": "https://www.skylinerta.com/ipo_status.php",
    "bse": "https://www.bseindia.com/investors/appli_check.aspx",
}


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or "ipo"


def _env(v, what: str = "metric") -> dict:
    return reported(v) if v is not None else not_disclosed(what)


def _registrar_link(name: str | None, fallback: str | None = None) -> str | None:
    if fallback:
        return fallback
    n = (name or "").lower()
    for key, url in REGISTRAR_LINKS.items():
        if key in n:
            return url
    return REGISTRAR_LINKS["bse"]


# --------------------------------------------------------------- live merge
def _sync_live(db: Session) -> dict:
    """Upsert the live InvestorGain rows into SQLite (cached 10 minutes)."""
    try:
        payload = IG.refresh_all()
    except Exception:  # noqa: BLE001
        return {"ok": False, "count": 0}
    rows = payload.get("ipos") or []
    added = updated = 0
    for r in rows:
        name = (r.get("name") or "").strip()
        if not name:
            continue
        row = (db.query(Ipo)
                 .filter(func.lower(Ipo.name) == name.lower())
                 .first())
        sub = r.get("subscription") or {}
        meta = {
            "gmp": r.get("gmp"),
            "gmp_pct": r.get("gmp_pct"),
            "fire_rating": r.get("fire_rating"),
            "subscription": {
                "qib": sub.get("qib"),
                "bnii": sub.get("bnii"),
                "snii": sub.get("snii"),
                "retail": sub.get("retail"),
                "total": sub.get("total") or r.get("subscription_total"),
                "employee": sub.get("employee"),
            },
            "subscription_total": r.get("subscription_total"),
            "listed_price": r.get("listed_price"),
            "listed_gain_pct": r.get("listed_gain_pct"),
            "anchor": r.get("anchor"),
            "updated_on": r.get("updated_on"),
            "ig_url": r.get("ig_url"),
            "ig_slug": r.get("ig_slug"),
            "ig_id": r.get("ig_id"),
            "live": True,
            "source": r.get("source") or "InvestorGain live GMP report",
        }
        if row is None:
            row = Ipo(name=name, symbol=None, board=r.get("board") or "MAINBOARD",
                      status=r.get("status") or "CLOSED",
                      open_date=r.get("open"), close_date=r.get("close"),
                      listing_date=r.get("listing"),
                      price_band_low=None, price_band_high=r.get("price_high"),
                      lot_size=r.get("lot"), issue_size=r.get("issue_size"),
                      registrar=None, note=None, meta=meta)
            db.add(row)
            added += 1
        else:
            row.board = r.get("board") or row.board
            row.status = r.get("status") or row.status
            row.open_date = r.get("open") or row.open_date
            row.close_date = r.get("close") or row.close_date
            row.listing_date = r.get("listing") or row.listing_date
            row.price_band_high = r.get("price_high") or row.price_band_high
            row.lot_size = r.get("lot") or row.lot_size
            row.issue_size = r.get("issue_size") or row.issue_size
            merged = dict(row.meta or {})
            merged.update({k: v for k, v in meta.items() if v is not None})
            row.meta = merged
            updated += 1
    db.commit()
    return {"ok": True, "count": len(rows), "added": added,
            "updated": updated, "fetched_at": payload.get("fetched_at")}


def _live_meta(i: Ipo) -> dict:
    return i.meta or {}


def _price(i: Ipo, db: Session) -> dict:
    """Live post-listing price: Yahoo-backed instrument row, then IG print."""
    m = i.meta or {}
    if i.symbol:
        row = (db.query(Instrument)
                 .filter_by(kind="EQUITY", symbol=i.symbol.upper()).one_or_none())
        if row:
            rm = row.meta or {}
            if rm.get("lastPrice") is not None:
                return {"last": _env(rm.get("lastPrice"), "post-listing price"),
                        "changepct": _env(rm.get("changepct"), "post-listing change"),
                        "source": rm.get("price_source") or "Yahoo Finance (.NS)"}
    if m.get("listed_price") is not None:
        return {"last": _env(m.get("listed_price"), "listing price"),
                "changepct": _env(m.get("listed_gain_pct"), "listing gain"),
                "source": "InvestorGain listing print"}
    return {"last": not_disclosed("post-listing price"),
            "changepct": not_disclosed("post-listing change"),
            "source": None}


def _gmp_trend(gmp: float | None, pct: float | None) -> str:
    if gmp is None:
        return "Neutral"
    if (pct or 0) >= 20 or (gmp or 0) >= 50:
        return "🔥 High Demand"
    if (pct or 0) <= 0:
        return "Discount"
    return "Neutral"


def _est_listing(i: Ipo, gmp: float | None) -> tuple[float | None, float | None, float | None]:
    price = i.price_band_high
    if price is None:
        return None, None, None
    est = round(price + (gmp or 0), 2)
    gain_rs = round(est - price, 2)
    gain_pct = round((est / price - 1) * 100, 2) if price else None
    return est, gain_rs, gain_pct


def _split_pcts(i: Ipo, m: dict) -> tuple[float | None, float | None]:
    """Fresh/OFS split for a live row.

    The GMP report only carries the total issue size. The offer-document page
    adds the fresh-issue amount, so when a detail scrape has been persisted we
    can derive both percentages from rupees instead of showing an empty bar.
    """
    fresh_pct = m.get("fresh_pct")
    ofs_pct = m.get("ofs_pct")
    if fresh_pct is not None or ofs_pct is not None:
        return fresh_pct, ofs_pct
    size = i.issue_size or m.get("issue_size_cr")
    fresh_cr = m.get("fresh_issue_cr")
    ofs_cr = m.get("ofs_crore")
    if not size or size <= 0:
        return None, None
    if fresh_cr is None and ofs_cr is not None:
        fresh_cr = max(size - ofs_cr, 0)
    if ofs_cr is None and fresh_cr is not None:
        ofs_cr = max(size - fresh_cr, 0)
    if fresh_cr is None:
        return None, None
    fresh = round(fresh_cr / size * 100, 2)
    ofs = round(max(100 - fresh, 0), 2)
    return fresh, ofs


def _row(i: Ipo, db: Session) -> dict:
    m = i.meta or {}
    sub = m.get("subscription") or {}
    fresh_pct, ofs_pct = _split_pcts(i, m)
    price = i.price_band_high
    lot = i.lot_size
    gmp = m.get("gmp")
    est, gain_rs, gain_pct = _est_listing(i, gmp)
    # A listed row's realised gain beats an indicative GMP.
    perf = _price(i, db)
    if i.status == "LISTED" and perf["last"].get("value") and price:
        realised = round((perf["last"]["value"] / price - 1) * 100, 2)
    else:
        realised = None
    return {
        "id": i.id, "slug": slugify(i.name), "name": i.name, "symbol": i.symbol,
        "board": i.board, "status": i.status,
        "open": i.open_date, "close": i.close_date, "allotment": m.get("allotment"),
        "listing": i.listing_date,
        "price": _env(price, "upper price band"),
        "price_band": reported([i.price_band_low, i.price_band_high],
                               note="Offer price band per share.") if i.price_band_low
        else reported([price, price], note="Upper-band price (floor not disclosed).")
        if price else not_disclosed("price band"),
        "lot": _env(lot, "lot size"),
        "min_investment": _env(round(lot * price, 2) if lot and price else None,
                               "minimum investment (1 lot)"),
        "issue_size": _env(i.issue_size, "issue size (₹ crore)"),
        "registrar": _env(i.registrar, "registrar"),
        "registrar_url": _registrar_link(i.registrar, m.get("registrar_url")),
        "fresh_pct": _env(fresh_pct, "fresh issue share"),
        "ofs_pct": _env(ofs_pct, "offer-for-sale share"),
        "subscription": {
            "qib": _env(sub.get("qib"), "QIB subscription"),
            "bnii": _env(sub.get("bnii"), "bNII subscription"),
            "snii": _env(sub.get("snii"), "sNII subscription"),
            "retail": _env(sub.get("retail"), "retail subscription"),
            "employee": _env(sub.get("employee"), "employee subscription"),
            "total": _env(sub.get("total") or m.get("subscription_total"),
                          "total subscription"),
        },
        "gmp": _env(gmp, "grey-market premium"),
        "gmp_pct": _env(m.get("gmp_pct"), "GMP percentage"),
        "gmp_trend": _gmp_trend(gmp, m.get("gmp_pct")),
        "fire_rating": _env(m.get("fire_rating"), "demand rating"),
        "est_listing_price": _env(est, "estimated listing price"),
        "est_listing_gain_rs": _env(gain_rs, "estimated listing gain ₹"),
        "est_listing_gain_pct": _env(gain_pct, "estimated listing gain %"),
        "realised_gain_pct": _env(realised, "realised listing gain"),
        "preipo_price": _env(m.get("preipo_price"), "pre-IPO share price"),
        "brlm": m.get("brlm") or [],
        "anchor_lockin_30": m.get("anchor_lockin_30"),
        "anchor_lockin_90": m.get("anchor_lockin_90"),
        "note": i.note,
        "performance": perf,
        "ig_url": m.get("ig_url"),
        "live": bool(m.get("live")),
        "source": m.get("source") or "Offer-document archive",
        "updated_on": m.get("updated_on"),
        "href": f"/ipos/{slugify(i.name)}",
    }


@router.get("")
def list_ipos(filter: str = "all", board: str | None = None,
              q: str | None = None, sort: str = "status",
              limit: int = Query(120, le=300), db: Session = Depends(get_db)):
    sync = _sync_live(db)
    query = db.query(Ipo)
    f = (filter or "all").lower()
    if f in ("open", "live"):
        query = query.filter(Ipo.status == "LIVE")
    elif f == "upcoming":
        query = query.filter(Ipo.status == "UPCOMING")
    elif f == "closed":
        query = query.filter(Ipo.status.in_(("CLOSED", "ALLOTMENT")))
    elif f == "listed":
        query = query.filter(Ipo.status == "LISTED")
    if board and board.lower() in ("mainboard", "sme"):
        query = query.filter(Ipo.board == board.upper())
    rows = query.all()
    if q:
        needle = q.strip().lower()
        rows = [r for r in rows if needle in r.name.lower()
                or needle in (r.symbol or "").lower()]
    order = {"LIVE": 0, "UPCOMING": 1, "CLOSED": 2, "ALLOTMENT": 2, "LISTED": 3}
    if sort == "gmp":
        rows.sort(key=lambda r: (r.meta or {}).get("gmp") or -1, reverse=True)
    elif sort == "listing":
        rows.sort(key=lambda r: r.listing_date or "", reverse=True)
    else:
        rows.sort(key=lambda r: (order.get(r.status, 4),
                                 r.listing_date or r.close_date or ""), reverse=False)
        # Within a status bucket, newest issues first.
        rows.sort(key=lambda r: (order.get(r.status, 4),
                                 -(int((r.listing_date or "2020-01-01")
                                       .replace("-", "")) if (r.listing_date or "")
                                    else 0)))
    items = [_row(i, db) for i in rows[:limit]]
    all_rows = db.query(Ipo).all()
    counts = {
        "all": len(all_rows),
        "mainboard": sum(1 for r in all_rows if r.board == "MAINBOARD"),
        "sme": sum(1 for r in all_rows if r.board == "SME"),
        "open": sum(1 for r in all_rows if r.status == "LIVE"),
        "upcoming": sum(1 for r in all_rows if r.status == "UPCOMING"),
        "closed": sum(1 for r in all_rows if r.status == "CLOSED"),
        "listed": sum(1 for r in all_rows if r.status == "LISTED"),
    }
    # Quarter listing-gain average from realised prints.
    qstart = dt.date.today() - dt.timedelta(days=92)
    quarter = [r for r in all_rows if r.status == "LISTED" and r.listing_date
               and r.listing_date >= qstart.isoformat()]
    gains = []
    for r in quarter:
        m = r.meta or {}
        if m.get("listed_gain_pct") is not None:
            gains.append(m["listed_gain_pct"])
        elif m.get("listed_price") and r.price_band_high:
            gains.append(round((m["listed_price"] / r.price_band_high - 1) * 100, 2))
    avg_gain = round(sum(gains) / len(gains), 2) if gains else None
    return {
        "filter": f, "board": (board or "all").lower(),
        "count": len(items), "total": counts["all"],
        "filters_available": ["all", "open", "upcoming", "closed", "listed"],
        "filter_counts": counts,
        "summary": {
            "open_now": counts["open"], "upcoming": counts["upcoming"],
            "listed_quarter": len(quarter),
            "avg_listing_gain_pct": avg_gain,
        },
        "ipos": items,
        "live_sync": sync,
        "feed_status": reported(
            "InvestorGain live GMP report + offer-document archive"
            if sync.get("ok") else "Offer-document archive (live scrape unavailable)"),
        "source_note": ("GMP, fire rating, subscription and listing prints are "
                        "scraped live from InvestorGain's public report. Issue facts "
                        "come from exchange offer documents. GMP is unofficial and "
                        "can vanish on listing day."),
    }


def _detail_scrape(i: Ipo) -> dict:
    m = i.meta or {}
    slug, ig_id = m.get("ig_slug"), m.get("ig_id")
    if not (slug and ig_id):
        return {}
    out = IG.ipo_page_detail(slug, ig_id)
    hist = IG.gmp_history(slug, ig_id)
    if hist:
        out["gmp_history"] = hist
    return out


@router.get("/{slug}")
def ipo_detail(slug: str, db: Session = Depends(get_db)):
    needle = slug.strip().lower()
    rows = db.query(Ipo).all()
    i = next((r for r in rows if slugify(r.name) == needle), None)
    if i is None and slug.isdigit():
        i = db.get(Ipo, int(slug))
    if i is None:
        # A live row may have been added after this slug was cached.
        _sync_live(db)
        rows = db.query(Ipo).all()
        i = next((r for r in rows if slugify(r.name) == needle), None)
    if i is None:
        raise HTTPException(404, "IPO not found in the live report or the seeded archive.")
    m = i.meta or {}
    scraped = _detail_scrape(i)
    # Persist the offer-document issue split so the list view's fresh/OFS bar
    # has real rupee figures even though the GMP report only prints the total.
    fresh_cr = scraped.get("fresh_issue_cr")
    size_cr = i.issue_size or scraped.get("issue_size_cr")
    if fresh_cr is not None and size_cr:
        ofs_cr = round(max(size_cr - fresh_cr, 0), 2)
        merged = dict(m)
        merged.update({
            "issue_size_cr": size_cr,
            "fresh_issue_cr": fresh_cr,
            "ofs_crore": ofs_cr,
            "fresh_pct": round(fresh_cr / size_cr * 100, 2),
            "ofs_pct": round(ofs_cr / size_cr * 100, 2),
        })
        i.meta = merged
        db.commit()
        m = merged
    base = _row(i, db)
    live_sub = IG.subscription_for(i.name)

    offer = i.price_band_high or i.price_band_low or 0
    sellers = []
    for s in (m.get("selling_shareholders") or []):
        cost = s.get("preipo_cost")
        sellers.append({
            "name": s.get("name"),
            "preipo_cost": _env(cost, "pre-IPO acquisition cost"),
            "offer_price": _env(s.get("offer_price") or offer, "IPO offer price"),
            "multiple": _env(round(offer / cost, 2) if offer and cost else None,
                             "return multiple"),
            "post_holding_pct": _env(s.get("post_holding_pct"), "post-IPO holding"),
        })

    struct = {
        "price_band": base["price_band"],
        "lot_size": base["lot"],
        "issue_size_crore": base["issue_size"],
        "fresh_issue_pct": base["fresh_pct"],
        "ofs_pct": base["ofs_pct"],
        "fresh_issue_crore": _env(
            scraped.get("fresh_issue_cr") or m.get("fresh_issue_cr")
            or (round(i.issue_size * (m.get("fresh_pct") or 0) / 100, 2)
                if i.issue_size else None), "fresh issue size"),
        "ofs_crore": _env(
            m.get("ofs_crore") if m.get("ofs_crore") is not None else
            (round(i.issue_size * (m.get("ofs_pct") or 0) / 100, 2)
                if i.issue_size and m.get("ofs_pct") is not None else None),
            "OFS size"),
        "face_value": _env(scraped.get("face_value"), "face value"),
        "employee_discount": scraped.get("employee_discount"),
    }

    pre = m.get("preipo_price")
    pre_compare = {
        "preipo_price": _env(pre, "pre-IPO unlisted price"),
        "offer_price": _env(offer or None, "IPO offer price"),
        "premium_pct": _env(round((offer / pre - 1) * 100, 2)
                            if pre and offer else None,
                            "offer premium over pre-IPO price"),
        "note": ("The pre-IPO price is the last unlisted-market transaction disclosed "
                 "in the offer documents. It is not a live unlisted quote."),
    }

    lead = scraped.get("lead_managers") or (m.get("brlm") or [])
    brlm = [{"name": name, "deals": None,
             "track_record": "Book-running lead manager named in the offer document."}
            for name in lead if name]

    # Financials: scraped offer-document table, else the curated seed.
    financials = []
    for f in (scraped.get("financials") or m.get("financials") or []):
        roe = None
        if f.get("pat") is not None and f.get("net_worth"):
            roe = round(f["pat"] / f["net_worth"] * 100, 2)
        financials.append({
            "period": f.get("period"),
            "revenue": _env(f.get("revenue"), "revenue"),
            "pat": _env(f.get("pat"), "profit after tax"),
            "ebitda": _env(f.get("ebitda"), "EBITDA"),
            "net_worth": _env(f.get("net_worth"), "net worth"),
            "borrowing": _env(f.get("borrowing"), "total borrowing"),
            "roe_pct": _env(roe, "return on equity"),
        })

    # Peer valuation: curated peers, else a sector proxy from the live universe.
    peers = m.get("peers") or []
    if not peers:
        peers = _sector_proxy(db, i)

    # Subscription: live report wins, then seeded offer-document numbers.
    sub_detail = {
        "qib": _env(live_sub.get("qib") or (m.get("subscription") or {}).get("qib"),
                    "QIB subscription"),
        "bnii": _env(live_sub.get("bnii") or (m.get("subscription") or {}).get("bnii"),
                     "bNII subscription"),
        "snii": _env(live_sub.get("snii") or (m.get("subscription") or {}).get("snii"),
                     "sNII subscription"),
        "retail": _env(live_sub.get("retail") or (m.get("subscription") or {}).get("retail"),
                       "retail subscription"),
        "employee": _env((m.get("subscription") or {}).get("employee"),
                         "employee subscription"),
        "total": _env(live_sub.get("total") or (m.get("subscription") or {}).get("total"),
                      "total subscription"),
        "anchor": live_sub.get("anchor"),
        "pe": _env(live_sub.get("pe"), "post-issue P/E"),
        "updated": scraped.get("source") or m.get("updated_on"),
    }

    # Lot-size application calculator. 1 retail lot, 14 sNII lots (₹2–10 L),
    # 68 bNII lots (above ₹10 L) are the standard SEBI application slabs.
    lot = i.lot_size or 0
    price = i.price_band_high or 0
    def chance(sub_key: str) -> float | None:
        v = (live_sub.get(sub_key) or (m.get("subscription") or {}).get(sub_key))
        if not v or v <= 0:
            return None
        return round(min(1.0, 1.0 / v) * 100, 2)
    lot_calc = {
        "lot_size": lot,
        "price": price,
        "retail": {"label": "Retail · 1 lot", "lots": 1,
                   "shares": lot, "amount": round(lot * price, 2),
                   "allotment_chance_pct": chance("retail")},
        "snii": {"label": "sNII · 14 lots", "lots": 14,
                 "shares": lot * 14, "amount": round(lot * 14 * price, 2),
                 "allotment_chance_pct": chance("snii")},
        "bnii": {"label": "bNII · 68 lots", "lots": 68,
                 "shares": lot * 68, "amount": round(lot * 68 * price, 2),
                 "allotment_chance_pct": chance("bnii")},
        "note": ("Application slabs follow SEBI's retail (up to ₹2 lakh), sNII "
                 "(₹2–10 lakh) and bNII (above ₹10 lakh) buckets. The chance is a "
                 "simple 1 ÷ category-subscription estimate, before the lottery."),
    }

    return {
        **base,
        "issue_structure": struct,
        "business_overview": scraped.get("about") or i.note or
        "The company's business description is not published in the free offer-document feed.",
        "gmp_history": scraped.get("gmp_history") or [],
        "subscription_detail": sub_detail,
        "lot_calculator": lot_calc,
        "ofs_selling_shareholders": sellers,
        "preipo_comparison": pre_compare,
        "merchant_bankers": brlm,
        "financials": financials,
        "kpis": scraped.get("kpis") or [],
        "peers": peers,
        "issue_objects": scraped.get("objects") or [],
        "registrar_link": base.get("registrar_url"),
        "anchor_lockin": {
            "30_day": m.get("anchor_lockin_30"),
            "90_day": m.get("anchor_lockin_90"),
            "note": "Anchor investors are locked in for 30 days on half the allocation "
                    "and 90 days on the remainder.",
        },
        "source_notes": [
            "GMP, subscription and listing prints are scraped live from "
            "InvestorGain's public report; GMP is unofficial and unregulated.",
            "Issue structure, objects and financials are from the exchange offer "
            "document reproduced on the IPO page.",
            "Post-listing price is a live/delayed Yahoo quote where the stock is "
            "already trading, otherwise the InvestorGain listing print.",
        ],
    }


def _sector_proxy(db: Session, i: Ipo) -> list[dict]:
    """Listed peers from the local universe when the offer page has no peer table."""
    name = i.name.lower()
    keywords = {
        "jio": "Telecom", "telecom": "Telecom", "platform": "Technology",
        "technolog": "Technology", "software": "Technology", "digital": "Technology",
        "finance": "Financial Services", "bank": "Financial Services",
        "capital": "Financial Services", "insurance": "Financial Services",
        "pharma": "Pharmaceuticals", "medical": "Pharmaceuticals",
        "health": "Healthcare", "hospital": "Healthcare",
        "steel": "Metals & Mining", "metal": "Metals & Mining",
        "power": "Power", "energy": "Power", "solar": "Power",
        "auto": "Automobile", "engineering": "Capital Goods",
        "electrical": "Capital Goods", "chemical": "Chemicals",
        "jewel": "Consumer Goods", "fashion": "Consumer Goods",
        "retail": "Consumer Goods", "food": "FMCG",
        "infra": "Infrastructure", "construction": "Infrastructure",
        "realty": "Real Estate", "housing": "Real Estate",
    }
    sector = next((v for k, v in keywords.items() if k in name), None)
    if not sector:
        return []
    rows = (db.query(Instrument)
              .filter(Instrument.kind == "EQUITY",
                      Instrument.sector.ilike(f"%{sector.split()[0]}%"))
              .limit(6).all())
    out = []
    for r in rows:
        m = r.meta or {}
        out.append({"name": r.name, "symbol": r.symbol,
                    "pe": _env(m.get("pe"), "P/E"),
                    "pb": _env(m.get("pb"), "P/B"),
                    "last": _env(m.get("lastPrice"), "price"),
                    "note": "Listed sector peer (proxy)"})
    return out


@router.post("/refresh-live")
def refresh_live(db: Session = Depends(get_db)):
    IG.live_gmp(force=True)
    IG.live_subscription(force=True)
    return _sync_live(db)


@router.post("/upsert")
def upsert_ipo(payload: dict, db: Session = Depends(get_db)):
    row = Ipo(name=payload.get("name") or "", symbol=payload.get("symbol"),
              board=payload.get("board", "MAINBOARD"),
              status=payload.get("status", "UPCOMING"),
              open_date=payload.get("open"), close_date=payload.get("close"),
              listing_date=payload.get("listing"),
              price_band_low=payload.get("price_low"),
              price_band_high=payload.get("price_high"),
              lot_size=payload.get("lot"), issue_size=payload.get("size"),
              registrar=payload.get("registrar"), meta=payload.get("meta") or {})
    db.add(row)
    db.commit()
    return {"ok": True, "id": row.id}
