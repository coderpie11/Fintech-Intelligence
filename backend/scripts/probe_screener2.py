import re

import httpx

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"}
r = httpx.get("https://www.screener.in/company/RELIANCE/consolidated/", headers=H,
              timeout=30, follow_redirects=True)
t = r.text
for pat in ("Quarterly Shareholding Pattern", "Shareholding Pattern", "Promoters",
            "FIIs", "DIIs"):
    i = t.find(pat)
    print("====", pat, i)
    if i > 0:
        print(t[max(0, i - 200):i + 1200].replace("\n", " ")[:1400])
