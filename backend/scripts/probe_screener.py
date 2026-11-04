import httpx

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"}
for u in [
    "https://www.screener.in/company/RELIANCE/consolidated/",
    "https://www.screener.in/company/RELIANCE/",
    "https://www.screener.in/api/company/RELIANCE/",
]:
    try:
        r = httpx.get(u, headers=H, timeout=30, follow_redirects=True)
        print(u, r.status_code, len(r.text))
        t = r.text
        i = t.lower().find("shareholding")
        print(" shareholding idx", i)
        if i > 0:
            print(t[i:i + 900].replace("\n", " ")[:900])
    except Exception as e:
        print(u, "ERR", type(e).__name__, str(e)[:100])
