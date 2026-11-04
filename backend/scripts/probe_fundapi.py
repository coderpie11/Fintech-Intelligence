import httpx

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0 Safari/537.36",
     "Accept": "application/json"}

for u in [
    "https://api.kuvera.in/mf/api/v5/fund_schemes/122639.json",
    "https://api.kuvera.in/mf/api/v4/fund_schemes/122639.json",
    "https://api.kuvera.in/mf/api/v5/fund_schemes/list.json",
    "https://api.kuvera.in/mf/api/v4/fund_schemes/list.json",
    "https://api.tickertape.in/mutualfunds/122639",
    "https://www.valueresearchonline.com/api/funds/122639",
]:
    try:
        r = httpx.get(u, headers=H, timeout=20, follow_redirects=True)
        print(u, r.status_code, len(r.text), r.text[:260].replace("\n", " "))
    except Exception as e:
        print(u, "ERR", type(e).__name__, str(e)[:90])
