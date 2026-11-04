"""Probe 5y history for questionable tickers + NSE historical index API."""
import datetime as dt
import json
import yfinance as yf
from jugaad_data.nse import NSELive

print("=== 5y history checks ===")
for t in ["^NSEI", "^BSESN", "^CNXFIN", "^CNXSC", "NIFTY_MIDCAP_100.NS", "^NSEMDCP50", "^INDIAVIX"]:
    try:
        h = yf.Ticker(t).history(period="5y", auto_adjust=False)
        print(f"{t:24s} rows={len(h):5d} first={None if h.empty else h.index[0].date()} last={None if h.empty else h.index[-1].date()} close={None if h.empty else round(float(h['Close'].iloc[-1]),2)}")
    except Exception as e:
        print(t, "ERR", type(e).__name__, str(e)[:80])

print("\n=== NSE historical index API ===")
n = NSELive()
s = n.session()
import requests
from datetime import date, timedelta
to = date.today()
frm = to - timedelta(days=365 * 5)
url = "https://www.nseindia.com/api/historical/indicesHistory"
params = {"indexType": "NIFTY MIDCAP 100",
          "from": frm.strftime("%d-%m-%Y"), "to": to.strftime("%d-%m-%Y")}
try:
    r = s.get(url, params=params, timeout=20, headers={"Referer": "https://www.nseindia.com/"})
    print("status", r.status_code, "len", len(r.text))
    print(r.text[:400])
    if r.status_code == 200:
        j = r.json()
        print("keys", list(j.keys())[:10])
        d = j.get("data") or []
        print("rows", len(d), d[:2])
except Exception as e:
    print("ERR", type(e).__name__, str(e)[:200])

print("\n=== allIndices pe/pb/dy ===")
try:
    rows = n.all_indices().get("data") or []
    for r in rows:
        if r.get("index") in ("NIFTY 50", "SENSEX", "NIFTY MIDCAP 100", "INDIA VIX", "NIFTY IT"):
            print(json.dumps({k: r.get(k) for k in ("index", "last", "percentChange", "pe", "pb", "dy", "open", "previousClose", "yearHigh", "yearLow")}, default=str))
except Exception as e:
    print("ERR", type(e).__name__, str(e)[:200])
