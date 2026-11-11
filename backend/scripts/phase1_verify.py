"""Phase-1 database-wide verification report.

Usage (backend running on :8000):

    python scripts/phase1_verify.py

It reads the SQLite store directly for completeness, then hits the live API for
list/detail/chart endpoints and prints one audit table. Read-only.
"""
from __future__ import annotations

import json
import random
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

import httpx

BASE = "http://localhost:8000/api/v1"
DB = Path(__file__).resolve().parent.parent / "data" / "bfi.db"
TIMEOUT = 45

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.seed.universe import INDICES  # noqa: E402

SLUG = {s["nse"]: s["slug"] for s in INDICES}


def num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f


def load(meta, hist):
    m = json.loads(meta) if meta else {}
    try:
        h = json.loads(hist) if hist else []
    except TypeError:
        h = []
    return (m or {}), (h or [])


def last_price(m):
    return num(m.get("lastPrice")) if num(m.get("lastPrice")) is not None else num(m.get("last"))


def spark_ok(h):
    closes = [b.get("c") for b in h[-40:] if isinstance(b, dict) and num(b.get("c")) is not None]
    return len(closes) >= 20


def instrument_stats(c, kind):
    rows = c.execute("select meta, history from instruments where kind=?", (kind,)).fetchall()
    n = len(rows)
    out = {"n": n, "last": 0, "prev": 0, "chg": 0, "w52": 0,
           "hist30": 0, "spark": 0}
    for meta, hist in rows:
        m, h = load(meta, hist)
        out["last"] += last_price(m) is not None
        out["prev"] += num(m.get("prevClose")) is not None
        out["chg"] += num(m.get("changepct")) is not None
        lo = num(m.get("yearLow")) or num(m.get("week52_low"))
        hi = num(m.get("yearHigh")) or num(m.get("week52_high"))
        out["w52"] += lo is not None and hi is not None
        out["hist30"] += len(h) >= 30
        out["spark"] += spark_ok(h)
    return out


def pct(part, whole):
    return f"{(part / whole * 100):5.1f}%" if whole else "   n/a"


def main() -> int:
    c = sqlite3.connect(DB)
    kinds = ["EQUITY", "INDEX", "ETF", "REIT", "INVIT", "COMMODITY"]
    stats = {k: instrument_stats(c, k) for k in kinds}

    funds = c.execute("select navs from fund_schemes").fetchall()
    fund_n = len(funds)
    fund_nav = fund_hist60 = 0
    for (navs,) in funds:
        try:
            series = json.loads(navs) if navs else []
        except TypeError:
            series = []
        if series:
            fund_nav += 1
        if len(series) >= 60:
            fund_hist60 += 1

    bonds = c.execute("select count(*) from bonds").fetchone()[0]
    ipos = c.execute("select count(*) from ipos").fetchone()[0]

    print("=" * 92)
    print("PHASE 1 · DATABASE-WIDE COMPLETENESS AUDIT")
    print("=" * 92)
    header = (f"{'asset class':12}{'rows':>7}{'last px':>18}{'prev close':>14}"
              f"{'52W range':>18}{'>=30 bars':>12}{'spark>=20':>12}")
    print(header)
    print("-" * len(header))
    label = {"EQUITY": "Equities", "INDEX": "Indices", "ETF": "ETFs",
             "REIT": "REITs", "INVIT": "InvITs", "COMMODITY": "Commodities"}
    for k in kinds:
        s = stats[k]
        print(f"{label[k]:12}{s['n']:>7}"
              f"{str(s['last']) + ' (' + pct(s['last'], s['n']).strip() + ')':>18}"
              f"{str(s['prev']) + ' (' + pct(s['prev'], s['n']).strip() + ')':>14}"
              f"{str(s['w52']) + ' (' + pct(s['w52'], s['n']).strip() + ')':>18}"
              f"{str(s['hist30']) + ' (' + pct(s['hist30'], s['n']).strip() + ')':>12}"
              f"{str(s['spark']) + ' (' + pct(s['spark'], s['n']).strip() + ')':>12}")
    print(f"{'Mutual funds':12}{fund_n:>7}"
          f"{'NAV ' + str(fund_nav):>18}{'':>14}{'':>18}"
          f"{str(fund_hist60) + ' (>=60 NAV)':>12}{'':>12}")
    print(f"{'Bonds':12}{bonds:>7}  (static G-Sec reference rows — no exchange tick)")
    print(f"{'IPOs':12}{ipos:>7}")
    print()

    client = httpx.Client(base_url=BASE, timeout=TIMEOUT)
    checks: list[tuple[str, str, bool, str]] = []

    def hit(label_: str, path: str, expect_keys: tuple[str, ...] = ()):
        try:
            r = client.get(path)
            ok = r.status_code == 200
            note = f"{r.status_code}"
            if ok and expect_keys:
                body = r.json()
                missing = [k for k in expect_keys if k not in body]
                if missing:
                    ok = False
                    note = f"missing {','.join(missing)}"
            checks.append((label_, path, ok, note))
            return r.json() if ok else None
        except Exception as exc:  # noqa: BLE001
            checks.append((label_, path, False, str(exc)[:60]))
            return None

    # ---- list payload sparkline coverage (live API) ----
    print("LIST PAYLOAD SPARKLINES (live API)")
    for label_, path, key in (
        ("indices", "/indices?expand=true", "indices"),
        ("stocks", "/stocks?limit=250", "stocks"),
        ("etfs", "/etfs", "etfs"),
        ("reits", "/reits", "reits"),
        ("commodities", "/commodities", "commodities"),
    ):
        body = hit(label_ + " list", path)
        if not body:
            continue
        items = body.get(key) or []
        withspark = sum(1 for i in items if len(i.get("spark") or []) >= 20)
        print(f"  {label_:13} {withspark:>5}/{len(items):<5} cards carry a >=20-point sparkline")
    print()

    # ---- sample instruments: detail + intraday + ladder ----
    print("SAMPLE ENDPOINT CHECKS")
    rows = c.execute(
        "select symbol, meta from instruments where kind='EQUITY'").fetchall()
    equities = []
    for sym, meta in rows:
        m, _ = load(meta, None)
        mc = num(m.get("marketCap"))
        if mc:
            equities.append((mc, sym))
    equities.sort()
    random.seed(7)
    picks = []
    if equities:
        picks.append(("large-cap", equities[-1][1]))
        picks.append(("mid-cap", equities[len(equities) // 2][1]))
        picks.append(("small-cap", equities[len(equities) // 10][1]))
        picks.append(("random-cap", random.choice(equities)[1]))
    for tag, sym in picks:
        body = hit(f"{tag} detail", f"/stocks/{sym}", ("symbol", "history", "returns"))
        if body:
            rets = body.get("returns") or {}
            filled = sum(1 for v in rets.values() if isinstance(v, dict) and v.get("value") is not None)
            print(f"  equities {tag:10} {sym:14} detail OK · ladder {filled}/{len(rets)} filled")
        hit(f"{tag} intraday", f"/stocks/{sym}/intraday")

    idx = c.execute(
        "select symbol, meta from instruments where kind='INDEX'").fetchall()
    idx_ok = 0
    for sym, meta in idx:
        m, _ = load(meta, None)
        slug = SLUG.get(sym) or (m.get("slug") or sym.lower().replace(" ", "-")
                                 .replace("_", "-"))
        body = hit(f"index {sym}", f"/indices/{slug}", ("symbol", "returns"))
        intra = hit(f"index {sym} 1D", f"/indices/{slug}/intraday")
        if body:
            rets = body.get("returns") or {}
            filled = sum(1 for v in rets.values()
                         if isinstance(v, dict) and v.get("value") is not None)
            idx_ok += 1
            print(f"  index {sym:28} detail OK · ladder {filled}/{len(rets)} · "
                  f"1D {'OK' if intra else 'FAIL'}")
    print(f"  indices reachable: {idx_ok}/{len(idx)}")

    etfs = [r[0] for r in c.execute(
        "select symbol from instruments where kind='ETF' limit 3").fetchall()]
    for sym in etfs:
        body = hit(f"etf {sym}", f"/etfs/{sym}", ("symbol", "history"))
        hit(f"etf {sym} 1D", f"/etfs/{sym}/intraday")
        if body:
            print(f"  ETF       {sym:14} detail OK · bars {body.get('history_points')}")

    trusts = [r[0] for r in c.execute(
        "select symbol from instruments where kind in ('REIT','INVIT')").fetchall()]
    for sym in trusts:
        body = hit(f"trust {sym}", f"/reits/{sym}")
        hit(f"trust {sym} 1D", f"/reits/{sym}/intraday")
        if body:
            print(f"  trust     {sym:14} detail OK · last {bool(body.get('last', {}).get('value'))}")

    for sym in ("GOLD", "SILVER"):
        body = hit(f"commodity {sym}", f"/commodities/{sym}", ("symbol", "chart"))
        hit(f"commodity {sym} 1D", f"/commodities/{sym}/intraday")
        if body:
            print(f"  commodity {sym:14} detail OK · chart {len(body.get('chart') or [])} bars")

    fund_rows = c.execute(
        "select code from fund_schemes where navs is not null limit 3").fetchall()
    for (code,) in fund_rows:
        body = hit(f"fund {code}", f"/mutual-funds/{code}", ("navs", "returns"))
        if body:
            print(f"  fund      {code:14} detail OK · navs {body.get('history_points')}")

    bond_id = c.execute("select id from bonds limit 1").fetchone()
    if bond_id:
        body = hit("bond detail", f"/bonds/{bond_id[0]}")
        if body:
            print(f"  bond      #{bond_id[0]:<13} detail OK")

    ipo_id = c.execute("select id from ipos limit 1").fetchone()
    if ipo_id:
        body = hit("ipo detail", f"/ipos/{ipo_id[0]}")
        if body:
            print(f"  ipo       #{ipo_id[0]:<13} detail OK")

    # ---- post bodies: portfolio x-ray, sandbox, AI hub ----
    def post(label_: str, path: str, payload: dict,
             expect_keys: tuple[str, ...] = ()):
        try:
            r = client.post(path, json=payload)
            ok = r.status_code == 200
            note = f"{r.status_code}"
            body = r.json() if ok else {}
            if ok and expect_keys:
                missing = [k for k in expect_keys if k not in body]
                if missing:
                    ok = False
                    note = f"missing {','.join(missing)}"
            checks.append((label_, path, ok, note))
            return body if ok else None
        except Exception as exc:  # noqa: BLE001
            checks.append((label_, path, False, str(exc)[:60]))
            return None

    print()
    print("PORTFOLIO X-RAY · LUMPSUM & MONTHLY SIP")
    xray_cases = (
        ("xray lumpsum",
         {"holdings": [{"kind": "EQUITY", "symbol": "RELIANCE",
                        "quantity": 10, "price": 1200}]}),
        ("xray lumpsum dated",
         {"holdings": [{"kind": "EQUITY", "symbol": "RELIANCE",
                        "value": 100000, "buy_date": "2024-01-15"}]}),
        ("xray sip equity",
         {"holdings": [{"kind": "EQUITY", "symbol": "RELIANCE", "mode": "SIP",
                        "sip_amount": 5000, "sip_start": "2024-01-05",
                        "sip_months": 12}]}),
        ("xray sip fund",
         {"holdings": [{"kind": "MF", "code": "122639", "mode": "SIP",
                        "sip_amount": 5000, "sip_start": "2023-01-05",
                        "sip_months": 24}]}),
        ("xray mixed",
         {"holdings": [
             {"kind": "EQUITY", "symbol": "HDFCBANK", "quantity": 40,
              "price": 720, "buy_date": "2022-05-10"},
             {"kind": "EQUITY", "symbol": "RELIANCE", "mode": "SIP",
              "sip_amount": 5000, "sip_start": "2024-01-05", "sip_months": 12},
             {"kind": "MF", "code": "122639", "value": 250000,
              "buy_date": "2021-01-01"}]}),
    )
    for label_, payload in xray_cases:
        body = post(label_, "/portfolio-xray/analyze", payload,
                    ("summary", "holdings", "allocation", "sector_weights"))
        if not body:
            continue
        s = body["summary"]
        h0 = (body.get("holdings") or [{}])[0]
        real_mark = (h0.get("current_price") is not None)
        print(f"  {label_:19} invested {s.get('invested_rs'):>12} · "
              f"value {s.get('value_rs'):>12} · xirr {s.get('xirr_pct')} · "
              f"mark {'real' if real_mark else 'MISSING'}")

    print()
    print("SANDBOX & AI HUB")
    body = post("sandbox quote RELIANCE", "/sandbox/quote",
                {"symbol": "RELIANCE", "side": "BUY", "quantity": 10},
                ("price", "value", "charges"))
    if body:
        print(f"  sandbox   RELIANCE     fills at {body.get('price')}")
    body = post("sandbox quote GOLD", "/sandbox/quote",
                {"symbol": "GOLD", "side": "BUY", "quantity": 1},
                ("price",))
    if body:
        print(f"  sandbox   GOLD         resolves to {body.get('symbol')} "
              f"at {body.get('price')}")

    body = hit("rangecast pc jewellers",
               "/quant-hub/rangecast/PCJEWELLER?horizon_days=7", ("spot", "band_80"))
    if body:
        print(f"  rangecast PCJEWELLER  spot {body.get('spot', {}).get('value')} "
              f"band {body.get('band_80', {}).get('value')}")
    body = hit("xray 4pm", "/quant-hub/xray", ("chain", "volume_shockers"))
    if body:
        print(f"  xray 4pm              shockers {len(body.get('volume_shockers') or [])}")
    body = post("ask dalal pc jewellers", "/quant-hub/ask-dalal",
                {"question": "what is the pe of pc jewellers"}, ("intent",))
    if body:
        d = body.get("data") or {}
        print(f"  ask-dalal             pc jewellers -> {d.get('symbol')} ({d.get('name')})")

    print()
    failed = [x for x in checks if not x[2]]
    print(f"endpoint checks: {len(checks) - len(failed)}/{len(checks)} passed")
    for label_, path, _ok, note in failed[:20]:
        print(f"  FAIL {label_:22} {path} · {note}")
    print()
    print("audit complete")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
