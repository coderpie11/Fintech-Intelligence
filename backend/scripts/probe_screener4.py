import httpx
from bs4 import BeautifulSoup

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"}
r = httpx.get("https://www.screener.in/company/RELIANCE/consolidated/", headers=H,
              timeout=30, follow_redirects=True)
soup = BeautifulSoup(r.text, "lxml")
for sec_id in ("profit-loss", "balance-sheet", "cash-flow", "shareholding"):
    sec = soup.find("section", id=sec_id)
    table = sec.find("table") if sec else None
    print("=====", sec_id, bool(table))
    if not table:
        continue
    for tr in table.find_all("tr")[:16]:
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
        print(cells[:8])
