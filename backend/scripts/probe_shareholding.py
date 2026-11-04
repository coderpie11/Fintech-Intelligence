from app.data.adapters import nse_adapter as N

sess = N.nse.session()
paths = [
    "/api/corporate-share-holdings?index=equities&symbol=RELIANCE",
    "/api/shareholding-pattern?symbol=RELIANCE",
    "/api/corporate-share-holdings?symbol=RELIANCE",
]
for p in paths:
    try:
        r = sess.s.get("https://www.nseindia.com" + p, timeout=20,
                       headers={"Referer": "https://www.nseindia.com/get-quotes/equity?symbol=RELIANCE"})
        print(p, r.status_code, len(r.text), r.text[:500].replace("\n", " "))
    except Exception as e:
        print(p, "ERR", str(e)[:100])
