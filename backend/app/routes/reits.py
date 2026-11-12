"""REITs & InvITs — six listed trusts with live prices, five-year history,
operating metrics (occupancy/WALE/cap rate/NDCF yield/Debt-GAV), on-demand
peer comparison and a four-component post-tax distribution calculator."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.data.adapters import yfinance_adapter as Y
from app.models.models import Instrument
from app.services import calc
from app.services import instrument_engine as IE
from app.services.contextual import not_applicable, not_disclosed, reported, source_issue

router = APIRouter(prefix="/reits", tags=["reits & invit s (trusts)"])


def _env(v, what="metric"):
    return reported(v) if v is not None else source_issue(what)


def _row(r: Instrument) -> dict:
    m = r.meta or {}
    price = m.get("lastPrice")
    dist = m.get("distribution_split") or {}
    return {
        "symbol": r.symbol, "name": r.name, "kind": r.kind,
        "last": _env(price, "trust price"),
        "changepct": _env(m.get("changepct"), "day change"),
        "prev_close": _env(m.get("prevClose"), "previous close"),
        "week52_high": _env(m.get("week52_high") or m.get("yearHigh"), "52-week high"),
        "week52_low": _env(m.get("week52_low") or m.get("yearLow"), "52-week low"),
        "spark": IE.sparkline(r),
        "asof": _env(m.get("asof"), "price date"),
        "market_cap": _env(m.get("marketCap"), "market cap"),
        "listing_date": _env(m.get("listingDate"), "listing date"),
        "occupancy_pct": _env(m.get("occupancy_pct"), "occupancy"),
        "wale_years": _env(m.get("wale_years"), "WALE"),
        "cap_rate_pct": _env(m.get("cap_rate_pct"), "cap rate"),
        "ndcf_yield_pct": _env(m.get("ndcf_yield_pct"), "NDCF distribution yield"),
        "debt_gav_pct": _env(m.get("debt_gav_pct"), "debt to GAV"),
        "nav_per_unit": _env(m.get("nav_per_unit"), "NAV per unit"),
        "distribution_split": dist,
        "distribution_rule": reported(
            "SEBI requires REITs/InvITs to distribute at least 90% of Net "
            "Distributable Cash Flows to unitholders."),
        "yield": _env(m.get("ndcf_yield_pct"), "distribution yield"),
        "facts_asof": m.get("facts_asof"),
        "href": f"/reits/{r.symbol}",
    }


@router.get("")
def list_reits(db: Session = Depends(get_db)):
    rows = (db.query(Instrument)
              .filter(Instrument.kind.in_(("REIT", "INVIT"))).all())
    IE.ensure_many(db, rows)
    items = [_row(r) for r in rows]
    items.sort(key=lambda x: x["symbol"])
    return {
        "count": len(items), "reits": items,
        "feed_status": reported("Yahoo Finance (.NS) EOD + latest disclosed facts"),
        "explain": ("REITs own rent-cash-flowing commercial parks; InvITs own "
                    "cash-flowing road/power infrastructure. Both must distribute "
                    "at least 90% of net distributable cash flows to unitholders. "
                    "Occupancy is only meaningful for REITs; for InvITs it is the "
                    "availability factor."),
    }


@router.get("/{symbol}/intraday")
def trust_intraday(symbol: str, interval: str = "2m",
                   db: Session = Depends(get_db)):
    row = (db.query(Instrument)
             .filter(Instrument.kind.in_(("REIT", "INVIT")),
                     Instrument.symbol == symbol.upper()).one_or_none())
    if not row:
        raise HTTPException(404, "This trust is not in the seeded REIT/InvIT universe.")
    IE.ensure_instrument_ready(db, row)
    from app.services import instant_intraday as II

    return II.get_intraday(db, row, f"{row.symbol}.NS", interval=interval)


@router.get("/{symbol}")
def trust_detail(symbol: str, db: Session = Depends(get_db)):
    row = (db.query(Instrument)
             .filter(Instrument.kind.in_(("REIT", "INVIT")),
                     Instrument.symbol == symbol.upper()).one_or_none())
    if not row:
        raise HTTPException(404, "This trust is not in the seeded REIT/InvIT universe.")
    IE.ensure_instrument_ready(db, row)
    base = _row(row)
    hist = row.history or []
    closes = [h["c"] for h in hist]
    rets = calc.nav_returns([{"date": h["date"], "nav": h["c"]} for h in hist])
    peers = []
    for p in (db.query(Instrument)
                .filter(Instrument.kind == row.kind,
                        Instrument.symbol != row.symbol).all()):
        pm = p.meta or {}
        peers.append({"symbol": p.symbol, "name": p.name,
                      "last": _env(pm.get("lastPrice"), "price"),
                      "ndcf_yield_pct": _env(pm.get("ndcf_yield_pct"), "yield"),
                      "occupancy_pct": _env(pm.get("occupancy_pct"), "occupancy"),
                      "cap_rate_pct": _env(pm.get("cap_rate_pct"), "cap rate"),
                      "debt_gav_pct": _env(pm.get("debt_gav_pct"), "debt/GAV"),
                      "href": f"/reits/{p.symbol}"})
    return {
        **base,
        "history": [{"date": h["date"], "close": h["c"], "open": h.get("o"),
                     "high": h.get("h"), "low": h.get("l")} for h in hist],
        "history_points": len(hist),
        "returns": {k: _env(v, f"{k.upper()} return") for k, v in rets.items()},
        "stats": {
            "vol_annual": _env(calc.annual_volatility(closes[-252:]) if closes else None,
                               "annual volatility"),
            "max_dd_5y": _env(calc.max_drawdown(closes) if closes else None, "max drawdown"),
            "cagr_5y": _env(calc.cagr(closes[0], closes[-1], len(closes) / 252)
                            if closes else None, "5Y CAGR"),
        },
        "peers": peers,
        "source_notes": [
            "Price and history come from Yahoo Finance (.NS), labelled EOD/delayed.",
            row.meta.get("operating_note") or "Operating metrics are latest disclosed figures.",
            "Occupancy is not applicable to InvITs; their availability factor is shown instead.",
            "Distribution components are the trust's disclosed split and vary by quarter.",
        ],
    }


class DistributionBody(BaseModel):
    units: float = 1000
    price_per_unit: float = 100.0
    distribution_per_unit: float = 7.0
    interest_pct: float = 45.0
    dividend_pct: float = 30.0
    amortization_pct: float = 20.0
    other_pct: float = 5.0
    tax_slab_pct: float = 30.0


@router.post("/{symbol}/distribution-calculator")
def distribution_calculator(symbol: str, body: DistributionBody,
                            db: Session = Depends(get_db)):
    row = (db.query(Instrument)
             .filter(Instrument.kind.in_(("REIT", "INVIT")),
                     Instrument.symbol == symbol.upper()).one_or_none())
    if not row:
        raise HTTPException(404, "Trust not found.")
    total = body.distribution_per_unit * body.units
    split = {
        "interest": round(total * body.interest_pct / 100, 2),
        "dividend": round(total * body.dividend_pct / 100, 2),
        "amortization": round(total * body.amortization_pct / 100, 2),
        "other": round(total * body.other_pct / 100, 2),
    }
    # Interest, dividend and other income are taxable at slab; amortization is
    # a return of capital (reduces cost basis, not taxed now).
    taxable = split["interest"] + split["dividend"] + split["other"]
    tax = round(taxable * body.tax_slab_pct / 100, 2)
    post_tax = round(total - tax, 2)
    invested = body.units * body.price_per_unit
    return {
        "symbol": row.symbol, "total_distribution": round(total, 2),
        "split": split, "taxable_component": round(taxable, 2),
        "tax_at_slab": tax, "tax_free_component": split["amortization"],
        "post_tax_distribution": post_tax,
        "pre_tax_yield_pct": round(total / invested * 100, 2) if invested else None,
        "post_tax_yield_pct": round(post_tax / invested * 100, 2) if invested else None,
        "note": ("Interest, dividend and other income are taxed at your slab; the "
                 "amortization component is a return of capital and reduces cost "
                 "basis instead of being taxed now. REIT/InvIT units held over 12 "
                 "months can also attract 12.5% LTCG on the unit price gain. A model, "
                 "not tax advice."),
    }
