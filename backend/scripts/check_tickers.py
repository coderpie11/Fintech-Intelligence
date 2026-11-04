import json
import sqlite3

import yfinance as yf

from app.seed.universe import INDICES

c = sqlite3.connect("data/bfi.db")
rows = {r[0]: (json.loads(r[1]) if r[1] else {})
        for r in c.execute("select symbol, meta from instruments where kind='INDEX'")}

for s in INDICES:
    m = rows.get(s["nse"], {})
    live = m.get("last")
    y = None
    if s.get("yahoo"):
        try:
            h = yf.Ticker(s["yahoo"]).history(period="5d", auto_adjust=False)
            y = round(float(h["Close"].iloc[-1]), 2) if len(h) else None
        except Exception:
            y = "ERR"
    print(f"{s['nse']:24s} live={str(live):>10s} yahoo({s.get('yahoo')})={y}")
