"""Probe NSE historical index API + allIndices pe/pb/dy."""
import json
from datetime import date, timedelta
from jugaad_data.nse import NSELive

n = NSELive()
to = date.today()
frm = to - timedelta(days=365 * 5)
url = "https://www.nseindia.com/api/historical/indicesHistory"
for idx in ["NIFTY MIDCAP 100", "NIFTY FIN SERVICE", "NIFTY SMALLCAP 100"]:
    params = {"indexType": idx, "from": frm.strftime("%d-%m-%Y"), "to": to.strftime("%d-%m-%Y")}
    try:
        r = n.s.get(url, params=params, timeout=25, headers={"Referer": "https://www.nseindia.com/"})
        print(idx, "status", r.status_code, "len", len(r.text), r.text[:200].replace("\n", " "))
        if r.status_code == 200:
            j = r.json()
            d = j.get("data") or []
            print("  rows", len(d), "sample", json.dumps(d[0], default=str)[:300] if d else None)
    except Exception as e:
        print(idx, "ERR", type(e).__name__, str(e)[:200])

print("\n=== allIndices fields ===")
try:
    rows = n.all_indices().get("data") or []
    print("fields:", sorted(rows[0].keys()) if rows else "none")
    for r in rows:
        if r.get("index") in ("NIFTY 50", "SENSEX", "NIFTY MIDCAP 100", "INDIA VIX", "NIFTY IT"):
            print(json.dumps({k: r.get(k) for k in ("index", "last", "percentChange", "pe", "pb", "dy", "open", "previousClose", "yearHigh", "yearLow")}, default=str))
except Exception as e:
    print("ERR", type(e).__name__, str(e)[:200])
