import json
import os

import httpx
import yfinance as yf

from app.core.config import FMP_API_KEY, FINNHUB_API_KEY

tk = yf.Ticker("RELIANCE.NS")
try:
    info = tk.info or {}
    keys = [
        "trailingPE", "forwardPE", "priceToBook", "bookValue", "dividendYield",
        "dividendRate", "returnOnEquity", "returnOnAssets", "profitMargins",
        "operatingMargins", "debtToEquity", "currentRatio", "ebitda",
        "enterpriseValue", "enterpriseToEbitda", "pegRatio", "earningsPerShare",
        "totalRevenue", "grossMargins", "revenueGrowth", "earningsGrowth",
        "beta", "totalDebt", "totalCash", "sharesOutstanding", "faceValue",
        "marketCap", "currentPrice", "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
        "sector", "industry", "longName",
    ]
    print("INFO", {k: info.get(k) for k in keys if info.get(k) is not None})
except Exception as e:
    print("INFO ERR", type(e).__name__, e)

for name in ("income_stmt", "balance_sheet", "cashflow", "quarterly_income_stmt",
             "quarterly_balance_sheet", "quarterly_cashflow"):
    try:
        df = getattr(tk, name)
        print(name, "shape", None if df is None else df.shape)
        if df is not None and not df.empty:
            print("  cols", [str(c)[:10] for c in df.columns][:6])
            print("  idx", [str(i) for i in df.index][:12])
    except Exception as e:
        print(name, "ERR", type(e).__name__, e)

try:
    fi = tk.fast_info
    print("FAST", {k: getattr(fi, k, None) for k in ("last_price", "year_high", "year_low", "market_cap")})
except Exception as e:
    print("FAST ERR", e)

try:
    h = tk.history(period="5d", interval="5m", auto_adjust=False)
    print("INTRADAY", h.shape, h.index[0] if len(h) else None, h.index[-1] if len(h) else None)
    if len(h):
        print(h.tail(2)[["Open", "High", "Low", "Close", "Volume"]])
except Exception as e:
    print("INTRADAY ERR", type(e).__name__, e)

print("--- FMP ---")
for path in ("profile", "key-metrics-ttm", "ratios-ttm", "income-statement"):
    try:
        r = httpx.get(
            f"https://financialmodelingprep.com/api/v3/{path}/RELIANCE.NS",
            params={"apikey": FMP_API_KEY, "limit": 5}, timeout=25,
        )
        print(path, r.status_code, str(r.text)[:300])
    except Exception as e:
        print(path, "ERR", e)

print("--- FINNHUB ---")
try:
    r = httpx.get(
        "https://finnhub.io/api/v1/stock/metric",
        params={"symbol": "RELIANCE.NS", "metric": "all", "token": FINNHUB_API_KEY},
        timeout=25,
    )
    print(r.status_code, str(r.text)[:400])
except Exception as e:
    print("ERR", e)
