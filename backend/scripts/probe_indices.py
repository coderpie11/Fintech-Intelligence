"""Probe: find working Yahoo tickers for every index + inspect NSE index fields."""
import json

import yfinance as yf
from jugaad_data.nse import NSELive

CANDIDATES = {
    "NIFTY 50": ["^NSEI"],
    "SENSEX": ["^BSESN"],
    "NIFTY BANK": ["^NSEBANK"],
    "NIFTY NEXT 50": ["^NSMIDCP", "^NSEI"],
    "NIFTY FIN SERVICE": ["^CNXFIN", "NIFTY_FIN_SERVICE.NS", "^NSEBANK"],
    "NIFTY MIDCAP 100": ["^CNXMDCP", "^NSEMDCP50", "^CNX100"],
    "NIFTY SMALLCAP 100": ["^CNXSC"],
    "INDIA VIX": ["^INDIAVIX"],
    "NIFTY IT": ["^CNXIT"],
    "NIFTY FMCG": ["^CNXFMCG"],
    "NIFTY PHARMA": ["^CNXPHARMA"],
    "NIFTY AUTO": ["^CNXAUTO"],
    "NIFTY METAL": ["^CNXMETAL"],
    "NIFTY REALTY": ["^CNXREALTY"],
    "NIFTY ENERGY": ["^CNXENERGY"],
    "NIFTY INFRASTRUCTURE": ["^CNXINFRA"],
    "NIFTY PSE": ["^CNXPSE"],
    "NIFTY INDIA CONSUMPTION": ["^CNXCONSUM"],
}

for name, tickers in CANDIDATES.items():
    found = None
    for t in tickers:
        try:
            h = yf.Ticker(t).history(period="5d", auto_adjust=False)
            if not h.empty:
                found = (t, round(float(h["Close"].iloc[-1]), 2), len(h))
                break
        except Exception as e:
            pass
    print(f"{name:28s} -> {found}")

n = NSELive()
raw = n.all_indices()
rows = raw.get("data") or []
print("\nall_indices fields:", sorted(rows[0].keys()) if rows else "none")
for r in rows:
    if r.get("index") in ("NIFTY 50", "SENSEX", "INDIA VIX"):
        print(json.dumps({k: r.get(k) for k in
                          ("index", "last", "percentChange", "pe", "pb", "dy",
                           "yearHigh", "yearLow", "open", "previousClose")}))
