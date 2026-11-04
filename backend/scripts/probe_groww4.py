import json

import httpx

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://groww.in/",
    "Origin": "https://groww.in",
    "x-app-id": "groww-web",
    "x-request-id": "web",
}

cands = [
    "https://groww.in/v1/api/data/mf/web/v4/scheme/detail/122639",
    "https://groww.in/v1/api/data/mf/web/v4/scheme/122639",
    "https://groww.in/v1/api/data/mf/web/v3/scheme/122639",
    "https://groww.in/v1/api/data/mf/web/v4/scheme/122639/portfolio",
    "https://groww.in/v1/api/data/mf/web/v4/scheme/detail/122639/portfolio",
    "https://groww.in/v1/api/data/mf/web/v4/scheme/search/parag",
]
for u in cands:
    try:
        r = httpx.get(u, headers=H, timeout=20)
        print(u, r.status_code, r.text[:220].replace("\n", " "))
    except Exception as e:
        print(u, "ERR", str(e)[:80])

print("=== NSE ETF ===")
from app.data.adapters import nse_adapter as N

sess = N.nse.session()
res = sess.s.get("https://www.nseindia.com/api/etf", timeout=20,
                 headers={"Referer": "https://www.nseindia.com/"})
rows = res.json().get("data") or []
print("count", len(rows))
print(json.dumps(rows[0], indent=1))
print("keys", list(rows[0].keys()))
for r in rows[:12]:
    print(r.get("symbol"), r.get("ltP"), r.get("nav"), r.get("iNav"), r.get("per"))
