import requests, json
HEAD = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}
for u in [
    "https://nsearchives.nseindia.com/content/indices/ind_close_all_2021.csv",
    "https://nsearchives.nseindia.com/content/indices/ind_close_all_2024.csv",
    "https://nsearchives.nseindia.com/content/indices/ind_close_all_2025.csv",
    "https://nsearchives.nseindia.com/content/indices/ind_close_all_2026.csv",
]:
    try:
        r = requests.get(u, headers=HEAD, timeout=20)
        print(u.split("/")[-1], r.status_code, len(r.text), r.text[:80].replace("\n", " | "))
    except Exception as e:
        print(u, "ERR", type(e).__name__)

for q in ["NIFTY FIN SERVICE", "NIFTY MIDCAP 100", "NIFTY SMALLCAP 100"]:
    try:
        r = requests.get("https://query1.finance.yahoo.com/v1/finance/search",
                         params={"q": q, "quotesCount": 10, "newsCount": 0}, headers=HEAD, timeout=20)
        j = r.json()
        print("\n", q)
        for x in (j.get("quotes") or [])[:10]:
            print("  ", x.get("symbol"), "|", x.get("shortname"), "|", x.get("quoteType"), "|", x.get("exchange"))
    except Exception as e:
        print(q, "ERR", type(e).__name__, str(e)[:100])
