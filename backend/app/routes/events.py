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
    rows = db.query(CorporateEvent).all()

    def bucket(k: str) -> str:
        return CATEGORY_MAP.get((k or "").upper(), (k or "OTHER").upper())

    if kind and kind.lower() != "all":
        want = kind.upper()
        rows = [e for e in rows
                if bucket(e.kind) == want or e.kind.upper() == want
                or TAB_LABELS.get(want, "").lower() in (e.kind or "").lower()]
    if q:
        needle = q.strip().lower()
        rows = [e for e in rows if needle in (e.company or "").lower()
                or needle in (e.symbol or "").lower()]

    start, end = _window_bounds(window)
    if start:
        rows = [e for e in rows if e.ex_date and e.ex_date >= start]
    if end:
        rows = [e for e in rows if e.ex_date and e.ex_date <= end]

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
