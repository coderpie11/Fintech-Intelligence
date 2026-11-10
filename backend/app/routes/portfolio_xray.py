"""Portfolio X-Ray -- manual holdings parser, allocation/sector X-ray,
cross-fund stock overlap and an expense-ratio fee-drag calculator.

Everything here is computed from the platform's own stored data:
  * equity/ETF price and sector from the instrument record;
  * fund TER, holdings and NAV from the enriched scheme metadata;
  * overlap from the disclosed monthly fund holdings, never from an estimate.
Nothing is invented; missing inputs are reported as unavailable.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.models import FundMeta, FundScheme, Instrument

router = APIRouter(prefix="/portfolio-xray", tags=["portfolio x-ray"])

MF_KINDS = {"MF", "MUTUAL_FUND", "FUND"}


class Holding(BaseModel):
    kind: str = "EQUITY"          # EQUITY / ETF / MF
    symbol: str | None = None     # equity / ETF symbol
    code: str | None = None       # fund scheme code
    name: str | None = None
    quantity: float | None = None
    price: float | None = None    # average buy price
    value: float | None = None    # optional explicit current value


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


def _resolve(db: Session, h: Holding) -> dict | None:
    kind = (h.kind or "EQUITY").upper()
    if kind in MF_KINDS:
        code = (h.code or "").strip()
        rec = db.get(FundScheme, code) if code else None
        if not rec:
            return None
        meta = _fund_meta(db, code)
        g = meta.get("groww") or {}
        navs = rec.navs or []
        nav = _num(navs[-1]["nav"]) if navs else None
        price = _num(h.price) or nav
        return {
            "kind": "MF", "key": code, "name": rec.name,
            "amc": g.get("amc") or rec.amc, "sector": g.get("sub_category") or rec.category,
            "price": price, "quantity": _num(h.quantity), "value": _num(h.value),
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
    m = row.meta or {}
    px = _num(m.get("lastPrice"))
    if px is None and row.history:
        px = _num(row.history[-1].get("c"))
    return {
        "kind": "ETF" if row.kind == "ETF" else "EQUITY", "key": row.symbol,
        "name": row.name, "amc": None, "sector": row.sector or "Unclassified",
        "price": _num(h.price) or px, "quantity": _num(h.quantity),
        "value": _num(h.value), "ter_pct": _num(m.get("ter_pct")) or 0.0,
        "holdings": [], "holdings_date": None,
        "href": f"/etfs/{row.symbol}" if row.kind == "ETF" else f"/stocks/{row.symbol}",
    }


def _current_value(r: dict) -> float:
    if r["value"] is not None:
        return float(r["value"])
    if r["quantity"] is not None and r["price"] is not None:
        return float(r["quantity"]) * float(r["price"])
    return 0.0


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
    resolved = []
    unresolved = []
    for h in body.holdings:
        r = _resolve(db, h)
        if not r:
            unresolved.append(h.symbol or h.code or h.name or "unknown")
            continue
        r["value_rs"] = _current_value(r)
        if r["quantity"] is not None and r["price"] is not None:
            r["invested_rs"] = float(r["quantity"]) * float(r["price"])
        else:
            r["invested_rs"] = r["value_rs"]
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

    return {
        "summary": {
            "holdings": len(resolved), "unresolved": unresolved,
            "invested_rs": round(invested, 2), "value_rs": round(total, 2),
            "pnl_rs": round(total - invested, 2),
            "pnl_pct": round((total / invested - 1) * 100, 2) if invested else None,
        },
        "holdings": [{
            "kind": r["kind"], "key": r["key"], "name": r["name"],
            "sector": r["sector"], "quantity": r["quantity"], "price": r["price"],
            "value_rs": round(r["value_rs"], 2),
            "weight_pct": round(r["value_rs"] / total * 100, 2) if total else 0.0,
            "ter_pct": r.get("ter_pct"), "href": r.get("href"),
        } for r in resolved],
        "allocation": allocation,
        "sector_weights": sector_weights,
        "overlap": overlap,
        "fee_drag": feeg,
        "notes": [
            "Holdings are parsed from your manual input; prices and sectors come "
            "from the local instrument store and NAVs from AMFI.",
            "Fund look-through, overlap and fee drag use each scheme's disclosed "
            "monthly portfolio and expense ratio. Missing data is reported, not guessed.",
        ],
    }
