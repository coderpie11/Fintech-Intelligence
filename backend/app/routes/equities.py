"""Equities — screener list, five-year deep dive, health scorecard,
statements, peer drawer, DCF/reverse-DCF, intraday and SIP/lumpsum maths."""
from __future__ import annotations

import datetime as dt
import statistics
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.data.adapters import screener_adapter as S
from app.data.adapters import stockanalysis_adapter as SA
from app.data.adapters import yfinance_adapter as Y
from app.models.models import Instrument
from app.services import calc, fundamentals as F, live_quote as LQ
from app.services.contextual import (not_applicable, not_disclosed, reported,
                                     source_issue)

# Ticker renames that should keep old deep links working. The platform shows the
# current listed symbol but accepts the former name.
SYMBOL_ALIASES = {
    "ZOMATO": "ETERNAL",
}

router = APIRouter(prefix="/stocks", tags=["equities"])

_MONETARY = {
    "revenue", "gross_profit", "cost_of_revenue", "ebitda", "operating_income",
    "net_income", "interest_expense", "sga", "depreciation", "tax",
    "pretax_income", "total_assets", "equity", "total_debt", "net_debt", "cash",
    "inventory", "receivables", "current_assets", "current_liabilities",
    "retained_earnings", "ppe", "payables", "cfo", "cfi", "cff", "fcf",
    "capex", "expenses", "operating_profit", "other_income",
    "equity_capital", "reserves", "borrowings", "other_liabilities",
    "total_liabilities", "fixed_assets", "cwip", "investments", "other_assets",
    "net_cash_flow",
}

FINANCIAL_HINTS = ("bank", "financial", "insurance", "nbfc", "capital markets")


def _env(v, what: str = "metric", nd: int | None = None) -> dict:
    if v is None:
        return source_issue(what)
    try:
        if isinstance(v, (list, tuple)):
            if all(x is None for x in v):
                return source_issue(what)
            return reported(list(v))
        f = float(v)
        if nd is not None:
            f = round(f, nd)
        return reported(f)
    except (TypeError, ValueError):
        return source_issue(what)


def _ratio(v, nd: int = 2):
    if v is None:
        return None
    try:
        f = float(v)
        return round(f, nd) if f else None
    except (TypeError, ValueError):
        return None


def _is_financial(sector: str | None, industry: str | None) -> bool:
    text = f"{sector or ''} {industry or ''}".lower()
    return any(h in text for h in FINANCIAL_HINTS)


def _extra(row: Instrument) -> dict:
    return (row.meta or {}).get("extra") or {}


def _snap(r: Instrument) -> dict:
    m = r.meta or {}
    x = _extra(r)
    fund = m.get("fundamentals") or {}
    hist = r.history or []
    sector = m.get("sector") or r.sector
    last_bar = hist[-1] if hist else {}
    prev_bar = hist[-2] if len(hist) > 1 else {}
    open_v = m.get("open") or last_bar.get("o")
    prev_v = m.get("prevClose") or prev_bar.get("c")
    high_v = m.get("high") or last_bar.get("h")
    low_v = m.get("low") or last_bar.get("l")
    pe = m.get("pe") or x.get("trailingPE") or (fund.get("valuation") or {}).get("pe")
    pb = x.get("priceToBook") or (fund.get("valuation") or {}).get("pb")
    bv = x.get("bookValue") or (fund.get("valuation") or {}).get("book_value_per_share")
    eps_raw = x.get("earningsPerShare") or (fund.get("valuation") or {}).get("eps")
    # Keep P/E consistent with the live price and the reported trailing EPS.
    if eps_raw and m.get("lastPrice"):
        pe = round(m["lastPrice"] / eps_raw, 2)
    dy = (fund.get("valuation") or {}).get("dividend_yield")
    if dy is None:
        rate = x.get("dividendRate")
        price = m.get("lastPrice")
        dy = round(rate / price * 100, 2) if rate and price else x.get("dividendYield")
    change = m.get("change")
    if change is None and m.get("lastPrice") is not None and m.get("prevClose") is not None:
        try:
            change = round(float(m["lastPrice"]) - float(m["prevClose"]), 2)
        except (TypeError, ValueError):
            change = None
    return {
        "symbol": r.symbol, "name": r.name, "slug": r.slug, "sector": sector,
        "industry": m.get("industry") or r.industry,
        "last": _env(m.get("lastPrice"), "last price"),
        "change": _env(change, "day change"),
        "changepct": _env(m.get("changepct"), "day change"),
        "live_asof": m.get("live_asof"),
        "live_time": m.get("live_time"),
        "live_source": m.get("live_source"),
        "open": _env(open_v, "day open"),
        "prev_close": _env(prev_v, "previous close"),
        "day_range": _env([low_v, high_v], "day range"),
        "year_range": _env([m.get("yearLow"), m.get("yearHigh")], "52-week range"),
        "pe": _env(_ratio(pe), "P/E"),
        "pb": _env(_ratio(pb), "P/B"),
        "book_value": _env(bv, "book value"),
        "dividend_yield": _env(dy, "dividend yield"),
        "face_value": _env(m.get("faceValue"), "face value"),
        "market_cap": _env(m.get("marketCap") or fund.get("market_cap"), "market cap"),
        "free_float_mcap": _env(m.get("ffmCap"), "free-float market cap"),
        "issued_size": _env(m.get("issuedSize"), "issued shares"),
        "sector_pe": _env(m.get("sectorPe"), "sector P/E"),
        "delivery_pct": _env(m.get("deliveryPct"), "delivery percentage"),
        "listing_date": _env(m.get("listingDate"), "listing date"),
        "indices": _env(m.get("indices") or r.indices, "index membership"),
        "roenew": _env(x.get("returnOnEquity"), "ROE"),
        "margin": _env(x.get("profitMargins"), "net margin"),
        "eps": _env(eps_raw, "EPS"),
        "beta": _env(x.get("beta"), "beta"),
        "debt_equity": _env(x.get("debtToEquity"), "debt/equity"),
        "href": f"/stocks/{r.symbol}",
    }


def _ensure_research(db: Session, row: Instrument, force: bool = False) -> dict:
    """Fetch and cache the expensive Yahoo/Screener payloads on the instrument."""
    meta = dict(row.meta or {})
    fund = meta.get("fundamentals")
    fresh = False
    if fund and not force:
        try:
            stamp = dt.datetime.fromisoformat(fund.get("fetched_at", "").replace("Z", ""))
            fresh = (dt.datetime.utcnow() - stamp).total_seconds() < 12 * 3600
        except Exception:  # noqa: BLE001
            fresh = False
    if not fresh:
        try:
            built = F.build(row.symbol, meta, row.history or [])
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
            meta["statements_consolidated"] = built["statements"]
            meta["statements_fetched_at"] = dt.datetime.utcnow().isoformat() + "Z"
        except Exception as e:  # noqa: BLE001
            meta["fundamentals_error"] = f"{type(e).__name__}: {e}"
    # Screener's annual tables carry six real columns and the exact line-item
    # keys the UI uses, so prefer them when available (Yahoo remains fallback).
    if not meta.get("statements_screener_consolidated") or force:
        try:
            sc = S.statements(row.symbol, consolidated=True)
            if sc and len((sc.get("annual") or {}).get("periods") or []) >= 5:
                meta["statements_screener_consolidated"] = sc
        except Exception:  # noqa: BLE001
            pass
    if (not meta.get("statements_screener_consolidated")
            or len((meta.get("statements_screener_consolidated", {}).get("annual", {})
                    .get("periods") or [])) < 5):
        if not meta.get("statements_stockanalysis") or force:
            try:
                sa = SA.statements(row.symbol)
                if sa:
                    meta["statements_stockanalysis"] = sa
            except Exception:  # noqa: BLE001
                pass
    if meta.get("statements_screener_consolidated"):
        meta["statements_consolidated"] = meta["statements_screener_consolidated"]
    elif meta.get("statements_stockanalysis"):
        meta["statements_consolidated"] = meta["statements_stockanalysis"]
    if not meta.get("shareholding"):
        try:
            shp = S.shareholding(row.symbol, consolidated=True)
            if shp:
                meta["shareholding"] = shp
        except Exception:  # noqa: BLE001
            pass
    if not meta.get("statements_standalone"):
        try:
            st = S.statements(row.symbol, consolidated=False)
            if st:
                meta["statements_standalone"] = st
        except Exception:  # noqa: BLE001
            pass
    row.meta = meta
    db.add(row)
    # The cache write is an optimisation, not part of the answer. If another
    # request holds the single SQLite writer slot, retry briefly and then serve
    # the freshly computed payload without persisting it rather than failing the
    # whole page with a 500.
    for attempt in range(3):
        try:
            db.commit()
            break
        except Exception:  # noqa: BLE001
            db.rollback()
            if attempt == 2:
                break
            try:
                import time as _time
                _time.sleep(0.35)
            except Exception:  # noqa: BLE001
                break
    return meta


# ---------------------------------------------------------------- list
@router.get("")
def list_stocks(q: str | None = None, sector: str | None = None,
                index: str | None = None,
                sort: str = "mcap", limit: int = Query(50, le=250),
                db: Session = Depends(get_db)):
    query = db.query(Instrument).filter(Instrument.kind == "EQUITY")
    q_mode = bool(q and q.strip())
    if q_mode:
        from app.services import fuzzy
        from app.services import stock_loader

        rows = fuzzy.rank(q.strip(), query.all(),
                          lambda r: f"{r.symbol} {r.name} {r.sector or ''}",
                          limit=250, floor=0.7)
        if not rows and len(q.strip()) >= 3:
            # Nothing local: let Yahoo resolve the company and create the row.
            try:
                created = stock_loader.ensure_by_symbol(db, q.strip().upper())
                if created is not None:
                    rows = [created]
            except Exception:  # noqa: BLE001
                rows = []
    else:
        rows = query.all()
    if sector:
        rows = [r for r in rows if (r.sector or "") == sector]
    items = [_snap(r) for r in rows]
    if not q_mode:
        # Discovery rows without a price stay out of the browse table, but a
        # search must be able to find them by name and open them on demand.
        items = [i for i in items if (i["last"]["value"] is not None)]
    if index:
        want = index.strip().upper()
        items = [i for i in items
                 if any(str(x).upper() == want for x in (i["indices"]["value"] or []))]
    index_names = sorted({str(x) for i in items
                          for x in (i["indices"]["value"] or [])})
    keymap = {
        "mcap": lambda i: i["market_cap"]["value"] or 0,
        "gainers": lambda i: (i["changepct"]["value"] or 0),
        "losers": lambda i: -(i["changepct"]["value"] or 0),
        "symbol": lambda i: i["symbol"],
        "pe": lambda i: (i["pe"]["value"] or 1e18),
    }
    if not q_mode:
        items.sort(key=keymap.get(sort, keymap["mcap"]), reverse=(sort in ("gainers", "mcap")))
    sectors = sorted({i["sector"] for i in items if i["sector"]})
    # Reconcile only the page being returned: a 45-symbol batch download keeps
    # the screener live without making the request wait for the whole universe.
    page = items[:limit]
    by_symbol = {r.symbol: r for r in rows}
    page_rows = [by_symbol[i["symbol"]] for i in page if i["symbol"] in by_symbol]
    LQ.refresh_rows(db, page_rows)
    refreshed = {r.symbol: _snap(r) for r in page_rows}
    page = [refreshed.get(i["symbol"], i) for i in page]
    return {"count": len(items), "stocks": page, "sectors": sectors,
            "indices": index_names, "sort": sort,
            "sorts_available": list(keymap),
            "live_source": LQ.QUOTE_SOURCE, "query": q}


# ---------------------------------------------------------------- peers
def _peer_metric(row: Instrument) -> dict:
    m = row.meta or {}
    x = _extra(row)
    fund = m.get("fundamentals") or {}
    val, prof, solv = (fund.get("valuation") or {}, fund.get("profitability") or {},
                       fund.get("solvency") or {})
    roe = prof.get("roe")
    roce = prof.get("roce")
    if roe is None and x.get("returnOnEquity") is not None:
        roe = round(float(x["returnOnEquity"]) * 100, 2)
    de = solv.get("debt_equity")
    if de is None and x.get("debtToEquity") is not None:
        de = round(float(x["debtToEquity"]) / 100, 2)
    pe = m.get("pe") or x.get("trailingPE") or val.get("pe")
    pb = x.get("priceToBook") or val.get("pb")
    hist = row.history or []
    rets = F.returns_ladder(hist)
    return {
        "symbol": row.symbol, "name": row.name,
        "sector": m.get("sector") or row.sector,
        "last": m.get("lastPrice"), "changepct": m.get("changepct"),
        "market_cap": m.get("marketCap") or fund.get("market_cap"),
        "pe": _ratio(pe), "pb": _ratio(pb), "roe": roe, "roce": roce,
        "debt_equity": de,
        "cagr_5y": rets.get("5y"), "return_1y": rets.get("1y"),
        "href": f"/stocks/{row.symbol}",
    }


def _peer_set(db: Session, rows: list[Instrument], subject: str) -> list[dict]:
    peers = [_peer_metric(r) for r in rows]
    if not peers:
        return []
    def best(key: str, lowest: bool = False):
        vals = [(p[key], p["symbol"]) for p in peers if p.get(key) is not None]
        if not vals:
            return None
        return (min if lowest else max)(vals)[1]
    leaders = {
        "highest_roe": best("roe"),
        "lowest_pe": best("pe", lowest=True),
        "lowest_debt_equity": best("debt_equity", lowest=True),
        "highest_cagr_5y": best("cagr_5y"),
    }
    badge_text = {
        "highest_roe": "#1 Leader · highest ROE",
        "lowest_pe": "#1 Leader · lowest P/E",
        "lowest_debt_equity": "#1 Leader · lowest D/E",
        "highest_cagr_5y": "#1 Leader · highest 5Y CAGR",
    }
    for p in peers:
        p["badges"] = [badge_text[k] for k, sym in leaders.items() if sym == p["symbol"]]
        p["is_subject"] = p["symbol"] == subject
    peers.sort(key=lambda p: (not p["is_subject"], -(p["market_cap"] or 0)))
    return peers


@router.get("/peer-set")
def peer_set(symbols: str, db: Session = Depends(get_db)):
    syms = [s.strip().upper() for s in (symbols or "").split(",") if s.strip()][:12]
    rows = (db.query(Instrument)
              .filter(Instrument.kind == "EQUITY", Instrument.symbol.in_(syms)).all())
    return {"peers": _peer_set(db, rows, syms[0] if syms else ""),
            "requested": syms, "found": [r.symbol for r in rows]}


@router.get("/{symbol}/peers")
def peers_for(symbol: str, db: Session = Depends(get_db)):
    row = _row_or_404(db, symbol)
    sector = (row.meta or {}).get("sector") or row.sector
    rows = (db.query(Instrument)
              .filter(Instrument.kind == "EQUITY", Instrument.sector == sector).all())
    return {"symbol": row.symbol, "sector": sector,
            "peers": _peer_set(db, rows, row.symbol)}


# ---------------------------------------------------------------- intraday
@router.get("/{symbol}/intraday")
def stock_intraday(symbol: str, interval: str = "5m",
                   db: Session = Depends(get_db)):
    row = _find_equity(db, symbol)
    if not row:
        raise HTTPException(404, f"{symbol} not in the seeded universe yet")
    quote = LQ.refresh_one(db, row)
    ticker = f"{row.symbol}.NS"
    try:
        data = Y.intraday(ticker, interval=interval, period="5d")
        if data["points"]:
            last = data["points"][-1]
            data["last"] = last["c"]
            if quote:
                data["prevClose"] = quote.get("prevClose")
                data["change"] = quote.get("change")
                data["changepct"] = quote.get("changepct")
                data["asof"] = quote.get("asof")
                data["session_date"] = quote.get("session")
                data["live_source"] = quote.get("source")
            else:
                prev = data["points"][0]
                data["changepct"] = (round((last["c"] / prev["o"] - 1) * 100, 2)
                                     if prev.get("o") else None)
            return data
    except Exception:  # noqa: BLE001
        pass
    hist = row.history or []
    if len(hist) >= 2:
        last_bar, prev_bar = hist[-1], hist[-2]
        change = round(last_bar["c"] - prev_bar["c"], 2)
        return {
            "ticker": ticker, "interval": "1d", "session": last_bar["date"],
            "source": "Yahoo Finance daily candles (intraday feed unavailable)",
            "points": [{"datetime": h["date"], "date": h["date"], "time": "15:30",
                        "o": h.get("o"), "h": h.get("h"), "l": h.get("l"),
                        "c": h["c"], "v": h.get("v")} for h in hist[-60:]],
            "last": last_bar["c"],
            "prevClose": prev_bar["c"],
            "change": change,
            "changepct": round((last_bar["c"] / prev_bar["c"] - 1) * 100, 2),
            "asof": (quote or {}).get("asof"),
            "note": "The intraday feed did not answer; the last 60 daily closes "
                    "are shown instead of fabricating candles.",
        }
    raise HTTPException(503, "No price history available for this symbol yet.")


# ---------------------------------------------------------------- detail
@router.get("/{symbol}")
def stock_detail(symbol: str, refresh: bool = False, db: Session = Depends(get_db)):
    row = _find_equity(db, symbol)
    if not row:
        raise HTTPException(404, f"{symbol} not in the seeded universe yet")
    quote = LQ.refresh_one(db, row, sync_history=True)
    meta = _ensure_research(db, row, force=refresh)
    snap = _snap(row)
    fund = meta.get("fundamentals") or {}
    hist = row.history or []
    sector = snap["sector"]
    financial = _is_financial(sector, snap["industry"])
    val = fund.get("valuation") or {}
    prof = fund.get("profitability") or {}
    solv = fund.get("solvency") or {}
    eff = fund.get("efficiency") or {}
    growth = fund.get("growth") or {}
    health = fund.get("health") or {}
    rets = fund.get("returns") or F.returns_ladder(hist)
    risk = fund.get("risk") or F.risk_stats(hist, {})

    def na(key: str) -> dict:
        return not_applicable(key, sector or "this sector")

    fundamentals = {
        "valuation": {
            "pe": snap["pe"], "pb": snap["pb"],
            "peg": _env(val.get("peg"), "PEG"),
            "ev_ebitda": _env(val.get("ev_ebitda"), "EV/EBITDA"),
            "dividend_yield": snap["dividend_yield"],
            "earnings_yield": _env(val.get("earnings_yield"), "earnings yield"),
            "graham_number": _env(val.get("graham_number"), "Graham number"),
            "book_value_per_share": _env(val.get("book_value_per_share"), "book value/share"),
            "eps": snap["eps"], "market_cap": snap["market_cap"],
        },
        "profitability": {
            "roe": _env(prof.get("roe"), "ROE"),
            "roa": _env(prof.get("roa"), "ROA"),
            "roic": _env(prof.get("roic"), "ROIC"),
            "roce": _env(prof.get("roce"), "ROCE"),
            "gross_margin": _env(prof.get("gross_margin"), "gross margin"),
            "operating_margin": _env(prof.get("operating_margin"), "operating margin"),
            "net_margin": _env(prof.get("net_margin"), "net margin"),
        },
        "solvency": {
            "debt_equity": _env(solv.get("debt_equity"), "debt/equity"),
            "current_ratio": (na("current ratio") if financial
                              else _env(solv.get("current_ratio"), "current ratio")),
            "quick_ratio": (na("quick ratio") if financial
                            else _env(solv.get("quick_ratio"), "quick ratio")),
            "interest_coverage": _env(solv.get("interest_coverage"), "interest coverage"),
            "net_debt_ebitda": _env(solv.get("net_debt_ebitda"), "net debt/EBITDA"),
        },
        "efficiency": {
            "asset_turnover": _env(eff.get("asset_turnover"), "asset turnover"),
            "inventory_turnover": (na("inventory turnover") if financial
                                   else _env(eff.get("inventory_turnover"), "inventory turnover")),
            "inventory_days": (na("inventory days") if financial
                               else _env(eff.get("inventory_days"), "inventory days")),
            "receivable_days": _env(eff.get("receivable_days"), "receivable days"),
            "payable_days": _env(eff.get("payable_days"), "payable days"),
            "cash_conversion_cycle": (na("cash conversion cycle") if financial
                                      else _env(eff.get("cash_conversion_cycle"), "cash conversion cycle")),
            "fcf": _env(eff.get("fcf"), "free cash flow"),
            "fcf_yield": _env(eff.get("fcf_yield"), "FCF yield"),
        },
        "growth": {k: _env(v, k.replace("_", " ")) for k, v in growth.items()},
    }

    # ---- statements (Screener annual preferred, Yahoo fallback) ----
    def _alias(sec: str, block: dict, periods_count: int) -> dict:
        """Map Yahoo/Screener keys onto the canonical UI line items and derive
        ratio rows (OPM %, tax rate) so every row renders real numbers."""
        out = {k: list(v) for k, v in (block or {}).items() if isinstance(v, list)}
        if sec == "income":
            out.setdefault("expenses", out.get("cost_of_revenue", []))
            out.setdefault("operating_profit", out.get("operating_income", []))
            rev = out.get("revenue") or []
            op = out.get("operating_profit") or []
            if rev and op:
                out["opm_pct"] = [round(o / r * 100, 2) if r else None
                                  for o, r in zip(op, rev)]
            tax, pre = out.get("tax") or [], out.get("pretax_income") or []
            if tax and pre:
                out["tax_pct"] = [round(t / p * 100, 2) if p else None
                                  for t, p in zip(tax, pre)]
        elif sec == "balance":
            out.setdefault("borrowings", out.get("total_debt", []))
            out.setdefault("fixed_assets", out.get("ppe", []))
            out.setdefault("payables", out.get("accounts_payable", []))
            out.setdefault("other_assets", out.get("other_current_assets", []))
        return out

    def convert(stmts: dict, limit: int = 5) -> dict:
        annual = (stmts or {}).get("annual") or {}
        periods = list(annual.get("periods") or [])
        units = str((stmts or {}).get("units") or "").lower()
        source = str((stmts or {}).get("source") or "")
        if "crore" in units:
            divisor = 1.0
        elif "million" in units:
            divisor = 10.0          # 1 crore = 10 million
        else:
            divisor = 1e7           # raw rupees → crore
        sections = {}
        for section in ("income", "balance", "cashflow"):
            block = annual.get(section) or {}
            vals_out = {}
            for k, vals in block.items():
                if not isinstance(vals, list) or not vals:
                    continue
                if k not in _MONETARY:
                    vals_out[k] = list(vals)
                else:
                    vals_out[k] = [None if x is None else round(x / divisor, 2)
                                   for x in vals]
            sections[section] = _alias(section, vals_out, len(periods))
        # Normalise to the newest `limit` periods, newest first. Screener gives
        # oldest→newest; Yahoo and StockAnalysis give newest→oldest.
        if "screener" in source.lower() and periods:
            periods = list(reversed(periods))
            for sec in sections:
                for k, vals in sections[sec].items():
                    sections[sec][k] = list(reversed(vals))
        periods = periods[:limit]
        n = len(periods)
        for sec in sections:
            for k, vals in list(sections[sec].items()):
                sections[sec][k] = (list(vals) + [None] * n)[:n]
        return {"periods": periods, "sections": sections,
                "units": "INR crore",
                "source": source or "Reported statements",
                "currency": "INR"}

    def convert_q(stmts: dict) -> dict:
        q = (stmts or {}).get("quarterly") or {}
        periods = q.get("periods") or []
        sections = {}
        for section in ("income", "balance", "cashflow"):
            block = q.get(section) or {}
            sections[section] = _alias(section, {
                k: ([None if x is None else round(x / 1e7, 2) for x in vals]
                    if k in _MONETARY else vals)
                for k, vals in block.items() if vals
            }, len(periods))
        return {"periods": periods, "sections": sections, "units": "INR crore"}

    stmts = meta.get("statements_consolidated") or {}
    annual = convert(stmts)
    quarterly = convert_q(stmts)
    standalone_raw = meta.get("statements_standalone") or {}
    standalone = None
    if standalone_raw.get("annual"):
        sa = convert(standalone_raw)
        standalone = {**sa, "basis": "standalone",
                      "source": standalone_raw.get("source")}

    # ---- shareholding ----
    shp = meta.get("shareholding") or {}
    shareholding = {
        "periods": list(reversed(shp.get("periods") or [])),
        "series": {k: list(reversed(v)) for k, v in (shp.get("series") or {}).items()},
        "source": shp.get("source"), "available": bool(shp.get("periods")),
    } if shp else {"periods": [], "series": {}, "available": False,
                   "note": "Screener.in did not return a shareholding table for this symbol."}

    # ---- peers ----
    srows = []
    if sector:
        srows = (db.query(Instrument)
                   .filter(Instrument.kind == "EQUITY", Instrument.sector == sector).all())
    # Peer quotes are only refreshed on an explicit "Refresh research" action.
    # Fetching 30 extra tickers on every cold detail view added 10-20 s to the
    # first paint; the stored peer prices are good enough for the table and are
    # refreshed by the screener/list views anyway.
    if refresh:
        LQ.refresh_rows(db, srows[:30])
    peers = _peer_set(db, srows, row.symbol)

    # ---- DCF defaults (₹ million) ----
    ann_inc = (stmts.get("annual") or {}).get("income") or {}
    ann_cf = (stmts.get("annual") or {}).get("cashflow") or {}
    ann_bal = (stmts.get("annual") or {}).get("balance") or {}
    def first(block, key):
        vals = block.get(key) or []
        return vals[0] if vals else None
    fcff, fcf_fallback = _positive_fcf(ann_cf)
    net_cash = None
    cash, debt = first(ann_bal, "cash"), first(ann_bal, "total_debt")
    if cash is not None and debt is not None:
        net_cash = cash - debt
    shares = val.get("market_cap") and val.get("price") and val["market_cap"] / val["price"]
    # Reported statements are in ₹ crore; the model works in ₹ million.
    # 1 crore = 10 million, so multiply by 10 (not divide by 1e6).
    dcf_defaults = {
        "fcff_millions": round(fcff * 10, 2) if fcff else None,
        "growth_pct": growth.get("revenue_cagr_3y") or growth.get("revenue_growth_1y"),
        "terminal_pct": 4.0, "wacc_pct": 11.5,
        "net_cash_millions": round(net_cash * 10, 2) if net_cash is not None else None,
        "shares_millions": round(shares / 1e6, 2) if shares else None,
        "price": val.get("price"),
        "years": 5,
        "note": ("Defaults are seeded from reported cash flow, net cash and share "
                 "count. Edit any input — the model is yours, not a recommendation."
                 + (" The latest year had negative free cash flow, so this default "
                    "uses the most recent positive reported year."
                    if fcf_fallback else "")),
    }

    fno_note = ("F&O is available for this stock when NSE publishes a derivatives "
                "contract; the Derivatives tab probes the live chain on open.")
    return {
        **snap,
        "about": _about(row),
        "financial_sector": financial,
        "returns": {k: _env(v, f"{k.upper()} return") for k, v in rets.items()},
        "risk": {k: _env(v, k.replace("_", " ")) for k, v in risk.items()},
        "fundamentals": fundamentals,
        "health": {
            "composite": _env(fund.get("composite_score"), "composite health score"),
            "piotroski": health.get("piotroski") or {"score": None, "max": 0,
                                                     "signals": [],
                                                     "note": "Fundamentals are still loading."},
            "altman": health.get("altman") or {"applicable": False, "note": "Unavailable."},
            "beneish": health.get("beneish") or {"applicable": False, "note": "Unavailable."},
            "dupont": health.get("dupont") or {"roe_pct": None, "note": "Unavailable."},
        },
        "statements": {"annual": annual, "quarterly": quarterly,
                       "standalone": standalone,
                       "consolidated_available": bool(annual["periods"]),
                       "note": ("Consolidated statements come from Yahoo Finance "
                                "(reported, ₹ crore). Standalone statements are "
                                "parsed from Screener.in when available.")},
        "shareholding": shareholding,
        "peers": peers,
        "peer_sector": sector,
        "dcf_defaults": dcf_defaults,
        "fno": {"available": True, "note": fno_note},
        "history": [{"date": h["date"], "close": h["c"], "open": h.get("o"),
                     "high": h.get("h"), "low": h.get("l")} for h in hist],
        "history_points": len(hist),
        "history_source": meta.get("history_source") or "Yahoo Finance daily candles",
        "asof": meta.get("asof") or (hist[-1]["date"] if hist else None),
        "live_time": meta.get("live_time"),
        "live_source": meta.get("live_source") or LQ.QUOTE_SOURCE,
        "source_notes": [
            "The header quote is reconciled on every request against the latest "
            "Yahoo 5-minute candle (15-second cache) and written back to the "
            "database, so it always equals the final candle on the 1D chart.",
            "Prices are delayed by roughly 15 minutes on the free feed. The 1D tab "
            "shows real 5-minute candles for the latest session.",
            "Fundamental ratios are platform-computed from reported statements. "
            "Where an input is missing the cell says why instead of showing a null.",
            "Nothing on this page is a buy/sell recommendation.",
        ],
        "data_error": meta.get("fundamentals_error"),
    }


def _about(row: Instrument) -> str:
    m = row.meta or {}
    parts: list[str] = []
    if m.get("sector"):
        sector_txt = m["sector"] + (f" ({m['industry']})" if m.get("industry") else "")
        parts.append(f"{row.name} operates in the {sector_txt} sector.")
    if m.get("marketCap"):
        mc = float(m["marketCap"] or 0)
        if mc > 1e11:
            parts.append(f"Market capitalisation of about \u20B9{mc/1e12:.2f} lakh crore.")
    if m.get("listingDate"):
        parts.append(f"Listed on NSE since {m['listingDate']}.")
    return " ".join(parts) or f"Listed equity security: {row.name} ({row.symbol})."


# ---------------------------------------------------------------- calculators
class DcfBody(BaseModel):
    fcff_millions: float | None = None
    growth_pct: float | None = None
    terminal_pct: float | None = None
    wacc_pct: float | None = None
    net_cash_millions: float | None = None
    shares_millions: float | None = None
    years: int = 5


class ReverseBody(BaseModel):
    price: float | None = None
    fcff_millions: float | None = None
    terminal_pct: float | None = None
    wacc_pct: float | None = None
    net_cash_millions: float | None = None
    shares_millions: float | None = None
    years: int = 5


class RelativeBody(BaseModel):
    metric: str = "pe"
    peer_multiple: float | None = None


class SipBody(BaseModel):
    monthly: float
    years: float = 5
    annual_return_pct: float = 12.0


class LumpsumBody(BaseModel):
    amount: float
    years: float = 5
    annual_return_pct: float = 12.0


def _positive_fcf(cf: dict) -> tuple[float | None, bool]:
    """Latest reported free cash flow, preferring a positive year.

    A single heavy-capex year can make FCF negative, which makes a DCF
    mathematically impossible. Rather than greet the user with an error before
    they have typed anything, seed the editable default from the most recent
    positive reported year and say so in the note.
    """
    def first(key):
        vals = cf.get(key) or []
        return vals[0] if vals else None
    cfo, capex = first("cfo"), first("capex")
    latest = (cfo + capex) if cfo is not None and capex is not None else first("fcf")
    series = list(cf.get("fcf") or [])
    if latest is None:
        positive = next((x for x in series if x and x > 0), None)
        return positive, False
    if latest > 0:
        return latest, False
    positive = next((x for x in series if x and x > 0), None)
    return (positive, True) if positive is not None else (latest, False)


def _defaults(row: Instrument) -> dict:
    meta = row.meta or {}
    fund = meta.get("fundamentals") or {}
    val = fund.get("valuation") or {}
    stmts = meta.get("statements_consolidated") or {}
    inc = (stmts.get("annual") or {}).get("income") or {}
    cf = (stmts.get("annual") or {}).get("cashflow") or {}
    bal = (stmts.get("annual") or {}).get("balance") or {}
    def first(block, key):
        vals = block.get(key) or []
        return vals[0] if vals else None
    fcff, _fallback = _positive_fcf(cf)
    net_cash = None
    if first(bal, "cash") is not None and first(bal, "total_debt") is not None:
        net_cash = first(bal, "cash") - first(bal, "total_debt")
    shares = (val.get("market_cap") / val["price"]
              if val.get("market_cap") and val.get("price") else None)
    # Statements are in ₹ crore; the DCF model expects ₹ million (×10).
    return {"fcff": fcff * 10 if fcff else None,
            "net_cash": net_cash * 10 if net_cash is not None else None,
            "shares": shares / 1e6 if shares else None,
            "price": val.get("price")}


@router.post("/{symbol}/dcf")
def dcf(symbol: str, body: DcfBody, db: Session = Depends(get_db)):
    row = _row_or_404(db, symbol)
    d = _defaults(row)
    fcff = body.fcff_millions if body.fcff_millions is not None else d["fcff"]
    shares = body.shares_millions if body.shares_millions is not None else d["shares"]
    net_cash = (body.net_cash_millions if body.net_cash_millions is not None
                else d["net_cash"] or 0)
    if fcff is None or shares is None:
        raise HTTPException(422, "FCFF and share count are required — the reported "
                                 "statements did not supply them.")
    out = calc.dcf_value(fcff, body.growth_pct if body.growth_pct is not None else 8,
                         body.terminal_pct if body.terminal_pct is not None else 4,
                         body.wacc_pct if body.wacc_pct is not None else 11.5,
                         net_cash, shares, body.years)
    out["current_price"] = d["price"]
    if out.get("per_share") and d["price"]:
        out["upside_pct"] = round((out["per_share"] / d["price"] - 1) * 100, 2)
    return out


@router.post("/{symbol}/reverse-dcf")
def reverse_dcf(symbol: str, body: ReverseBody, db: Session = Depends(get_db)):
    row = _row_or_404(db, symbol)
    d = _defaults(row)
    fcff = body.fcff_millions if body.fcff_millions is not None else d["fcff"]
    shares = body.shares_millions if body.shares_millions is not None else d["shares"]
    net_cash = (body.net_cash_millions if body.net_cash_millions is not None
                else d["net_cash"] or 0)
    price = body.price if body.price is not None else d["price"]
    if fcff is None or shares is None or price is None:
        raise HTTPException(422, "FCFF, share count and a market price are required.")
    return calc.reverse_dcf_growth(fcff, body.terminal_pct if body.terminal_pct is not None else 4,
                                   body.wacc_pct if body.wacc_pct is not None else 11.5,
                                   net_cash, shares, price, body.years)


@router.post("/{symbol}/relative-value")
def relative_value(symbol: str, body: RelativeBody, db: Session = Depends(get_db)):
    row = _row_or_404(db, symbol)
    meta = _ensure_research(db, row)
    fund = meta.get("fundamentals") or {}
    val = fund.get("valuation") or {}
    metric = body.metric.lower()
    base = val.get("eps") if metric == "pe" else val.get("book_value_per_share")
    multiple = body.peer_multiple
    if multiple is None:
        srows = (db.query(Instrument)
                   .filter(Instrument.kind == "EQUITY",
                           Instrument.sector == (meta.get("sector") or row.sector)).all())
        vals = []
        for r in srows:
            if r.symbol == row.symbol:
                continue
            pm = r.meta or {}
            px = _extra(r)
            v = pm.get("pe") if metric == "pe" else px.get("priceToBook")
            if v:
                vals.append(float(v))
        multiple = round(statistics.median(vals), 2) if vals else None
    price = val.get("price") or (row.meta or {}).get("lastPrice")
    if base is None or multiple is None or price is None:
        raise HTTPException(422, "This stock does not have the earnings/book value "
                                 "input needed for the relative-value model.")
    implied = round(float(base) * float(multiple), 2)
    return {
        "metric": metric, "base_per_share": round(float(base), 2),
        "peer_multiple": round(float(multiple), 2),
        "implied_price": implied, "current_price": round(float(price), 2),
        "upside_pct": round((implied / float(price) - 1) * 100, 2),
        "note": ("Implied price = peer multiple × this company's per-share metric. "
                 "A relative-value cross-check, not a target price."),
    }


@router.post("/{symbol}/sip")
def stock_sip(symbol: str, body: SipBody, db: Session = Depends(get_db)):
    _row_or_404(db, symbol)
    out = calc.sip_future_value(body.monthly, body.years, body.annual_return_pct)
    if out.get("error"):
        return out
    charges = calc.net_in_pocket("BUY+SELL", out["invested"], out["future_value"])
    out["charges"] = charges
    out["net_after_charges"] = round(out["future_value"] - charges["total_charges"], 2)
    out["note"] = ("Projection assumes a constant annual return. Delivery equity "
                   "charges include STT, exchange, SEBI, stamp duty, DP and GST; "
                   "brokerage is excluded.")
    return out


@router.post("/{symbol}/lumpsum")
def stock_lumpsum(symbol: str, body: LumpsumBody, db: Session = Depends(get_db)):
    _row_or_404(db, symbol)
    fv = body.amount * (1 + body.annual_return_pct / 100) ** body.years
    charges = calc.net_in_pocket("BUY+SELL", body.amount, fv)
    return {
        "invested": round(body.amount, 2),
        "future_value": round(fv, 2),
        "gain": round(fv - body.amount, 2),
        "cagr_pct": body.annual_return_pct,
        "years": body.years,
        "charges": charges,
        "net_after_charges": round(fv - charges["total_charges"], 2),
        "note": "Constant-return projection with delivery-trade statutory charges.",
    }


def _find_equity(db: Session, symbol: str) -> Instrument | None:
    want = (symbol or "").upper()
    want = SYMBOL_ALIASES.get(want, want)
    row = (db.query(Instrument)
             .filter_by(kind="EQUITY", symbol=want).one_or_none())
    if row is not None:
        return row
    # Long-tail listing: resolve and create on demand through Yahoo's Indian
    # feed so any NSE/BSE company can be opened, not only the seeded names.
    if not want or len(want) > 24 or not all(c.isalnum() or c in ".-&" for c in want):
        return None
    try:
        from app.services import stock_loader

        return stock_loader.ensure_by_symbol(db, want)
    except Exception:  # noqa: BLE001
        return None


def _row_or_404(db: Session, symbol: str) -> Instrument:
    row = _find_equity(db, symbol)
    if not row:
        raise HTTPException(404, f"{symbol} not in the seeded universe yet")
    return row
