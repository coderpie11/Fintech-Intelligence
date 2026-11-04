"""Yahoo Finance adapter — daily OHLCV, intraday candles, company
fundamentals and reported financial statements for equities, indices, ETFs,
commodities and FX. Free and delayed. Swift to swap for a broker later because
the platform never reads Yahoo directly outside this module.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

import httpx
import pandas as pd
import yfinance as yf

from app.core.config import cache_get, cache_set

PERIODS = {"3m": "3mo", "6m": "6mo", "1y": "1y", "3y": "3y", "5y": "5y",
           "10y": "10y", "max": "max"}

# Corporate actions rename Yahoo symbols without notice. Keep a small factual
# alias map so the platform follows the listed successor entity.
TICKER_ALIASES = {
    "TATAMOTORS.NS": "TMPV.NS",   # passenger-vehicle entity after the 2025 demerger
    "UNICOMMERCE.NS": "UNIECOM.NS",  # Yahoo lists Unicommerce under its NSE symbol
    "ZOMATO.NS": "ETERNAL.NS",     # Zomato renamed Eternal in 2025
}

# Yahoo intraday data is delayed by roughly 15 minutes on the free feed. The
# quote cache is deliberately tiny (15 seconds): the detail pages poll at the
# same cadence, so users see every new candle without hammering the source.
LIVE_TTL = 15


def _ticker(ticker: str) -> str:
    return TICKER_ALIASES.get(ticker.upper(), ticker)


# ------------------------------------------------------------------ history
def history(ticker: str, period: str = "5y") -> list[dict]:
    ticker = _ticker(ticker)
    # The cache key carries the IST date so a new trading session always
    # refreshes the daily series instead of serving yesterday's last candle.
    today = (dt.datetime.utcnow() + dt.timedelta(hours=5, minutes=30)).date()
    key = f"yf:{ticker}:{period}:{today}"
    hit = cache_get(key)
    if hit is not None:
        return hit
    df = yf.Ticker(ticker).history(period=PERIODS.get(period, "5y"),
                                   auto_adjust=False)
    if df.empty:
        raise RuntimeError(f"Yahoo returned no history for {ticker}")
    rows = []
    for idx, r in df.iterrows():
        rows.append({
            "date": idx.strftime("%Y-%m-%d"),
            "o": round(float(r["Open"]), 4), "h": round(float(r["High"]), 4),
            "l": round(float(r["Low"]), 4), "c": round(float(r["Close"]), 4),
            "v": int(r["Volume"]),
        })
    out = rows[-1300:]
    cache_set(key, out, ttl=6 * 3600)
    return out


# ------------------------------------------------------- live session frames
def _num(v) -> float | None:
    try:
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _frame_rows(sub: pd.DataFrame) -> list[dict]:
    """Turn a yfinance OHLCV frame into the platform's candle dictionaries."""
    rows: list[dict] = []
    if sub is None or getattr(sub, "empty", True):
        return rows
    for idx, r in sub.iterrows():
        close = _num(r.get("Close"))
        if close is None:
            continue
        open_, high, low = _num(r.get("Open")), _num(r.get("High")), _num(r.get("Low"))
        vol = _num(r.get("Volume"))
        # Show every clock in IST. yfinance returns the index in the exchange's
        # own timezone, so a COMEX gold candle would otherwise be labelled with
        # New York hours (00:00–11:50) on an Indian desk.
        try:
            ts = idx.tz_convert("Asia/Kolkata") if idx.tzinfo else idx
        except Exception:  # noqa: BLE001
            ts = idx
        rows.append({
            "datetime": ts.isoformat(),
            "date": ts.strftime("%Y-%m-%d"),
            "time": ts.strftime("%H:%M"),
            "o": round(open_, 2) if open_ is not None else None,
            "h": round(high, 2) if high is not None else None,
            "l": round(low, 2) if low is not None else None,
            "c": round(close, 2),
            "v": int(vol or 0),
        })
    return rows


def _sessions_from_frame(sub: pd.DataFrame) -> list[dict]:
    """Split a multi-session intraday frame into ordered session buckets."""
    if sub is None or getattr(sub, "empty", True):
        return []
    sub = sub.dropna(subset=["Close"])
    if sub.empty:
        return []
    dates = sorted({idx.date() for idx in sub.index})
    out = []
    for day in dates:
        part = sub[[idx.date() == day for idx in sub.index]]
        rows = _frame_rows(part)
        if rows:
            out.append({"date": str(day), "rows": rows})
    return out


def live_sessions(ticker: str, period: str = "5d", interval: str = "5m") -> list[dict]:
    """Latest 5 sessions of candles with a 15-second TTL.

    Both the quote reconciler and the chart read this same cache entry, so the
    header price is guaranteed to be the final candle that the chart draws.
    """
    ticker = _ticker(ticker)
    key = f"yf:live:{ticker}:{interval}:{period}"
    hit = cache_get(key)
    if hit is not None:
        return hit
    sessions: list[dict] = []
    try:
        df = yf.Ticker(ticker).history(period=period, interval=interval,
                                       auto_adjust=False)
        sessions = _sessions_from_frame(df)
    except Exception:  # noqa: BLE001
        sessions = []
    cache_set(key, sessions, ttl=LIVE_TTL if sessions else 5)
    return sessions


def live_sessions_batch(tickers: list[str], period: str = "5d",
                        interval: str = "5m", chunk: int = 45) -> dict[str, list[dict]]:
    """Batch live sessions for screener/indices/home lists.

    Cached per ticker for 15 seconds. Only cache misses are downloaded, in
    chunks, so overlapping list pages reuse the same work.
    """
    uniq = list(dict.fromkeys(_ticker(t) for t in tickers if t))
    out: dict[str, list[dict]] = {}
    missing: list[str] = []
    for t in uniq:
        hit = cache_get(f"yf:live:{t}:{interval}:{period}")
        if hit is not None:
            out[t] = hit
        else:
            missing.append(t)
    for start in range(0, len(missing), chunk):
        batch = missing[start:start + chunk]
        try:
            df = yf.download(batch, period=period, interval=interval,
                             group_by="ticker", progress=False, threads=True,
                             auto_adjust=False)
        except Exception:  # noqa: BLE001
            df = None
        for t in batch:
            sessions: list[dict] = []
            try:
                if df is not None and not df.empty:
                    sub = df[t] if isinstance(df.columns, pd.MultiIndex) else df
                    sessions = _sessions_from_frame(sub)
            except Exception:  # noqa: BLE001
                sessions = []
            out[t] = sessions
            cache_set(f"yf:live:{t}:{interval}:{period}", sessions,
                      ttl=LIVE_TTL if sessions else 5)
    return out


def _best_session(sessions: list[dict], min_points: int = 15) -> dict | None:
    """Most recent session that actually has enough bars to draw a curve.

    A market that has just opened can have two or three 5-minute candles. The
    old endpoint treated that as a complete 1D chart, which is how a two-point
    straight line reached the browser. Prefer the latest *substantial* session
    so 1D always shows real market fluctuation.
    """
    if not sessions:
        return None
    for session in reversed(sessions):
        if len(session.get("rows") or []) >= min_points:
            return session
    return sessions[-1]


def intraday(ticker: str, interval: str = "5m", period: str = "5d") -> dict:
    """Intraday candles sliced to the latest usable trading session.

    The primary feed is 5-minute bars. If the newest session is sparse (for
    example a just-opened market), the adapter retries with 15-minute bars and
    then falls back to the latest session that has enough real candles. It
    never fabricates a point and never returns a two-point "chart".
    """
    ticker = _ticker(ticker)
    sessions = live_sessions(ticker, period=period, interval=interval)
    chosen = _best_session(sessions, 15)
    used_interval = interval

    if chosen is None or len(chosen.get("rows") or []) < 15:
        if interval != "15m":
            alt = live_sessions(ticker, period=period, interval="15m")
            alt_chosen = _best_session(alt, 15)
            if alt_chosen and len(alt_chosen.get("rows") or []) > len(chosen.get("rows") or [] if chosen else []):
                sessions, chosen, used_interval = alt, alt_chosen, "15m"

    rows = list(chosen.get("rows") or []) if chosen else []
    session_date = chosen.get("date") if chosen else None

    if len(rows) < 15 and len(sessions) >= 2:
        # Last resort: stitch the two most recent sessions together. Every row
        # is a real candle; the header records the span instead of pretending
        # it is a single day.
        tail = sessions[-2:]
        rows = [r for s in tail for r in (s.get("rows") or [])]
        if tail:
            session_date = f"{tail[0].get('date')}..{tail[-1].get('date')}"

    if not rows:
        raise RuntimeError(f"Yahoo returned no intraday candles for {ticker}")

    out = {"ticker": ticker, "interval": used_interval,
           "session": session_date,
           "source": (f"Yahoo Finance intraday ({used_interval} candles, delayed)"),
           "points": rows,
           "point_count": len(rows)}
    return out


# ---------------------------------------------------------------- symbol search
SEARCH_TTL = 15 * 60
_YAHOO_SEARCH = "https://query2.finance.yahoo.com/v1/finance/search"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")


def search(query: str, count: int = 15) -> list[dict]:
    """Live Yahoo symbol search restricted to Indian NSE/BSE listings.

    Used to make every listed Indian company discoverable even when it is not
    in the local NSE master. Results are cached for 15 minutes so typing in the
    global search does not hammer the upstream endpoint.
    """
    q = (query or "").strip()
    if len(q) < 1:
        return []
    key = f"yf:search:{q.lower()}:{count}"
    hit = cache_get(key)
    if hit is not None:
        return hit
    out: list[dict] = []
    try:
        r = httpx.get(
            _YAHOO_SEARCH,
            params={"q": q, "quotesCount": count, "newsCount": 0,
                    "listsCount": 0, "enableFuzzyQuery": "true",
                    "quotesQueryId": "tss_match_phrase_query"},
            headers={"User-Agent": _UA, "Accept": "application/json"},
            timeout=15,
        )
        if r.status_code == 200:
            for item in (r.json().get("quotes") or []):
                symbol = str(item.get("symbol") or "").upper()
                if not symbol.endswith((".NS", ".BO")):
                    continue
                qtype = str(item.get("quoteType") or item.get("typeDisp") or "").upper()
                if qtype and qtype not in ("EQUITY", "ETF", "MUTUALFUND"):
                    continue
                base = symbol.rsplit(".", 1)[0]
                out.append({
                    "symbol": base,
                    "yahoo": symbol,
                    "exchange": "NSE" if symbol.endswith(".NS") else "BSE",
                    "name": (item.get("longname") or item.get("shortname")
                             or item.get("name") or base),
                    "sector": item.get("sector"),
                    "industry": item.get("industry"),
                    "type": qtype or "EQUITY",
                    "price": _num(item.get("regularMarketPrice")),
                    "changepct": _num(item.get("regularMarketChangePercent")),
                })
    except Exception:  # noqa: BLE001
        out = []
    cache_set(key, out, ttl=SEARCH_TTL)
    return out



# ------------------------------------------------------------------ info
def info(ticker: str) -> dict:
    ticker = _ticker(ticker)
    """Full Yahoo quoteSummary info, cached. Returns {} when throttled."""
    key = f"yf:info:{ticker}"
    hit = cache_get(key)
    if hit is not None:
        return hit
    try:
        data = yf.Ticker(ticker).info or {}
    except Exception:  # noqa: BLE001
        data = {}
    if data:
        cache_set(key, data, ttl=6 * 3600)
    return data


def fast_info(ticker: str) -> dict:
    ticker = _ticker(ticker)
    try:
        fi = yf.Ticker(ticker).fast_info
        return {
            "last_price": getattr(fi, "last_price", None),
            "year_high": getattr(fi, "year_high", None),
            "year_low": getattr(fi, "year_low", None),
            "market_cap": getattr(fi, "market_cap", None),
        }
    except Exception:  # noqa: BLE001
        return {}


def quote_fallback(ticker: str) -> dict | None:
    """Used when an NSE live quote is unavailable; returns last close data."""
    try:
        h = history(ticker, "1y")
        last, prev = h[-1], h[-2]
        return {"lastPrice": last["c"], "prevClose": prev["c"],
                "changepct": round((last["c"] / prev["c"] - 1) * 100, 2)}
    except Exception:  # noqa: BLE001
        return None


def history_multi(tickers: list[str], period: str = "5y") -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for t in tickers:
        try:
            out[t] = history(t, period)
        except Exception:  # noqa: BLE001
            out[t] = []
    return out


# ------------------------------------------------------------------ statements
# Canonical line items the platform understands. Yahoo's row labels vary by
# company, so each canonical key lists the labels it may appear under.
_INCOME_ROWS = {
    "revenue": ["Total Revenue", "Operating Revenue"],
    "gross_profit": ["Gross Profit"],
    "cost_of_revenue": ["Cost Of Revenue", "Reconciled Cost Of Revenue"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "operating_income": ["Operating Income", "EBIT"],
    "net_income": ["Net Income", "Net Income Common Stockholders",
                   "Net Income From Continuing Operation Net Minority Interest"],
    "eps": ["Diluted EPS", "Basic EPS"],
    "interest_expense": ["Interest Expense", "Interest Expense Non Operating"],
    "sga": ["Selling General And Administration", "Selling General And Administrative"],
    "depreciation": ["Reconciled Depreciation", "Depreciation And Amortization",
                     "Depreciation"],
    "tax": ["Tax Provision"],
    "pretax_income": ["Pretax Income"],
}

_BALANCE_ROWS = {
    "total_assets": ["Total Assets"],
    "equity": ["Stockholders Equity", "Common Stock Equity",
               "Total Equity Gross Minority Interest"],
    "total_debt": ["Total Debt"],
    "net_debt": ["Net Debt"],
    "cash": ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"],
    "inventory": ["Inventory"],
    "receivables": ["Accounts Receivable", "Receivables"],
    "current_assets": ["Current Assets"],
    "current_liabilities": ["Current Liabilities"],
    "retained_earnings": ["Retained Earnings"],
    "ppe": ["Net PPE", "Gross PPE"],
    "shares": ["Ordinary Shares Number", "Share Issued"],
    "payables": ["Accounts Payable", "Payables"],
}

_CASH_ROWS = {
    "cfo": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
    "cfi": ["Investing Cash Flow", "Cash Flow From Continuing Investing Activities"],
    "cff": ["Financing Cash Flow", "Cash Flow From Continuing Financing Activities"],
    "fcf": ["Free Cash Flow"],
    "capex": ["Capital Expenditure"],
    "depreciation": ["Depreciation And Amortization", "Depreciation Amortization Depletion"],
}


def _row(df, names: list[str]) -> list[float | None]:
    if df is None or getattr(df, "empty", True):
        return []
    index = {str(i).strip().lower(): i for i in df.index}
    for name in names:
        key = index.get(name.strip().lower())
        if key is None:
            continue
        vals = []
        for v in df.loc[key].tolist():
            try:
                vals.append(None if v is None or v != v else float(v))
            except (TypeError, ValueError):
                vals.append(None)
        return vals
    return []


def _statement(df, spec: dict) -> dict:
    return {key: _row(df, names) for key, names in spec.items()}


def _periods(df) -> list[str]:
    if df is None or getattr(df, "empty", True):
        return []
    out = []
    for c in df.columns:
        try:
            out.append(str(c)[:10])
        except Exception:  # noqa: BLE001
            out.append(str(c))
    return out


def statements(ticker: str) -> dict:
    """Five annual periods + five recent quarters, normalised to canonical
    line items. Cached for six hours; never fabricates a missing line."""
    key = f"yf:stmts:{ticker}"
    ticker = _ticker(ticker)
    key = f"yf:stmts:{ticker}"
    hit = cache_get(key)
    if hit is not None:
        return hit
    tk = yf.Ticker(ticker)

    def safe(attr):
        try:
            df = getattr(tk, attr)
            return df if df is not None and not df.empty else None
        except Exception:  # noqa: BLE001
            return None

    inc_a, bal_a, cf_a = safe("income_stmt"), safe("balance_sheet"), safe("cashflow")
    inc_q, bal_q, cf_q = (safe("quarterly_income_stmt"),
                          safe("quarterly_balance_sheet"),
                          safe("quarterly_cashflow"))

    def pack(inc, bal, cf):
        periods = _periods(inc) or _periods(bal) or _periods(cf)
        return {
            "periods": periods,
            "income": _statement(inc, _INCOME_ROWS),
            "balance": _statement(bal, _BALANCE_ROWS),
            "cashflow": _statement(cf, _CASH_ROWS),
        }

    out = {
        "annual": pack(inc_a, bal_a, cf_a),
        "quarterly": pack(inc_q, bal_q, cf_q),
        "currency": "INR",
        "units": " rupees (as reported by Yahoo Finance )",
        "source": "Yahoo Finance reported statements (consolidated)",
        "fetched_at": dt.datetime.utcnow().isoformat() + "Z",
    }
    if out["annual"]["periods"] or out["quarterly"]["periods"]:
        cache_set(key, out, ttl=6 * 3600)
    return out
