import httpx

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"}
r = httpx.get("https://groww.in/mutual-funds/parag-parikh-long-term-value-fund-direct-growth",
              headers=H, timeout=30, follow_redirects=True)
t = r.text
i = t.find("__NEXT_DATA__")
print(repr(t[i - 120:i + 400]))
print("---- holdings ctx ----")
j = t.find("holdings")
print(repr(t[j - 300:j + 800]))
