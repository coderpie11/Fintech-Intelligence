import re

import httpx

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"}
r = httpx.get("https://www.screener.in/company/RELIANCE/consolidated/", headers=H,
              timeout=30, follow_redirects=True)
t = r.text
for sec in ("profit-loss", "balance-sheet", "cash-flow", "shareholding", "ratios"):
    i = t.find(f'id="{sec}"')
    print("=====", sec, i)
    if i > 0:
        chunk = t[i:i + 5000]
        # strip tags roughly
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", chunk, re.S)
        for row in rows[:14]:
            cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S)
            clean = [re.sub(r"<[^>]+>", "", c).strip()[:22] for c in cells]
            if clean:
                print(clean)
        print("---- raw head ----")
        print(chunk[:900].replace("\n", " "))
