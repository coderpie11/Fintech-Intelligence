import json

import httpx
import yfinance as yf

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"}

print("=== Groww scheme page ===")
urls = [
    "https://groww.in/mutual-funds/parag-parikh-long-term-value-fund-direct-growth",
    "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
]
for u in urls:
    try:
        r = httpx.get(u, headers=H, timeout=30, follow_redirects=True)
        t = r.text
        print(u, r.status_code, len(t), "holdings" in t.lower(), "expense" in t.lower())
        # look for embedded json
        for token in ("__NEXT_DATA__", "holdings", "expenseRatio", "aum"):
            i = t.find(token)
            print("  ", token, i)
        if "expenseRatio" in t:
            i = t.find("expenseRatio")
            print("   ctx", t[max(0, i - 200):i + 300].replace("\n", " ")[:500])
    except Exception as e:
        print(u, "ERR", type(e).__name__, str(e)[:100])

print("=== Groww search api ===")
for u in [
    "https://groww.in/v1/api/data/mf/web/v4/scheme/search/parag%20parikh",
    "https://groww.in/v1/api/data/mf/web/v3/scheme/search/parag",
    "https://groww.in/v1/api/data/mf/web/v2/scheme/search/parag",
]:
    try:
        r = httpx.get(u, headers=H, timeout=20)
        print(u, r.status_code, r.text[:300])
    except Exception as e:
        print(u, "ERR", str(e)[:80])

print("=== NSE ETF endpoints ===")
from app.data.adapters import nse_adapter as N

sess = N.nse.session()
for p in ["/api/etf", "/api/etfmaster", "/api/etf-list"]:
    try:
        r = sess.s.get("https://www.nseindia.com" + p, timeout=20,
                       headers={"Referer": "https://www.nseindia.com/"})
        print(p, r.status_code, len(r.text), r.text[:250])
    except Exception as e:
        print(p, "ERR", str(e)[:100])

print("=== Yahoo index intraday ===")
for t in ("^NSEI", "^BSESN", "^NSEBANK", "^INDIAVIX", "^CNXIT", "NIFTY_MIDCAP_100.NS", "^CNXSC"):
    try:
        h = yf.Ticker(t).history(period="5d", interval="5m", auto_adjust=False)
        print(t, h.shape, h.index[-1] if len(h) else None)
    except Exception as e:
        print(t, "ERR", type(e).__name__, str(e)[:80])

print("=== Yahoo ETF quote fields ===")
tk = yf.Ticker("GOLDBEES.NS")
info = tk.info or {}
print({k: info.get(k) for k in ("navPrice", "previousClose", "fiftyTwoWeekHigh",
                                 "fiftyTwoWeekLow", "volume", "averageVolume",
                                 "totalAssets", "yield", "beta3Year") if info.get(k) is not None})
