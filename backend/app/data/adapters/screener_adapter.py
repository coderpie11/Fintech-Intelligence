"""Screener.in adapter — quarterly shareholding pattern plus standalone and
consolidated annual statements. Free HTML, parsed with BeautifulSoup and
cached aggressively so we never hammer the site. Used only where Yahoo does
not publish the data (shareholding, standalone basis)."""
from __future__ import annotations

import re
import time

import httpx
from bs4 import BeautifulSoup

from app.core.config import cache_get, cache_set

BASE = "https://www.screener.in"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")

# Screener rate-limits with HTTP 429 and sometimes just hangs. Once that is
# seen, stop hammering it for a cooling-off window and let StockAnalysis carry
# the statements. This keeps a 232-name seed from spending hours in timeouts.
_blocked_until = [0.0]
_last_call = [0.0]

# Screener still uses the pre-demerger / pre-listing slug for a few symbols.
SYMBOL_ALIASES = {
    "TATAMOTORS": "TMPV",       # passenger-vehicle entity after the 2025 demerger
    "UNICOMMERCE": "UNIECOM",   # Screener lists Unicommerce under its NSE symbol
}


def _sym(symbol: str) -> str:
    sym = symbol.upper().strip()
    return SYMBOL_ALIASES.get(sym, sym)


def _blocked() -> bool:
    return time.time() < _blocked_until[0]


def _throttle() -> None:
    wait = _last_call[0] + 0.35 - time.time()
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.time()


def _url(symbol: str, consolidated: bool) -> str:
    sym = _sym(symbol)
    return f"{BASE}/company/{sym}/consolidated/" if consolidated else f"{BASE}/company/{sym}/"


def _page(symbol: str, consolidated: bool) -> BeautifulSoup | None:
    if _blocked():
        return None
    key = f"screener:{_sym(symbol)}:{'c' if consolidated else 's'}"
    html = cache_get(key)
    if html is None:
        try:
            _throttle()
            r = httpx.get(_url(symbol, consolidated), headers={"User-Agent": UA},
                          timeout=12, follow_redirects=True)
            if r.status_code == 429:
                _blocked_until[0] = time.time() + 1800
                return None
            if r.status_code != 200:
                return None
            html = r.text
            cache_set(key, html, ttl=12 * 3600)
        except Exception:  # noqa: BLE001
            _blocked_until[0] = time.time() + 300
            return None
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:  # noqa: BLE001
        return None


def _num(text: str) -> float | None:
    t = (text or "").replace(",", "").replace("%", "").strip()
    if not t or t in ("-", "--", "NA", "N/A"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _clean_label(text: str) -> str:
    t = (text or "").replace("\xa0", " ").strip()
    t = re.sub(r"\s*\+$", "", t)
    return re.sub(r"\s+", " ", t)


def _table(soup: BeautifulSoup, section_id: str) -> tuple[list[str], dict[str, list[float | None]]]:
    sec = soup.find("section", id=section_id)
    table = sec.find("table") if sec else None
    if not table:
        return [], {}
    rows = table.find_all("tr")
    if not rows:
        return [], {}
    header = [_clean_label(c.get_text(" ", strip=True))
              for c in rows[0].find_all(["th", "td"])]
    periods = header[1:]
    series: dict[str, list[float | None]] = {}
    for tr in rows[1:]:
        cells = tr.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        label = _clean_label(cells[0].get_text(" ", strip=True))
        vals = [_num(c.get_text(" ", strip=True)) for c in cells[1:]]
        vals += [None] * (len(periods) - len(vals))
        series[label] = vals[:len(periods)]
    return periods, series


def shareholding(symbol: str, consolidated: bool = True) -> dict | None:
    """Quarterly shareholding percentages (last 12 quarters) + holder count."""
    key = f"screener:shp:{symbol.upper()}:{'c' if consolidated else 's'}"
    hit = cache_get(key)
    if hit is not None:
        return hit
    soup = _page(symbol, consolidated)
    if soup is None:
        return None
    periods, series = _table(soup, "shareholding")
    if not periods:
        return None
    want = ["Promoters", "FIIs", "DIIs", "Government", "Public",
            "No. of Shareholders"]
    out_series: dict[str, list[float | None]] = {}
    for name in want:
        vals = series.get(name)
        if vals is None:
            # labels may carry a "+" or extra qualifier
            for k, v in series.items():
                if k.lower().startswith(name.lower()):
                    vals = v
                    break
        if vals is not None:
            out_series[name] = vals[-12:]
    out = {
        "periods": periods[-12:],
        "series": out_series,
        "source": "Screener.in quarterly shareholding pattern",
        "basis": "consolidated" if consolidated else "standalone",
        "url": _url(symbol, consolidated),
    }
    cache_set(key, out, ttl=12 * 3600)
    return out


# Screener row label -> canonical line item. Values are in ₹ crore.
_PL = {
    "revenue": "Sales", "expenses": "Expenses", "operating_profit": "Operating Profit",
    "opm_pct": "OPM %", "other_income": "Other Income",
    "interest_expense": "Interest", "depreciation": "Depreciation",
    "pretax_income": "Profit before tax", "tax_pct": "Tax %",
    "net_income": "Net Profit", "eps": "EPS in Rs",
    "dividend_payout_pct": "Dividend Payout %",
}
_BS = {
    "equity_capital": "Equity Capital", "reserves": "Reserves",
    "borrowings": "Borrowings", "other_liabilities": "Other Liabilities",
    "total_liabilities": "Total Liabilities", "fixed_assets": "Fixed Assets",
    "cwip": "CWIP", "investments": "Investments", "other_assets": "Other Assets",
    "total_assets": "Total Assets",
}
_CF = {
    "cfo": "Cash from Operating Activity", "cfi": "Cash from Investing Activity",
    "cff": "Cash from Financing Activity", "net_cash_flow": "Net Cash Flow",
    "fcf": "Free Cash Flow",
}


def statements(symbol: str, consolidated: bool = False) -> dict | None:
    """Annual statements (last 6 years) on the requested basis, in ₹ crore."""
    key = f"screener:stmts:{symbol.upper()}:{'c' if consolidated else 's'}"
    hit = cache_get(key)
    if hit is not None:
        return hit
    soup = _page(symbol, consolidated)
    if soup is None:
        return None

    def pick(section: str, spec: dict) -> tuple[list[str], dict]:
        periods, series = _table(soup, section)
        # Screener appends a TTM column; annual statements should contain real
        # fiscal-year columns only.
        drop = {i for i, p in enumerate(periods)
                if str(p).strip().upper() in ("TTM",)}
        periods = [p for i, p in enumerate(periods) if i not in drop]
        out = {}
        for canon, label in spec.items():
            vals = series.get(label)
            if canon == "revenue" and not vals:
                # Banks/NBFCs label the top line "Revenue" instead of "Sales".
                vals = series.get("Revenue")
            if vals is None:
                for k, v in series.items():
                    if k.lower() == label.lower() or k.lower().startswith(label.lower()):
                        vals = v
                        break
            vals = [v for i, v in enumerate(vals or []) if i not in drop]
            out[canon] = vals[-6:]
        return periods[-6:], out

    pl_periods, pl = pick("profit-loss", _PL)
    bs_periods, bs = pick("balance-sheet", _BS)
    cf_periods, cf = pick("cash-flow", _CF)
    if not (pl_periods or bs_periods or cf_periods):
        return None
    # derive equity for convenience
    eq = []
    for i in range(len(bs_periods)):
        ec = (bs.get("equity_capital") or [None] * len(bs_periods))[i]
        rs = (bs.get("reserves") or [None] * len(bs_periods))[i]
        eq.append(round(ec + rs, 2) if ec is not None and rs is not None else None)
    bs["equity"] = eq
    # Canonical aliases used by the ratio/health engine.
    pl["operating_income"] = pl.get("operating_profit") or []
    pl["cost_of_revenue"] = pl.get("expenses") or []
    pl["gross_profit"] = [
        round(r - c, 2) if r is not None and c is not None else None
        for r, c in zip(pl.get("revenue") or [], pl.get("expenses") or [])
    ] if pl.get("revenue") and pl.get("expenses") else []
    if pl.get("tax_pct") and pl.get("pretax_income"):
        pl["tax"] = [
            round(p * t / 100, 2) if p is not None and t is not None else None
            for p, t in zip(pl["pretax_income"], pl["tax_pct"])
        ]
    bs["total_debt"] = bs.get("borrowings") or []
    bs["ppe"] = bs.get("fixed_assets") or []
    out = {
        "basis": "consolidated" if consolidated else "standalone",
        "units": "INR crore",
        "source": "Screener.in annual statements",
        "url": _url(symbol, consolidated),
        "annual": {"periods": pl_periods or bs_periods or cf_periods,
                   "income": pl, "balance": bs, "cashflow": cf},
    }
    cache_set(key, out, ttl=12 * 3600)
    return out
