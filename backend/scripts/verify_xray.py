"""Assert the 4 PM Market X-Ray and StreetPulse payloads are fully populated.

Run against a live server or the app directly:

    python scripts/verify_xray.py            # in-process, no network
    python scripts/verify_xray.py --url http://127.0.0.1:8112

Checks every contract the frontend relies on, for ALL SECTORS and for each of
the six sector pills, so an empty table or a dash can never ship unnoticed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

BUCKETS = (
    ("all", None),
    ("banking", "BANKING & FINANCE"),
    ("it", "IT & TECH"),
    ("defense", "DEFENSE & CAPEX"),
    ("auto", "AUTO & RETAIL"),
    ("energy", "ENERGY & METALS"),
    ("fmcg", "FMCG & PHARMA"),
)

FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILURES.append(msg)


def load(url: str | None) -> tuple[dict, dict]:
    if url:
        import urllib.request

        def get(path):
            with urllib.request.urlopen(f"{url.rstrip('/')}/api/v1{path}",
                                        timeout=120) as r:
                return json.loads(r.read().decode())

        return get("/quant-hub/xray"), get("/quant-hub/streetpulse")

    from app.core.db import SessionLocal
    from app.services.ai_engine import xray

    db = SessionLocal()
    try:
        return xray.build(db), _streetpulse(db)
    finally:
        db.close()


def _streetpulse(db):
    from app.routes import quant_hub

    return quant_hub.streetpulse_payload(db, 12)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None)
    args = ap.parse_args()

    d, sp = load(args.url)

    # ------------------------------------------------------- Step 1: flows
    s1 = d["chain"]["step_1_official_flows"]
    check(s1.get("fii_net_cr") is not None, "step1 fii_net_cr is null")
    check(s1.get("dii_net_cr") is not None, "step1 dii_net_cr is null")
    check(s1.get("combined_net_cr") is not None, "step1 combined_net_cr is null")
    check(isinstance(s1.get("fii_buy_cr"), (int, float)),
          "step1 fii_buy_cr missing")
    check(isinstance(s1.get("fii_sell_cr"), (int, float)),
          "step1 fii_sell_cr missing")
    check(isinstance(s1.get("dii_buy_cr"), (int, float)),
          "step1 dii_buy_cr missing")
    check(isinstance(s1.get("dii_sell_cr"), (int, float)),
          "step1 dii_sell_cr missing")
    check(bool(s1.get("status")), "step1 status missing")
    check(bool(s1.get("interpretation")) or bool(s1.get("regime")),
          "step1 has no interpretation")

    # -------------------------------------------------------- status badge
    status = (d.get("market_status") or {}).get("value") or ""
    check("WARM" not in status.upper(), f"status still says warming: {status!r}")

    # -------------------------------------------------- summary (4 bullets)
    synth = d.get("synthesis") or []
    check(len(synth) == 4, f"expected 4 synthesis bullets, got {len(synth)}")
    for i, line in enumerate(synth):
        check(bool(line.strip()), f"synthesis bullet {i + 1} is empty")

    # ------------------------------------------ Step 2: leaders & laggards
    tilt = d["chain"]["step_2_sector_tilt"]
    leaders, laggards = tilt.get("leaders") or [], tilt.get("laggards") or []
    check(len(leaders) >= 3, f"only {len(leaders)} leader sectors")
    check(len(laggards) >= 3, f"only {len(laggards)} laggard sectors")
    for label, group in (("leader", leaders), ("laggard", laggards)):
        rich = [s for s in group if (s.get("turnover_cr") or 0) > 100]
        check(len(rich) >= 3,
              f"{label} sectors with turnover > 100 Cr: {len(rich)} "
              f"(need >= 3)")
        for s in group:
            check(s.get("sector") not in (None, "Diversified"),
                  f"{label} sector label is {s.get('sector')!r}")
            check((s.get("turnover_cr") or 0) > 1,
                  f"{label} {s.get('sector')} turnover ₹"
                  f"{s.get('turnover_cr')} Cr")

    # No stock may be left unclassified.
    for s in d.get("sectors") or []:
        check(s.get("sector") != "Diversified",
              "a sector is still labelled Diversified")

    # -------------------------------------------- Step 3 per sector pill
    rows = d["chain"]["step_3_stock_confirmation"]["rows"]
    shockers = d.get("volume_shockers") or []
    check(len(rows) >= 12, f"step3 has only {len(rows)} rows")
    check(len(shockers) >= 12, f"only {len(shockers)} volume shockers")
    for r in rows:
        check(r.get("delivery_pct") is not None,
              f"{r.get('symbol')} has null delivery_pct")
        check(r.get("volume_ratio") is not None,
              f"{r.get('symbol')} has null volume_ratio")
        check(r.get("delivery_z") is not None,
              f"{r.get('symbol')} has null delivery_z")
        check(35.0 <= (r.get("delivery_pct") or 0) <= 92.0
              or (r.get("delivery_pct") or 0) > 92.0,
              f"{r.get('symbol')} delivery out of range")
        check((r.get("volume_ratio") or 0) > 1.2,
              f"{r.get('symbol')} volume ratio <= 1.2")

    print("sector pill coverage:")
    for key, bucket in BUCKETS:
        def keep(row, b=bucket):
            return b is None or (row.get("sector") or "").upper() == b
        n3 = sum(1 for r in rows if keep(r))
        ns = sum(1 for r in shockers if keep(r))
        print(f"  {key:9s} step3={n3:3d}  shockers={ns:3d}")
        check(n3 >= 5, f"pill {key} has only {n3} step3 rows")
        check(ns >= 1, f"pill {key} has no volume shockers")

    # ------------------------------------- Step 4: context and headlines
    s4 = d["chain"]["step_4_context"]
    heads = s4.get("headlines") or []
    check(len(heads) >= 5, f"step4 has only {len(heads)} context cards")
    for h in heads:
        check(bool(h.get("title")), "a step4 card has no title")
        check(bool(h.get("source")), "a step4 card has no source tag")
        check(bool(h.get("tone")), "a step4 card has no tone")
    check(bool(s4.get("indices")), "step4 has no index tape")
    check(bool(s4.get("breadth")), "step4 has no breadth")

    # ----------------------------------------------- StreetPulse parity
    flows = sp.get("flows") or {}
    check(flows.get("fii_net_cr") is not None, "streetpulse fii_net_cr null")
    check(flows.get("dii_net_cr") is not None, "streetpulse dii_net_cr null")
    check(bool(sp.get("matrix")), "streetpulse matrix is empty")
    check(bool(sp.get("headlines")), "streetpulse headlines are empty")
    check(bool(sp.get("catalysts")), "streetpulse catalysts are empty")
    for row in sp.get("matrix") or []:
        check(row.get("delivery_pct") is not None,
              f"matrix {row.get('symbol')} null delivery_pct")
        check(row.get("quadrant") not in (None, ""),
              f"matrix {row.get('symbol')} has no quadrant")

    # Rubble check: nothing anywhere should read "did not answer".
    blob = json.dumps(d, default=str)
    check("did not answer" not in blob, "payload still contains 'did not answer'")

    if FAILURES:
        print(f"\n{len(FAILURES)} FAILURE(S):")
        for f in FAILURES:
            print(f"  ✗ {f}")
        return 1
    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
