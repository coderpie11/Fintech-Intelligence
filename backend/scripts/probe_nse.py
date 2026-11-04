import json
import requests
from jugaad_data.nse import NSELive

class NSEPlus(NSELive):
    _routes = dict(
        NSELive._routes,
        ipo_announce="/ipo-announce",
        ipo_centre="/ipo-centre-scrutinary"
    )

n = NSEPlus()
for name in ["ipo_announce", "ipo_centre"]:
    try:
        r = n.get(name)
        print(name, "OK", len(json.dumps(r)), str(r)[:200])
    except Exception as e:
        print(name, "FAIL", type(e).__name__, str(e)[:120])

try:
    r = requests.post("https://webapi.chittorgarh.com/AllWebService/GetIPOListAll/1",
                      headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"},
                      json={}, timeout=30)
    print("chittorgarh:", r.status_code, len(r.content), r.text[:150])
except Exception as e:
    print("chittorgarh FAIL", type(e).__name__, str(e)[:120])
