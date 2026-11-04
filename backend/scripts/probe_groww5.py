import json
import re

import httpx

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"}
r = httpx.get("https://groww.in/mutual-funds/parag-parikh-long-term-value-fund-direct-growth",
              headers=H, timeout=30, follow_redirects=True)
m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
mf = json.loads(m.group(1))["props"]["pageProps"]["mfServerSideData"]
hold = mf.get("holdings")
print("holdings type", type(hold), list(hold.keys()) if isinstance(hold, dict) else len(hold))
print(json.dumps(hold, indent=1)[:3000])
print("=== stats ===")
print(json.dumps(mf.get("stats"), indent=1)[:1200])
print("=== return_stats ===")
print(json.dumps(mf.get("return_stats"), indent=1)[:1600])
print("=== key fields ===")
for k in ("expense_ratio", "aum", "exit_load", "benchmark_name", "portfolio_turnover",
          "category", "sub_category", "riskometer", "nav", "nav_date", "plan_type",
          "scheme_type", "launch_date", "fund_manager"):
    print(k, "=", mf.get(k))
print("=== analysis ===")
print(json.dumps(mf.get("analysis"), indent=1)[:800])

print("=== sitemap count ===")
xml = open("data/groww_mf_sitemap.xml", encoding="utf-8").read()
urls = re.findall(r"<loc>(.*?)</loc>", xml)
print(len(urls))
print(urls[1:4])
