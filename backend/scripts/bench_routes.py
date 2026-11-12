"""Latency benchmark for the demo-critical routes.

Every GET is timed on the wire; every /intraday payload is also checked for a
usable candle count. Run against a live instance:

    python scripts/bench_routes.py [base_url]
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
API = f"{BASE}/api/v1"

GETS = [
    "/health",
    "/indices?expand=true",
    "/indices/sensex",
    "/indices/sensex/intraday",
    "/indices/nifty-50/intraday",
    "/stocks?limit=60",
    "/stocks/RELIANCE",
    "/stocks/RELIANCE/intraday",
    "/stocks/PCJEWELLER/intraday",
    "/etfs",
    "/etfs/NIFTYBEES/intraday",
    "/reits",
    "/reits/EMBASSY/intraday",
    "/commodities",
    "/commodities/detail/GOLD",
    "/commodities/GOLD/intraday",
    "/mutual-funds?limit=40",
    "/pulse",
    "/ipos",
    "/bonds",
    "/quant-hub/streetpulse?limit=12",
    "/quant-hub/streetpulse?limit=24",
    "/quant-hub/rangecast/PCJEWELLER?horizon_days=30",
]

POSTS = [
    ("/quant-hub/ask-dalal", {"question": "pc jewellers"}),
    ("/quant-hub/ask-dalal", {"question": "reliance"}),
    ("/sandbox/quote", {"symbol": "RELIANCE", "quantity": 10}),
    ("/portfolio-xray/analyze", {"holdings": [
        {"symbol": "RELIANCE", "mode": "LUMPSUM", "quantity": 10,
         "buy_price": 2400, "buy_date": "2024-01-15"},
        {"symbol": "NIFTYBEES", "mode": "SIP", "amount": 5000,
         "sip_start": "2024-01-01", "sip_months": 12},
    ]}),
]

TIMEOUT = 60.0


def _call(path: str, body: dict | None = None) -> tuple[int, float, str]:
    url = API + path
    data = None
    headers = {"Accept-Encoding": "gzip"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if body is not None else "GET")
    import time
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
            return resp.status, time.perf_counter() - t0, raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, time.perf_counter() - t0, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return 0, time.perf_counter() - t0, f"{type(e).__name__}: {e}"


def _points(text: str) -> int | None:
    try:
        payload = json.loads(text)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, dict):
        return None
    for key in ("points", "candles"):
        pts = payload.get(key)
        if isinstance(pts, list):
            valid = [p for p in pts
                     if isinstance(p, dict) and p.get("c") is not None]
            return len(valid)
    return None


def main() -> int:
    failures = []
    print(f"{'route':52} {'code':>5} {'secs':>7} {'candles':>8}")
    print("-" * 78)
    for path in GETS:
        code, secs, text = _call(path)
        candles = _points(text) if "intraday" in path else None
        print(f"{path[:52]:52} {code:5} {secs:7.3f} "
              f"{('' if candles is None else candles):>8}")
        if code != 200:
            failures.append((path, code, "http"))
        elif secs > 0.4:
            failures.append((path, code, f"slow {secs:.3f}s"))
        elif candles is not None and candles < 30:
            failures.append((path, code, f"only {candles} candles"))
    for path, body in POSTS:
        label = f"{path} {json.dumps(body)[:26]}"
        code, secs, text = _call(path, body)
        print(f"{label[:52]:52} {code:5} {secs:7.3f}")
        if code != 200:
            failures.append((label, code, text[:160]))
        elif secs > 0.4:
            failures.append((label, code, f"slow {secs:.3f}s"))
    print("-" * 78)
    if failures:
        print("FAILURES:")
        for item in failures:
            print("  ", item)
        return 1
    print("ALL ROUTES < 0.4s, every intraday >= 30 candles")
    return 0


if __name__ == "__main__":
    sys.exit(main())
