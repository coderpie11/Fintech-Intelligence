import httpx

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"}
for u in [
    "https://groww.in/sitemap.xml",
    "https://groww.in/sitemap-mutual-funds.xml",
    "https://groww.in/mutual-funds/sitemap.xml",
    "https://groww.in/robots.txt",
]:
    try:
        r = httpx.get(u, headers=H, timeout=30, follow_redirects=True)
        print(u, r.status_code, len(r.text))
        print(r.text[:600].replace("\n", " "))
    except Exception as e:
        print(u, "ERR", str(e)[:100])
