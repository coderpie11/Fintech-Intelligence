import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)

paths = ["/api/v1/health", "/api/v1/market/status", "/api/v1/indices",
         "/api/v1/indices/nifty-50", "/api/v1/stocks", "/api/v1/stocks/TCS",
         "/api/v1/pulse", "/api/v1/reits", "/api/v1/bonds", "/api/v1/events",
         "/api/v1/mutual-funds", "/api/v1/academy", "/api/v1/academy/fno-first-steps",
         "/api/v1/ipos", "/api/v1/commodities", "/api/v1/quant/streetpulse",
         "/api/v1/search?q=rel", "/api/v1/quant/rangecast/RELIANCE?horizon_days=7"]
for p in paths:
    r = c.get(p)
    print(p, "->", r.status_code, str(r.json())[:100])

print("\n-- live F&O chain (NIFTY) --")
r = c.get("/api/v1/fno/NIFTY")
print(r.status_code, str(r.json())[:300] if r.status_code == 200 else r.json())

print("\n-- sandbox CRUD --")
o = c.post("/api/v1/sandbox/orders", json={"symbol": "RELIANCE", "side": "BUY",
                                          "quantity": 10}).json()
print("order placed:", o)
print("summary:", str(c.get("/api/v1/sandbox/summary").json())[:220])
print("closed:", c.post(f"/api/v1/sandbox/orders/{o['id']}/close").json())
print("watch add:", c.post("/api/v1/watchlist", params={"symbol": "TCS"}).json())
print("watchlist:", str(c.get("/api/v1/watchlist").json())[:180])
