import json
import re

import httpx

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"}
r = httpx.get("https://groww.in/mutual-funds/parag-parikh-long-term-value-fund-direct-growth",
              headers=H, timeout=30, follow_redirects=True)
m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
data = json.loads(m.group(1))
mf = data["props"]["pageProps"]["mfServerSideData"]
print("mf keys", list(mf.keys()))
for k in mf:
    v = mf[k]
    if isinstance(v, dict):
        print(k, "dict keys:", list(v.keys())[:30])
    elif isinstance(v, list):
        print(k, "list len", len(v), "first", json.dumps(v[0])[:200] if v else None)
    else:
        print(k, "=", str(v)[:120])
print(json.dumps(mf.get("fund_details"), indent=1)[:3000])
