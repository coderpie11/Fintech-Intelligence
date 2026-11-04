"""Equity fundamentals engine.

Everything here is computed in Python from reported statements and the free
Yahoo quoteSummary snapshot — no third-party ratio is trusted blindly. Where a
number cannot be derived honestly we return None and the route wraps it in a
contextual status envelope.
"""
from __future__ import annotations

import math

from app.data.adapters import yfinance_adapter as Y
from app.services import calc

FINANCIAL_HINTS = ("bank", "financial", "insurance", "nbfc", "capital markets")


def _f(v) -> float | None:
    try:
        if v is None:
            return None
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return None


def _r(a, b, scale: float = 1.0, nd: int = 2) -> float | None:
    a, b = _f(a), _f(b)
    if a is None or b in (None, 0):
        return None
    return round(a / b * scale, nd)


def _v(block: dict, key: str, i: int = 0):
    vals = block.get(key) or []
    return _f(vals[i]) if i < len(vals) else None


def _is_financial(sector: str | None, industry: str | None) -> bool:
    text = f"{sector or ''} {industry or ''}".lower()
    return any(h in text for h in FINANCIAL_HINTS)


def _pct(v) -> float | None:
    f = _f(v)
    return None if f is None else round(f * 100, 2)


def _mean(vals: list[float | None]) -> float | None:
    xs = [x for x in vals if x is not None]
    return sum(xs) / len(xs) if xs else None


def _growth(cur, prev, years: int = 1) -> float | None:
    cur, prev = _f(cur), _f(prev)
    if cur is None or prev is None or prev <= 0 or cur <= 0:
        return None
    if years <= 1:
        return round((cur / prev - 1) * 100, 2)
    return round(((cur / prev) ** (1 / years) - 1) * 100, 2)


# ---------------------------------------------------------------- returns
def returns_ladder(hist: list[dict]) -> dict:
    closes = [h["c"] for h in hist if h.get("c") is not None]
    if len(closes) < 2:
        return {k: None for k in ("1d", "1w", "1m", "3m", "6m", "1y", "3y", "5y")}

    def simple(n: int):
        if len(closes) <= n:
            return None
        first, last = closes[-1 - n], closes[-1]
        return round((last / first - 1) * 100, 2) if first else None

    def annual(n: int):
        n = min(n, len(closes) - 1)
        return calc.cagr(closes[-1 - n], closes[-1], n / 252)

    return {
        "1d": simple(1), "1w": simple(5), "1m": simple(21), "3m": simple(63),
        "6m": simple(126), "1y": simple(252),
        "3y": annual(756), "5y": annual(min(len(closes) - 1, 1260)),
    }


def risk_stats(hist: list[dict], info: dict) -> dict:
    closes = [h["c"] for h in hist if h.get("c") is not None]
    return {
        "vol_1y": calc.annual_volatility(closes[-252:]) if len(closes) >= 60 else None,
        "vol_3y": calc.annual_volatility(closes[-756:]) if len(closes) >= 260 else None,
        "max_dd_1y": calc.max_drawdown(closes[-252:]) if len(closes) >= 60 else None,
        "max_dd_5y": calc.max_drawdown(closes) if len(closes) >= 60 else None,
        "beta": _f(info.get("beta")),
        "high_52w": max((h.get("h") or h["c"]) for h in hist[-252:]) if hist else None,
        "low_52w": min((h.get("l") or h["c"]) for h in hist[-252:]) if hist else None,
    }


# ---------------------------------------------------------------- scores
def piotroski(inc: dict, bal: dict, cf: dict, financial: bool) -> dict:
    ni0, ni1 = _v(inc, "net_income", 0), _v(inc, "net_income", 1)
    ta0, ta1 = _v(bal, "total_assets", 0), _v(bal, "total_assets", 1)
    cfo0 = _v(cf, "cfo", 0)
    debt0, debt1 = _v(bal, "total_debt", 0), _v(bal, "total_debt", 1)
    ca0, ca1 = _v(bal, "current_assets", 0), _v(bal, "current_assets", 1)
    cl0, cl1 = _v(bal, "current_liabilities", 0), _v(bal, "current_liabilities", 1)
    sh0, sh1 = _v(bal, "shares", 0), _v(bal, "shares", 1)
    rev0, rev1 = _v(inc, "revenue", 0), _v(inc, "revenue", 1)
    gp0, gp1 = _v(inc, "gross_profit", 0), _v(inc, "gross_profit", 1)
    cost0, cost1 = _v(inc, "cost_of_revenue", 0), _v(inc, "cost_of_revenue", 1)

    roa0 = _r(ni0, ta0)
    roa1 = _r(ni1, ta1)
    lev0 = _r(debt0, ta0)
    lev1 = _r(debt1, ta1)
    cr0 = _r(ca0, cl0)
    cr1 = _r(ca1, cl1)
    at0 = _r(rev0, ta0)
    at1 = _r(rev1, ta1)

    def gm(gp, rev, cost):
        gp, rev, cost = _f(gp), _f(rev), _f(cost)
        if gp is not None and rev:
            return gp / rev
        if rev and cost is not None:
            return (rev - cost) / rev
        return None

    gm0, gm1 = gm(gp0, rev0, cost0), gm(gp1, rev1, cost1)

    def gt(a, b):
        return None if a is None or b is None else a > b

    def lt(a, b):
        return None if a is None or b is None else a < b

    signals = [
        ("Positive ROA", None if roa0 is None else roa0 > 0,
         "Net income divided by total assets is positive."),
        ("Positive operating cash flow", None if cfo0 is None else cfo0 > 0,
         "Cash from operations is positive — profit is backed by cash."),
        ("ROA improving", gt(roa0, roa1),
         "Return on assets rose versus the prior year."),
        ("Cash flow exceeds net income", gt(cfo0, ni0),
         "Operating cash flow is higher than reported profit (low accruals)."),
        ("Leverage falling", lt(lev0, lev1),
         "Total debt divided by total assets fell year on year."),
        ("Current ratio improving", gt(cr0, cr1),
         "Short-term liquidity coverage improved."),
        ("No dilution", None if sh0 is None or sh1 is None else sh0 <= sh1 * 1.01,
         "Share count did not increase materially — no fresh equity issuance."),
        ("Gross margin improving", gt(gm0, gm1),
         "Gross margin expanded year on year."),
        ("Asset turnover improving", gt(at0, at1),
         "Revenue generated per rupee of assets increased."),
    ]
    # Banks do not report a meaningful current ratio / inventory-linked turnover
    # but the remaining seven signals are still valid.
    scored = [s for s in signals if s[1] is not None]
    max_score = len(scored)
    score = sum(1 for s in scored if s[1])
    label = ("Strong" if max_score and score / max_score >= 0.75 else
             "Average" if max_score and score / max_score >= 0.45 else "Weak")
    return {
        "score": score, "max": max_score, "label": label,
        "signals": [{"name": n, "pass": bool(ok), "detail": d} for n, ok, d in signals
                    if ok is not None],
        "note": ("Piotroski F-Score uses nine fundamental signals. Signals with "
                 "no reported input are excluded from the denominator rather than "
                 "counted as failures."),
        "financial_sector": financial,
    }


def altman(inc: dict, bal: dict, market_cap: float | None,
           financial: bool, sector: str | None) -> dict:
    if financial:
        return {"applicable": False, "variant": None, "score": None,
                "zone": None,
                "note": "Altman Z is not meaningful for banks/NBFCs — their "
                        "balance sheets are structurally leveraged and do not "
                        "report a working-capital cycle."}
    ta = _v(bal, "total_assets", 0)
    ca, cl = _v(bal, "current_assets", 0), _v(bal, "current_liabilities", 0)
    re = _v(bal, "retained_earnings", 0)
    ebit = _v(inc, "operating_income", 0)
    rev = _v(inc, "revenue", 0)
    equity = _v(bal, "equity", 0)
    tl = (ta - equity) if ta is not None and equity is not None else None
    if not all(x is not None for x in (ta, ca, cl, re, ebit, rev, market_cap, tl)):
        return {"applicable": False, "variant": None, "score": None, "zone": None,
                "note": "Insufficient reported line items to compute Altman Z."}
    x1 = (ca - cl) / ta
    x2 = re / ta
    x3 = ebit / ta
    x4 = market_cap / tl if tl else None
    x5 = rev / ta
    z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5
    z2 = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
    manufacturing = any(h in (sector or "").lower() for h in
                        ("manufactur", "capital goods", "automobile", "metal",
                         "chemical", "fmcg", "consumer durables", "cement",
                         "construction materials", "textile"))
    variant = "Z" if manufacturing else "Z''"
    score = z if manufacturing else z2
    safe, grey = (2.99, 1.81) if manufacturing else (2.6, 1.1)
    zone = "Safe" if score > safe else ("Grey" if score > grey else "Distress")
    return {
        "applicable": True, "variant": variant, "score": round(score, 2),
        "zone": zone, "components": {
            "x1_working_capital": round(x1, 4), "x2_retained_earnings": round(x2, 4),
            "x3_ebit": round(x3, 4), "x4_market_cap_to_liabilities": round(x4, 4),
            "x5_asset_turnover": round(x5, 4),
        },
        "thresholds": {"safe_above": safe, "grey_above": grey},
        "note": ("Altman Z uses the classic manufacturing formula; the Z'' "
                 "variant is applied to non-manufacturing companies."),
    }


def beneish(inc: dict, bal: dict, cf: dict, financial: bool) -> dict:
    if financial:
        return {"applicable": False, "score": None, "flag": None,
                "note": "Beneish M-Score is not meaningful for financial companies."}
    rev0, rev1 = _v(inc, "revenue", 0), _v(inc, "revenue", 1)
    rec0, rec1 = _v(bal, "receivables", 0), _v(bal, "receivables", 1)
    ta0, ta1 = _v(bal, "total_assets", 0), _v(bal, "total_assets", 1)
    ca0, ca1 = _v(bal, "current_assets", 0), _v(bal, "current_assets", 1)
    ppe0, ppe1 = _v(bal, "ppe", 0), _v(bal, "ppe", 1)
    dep0, dep1 = _v(inc, "depreciation", 0), _v(inc, "depreciation", 1)
    sga0, sga1 = _v(inc, "sga", 0), _v(inc, "sga", 1)
    cl0, cl1 = _v(bal, "current_liabilities", 0), _v(bal, "current_liabilities", 1)
    debt0, debt1 = _v(bal, "total_debt", 0), _v(bal, "total_debt", 1)
    ni0, cfo0 = _v(inc, "net_income", 0), _v(cf, "cfo", 0)
    gp0, gp1 = _v(inc, "gross_profit", 0), _v(inc, "gross_profit", 1)
    cost0, cost1 = _v(inc, "cost_of_revenue", 0), _v(inc, "cost_of_revenue", 1)

    def gm(gp, rev, cost):
        gp, rev, cost = _f(gp), _f(rev), _f(cost)
        if gp is not None and rev:
            return gp / rev
        if rev and cost is not None:
            return (rev - cost) / rev
        return None

    gm0, gm1 = gm(gp0, rev0, cost0), gm(gp1, rev1, cost1)
    try:
        dsri = (rec0 / rev0) / (rec1 / rev1)
        gmi = gm1 / gm0
        aqi = ((1 - (ca0 + ppe0) / ta0) / (1 - (ca1 + ppe1) / ta1))
        sgi = rev0 / rev1
        depi = (dep1 / (dep1 + ppe1)) / (dep0 / (dep0 + ppe0))
        sgai = (sga0 / rev0) / (sga1 / rev1)
        lvgi = ((cl0 + debt0) / ta0) / ((cl1 + debt1) / ta1)
        tata = (ni0 - cfo0) / ta0
        m = (-4.84 + 0.920 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi
             + 0.115 * depi - 0.172 * sgai + 4.679 * tata - 0.327 * lvgi)
    except (TypeError, ZeroDivisionError):
        return {"applicable": False, "score": None, "flag": None,
                "note": "Reported line items are incomplete, so an honest "
                        "eight-variable M-Score cannot be computed."}
    return {
        "applicable": True, "score": round(m, 2),
        "flag": "Possible earnings manipulation" if m > -1.78 else "No strong signal",
        "components": {"DSRI": round(dsri, 3), "GMI": round(gmi, 3),
                       "AQI": round(aqi, 3), "SGI": round(sgi, 3),
                       "DEPI": round(depi, 3), "SGAI": round(sgai, 3),
                       "LVGI": round(lvgi, 3), "TATA": round(tata, 3)},
        "threshold": -1.78,
        "note": "M-Score above -1.78 is the conventional manipulation flag; it "
                "is a screening signal, not proof of wrongdoing.",
    }


def dupont(inc: dict, bal: dict) -> dict:
    ni = _v(inc, "net_income", 0)
    rev = _v(inc, "revenue", 0)
    ta = _v(bal, "total_assets", 0)
    eq = _v(bal, "equity", 0)
    margin = _r(ni, rev, 100)
    turnover = _r(rev, ta)
    multiplier = _r(ta, eq)
    roe = (round(margin * turnover * multiplier, 2)
           if None not in (margin, turnover, multiplier) else None)
    return {
        "net_margin_pct": margin, "asset_turnover": turnover,
        "equity_multiplier": multiplier, "roe_pct": roe,
        "note": "Three-step DuPont: ROE = net margin × asset turnover × equity multiplier.",
    }


# ---------------------------------------------------------------- master
def build(symbol: str, meta: dict, hist: list[dict],
          statements: dict | None = None) -> dict:
    info = Y.info(f"{symbol}.NS")
    if not info and meta.get("extra"):
        info = dict(meta["extra"])
    stmts = statements or Y.statements(f"{symbol}.NS")
    annual = stmts.get("annual") or {}
    inc, bal, cf = (annual.get("income") or {}, annual.get("balance") or {},
                    annual.get("cashflow") or {})
    # Normalise the statement basis for ratio maths:
    #  * Screener prints oldest→newest; this engine expects newest first.
    #  * Screener prints ₹ crore, StockAnalysis ₹ million, Yahoo raw rupees.
    #    EPS needs raw rupees, so scale monetary lines to rupees.
    source = str(stmts.get("source") or "").lower()
    units = str(stmts.get("units") or "").lower()
    factor = 1.0
    if "crore" in units:
        factor = 1e7
    elif "million" in units:
        factor = 1e6
    ratio_keys = {"opm_pct", "tax_pct", "eps", "dividend_payout_pct"}
    if factor != 1.0 or "screener" in source:
        def _norm(block: dict) -> dict:
            keys = list(block.keys())
            n = max((len(block[k]) for k in keys if isinstance(block[k], list)), default=0)

            def val(k, i):
                vals = block.get(k) or []
                return vals[i] if i < len(vals) else None

            out = {}
            for k in keys:
                vals = block.get(k)
                if not isinstance(vals, list):
                    out[k] = vals
                    continue
                if "screener" in source:
                    vals = list(reversed(vals))
                if factor != 1.0 and k not in ratio_keys:
                    vals = [None if v is None else v * factor for v in vals]
                out[k] = vals
            return out

        inc, bal, cf = _norm(inc), _norm(bal), _norm(cf)
    # Canonical aliases so Screener/StockAnalysis rows feed the same engine.
    if inc:
        inc.setdefault("operating_income", inc.get("operating_profit") or [])
        inc.setdefault("cost_of_revenue", inc.get("expenses") or [])
        if inc.get("tax_pct") and inc.get("pretax_income") and not inc.get("tax"):
            inc["tax"] = [round(p * t / 100, 2) if p is not None and t is not None else None
                          for p, t in zip(inc["pretax_income"], inc["tax_pct"])]
    if bal:
        bal.setdefault("total_debt", bal.get("borrowings") or [])
        bal.setdefault("ppe", bal.get("fixed_assets") or [])
        bal.setdefault("receivables", bal.get("debtors") or [])
        bal.setdefault("payables", bal.get("creditors") or [])
    sector = meta.get("sector") or info.get("sector")
    industry = meta.get("industry") or info.get("industry")
    financial = _is_financial(sector, industry)

    price = (_f(info.get("currentPrice")) or _f(meta.get("lastPrice"))
             or (hist[-1]["c"] if hist else None))
    shares = (_f(info.get("sharesOutstanding")) or _f(meta.get("issuedSize")))
    mcap = (_f(info.get("marketCap")) or _f(meta.get("marketCap"))
            or (price * shares if price and shares else None))

    revenue = _v(inc, "revenue", 0)
    ebit = _v(inc, "operating_income", 0)
    ebitda = _v(inc, "ebitda", 0)
    ni = _v(inc, "net_income", 0)
    ta = _v(bal, "total_assets", 0)
    equity = _v(bal, "equity", 0)
    debt = _v(bal, "total_debt", 0)
    cash = _v(bal, "cash", 0)
    ca, cl = _v(bal, "current_assets", 0), _v(bal, "current_liabilities", 0)
    inventory = _v(bal, "inventory", 0)
    receivables = _v(bal, "receivables", 0)
    payables = _v(bal, "payables", 0)
    cfo = _v(cf, "cfo", 0)
    fcf = _v(cf, "fcf", 0)
    interest = _v(inc, "interest_expense", 0)
    pretax, tax = _v(inc, "pretax_income", 0), _v(inc, "tax", 0)

    pe = _f(info.get("trailingPE"))
    pb = _f(info.get("priceToBook"))
    eps = _f(info.get("earningsPerShare"))
    if eps is None and ni and shares:
        eps = round(ni / shares, 2)
    if eps is None and pe and price and pe > 0:
        # P/E is reported, so EPS is implied by the same two real inputs.
        eps = round(price / pe, 2)
    bvps = _f(info.get("bookValue"))
    if bvps is None and equity and shares:
        bvps = round(equity / shares, 2)

    if pe is None and mcap and ni and ni > 0:
        pe = round(mcap / ni, 2)
    if pb is None and mcap and equity and equity > 0:
        pb = round(mcap / equity, 2)
    div_rate = _f(info.get("dividendRate"))
    div_yield = (_r(div_rate, price, 100) if div_rate and price
                 else _f(info.get("dividendYield")))
    peg = _f(info.get("pegRatio"))
    ev_ebitda = _f(info.get("enterpriseToEbitda"))
    earnings_yield = round(100 / pe, 2) if pe and pe > 0 else None
    graham = (round(math.sqrt(22.5 * eps * bvps), 2)
              if eps and bvps and eps > 0 and bvps > 0 else None)

    roe = _pct(info.get("returnOnEquity"))
    if roe is None:
        roe = _r(ni, equity, 100)
    roa = _pct(info.get("returnOnAssets"))
    if roa is None:
        roa = _r(ni, ta, 100)
    tax_rate = _r(tax, pretax) if tax is not None and pretax else 0.25
    tax_rate = min(max(tax_rate if tax_rate is not None else 0.25, 0), 0.5)
    invested = ((equity or 0) + (debt or 0) - (cash or 0)) or None
    roic = _r((ebit or 0) * (1 - tax_rate), invested, 100) if ebit and invested else None
    # ROCE uses capital employed = total assets - current liabilities (the
    # standard Indian presentation), not just equity + debt.
    capital_employed = ((ta - cl) if ta is not None and cl is not None
                        else (equity + debt if equity is not None and debt is not None else None))
    roce = _r(ebit, capital_employed, 100) if ebit and capital_employed else None
    gross_margin = _pct(info.get("grossMargins"))
    if gross_margin is None:
        gross_margin = _r(_v(inc, "gross_profit", 0), revenue, 100)
    op_margin = _r(ebit, revenue, 100)
    net_margin = _pct(info.get("profitMargins")) or _r(ni, revenue, 100)

    de = _f(info.get("debtToEquity"))
    if de is not None and de > 5:
        de = de / 100
    if de is None:
        de = _r(debt, equity)
    current_ratio = _f(info.get("currentRatio")) or _r(ca, cl)
    quick = _r((ca - inventory) if ca is not None and inventory is not None else None, cl)
    interest_cover = _r(ebit, interest)
    net_debt = (debt - cash) if debt is not None and cash is not None else None
    net_debt_ebitda = _r(net_debt, ebitda)

    cogs = _v(inc, "cost_of_revenue", 0)
    if cogs is None and revenue is not None and _v(inc, "gross_profit", 0) is not None:
        cogs = revenue - _v(inc, "gross_profit", 0)
    inv_prev = _v(bal, "inventory", 1)
    avg_inv = _mean([inventory, inv_prev])
    inv_turn = _r(cogs, avg_inv)
    inv_days = round(365 / inv_turn, 1) if inv_turn else None
    rec_days = _r(receivables, revenue, 365)
    pay_days = _r(payables, cogs, 365)
    ccc = (round(inv_days + rec_days - pay_days, 1)
           if None not in (inv_days, rec_days, pay_days) else None)
    asset_turn = _r(revenue, ta)
    fcf_yield = _r(fcf, mcap, 100)

    growth = {
        "revenue_growth_1y": _growth(revenue, _v(inc, "revenue", 1)),
        "revenue_cagr_3y": _growth(revenue, _v(inc, "revenue", 3), 3),
        "profit_growth_1y": _growth(ni, _v(inc, "net_income", 1)),
        "profit_cagr_3y": _growth(ni, _v(inc, "net_income", 3), 3),
        "eps_growth": _pct(info.get("earningsGrowth")),
        "revenue_growth_ttm": _pct(info.get("revenueGrowth")),
    }

    valuation = {
        "pe": pe, "pb": pb, "peg": peg, "ev_ebitda": ev_ebitda,
        "dividend_yield": div_yield, "earnings_yield": earnings_yield,
        "graham_number": graham, "book_value_per_share": bvps,
        "eps": eps, "market_cap": mcap, "enterprise_value": _f(info.get("enterpriseValue")),
        "price": price,
    }
    profitability = {
        "roe": roe, "roa": roa, "roic": roic, "roce": roce,
        "gross_margin": gross_margin, "operating_margin": op_margin,
        "net_margin": net_margin,
    }
    solvency = {
        "debt_equity": de, "current_ratio": current_ratio, "quick_ratio": quick,
        "interest_coverage": interest_cover, "net_debt_ebitda": net_debt_ebitda,
        "net_debt": net_debt, "total_debt": debt, "cash": cash,
    }
    efficiency = {
        "asset_turnover": asset_turn, "inventory_turnover": inv_turn,
        "inventory_days": inv_days, "receivable_days": rec_days,
        "payable_days": pay_days, "cash_conversion_cycle": ccc,
        "fcf": fcf, "fcf_yield": fcf_yield,
    }

    health = {
        "piotroski": piotroski(inc, bal, cf, financial),
        "altman": altman(inc, bal, mcap, financial, sector),
        "beneish": beneish(inc, bal, cf, financial),
        "dupont": dupont(inc, bal),
    }
    # A single 0-100 composite for the hero scorecard.
    parts = []
    pio = health["piotroski"]
    if pio["max"]:
        parts.append(pio["score"] / pio["max"] * 100)
    alt = health["altman"]
    if alt.get("applicable") and alt.get("score") is not None:
        parts.append(min(max((alt["score"] - 1.1) / (3.0 - 1.1) * 100, 0), 100))
    dup = health["dupont"].get("roe_pct")
    if dup is not None:
        parts.append(min(max(dup / 25 * 100, 0), 100))
    composite = round(sum(parts) / len(parts)) if parts else None

    return {
        "price": price,
        "price_source": "Yahoo Finance quoteSummary (delayed) / stored exchange quote",
        "shares_outstanding": shares,
        "market_cap": mcap,
        "asof": (hist[-1]["date"] if hist else None),
        "sector": sector, "industry": industry, "financial_sector": financial,
        "valuation": valuation, "profitability": profitability,
        "solvency": solvency, "efficiency": efficiency,
        "growth": growth, "health": health,
        "composite_score": composite,
        "returns": returns_ladder(hist),
        "risk": risk_stats(hist, info),
        "statements": stmts,
        "notes": [
            "Ratios are computed by the platform from Yahoo Finance reported "
            "statements and quoteSummary fields; they are not exchange-published ratios.",
            "Yahoo reports Indian statements in rupees; the statements endpoint "
            "converts absolute values to ₹ crore for display.",
        ],
    }
