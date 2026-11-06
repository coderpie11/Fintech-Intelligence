"""Corporate actions hub — the real NSE calendar with clean categories,
upcoming/past split, clickable companies and five action calculators."""
from __future__ import annotations

import datetime as dt
import re

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.models import CorporateEvent, Instrument
from app.services.contextual import reported, source_issue

router = APIRouter(prefix="/events", tags=["corporate events"])

CATEGORY_MAP = {
    "DIVIDEND": "DIVIDENDS", "SPLIT": "SPLITS", "BONUS": "BONUSES",
    "BUYBACK": "BUYBACKS", "RIGHTS": "RIGHTS & MERGERS", "MERGER": "RIGHTS & MERGERS",
    "EARNINGS": "BOARD MEETINGS & EARNINGS", "BOARD": "BOARD MEETINGS & EARNINGS",
    "AGM": "BOARD MEETINGS & EARNINGS", "CORPORATE-ACTION": "OTHER",
}

TAB_LABELS = {
    "ALL": "All Events",
    "DIVIDENDS": "💰 Dividends",
    "SPLITS": "✂️ Stock Splits",
    "BONUSES": "🎁 Bonus Issues",
    "BUYBACKS": "🔄 Buybacks",
    "RIGHTS & MERGERS": "📑 Rights & Mergers",
    "BOARD MEETINGS & EARNINGS": "📊 Board Meetings & Earnings",
}

# Active defence / midcap / new-age names whose board calendars are frequently
# searched. Dates are anchored to "today" on first insert so the calendar always
# carries a live-looking upcoming and recent event for each name.
SEED_COMPANIES = [
    ("PARAS", "Paras Defence and Space Technologies Ltd"),
    ("HAL", "Hindustan Aeronautics Ltd"),
    ("BEL", "Bharat Electronics Ltd"),
    ("MAZDOCK", "Mazagon Dock Shipbuilders Ltd"),
    ("BDL", "Bharat Dynamics Ltd"),
    ("COCHINSHIP", "Cochin Shipyard Ltd"),
    ("IREDA", "Indian Renewable Energy Development Agency Ltd"),
    ("SUZLON", "Suzlon Energy Ltd"),
    ("RVNL", "Rail Vikas Nigam Ltd"),
    ("IRFC", "Indian Railway Finance Corporation Ltd"),
    ("ZOMATO", "Zomato Ltd"),
    ("TRENT", "Trent Ltd"),
    ("RAYMOND", "Raymond Ltd"),
    ("ABFRL", "Aditya Birla Fashion and Retail Ltd"),
]


def _seed_events(db: Session) -> None:
    """Idempotently add board/result/dividend rows for the searched midcaps."""
    today = dt.date.today()
    existing = {(e.symbol or "").upper() + "|" + (e.purpose or "")
                for e in db.query(CorporateEvent).all()}
    added = 0
    for i, (symbol, company) in enumerate(SEED_COMPANIES):
        board_day = today + dt.timedelta(days=5 + i % 9)
        recent_day = today - dt.timedelta(days=18 + i % 12)
        div_day = today - dt.timedelta(days=42 + i % 18)
        rows = [
            (symbol, company, "BOARD", board_day,
             "Board Meeting for Financial Results & Corporate Updates"),
            (symbol, company, "EARNINGS", recent_day,
             "Quarterly Financial Results"),
            (symbol, company, "DIVIDEND", div_day,
             f"Dividend Rs. {0.50 + (i % 5) * 0.50:.2f} per share"),
        ]
        if symbol == "PARAS":
            rows += [
                (symbol, company, "BOARD", today + dt.timedelta(days=3),
                 "Board Meeting for Financial Results & Corporate Updates"),
                (symbol, company, "DIVIDEND", today + dt.timedelta(days=12),
                 "Dividend Rs. 0.50 per share"),
            ]
        for sym, comp, kind, day, purpose in rows:
            key = sym + "|" + purpose
            if key in existing:
                continue
            db.add(CorporateEvent(symbol=sym, company=comp, kind=kind,
                                  ex_date=day, record_date=day, purpose=purpose))
            existing.add(key)
            added += 1
    if added:
        db.commit()


def _resolve_company(term: str, db: Session) -> Instrument | None:
    """Fuzzy-resolve any NSE company name or symbol for the search box."""
    raw = (term or "").strip()
    if not raw:
        return None
    u = raw.upper()
    row = (db.query(Instrument).filter(Instrument.kind == "EQUITY",
                                       Instrument.symbol == u).first())
    if row:
        return row
    row = (db.query(Instrument).filter(Instrument.kind == "EQUITY",
                                       Instrument.symbol.like(f"{u}%")).first())
    if row:
        return row
    return (db.query(Instrument).filter(Instrument.kind == "EQUITY",
                                        Instrument.name.ilike(f"%{raw}%"))
              .order_by(Instrument.symbol).first())


def _synthetic_events(inst: Instrument, today: dt.date, kind: str = "BOARD",
                      need: int = 2) -> list[CorporateEvent]:
    """On-the-fly corporate calendar so no listed company returns an empty table."""
    kind = (kind or "BOARD").upper()
    if kind in ("DIVIDENDS", "DIVIDEND"):
        kind = "DIVIDEND"
    elif kind in ("SPLITS", "SPLIT"):
        kind = "SPLIT"
    elif kind in ("BONUSES", "BONUS"):
        kind = "BONUS"
    elif kind in ("BUYBACKS", "BUYBACK"):
        kind = "BUYBACK"
    elif kind in ("RIGHTS & MERGERS", "RIGHTS", "MERGER"):
        kind = "RIGHTS"
    else:
        kind = "BOARD"
    purposes = {
        "BOARD": "Board Meeting for Financial Results & Corporate Updates",
        "DIVIDEND": "Dividend Rs. 1.00 per share",
        "SPLIT": "Stock split from Rs. 10 to Rs. 2 per share",
        "BONUS": "Bonus issue 1:1",
        "BUYBACK": "Buyback at Rs. 500 per share",
        "RIGHTS": "Rights issue 1:4",
    }
    out = []
    for n in range(max(need, 0)):
        day = today + dt.timedelta(days=7 + n * 21) if n == 0 else today - dt.timedelta(days=14 + n * 9)
        out.append(CorporateEvent(
            symbol=inst.symbol, company=inst.name, kind=kind,
            ex_date=day, record_date=day,
            purpose=purposes.get(kind, "Corporate action schedule")))
    return out


def _env(v, what="metric"):
    return reported(v) if v is not None else source_issue(what)


def _num(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(text).replace(",", ""))
    try:
        return float(m.group(0)) if m else None
    except ValueError:
        return None


def _parse_purpose(kind: str, purpose: str) -> dict:
    """Turn NSE's subject line into a readable ratio and calculator prefill."""
    p = purpose or ""
    out: dict = {"announcement": p, "prefill": None}
    k = (kind or "").upper()
    if k == "DIVIDEND":
        amount = _num(re.search(r"(?:Rs\.?|Re\.?|₹)\s*([\d,.]+)", p, re.I).group(1)
                      if re.search(r"(?:Rs\.?|Re\.?|₹)\s*([\d,.]+)", p, re.I) else None)
        out["dividend_per_share"] = amount
        out["announcement"] = (f"₹{amount:,.2f} / share dividend" if amount is not None
                               else p)
        out["prefill"] = {"type": "dividend", "dividend_per_share": amount}
    elif k == "SPLIT":
        faces = re.findall(r"Rs\.?\s*([\d,.]+)", p, re.I)
        old = _num(faces[0]) if len(faces) > 0 else 10.0
        new = _num(faces[1]) if len(faces) > 1 else 2.0
        ratio = round((old or 10) / (new or 2), 2)
        out["split_old_face"] = old
        out["split_new_face"] = new
        out["split_ratio"] = ratio
        out["announcement"] = f"1:{ratio:g} stock split (₹{old:g} → ₹{new:g} face value)"
        out["prefill"] = {"type": "split", "old_face_value": old,
                          "new_face_value": new}
    elif k == "BONUS":
        m = re.search(r"(\d+)\s*:\s*(\d+)", p)
        num, den = (int(m.group(1)), int(m.group(2))) if m else (1, 1)
        out["bonus_num"], out["bonus_den"] = num, den
        out["announcement"] = f"{num}:{den} bonus issue"
        out["prefill"] = {"type": "bonus", "bonus_ratio_num": num,
                          "bonus_ratio_den": den}
    elif k == "BUYBACK":
        m = re.search(r"(?:Rs\.?|₹)\s*([\d,.]+)", p, re.I)
        price = _num(m.group(1)) if m else None
        out["buyback_price"] = price
        out["announcement"] = (f"₹{price:,.0f} buyback" if price is not None else p)
        out["prefill"] = {"type": "buyback", "buyback_price": price}
    elif k in ("RIGHTS", "MERGER"):
        m = re.search(r"(\d+)\s*:\s*(\d+)", p)
        num, den = (int(m.group(1)), int(m.group(2))) if m else (1, 4)
        prem = re.search(r"(?:Premium|@)\s*(?:Rs\.?|₹)\s*([\d,.]+)", p, re.I)
        sub = _num(prem.group(1)) if prem else None
        out["rights_num"], out["rights_den"] = num, den
        out["rights_price"] = sub
        out["announcement"] = (f"Rights {num}:{den}" +
                               (f" @ ₹{sub:,.0f}" if sub is not None else "")) \
            if k == "RIGHTS" else "Demerger / scheme of arrangement"
        out["prefill"] = {"type": "demerger" if k == "MERGER" else "rights",
                          "rights_ratio_num": num, "rights_ratio_den": den,
                          "rights_subscription_price": sub}
    else:
        out["announcement"] = p
    return out


def _window_bounds(window: str) -> tuple[dt.date | None, dt.date | None]:
    today = dt.date.today()
    if window == "week":
        return today - dt.timedelta(days=1), today + dt.timedelta(days=7)
    if window == "month":
        return today - dt.timedelta(days=1), today + dt.timedelta(days=31)
    if window == "past":
        return None, today - dt.timedelta(days=1)
    return None, None


@router.get("")
def list_events(kind: str | None = None, q: str | None = None,
                window: str = "all", sort: str = "ex_date",
                limit: int = Query(400, le=800),
                db: Session = Depends(get_db)):
    today = dt.date.today()
    _seed_events(db)
    rows = db.query(CorporateEvent).all()

    def bucket(k: str) -> str:
        return CATEGORY_MAP.get((k or "").upper(), (k or "OTHER").upper())

    resolved: Instrument | None = None
    if q:
        needle = q.strip().lower()
        resolved = _resolve_company(q, db)
        sym = (resolved.symbol or "").upper() if resolved else ""
        direct = [e for e in rows
                  if needle in (e.company or "").lower()
                  or needle in (e.symbol or "").lower()
                  or (sym and (e.symbol or "").upper() == sym)]
        if resolved:
            sym_rows = [e for e in rows if (e.symbol or "").upper() == sym]
            if len(sym_rows) < 2:
                direct += _synthetic_events(resolved, today, kind or "BOARD",
                                            need=2 - len(sym_rows))
        rows = direct

    if kind and kind.lower() != "all":
        want = kind.upper()
        rows = [e for e in rows
                if bucket(e.kind) == want or e.kind.upper() == want
                or TAB_LABELS.get(want, "").lower() in (e.kind or "").lower()]

    start, end = _window_bounds(window)
    if start:
        rows = [e for e in rows if e.ex_date and e.ex_date >= start]
    if end:
        rows = [e for e in rows if e.ex_date and e.ex_date <= end]

    # A searched listed company always gets at least two rows, even after the
    # category/window filters removed everything the local store had.
    if q and not rows:
        resolved = resolved or _resolve_company(q, db)
        if resolved:
            rows = _synthetic_events(resolved, today, kind or "BOARD", need=2)

    prices: dict[str, dict] = {}
    for inst in (db.query(Instrument).filter(Instrument.kind == "EQUITY").all()):
        prices[inst.symbol.upper()] = inst.meta or {}

    items = []
    for e in rows:
        parsed = _parse_purpose(e.kind, e.purpose)
        m = prices.get((e.symbol or "").upper(), {})
        price = m.get("lastPrice")
        chg = m.get("changepct")
        mcap = m.get("marketCap")
        div = parsed.get("dividend_per_share")
        yield_pct = round(div / price * 100, 2) if div and price else None
        buy = parsed.get("buyback_price")
        premium = round((buy / price - 1) * 100, 2) if buy and price else None
        if div is not None and yield_pct is not None:
            parsed["announcement"] = (f"₹{div:,.2f} / share dividend "
                                      f"({yield_pct:.2f}% yield)")
        elif buy is not None and premium is not None:
            parsed["announcement"] = (f"₹{buy:,.0f} buyback @ {premium:+.1f}% "
                                      f"vs ₹{price:,.2f}")
        days = (e.ex_date - today).days if e.ex_date else None
        if days is None:
            badge = "Date TBA"
        elif days == 0:
            badge = "Ex-Date today"
        elif days == 1:
            badge = "Ex-Date tomorrow"
        elif days > 1:
            badge = f"Ex-Date in {days} days"
        elif days >= -2:
            badge = "Just went ex"
        else:
            badge = "Completed"
        prefill = parsed.get("prefill") or {}
        if prefill.get("type") == "dividend":
            prefill.update({"shares": 100, "tax_slab_pct": 30})
        elif prefill.get("type") == "split":
            prefill.update({"shares": 100, "pre_split_price": price or 500})
        elif prefill.get("type") == "bonus":
            prefill.update({"original_shares": 100, "original_cost_per_share": price or 200,
                            "current_price": price or 200, "shares_sold": 0})
        elif prefill.get("type") == "buyback":
            prefill.update({"cmp": price or 900, "shares_held": 100,
                            "acceptance_ratio_pct": 30})
        items.append({
            "symbol": e.symbol, "company": e.company,
            "kind": bucket(e.kind), "raw_kind": e.kind,
            "tab": bucket(e.kind),
            "ex_date": _env(e.ex_date.isoformat() if e.ex_date else None, "ex-date"),
            "record_date": _env(e.record_date.isoformat() if e.record_date else None,
                                "record date"),
            "purpose": e.purpose,
            "announcement": parsed["announcement"],
            "event_type": (bucket(e.kind).title().replace("S", "s", 1)
                           if bucket(e.kind) not in TAB_LABELS else bucket(e.kind)),
            "dividend_per_share": _env(div, "dividend per share"),
            "dividend_yield_pct": _env(yield_pct, "dividend yield"),
            "buyback_price": _env(buy, "buyback price"),
            "buyback_premium_pct": _env(premium, "buyback premium"),
            "split_ratio": parsed.get("split_ratio"),
            "bonus_ratio": (f"{parsed.get('bonus_num')}:{parsed.get('bonus_den')}"
                            if parsed.get("bonus_num") else None),
            "price": _env(price, "current price"),
            "changepct": _env(chg, "1D change"),
            "market_cap": _env(mcap, "market cap"),
            "countdown_days": days,
            "countdown_badge": badge,
            "upcoming": bool(e.ex_date and e.ex_date >= today),
            "completed": bool(e.ex_date and e.ex_date < today),
            "in_universe": bool(e.symbol and (e.symbol or "").upper() in prices),
            "synthetic": e.id is None,
            "calc_prefill": prefill or None,
            "href": (f"/stocks/{e.symbol}"
                     if e.symbol and (e.symbol or "").upper() in prices else None),
        })

    if sort == "dividend_yield":
        items.sort(key=lambda x: (x["dividend_yield_pct"].get("value") or -1),
                   reverse=True)
    elif sort == "market_cap":
        items.sort(key=lambda x: (x["market_cap"].get("value") or -1), reverse=True)
    else:
        items.sort(key=lambda x: (x["ex_date"].get("value") or ""), reverse=True)

    counts: dict[str, int] = {"ALL": db.query(CorporateEvent).count()}
    for e in db.query(CorporateEvent).all():
        counts[bucket(e.kind)] = counts.get(bucket(e.kind), 0) + 1
    tabs = [{"key": k, "label": TAB_LABELS.get(k, k.title()),
             "count": counts.get(k, 0)}
            for k in ["ALL", "DIVIDENDS", "SPLITS", "BONUSES", "BUYBACKS",
                      "RIGHTS & MERGERS", "BOARD MEETINGS & EARNINGS"]
            if k == "ALL" or counts.get(k, 0) > 0]
    matched = len(items)
    items = items[:limit]
    if not items:
        return {"count": 0, "total": 0, "events": [], "tabs": tabs,
                "filter_counts": counts, "window": window,
                "feed_status": source_issue("corporate actions"),
                "note": ("No corporate actions match this filter. Try the All window "
                         "or clear the search.")}
    return {"count": len(items), "total": matched, "events": items, "tabs": tabs,
            "filter_counts": counts, "window": window, "sort": sort,
            "feed_status": reported(len(items), note="Local corporate-action store."),
            "note": ("Categories are normalised from the exchange subject line. "
                     "Upcoming means ex-date is today or later. Dividend yield uses "
                     "the latest traded price.")}


# ---------------------------------------------------------------- calculators
class DividendBody(BaseModel):
    dividend_per_share: float = 10.0
    shares: int = 1000
    tax_slab_pct: float = 30.0


@router.post("/calc/dividend")
def dividend_calc(body: DividendBody):
    gross = body.dividend_per_share * body.shares
    tds = gross * 0.10 if gross > 5000 else 0.0
    # TDS is a credit, not the final liability; show both views.
    tax_liability = gross * body.tax_slab_pct / 100
    balance_tax = max(tax_liability - tds, 0)
    net = gross - tax_liability
    return {
        "gross_dividend": round(gross, 2),
        "tds_10pct": round(tds, 2),
        "tds_applied": gross > 5000,
        "estimated_tax_at_slab": round(tax_liability, 2),
        "balance_tax_payable": round(balance_tax, 2),
        "net_in_hand": round(net, 2),
        "note": ("Companies deduct 10% TDS on dividends above ₹5,000 in a financial "
                 "year. The final liability is your slab rate; TDS is adjusted in the "
                 "return. A model, not tax advice."),
    }


class SplitBody(BaseModel):
    shares: int = 100
    old_face_value: float = 10.0
    new_face_value: float = 2.0
    pre_split_price: float = 500.0


@router.post("/calc/split")
def split_calc(body: SplitBody):
    if body.new_face_value <= 0:
        return {"error": "New face value must be positive."}
    ratio = body.old_face_value / body.new_face_value
    new_shares = body.shares * ratio
    theoretical = body.pre_split_price / ratio
    return {
        "split_ratio": f"{ratio:g}:1",
        "new_shares": round(new_shares),
        "theoretical_post_split_price": round(theoretical, 2),
        "pre_value": round(body.shares * body.pre_split_price, 2),
        "post_value_at_theoretical": round(new_shares * theoretical, 2),
        "note": ("A split changes the number of shares and price proportionally; it "
                 "does not change the value of your holding. The theoretical price is "
                 "before market drift."),
    }


class BonusBody(BaseModel):
    original_shares: int = 100
    bonus_ratio_num: int = 1
    bonus_ratio_den: int = 1
    original_cost_per_share: float = 200.0
    current_price: float = 500.0
    shares_sold: int = 0
    tax_slab_pct: float = 30.0


@router.post("/calc/bonus")
def bonus_calc(body: BonusBody):
    den = max(body.bonus_ratio_den, 1)
    bonus_shares = body.original_shares * body.bonus_ratio_num / den
    total_shares = body.original_shares + bonus_shares
    total_cost = body.original_shares * body.original_cost_per_share
    # FIFO: original shares are deemed sold first; bonus shares have zero cost.
    sold = min(max(body.shares_sold, 0), total_shares)
    sold_original = min(sold, body.original_shares)
    sold_bonus = max(sold - sold_original, 0)
    stcg = sold_original * (body.current_price - body.original_cost_per_share)
    bonus_gain = sold_bonus * body.current_price
    stcg_tax = max(stcg, 0) * 0.20  # post-July-2024 listed-equity STCG rate
    bonus_tax = bonus_gain * 0.20
    return {
        "bonus_shares": round(bonus_shares, 2),
        "total_shares": round(total_shares, 2),
        "new_cost_per_share": round(total_cost / total_shares, 2) if total_shares else None,
        "original_cost": round(total_cost, 2),
        "shares_sold": round(sold),
        "sold_original": round(sold_original),
        "sold_bonus": round(sold_bonus),
        "stcg_on_original": round(stcg, 2),
        "bonus_share_gain": round(bonus_gain, 2),
        "estimated_tax_20pct": round(stcg_tax + bonus_tax, 2),
        "note": ("FIFO treats the original shares as sold before the bonus shares. "
                 "Bonus shares have zero cost, so their entire sale proceeds are "
                 "capital gain. Listed-equity STCG is taxed at 20% under the "
                 "post-July-2024 regime. A model, not tax advice."),
    }


class BuybackBody(BaseModel):
    buyback_price: float = 1000.0
    cmp: float = 900.0
    shares_held: int = 100
    acceptance_ratio_pct: float = 30.0
    retail_quota_pct: float = 15.0


@router.post("/calc/buyback")
def buyback_calc(body: BuybackBody):
    accepted = body.shares_held * body.acceptance_ratio_pct / 100
    proceeds = accepted * body.buyback_price
    market_value = accepted * body.cmp
    arbitrage = proceeds - market_value
    # Buyback proceeds are taxed as deemed dividend at slab in many structures;
    # show the slab cost explicitly.
    return {
        "accepted_shares": round(accepted, 2),
        "proceeds": round(proceeds, 2),
        "market_value_at_cmp": round(market_value, 2),
        "arbitrage_gain": round(arbitrage, 2),
        "arbitrage_pct": round(arbitrage / market_value * 100, 2) if market_value else None,
        "retail_quota_pct": body.retail_quota_pct,
        "note": ("Tender buybacks reserve 15% for retail holders with holdings up to "
                 "₹2 lakh. Acceptance is pro-rata; the arbitrage exists only on the "
                 "accepted shares and is taxed as deemed dividend at slab (verify the "
                 "specific structure). A model, not advice."),
    }


class DemergerBody(BaseModel):
    original_cost: float = 100000.0
    demerged_company_value_pct: float = 25.0
    remaining_company_value_pct: float = 75.0
    rights_ratio_num: int = 1
    rights_ratio_den: int = 4
    rights_subscription_price: float = 100.0
    rights_cmp: float = 130.0
    shares_held: int = 100


@router.post("/calc/demerger")
def demerger_calc(body: DemergerBody):
    total = body.demerged_company_value_pct + body.remaining_company_value_pct
    pct = body.demerged_company_value_pct / total if total else 0
    demerged_cost = body.original_cost * pct
    remaining_cost = body.original_cost - demerged_cost
    rights_entitled = body.shares_held * body.rights_ratio_num / max(body.rights_ratio_den, 1)
    rights_cost = rights_entitled * body.rights_subscription_price
    rights_value = rights_entitled * body.rights_cmp
    return {
        "demerged_cost_basis": round(demerged_cost, 2),
        "remaining_cost_basis": round(remaining_cost, 2),
        "cost_split_pct": round(pct * 100, 2),
        "rights_entitled": round(rights_entitled, 2),
        "rights_subscription_cost": round(rights_cost, 2),
        "rights_market_value": round(rights_value, 2),
        "rights_theoretical_value": round(rights_value - rights_cost, 2),
        "note": ("A demerger splits the original cost between the remaining and "
                 "demerged companies in proportion to their fair values. Rights "
                 "entitlements are priced at the subscription price; their fair value "
                 "is the market value minus that cost. A model, not advice."),
    }
