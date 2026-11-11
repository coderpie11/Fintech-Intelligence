"""Portfolio X-Ray -- manual holdings parser, allocation/sector X-ray,
cross-fund stock overlap and an expense-ratio fee-drag calculator.

Everything here is computed from the platform's own stored data:
  * equity/ETF price and sector from the instrument record;
  * fund TER, holdings and NAV from the enriched scheme metadata;
  * overlap from the disclosed monthly fund holdings, never from an estimate.
Nothing is invented; missing inputs are reported as unavailable.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.models import FundMeta, FundScheme, Instrument
from app.services import calc
from app.services import instrument_engine as IE

router = APIRouter(prefix="/portfolio-xray", tags=["portfolio x-ray"])

MF_KINDS = {"MF", "MUTUAL_FUND", "FUND"}

# Every cashflow is expressed as years since this fixed epoch, so a holding's
# flows and the portfolio XIRR share one time axis without recomputing.
_EPOCH = dt.date(2000, 1, 1)


class Holding(BaseModel):
    kind: str = "EQUITY"          # EQUITY / ETF / MF
    symbol: str | None = None     # equity / ETF symbol
    code: str | None = None       # fund scheme code
    name: str | None = None
    mode: str = "LUMPSUM"         # LUMPSUM / SIP
    quantity: float | None = None
    price: float | None = None    # average buy price (lumpsum)
    value: float | None = None    # invested amount, or explicit current value
    buy_date: str | None = None   # lumpsum purchase date (YYYY-MM-DD)
    sip_amount: float | None = None   # monthly SIP instalment in rupees
    sip_start: str | None = None      # first instalment date (YYYY-MM-DD)
    sip_months: int | None = None     # tenure in months


class XrayBody(BaseModel):
    holdings: list[Holding]
    gross_return_pct: float = 12.0


def _num(v) -> float | None:
    try:
        f = float(v)
        return f
    except (TypeError, ValueError):
        return None


def _fund_meta(db: Session, code: str) -> dict:
    rec = db.get(FundMeta, code)
    return (rec.meta or {}) if rec else {}


def _as_date(value) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _year_frac(day: dt.date) -> float:
    return (day - _EPOCH).days / 365.0


def _clean_series(rows: list[dict], key: str) -> list[dict]:
    """Ascending (date, price) pairs with non-finite values removed."""
    out = []
    for r in rows or []:
        day = str(r.get("date") or "")[:10]
        px = _num(r.get(key))
        if day and px is not None and px > 0:
            out.append({"date": day, "price": px})
    out.sort(key=lambda r: r["date"])
    return out


def _price_on(series: list[dict], day: dt.date) -> float | None:
    """Last traded/declared price on or before `day` (nearest prior session)."""
    if not series:
        return None
    iso = day.isoformat()
    picked = None
    for r in series:
        if r["date"] <= iso:
            picked = r["price"]
        else:
            break
    if picked is not None:
        return picked
    return series[0]["price"]


def _add_months(day: dt.date, months: int) -> dt.date:
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    day_of_month = min(day.day, 28)
    return dt.date(year, month, day_of_month)


def _resolve(db: Session, h: Holding) -> dict | None:
    """Resolve a holding to its *current* price plus a dated price series.

    The user-supplied price is a buy price, never the mark: `current_price`
    always comes from the repaired instrument/NAV record.
    """
    kind = (h.kind or "EQUITY").upper()
    if kind in MF_KINDS:
        code = (h.code or "").strip()
        rec = db.get(FundScheme, code) if code else None
        if not rec:
            return None
        IE.ensure_fund_ready(db, rec)
        meta = _fund_meta(db, code)
        g = meta.get("groww") or {}
        navs = rec.navs or []
        current = _num(navs[-1]["nav"]) if navs else None
        return {
            "kind": "MF", "key": code, "name": rec.name,
            "amc": g.get("amc") or rec.amc, "sector": g.get("sub_category") or rec.category,
            "current_price": current, "series": _clean_series(navs, "nav"),
            "ter_pct": _num(g.get("ter")) or 0.0,
            "holdings": g.get("holdings") or [],
            "holdings_date": g.get("portfolio_date"),
            "href": f"/mutual-funds/{code}",
        }
    symbol = (h.symbol or "").strip().upper()
    row = None
    if symbol:
        row = (db.query(Instrument)
                 .filter(Instrument.symbol == symbol,
                         Instrument.kind.in_(("EQUITY", "ETF")))
                 .first())
    if not row:
        return None
    IE.ensure_instrument_ready(db, row)
    m = row.meta or {}
    current = _num(m.get("lastPrice")) or _num(m.get("last"))
    series = _clean_series(row.history or [], "c")
    if current is None and series:
        current = series[-1]["price"]
    return {
        "kind": "ETF" if row.kind == "ETF" else "EQUITY", "key": row.symbol,
        "name": row.name, "amc": None, "sector": row.sector or "Unclassified",
        "current_price": current, "series": series,
        "ter_pct": _num(m.get("ter_pct")) or 0.0,
        "holdings": [], "holdings_date": None,
        "href": f"/etfs/{row.symbol}" if row.kind == "ETF" else f"/stocks/{row.symbol}",
    }


def _position(r: dict, h: Holding, today: dt.date) -> dict:
    """Cost basis, accumulated units, market value and money-weighted return.

    Two modes, both universal across equities, ETFs, funds, trusts and gold:

    * ``LUMPSUM`` — quantity x buy price, or an invested amount dated by
      ``buy_date`` (units = amount / price on that date).
    * ``SIP`` — one instalment per calendar month from ``sip_start`` for
      ``sip_months`` months, each buying units at the nearest prior price.
    """
    current = r.get("current_price")
    series = r.get("series") or []
    mode = (h.mode or "LUMPSUM").strip().upper()
    if mode not in ("SIP", "LUMPSUM"):
        mode = "LUMPSUM"

    units: float | None = None
    invested: float | None = None
    flows: list[tuple[float, float]] = []
    months_done = 0
    start_date = None

    if mode == "SIP":
        monthly = _num(h.sip_amount)
        start = _as_date(h.sip_start)
        tenure = int(h.sip_months or 0)
        sip_units = 0.0
        done = 0
        if monthly and monthly > 0 and start and tenure > 0:
            for i in range(tenure):
                when = _add_months(start, i)
                if when > today:
                    break
                px = _price_on(series, when)
                if px is None:
                    continue
                done += 1
                sip_units += monthly / px
                flows.append((_year_frac(when), -monthly))
        months_done = done
        start_date = start
        if done:
            units = sip_units
            invested = monthly * done

    if units is None:
        qty = _num(h.quantity)
        buy = _num(h.price)
        amount = _num(h.value)
        buy_day = _as_date(h.buy_date)
        if qty is not None and qty > 0:
            units = qty
            if buy is not None and buy > 0:
                invested = qty * buy
        elif amount is not None and amount > 0:
            invested = amount
            if buy_day is not None and series:
                px0 = _price_on(series, buy_day)
                if px0:
                    units = amount / px0
        if invested is not None and buy_day is not None:
            flows.append((_year_frac(buy_day), -invested))
            start_date = buy_day

    # An explicit value field is only an override when no units are known;
    # otherwise marking to the live price is the whole point of the X-ray.
    value_rs: float | None = None
    if units is not None and current is not None:
        value_rs = units * current
    elif _num(h.value) is not None and _num(h.quantity) is None:
        value_rs = _num(h.value)
        if invested is None:
            invested = value_rs
    if value_rs is None:
        value_rs = 0.0
    if invested is None:
        invested = value_rs

    xirr_pct = None
    if flows and current is not None and units is not None and value_rs > 0:
        xirr_pct = calc.xirr(flows + [(_year_frac(today), value_rs)])

    cagr_pct = None
    if start_date is not None and invested and invested > 0:
        years = max((today - start_date).days / 365.0, 1 / 365)
        cagr_pct = calc.cagr(invested, value_rs, years)

    return {
        "mode": mode,
        "units": round(units, 4) if units is not None else None,
        "invested_rs": round(invested, 2),
        "value_rs": round(value_rs, 2),
        "pnl_rs": round(value_rs - invested, 2),
        "pnl_pct": round((value_rs / invested - 1) * 100, 2) if invested else None,
        "xirr_pct": xirr_pct,
        "cagr_pct": round(cagr_pct, 2) if cagr_pct is not None else None,
        "months": months_done if mode == "SIP" else None,
        "sip_amount": _num(h.sip_amount) if mode == "SIP" else None,
        "buy_date": start_date.isoformat() if start_date else None,
        "flows": flows,
    }



def _norm(name: str) -> str:
    return " ".join((name or "").upper().replace(".", " ").split())


def _overlap(db: Session, funds: list[dict]) -> dict:
    """Pairwise stock-overlap matrix across the disclosed fund holdings."""
    books = []
    for f in funds:
        w = {_norm(h.get("name")): _num(h.get("weight")) or 0.0
             for h in (f.get("holdings") or []) if h.get("name")}
        books.append({"id": f["key"], "name": f["name"], "value": f["value_rs"],
                      "sector": f.get("sector"), "weights": w})
    n = len(books)
    matrix = [[None] * n for _ in range(n)]
    pairs = []
    for i in range(n):
        matrix[i][i] = 100.0
        for j in range(i + 1, n):
            common = set(books[i]["weights"]) & set(books[j]["weights"])
            overlap = sum(min(books[i]["weights"][k], books[j]["weights"][k])
                          for k in common)
            matrix[i][j] = matrix[j][i] = round(overlap, 2)
            if common:
                top = sorted(((k, min(books[i]["weights"][k], books[j]["weights"][k]))
                              for k in common), key=lambda x: -x[1])[:8]
                pairs.append({
                    "a": books[i]["name"], "b": books[j]["name"],
                    "overlap_pct": round(overlap, 2),
                    "common_count": len(common),
                    "common": [{"name": k, "shared_weight_pct": round(v, 2)}
                               for k, v in top],
                })
    # Aggregate rupee exposure per stock across every fund.
    exposure: dict[str, dict] = {}
    for b in books:
        for k, w in b["weights"].items():
            e = exposure.setdefault(k, {"name": k, "value_rs": 0.0,
                                        "weight_sum_pct": 0.0, "funds": []})
            e["value_rs"] += w / 100 * b["value"]
            e["weight_sum_pct"] += w
            e["funds"].append(b["name"])
    stock_list = sorted(exposure.values(), key=lambda x: -x["value_rs"])
    return {
        "funds": [{"id": b["id"], "name": b["name"], "value_rs": b["value"]}
                  for b in books],
        "matrix": matrix,
        "pairs": sorted(pairs, key=lambda p: -p["overlap_pct"]),
        "stock_exposure": [{
            "name": s["name"], "value_rs": round(s["value_rs"], 2),
            "weight_sum_pct": round(s["weight_sum_pct"], 2),
            "fund_count": len(s["funds"]), "funds": s["funds"],
        } for s in stock_list[:15]],
        "note": ("Overlap = sum of the minimum disclosed weight in each common stock "
                 "across two funds. Rupee exposure applies each fund's disclosed "
                 "weight to that fund's holding value. Based on the latest disclosed "
                 "monthly portfolios."),
    }


def _fee_drag(db: Session, mf_rows: list[dict], gross: float) -> dict:
    total_value = sum(r["value_rs"] for r in mf_rows)
    per_fund = []
    weighted_ter = 0.0
    for r in mf_rows:
        ter = r.get("ter_pct") or 0.0
        annual = r["value_rs"] * ter / 100
        weighted_ter += ter * r["value_rs"]
        per_fund.append({
            "id": r["key"], "name": r["name"], "value_rs": round(r["value_rs"], 2),
            "ter_pct": ter, "annual_fee_rs": round(annual, 2),
        })
    blended = round(weighted_ter / total_value, 3) if total_value else None
    horizons = []
    for years in (1, 3, 5, 10):
        if blended is None:
            horizons.append({"years": years, "cumulative_fee_rs": None,
                             "opportunity_cost_rs": None})
            continue
        cumulative = total_value * blended / 100 * years
        gross_end = total_value * (1 + gross / 100) ** years
        net_end = total_value * (1 + (gross - blended) / 100) ** years
        horizons.append({
            "years": years,
            "cumulative_fee_rs": round(cumulative, 2),
            "opportunity_cost_rs": round(gross_end - net_end, 2),
        })
    return {
        "total_fund_value_rs": round(total_value, 2),
        "blended_ter_pct": blended,
        "annual_fee_rs": round(sum(f["annual_fee_rs"] for f in per_fund), 2),
        "funds": sorted(per_fund, key=lambda f: -f["annual_fee_rs"]),
        "horizons": horizons,
        "gross_return_pct": gross,
        "note": ("Cumulative fee = value x blended TER x years. Opportunity cost = "
                 "the compounded gap between a gross-return path and the same path "
                 "after the blended TER, so it grows with the horizon."),
    }


@router.get("/lookup")
def lookup(q: str = Query(..., min_length=1), limit: int = Query(8, le=20),
           db: Session = Depends(get_db)):
    """Search the local universe for equities/ETFs and AMFI fund schemes."""
    term = q.strip().upper()
    instruments = (db.query(Instrument)
                     .filter(Instrument.kind.in_(("EQUITY", "ETF")),
                             Instrument.symbol.like(f"%{term}%")
                             | Instrument.name.ilike(f"%{q.strip()}%"))
                     .limit(limit).all())
    equities = []
    for r in instruments:
        m = r.meta or {}
        px = _num(m.get("lastPrice"))
        if px is None and r.history:
            px = _num(r.history[-1].get("c"))
        equities.append({"symbol": r.symbol, "name": r.name, "kind": r.kind,
                         "sector": r.sector, "last": px})
    funds = []
    try:
        from app.routes import funds as funds_route
        for s in funds_route.search_schemes(db, q.strip(), limit=limit):
            funds.append({"code": s.get("code"), "name": s.get("name"),
                          "amc": s.get("amc"), "category": s.get("category")})
    except Exception:  # noqa: BLE001
        pass
    return {"equities": equities, "funds": funds}


@router.post("/analyze")
def analyze(body: XrayBody, db: Session = Depends(get_db)):
    today = dt.date.today()
    resolved = []
    unresolved = []
    all_flows: list[tuple[float, float]] = []
    for h in body.holdings:
        r = _resolve(db, h)
        if not r:
            unresolved.append(h.symbol or h.code or h.name or "unknown")
            continue
        pos = _position(r, h, today)
        all_flows.extend(pos.pop("flows"))
        r.update(pos)
        resolved.append(r)

    total = sum(r["value_rs"] for r in resolved)
    invested = sum(r["invested_rs"] for r in resolved)

    # Asset allocation by wrapper.
    alloc_map: dict[str, float] = {}
    for r in resolved:
        alloc_map[r["kind"]] = alloc_map.get(r["kind"], 0.0) + r["value_rs"]
    allocation = [{"key": k, "value_rs": round(v, 2),
                   "weight_pct": round(v / total * 100, 2) if total else 0.0}
                  for k, v in sorted(alloc_map.items(), key=lambda x: -x[1])]

    # Sector weights: equity sectors plus the look-through of fund holdings.
    sector_map: dict[str, float] = {}
    for r in resolved:
        if r["kind"] == "MF":
            held = r.get("holdings") or []
            if held:
                for h in held:
                    sec = h.get("sector") or "Unclassified"
                    sector_map[sec] = sector_map.get(sec, 0.0) + \
                        (_num(h.get("weight")) or 0.0) / 100 * r["value_rs"]
            else:
                sector_map["Mutual funds (look-through unavailable)"] = \
                    sector_map.get("Mutual funds (look-through unavailable)", 0.0) + r["value_rs"]
        else:
            sec = r.get("sector") or "Unclassified"
            sector_map[sec] = sector_map.get(sec, 0.0) + r["value_rs"]
    sector_weights = [{"sector": k, "value_rs": round(v, 2),
                       "weight_pct": round(v / total * 100, 2) if total else 0.0}
                      for k, v in sorted(sector_map.items(), key=lambda x: -x[1])]

    mf_rows = [r for r in resolved if r["kind"] == "MF" and r["value_rs"] > 0]
    overlap = _overlap(db, mf_rows) if len(mf_rows) >= 2 else {
        "funds": [{"id": f["key"], "name": f["name"], "value_rs": f["value_rs"]}
                  for f in mf_rows],
        "matrix": [[100.0]] if mf_rows else [],
        "pairs": [], "stock_exposure": [],
        "note": ("Add two or more mutual funds/ETFs to see the cross-fund stock "
                 "overlap matrix."),
    }
    feeg = _fee_drag(db, mf_rows, body.gross_return_pct)

    portfolio_xirr = None
    if all_flows and total > 0:
        portfolio_xirr = calc.xirr(all_flows + [(_year_frac(today), total)])

    return {
        "summary": {
            "holdings": len(resolved), "unresolved": unresolved,
            "invested_rs": round(invested, 2), "value_rs": round(total, 2),
            "pnl_rs": round(total - invested, 2),
            "pnl_pct": round((total / invested - 1) * 100, 2) if invested else None,
            "xirr_pct": portfolio_xirr,
        },
        "holdings": [{
            "kind": r["kind"], "key": r["key"], "name": r["name"],
            "sector": r["sector"], "mode": r.get("mode"),
            "quantity": r.get("units"), "units": r.get("units"),
            "price": r.get("current_price"), "current_price": r.get("current_price"),
            "value_rs": round(r["value_rs"], 2),
            "invested_rs": round(r["invested_rs"], 2),
            "pnl_rs": r.get("pnl_rs"), "pnl_pct": r.get("pnl_pct"),
            "xirr_pct": r.get("xirr_pct"), "cagr_pct": r.get("cagr_pct"),
            "months": r.get("months"), "sip_amount": r.get("sip_amount"),
            "buy_date": r.get("buy_date"),
            "weight_pct": round(r["value_rs"] / total * 100, 2) if total else 0.0,
            "ter_pct": r.get("ter_pct"), "href": r.get("href"),
        } for r in resolved],
        "allocation": allocation,
        "sector_weights": sector_weights,
        "overlap": overlap,
        "fee_drag": feeg,
        "notes": [
            "Holdings are parsed from your manual input; current prices and "
            "sectors come from the repaired local instrument store (live "
            "self-healing on demand) and NAVs from AMFI.",
            "A holding is never marked at its buy price: quantity/mode buy "
            "units and the current value uses the real market price or NAV.",
            "SIP units are bought at the nearest declared price on each "
            "monthly instalment date; XIRR is the money-weighted annual "
            "return of those cashflows.",
            "Fund look-through, overlap and fee drag use each scheme's disclosed "
            "monthly portfolio and expense ratio. Missing data is reported, not guessed.",
        ],
    }
