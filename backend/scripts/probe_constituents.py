"""Probe NSE constituent row fields + Midcap ticker + BSE SENSEX sources."""
import json
import yfinance as yf
from jugaad_data.nse import NSELive

n = NSELive()

print("=== live_index NIFTY 50 sample row ===")
try:
    d = n.live_index("NIFTY 50").get("data") or []
    print("rows:", len(d))
    print(json.dumps(d[0], indent=2, default=str))
except Exception as e:
    print("ERR", type(e).__name__, e)

print("\n=== live_index INDIA VIX ===")
try:
    d = n.live_index("INDIA VIX").get("data") or []
    print("rows:", len(d))
    if d:
        print(json.dumps(d[0], default=str))
except Exception as e:
    print("ERR", type(e).__name__, e)

print("\n=== midcap ticker candidates ===")
for t in ["^NSEMDCP50", "^CNXMDCP", "NIFTY_MIDCAP_100.NS", "^CNX100", "^CNXMDCP100", "NIFTYMIDCAP100.NS"]:
    try:
        h = yf.Ticker(t).history(period="5d", auto_adjust=False)
        print(t, "->", None if h.empty else (len(h), round(float(h["Close"].iloc[-1]), 2)))
    except Exception as e:
        print(t, "ERR", type(e).__name__, str(e)[:80])

print("\n=== BSE sensex list attempts ===")
import requests
for url in [
    "https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w?Group=&Scripcode=&industry=&segment=Equity&status=Active",
    "https://api.bseindia.com/BseIndiaAPI/api/SensexConstituents/w",
    "https://www.bseindia.com/api/GetSensexConstituents",
]:
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.bseindia.com/"})
        print(url[:60], r.status_code, (r.text or "")[:120].replace("\n", " "))
    except Exception as e:
        print(url[:60], "ERR", type(e).__name__, str(e)[:80])
