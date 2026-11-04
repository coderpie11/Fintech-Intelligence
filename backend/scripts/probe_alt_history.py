"""Probe alternative history sources for the three thin Yahoo indices."""
import json
import requests
from app.core.config import TWELVEDATA_API_KEY, FMP_API_KEY

HEAD = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

print("=== yahoo chart v8 direct ===")
for sym in ["^CNXFIN", "^CNXSC", "NIFTY_MIDCAP_100.NS"]:
    try:
        r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                         params={"range": "5y", "interval": "1d"}, headers=HEAD, timeout=20)
        j = r.json()
        res = (j.get("chart") or {}).get("result")
        if res:
            ts = res[0].get("timestamp") or []
            print(sym, r.status_code, "bars", len(ts))
        else:
            print(sym, r.status_code, "no result", json.dumps(j)[:200])
    except Exception as e:
        print(sym, "ERR", type(e).__name__, str(e)[:120])

print("\n=== twelve data ===")
for sym, exch in [("NIFTY FIN SERVICE", "NSE"), ("NIFTY MIDCAP 100", "NSE"), ("NIFTY SMALLCAP 100", "NSE"), ("NIFTY 50", "NSE")]:
    try:
        r = requests.get("https://api.twelvedata.com/time_series",
                         params={"symbol": sym, "exchange": exch, "interval": "1day",
                                 "outputsize": 1300, "apikey": TWELVEDATA_API_KEY},
                         headers=HEAD, timeout=30)
        j = r.json()
        vals = j.get("values") or []
        print(sym, r.status_code, "status", j.get("status"), "bars", len(vals),
              "msg", (j.get("message") or "")[:80])
    except Exception as e:
        print(sym, "ERR", type(e).__name__, str(e)[:120])

print("\n=== FMP ===")
for sym in ["^CNXFIN", "^CNXSC", "NIFTY_MIDCAP_100.NS"]:
    try:
        r = requests.get(f"https://financialmodelingprep.com/api/v3/historical-price-full/{sym}",
                         params={"apikey": FMP_API_KEY, "timeseries": 1300}, headers=HEAD, timeout=30)
        j = r.json()
        hist = j.get("historical") or []
        print(sym, r.status_code, "bars", len(hist), (str(j)[:100] if not hist else ""))
    except Exception as e:
        print(sym, "ERR", type(e).__name__, str(e)[:120])

print("\n=== niftyindices.com historical ===")
for name in ["NIFTY MIDCAP 100", "NIFTY FIN SERVICE", "NIFTY SMALLCAP 100"]:
    try:
        payload = {"cinfo": json.dumps({"name": name, "startDate": "01-11-2021",
                                        "endDate": "01-11-2026", "indexName": name})}
        r = requests.post("https://www.niftyindices.com/BackPage/getHistoricaldata",
                          json=payload, headers={**HEAD, "Referer": "https://www.niftyindices.com/reports/historical-data",
                                                 "Content-Type": "application/json"}, timeout=30)
        print(name, r.status_code, len(r.text), r.text[:160].replace("\n", " "))
    except Exception as e:
        print(name, "ERR", type(e).__name__, str(e)[:120])
