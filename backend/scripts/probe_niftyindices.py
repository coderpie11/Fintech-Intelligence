"""Probe niftyindices historical CSV/JSON endpoints properly."""
import json
import requests

HEAD = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Referer": "https://www.niftyindices.com/reports/historical-data",
        "Origin": "https://www.niftyindices.com",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01"}

s = requests.Session()
try:
    s.get("https://www.niftyindices.com/reports/historical-data", headers=HEAD, timeout=20)
    print("cookie", len(s.cookies))
except Exception as e:
    print("warm ERR", e)

name = "NIFTY MIDCAP 100"
cinfo = json.dumps({"name": name, "startDate": "01-11-2021", "endDate": "01-11-2026", "indexName": name})
for url, mode in [("https://www.niftyindices.com/BackPage/getHistoricaldata", "form"),
                  ("https://www.niftyindices.com/BackPage/getHistoricaldata", "json"),
                  ("https://www.niftyindices.com/BackPage/get_histindices_data", "form")]:
    try:
        if mode == "form":
            r = s.post(url, data={"cinfo": cinfo},
                       headers={**HEAD, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
                       timeout=40)
        else:
            r = s.post(url, json={"cinfo": cinfo},
                       headers={**HEAD, "Content-Type": "application/json"}, timeout=40)
        print(url.split("/")[-1], mode, r.status_code, len(r.text), r.text[:200].replace("\n", " "))
        if r.text.strip().startswith(("[", "{")):
            try:
                j = r.json()
                print("  JSON keys", list(j.keys()) if isinstance(j, dict) else f"list {len(j)}")
                print("  sample", json.dumps(j)[:400])
            except Exception as e:
                print("  json err", e)
    except Exception as e:
        print(url, mode, "ERR", type(e).__name__, str(e)[:120])

print("\n=== niftyindices daily snapshot CSV ===")
for d in ["01112021", "30102026"]:
    u = f"https://nsearchives.nseindia.com/content/indices/ind_close_all_{d}.csv"
    try:
        r = requests.get(u, headers=HEAD, timeout=30)
        print(u.split("/")[-1], r.status_code, len(r.text), r.text[:150].replace("\n", " | "))
    except Exception as e:
        print(u, "ERR", type(e).__name__, str(e)[:100])
