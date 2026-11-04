"""StockAnalysis.com adapter — free five-year annual statements for NSE names.

Screener.in rate-limits aggressively (HTTP 429). StockAnalysis publishes the
same fiscal-year tables in a stable HTML layout without a login, so it is used
as the statement fallback. Values are INR million; the platform converts them
to ₹ crore. Nothing is computed unless the source actually prints it.
"""
from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup

from app.core.config import cache_get, cache_set

BASE = "https://stockanalysis.com/quote/nse"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")

PAGES = {
    "income": "financials",
    "balance": "financials/balance-sheet",
    "cashflow": "financials/cash-flow-statement",
}


def _num(text: str) -> float | None:
    t = (text or "").replace(",", "").replace("%", "").strip()
    if not t or t in ("-", "—", "N/A", "TTM"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _label(text: str) -> str:
    """Rows carry a duplicated growth label inside spans, e.g.
    'Revenue Revenue Growth'. Keep the first human label."""
    t = re.sub(r"\s+", " ", (text or "")).strip()
    for suffix in (" Growth",):
        if t.endswith(suffix):
            t = t[: -len(suffix)]
    parts = t.split(" ")
    # collapse an immediately repeated phrase ("Revenue Revenue")
    half = len(parts) // 2
    if half and parts[:half] == parts[half:2 * half]:
        t = " ".join(parts[:half])
    return t


def _table(html: str) -> tuple[list[str], dict[str, list[float | None]]]:
    soup = BeautifulSoup(html, "lxml")
    headers: list[str] | None = None
    series: dict[str, list[float | None]] = {}
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        hdr = [c.get_text(" ", strip=True) for c in rows[0].find_all(["th", "td"])]
        if not hdr or hdr[0].lower() != "fiscal year":
            continue
        hdr = hdr[1:]          # drop the row-label column
        if headers is None:
            headers = hdr
        for row in rows[2:]:
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            label = _label(cells[0].get_text(" ", strip=True))
            vals = [_num(c.get_text(" ", strip=True)) for c in cells[1:]]
            vals += [None] * (len(headers) - len(vals))
            if label and label not in series:
                series[label] = vals[:len(headers)]
    if not headers:
        return [], {}
    return headers, series


def _find(series: dict, *needles: str) -> list[float | None]:
    for needle in needles:
        for k, v in series.items():
            if k.lower() == needle.lower():
                return v
    for needle in needles:
        for k, v in series.items():
            if k.lower().startswith(needle.lower()):
                return v
    return []


def statements(symbol: str) -> dict | None:
    key = f"stockanalysis:{symbol.upper()}"
    hit = cache_get(key)
    if hit is not None:
        return hit
    data: dict[str, tuple[list[str], dict]] = {}
    for section, path in PAGES.items():
        try:
            r = httpx.get(f"{BASE}/{symbol.upper()}/{path}/",
                          headers={"User-Agent": UA}, timeout=30,
                          follow_redirects=True)
            if r.status_code != 200:
                return None
            data[section] = _table(r.text)
        except Exception:  # noqa: BLE001
            return None
    headers, _ = data["income"]
    if not headers:
        return None
    # Drop TTM, keep the five real fiscal years, newest first.
    keep = [i for i, h in enumerate(headers)
            if h.strip().upper().startswith("FY")][:5]
    if len(keep) < 4:
        return None
    periods = [headers[i].replace("FY ", "").strip() for i in keep]

    def take(series: dict, *needles: str) -> list[float | None]:
        vals = _find(series, *needles)
        return [vals[i] if i < len(vals) else None for i in keep]

    _, inc_s = data["income"]
    _, bal_s = data["balance"]
    _, cf_s = data["cashflow"]

    revenue = take(inc_s, "Revenue")
    gross = take(inc_s, "Gross Profit")
    op = take(inc_s, "Operating Income")
    ni = take(inc_s, "Net Income")
    eps = take(inc_s, "Earnings Per Share", "EPS")
    dep = take(cf_s, "Depreciation & Amortization")
    ebitda = [round(o + d, 2) if o is not None and d is not None else None
              for o, d in zip(op, dep)]
    cogs = [round(r - g, 2) if r is not None and g is not None else None
            for r, g in zip(revenue, gross)]

    cash = take(bal_s, "Cash & Equivalents", "Cash & Short-Term Investments")
    recv = take(bal_s, "Receivables")
    inv = take(bal_s, "Inventory")
    ca = take(bal_s, "Total Current Assets")
    cl = take(bal_s, "Total Current Liabilities")
    ta = take(bal_s, "Total Assets")
    tl = take(bal_s, "Total Liabilities")
    ppe = take(bal_s, "Property, Plant & Equipment")
    equity = take(bal_s, "Shareholders' Equity", "Total Common Equity")
    debt = take(bal_s, "Total Debt")
    retained = take(bal_s, "Retained Earnings")
    payables = take(bal_s, "Accounts Payable")
    common = take(bal_s, "Common Stock")
    reserves = [round(e - c, 2) if e is not None and c is not None else None
                for e, c in zip(equity, common)]

    cfo = take(cf_s, "Operating Cash Flow")
    cfi = take(cf_s, "Investing Cash Flow")
    cff = take(cf_s, "Financing Cash Flow")
    capex = take(cf_s, "Capital Expenditures")
    fcf = take(cf_s, "Free Cash Flow")
    net_cf = take(cf_s, "Net Cash Flow")

    out = {
        "basis": "consolidated", "units": "INR million", "source": "StockAnalysis.com",
        "url": f"{BASE}/{symbol.upper()}/financials/",
        "annual": {
            "periods": [f"{p}-03-31" for p in periods],
            "income": {
                "revenue": revenue, "gross_profit": gross, "cost_of_revenue": cogs,
                "operating_income": op, "net_income": ni, "eps": eps,
                "ebitda": ebitda, "depreciation": dep,
            },
            "balance": {
                "cash": cash, "receivables": recv, "inventory": inv,
                "current_assets": ca, "current_liabilities": cl,
                "total_assets": ta, "total_liabilities": tl, "ppe": ppe,
                "equity": equity, "total_debt": debt, "retained_earnings": retained,
                "payables": payables, "equity_capital": common, "reserves": reserves,
            },
            "cashflow": {
                "cfo": cfo, "cfi": cfi, "cff": cff, "capex": capex,
                "fcf": fcf, "net_cash_flow": net_cf,
            },
        },
        # values are INR million; the route converts to crore using this factor
        "scale_to_crore": 0.1,
    }
    cache_set(key, out, ttl=12 * 3600)
    return out
