import json
import re

import httpx

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"}

r = httpx.get("https://groww.in/mutual-funds/parag-parikh-long-term-value-fund-direct-growth",
              headers=H, timeout=30, follow_redirects=True)
m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', r.text, re.S)
data = json.loads(m.group(1))
print("top keys", list(data.keys()))
props = data.get("props", {}).get("pageProps", {})
print("pageProps keys", list(props.keys()))


def walk(obj, path="", depth=0):
    if depth > 4:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}"
            if isinstance(v, (dict, list)):
                walk(v, p, depth + 1)
            elif isinstance(v, str) and len(v) < 90:
                if any(t in k.lower() for t in ("expense", "aum", "exit", "nav", "name", "category", "risk", "benchmark")):
                    print(p, "=", v)


walk(props)

print("=== find holdings arrays ===")


def find(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("holdings", "topHoldings", "portfolio", "holdingsData") and isinstance(v, list) and v:
                print("FOUND", path + "." + k, "len", len(v))
                print(json.dumps(v[:2], indent=1)[:1200])
            find(v, path + "." + k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:6]):
            find(v, f"{path}[{i}]")


find(props)

print("=== NSE ETF row ===")
from app.data.adapters import nse_adapter as N

sess = N.nse.session()
res = sess.s.get("https://www.nseindia.com/api/etf", timeout=20,
                 headers={"Referer": "https://www.nseindia.com/"})
rows = res.json().get("data") or []
print("count", len(rows))
print(json.dumps(rows[0], indent=1))
print(json.dumps(rows[1], indent=1))
