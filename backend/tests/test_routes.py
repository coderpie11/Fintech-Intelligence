"""API contract smoke tests across every core module."""
from __future__ import annotations

import pytest


def _ok(resp):
    assert resp.status_code == 200, f"{resp.request.url} -> {resp.status_code}: {resp.text[:300]}"
    return resp.json()


# --------------------------------------------------------------- meta
def test_health_and_docs(client):
    body = _ok(client.get("/api/v1/health"))
    assert body["status"] == "ok"
    assert "version" in body
    assert client.get("/openapi.json").status_code == 200


def test_source_registry_has_no_null_contract(client):
    body = _ok(client.get("/api/v1/sources"))
    assert isinstance(body, dict) and body


# ------------------------------------------------------------ academy
def test_academy_index_lists_all_tracks(client):
    body = _ok(client.get("/api/v1/academy"))
    ids = {t["id"] for t in body["tracks"]}
    required = {"technical-analysis", "indices-vix", "ipos",
                "reits-invits", "forensic-guides"}
    assert required <= ids
    assert body["total_lessons"] >= 80
    forensic = next(t for t in body["tracks"] if t["id"] == "forensic-guides")
    assert forensic["masterclass"] is True
    assert forensic["lesson_count"] == 6


@pytest.mark.parametrize("track", [
    "universal-fundamentals", "equities", "technical-analysis",
    "derivatives", "indices-vix", "ipos", "mutual-funds", "etfs",
    "bonds", "commodities-reits", "reits-invits", "forensic-guides",
])
def test_academy_track_schema(client, track):
    body = _ok(client.get(f"/api/v1/academy/{track}"))
    assert body["id"] == track
    assert body["lessons"], "track must contain lessons"
    for lesson in body["lessons"]:
        assert {"id", "title", "simple", "formula", "example",
                "thumb_rule", "link"} <= set(lesson)


def test_academy_search_and_missing_track(client):
    body = _ok(client.get("/api/v1/academy/search", params={"q": "reit"}))
    assert body["count"] >= 1
    assert client.get("/api/v1/academy/not-a-track").status_code == 404


# ------------------------------------------------------------ markets
@pytest.mark.parametrize("path", [
    "/api/v1/indices",
    "/api/v1/stocks?limit=5",
    "/api/v1/fno/underlyings?limit=10",
    "/api/v1/ipos?limit=5",
    "/api/v1/mutual-funds?limit=5",
    "/api/v1/etfs",
    "/api/v1/etfs/liquidity-scan?limit=5",
    "/api/v1/bonds",
    "/api/v1/commodities",
    "/api/v1/reits",
    "/api/v1/events?limit=5",
    "/api/v1/pulse",
])
def test_core_list_endpoints(client, path):
    body = _ok(client.get(path))
    assert isinstance(body, dict) and body


def test_indices_detail_and_vix(client):
    body = _ok(client.get("/api/v1/indices/nifty-50"))
    assert "constituents" in body or "index" in body
    vix = _ok(client.get("/api/v1/indices/vix-stability"))
    assert "regime" in vix or "vix" in vix


def test_etf_scanner_flags_have_contract(client):
    body = _ok(client.get("/api/v1/etfs/liquidity-scan", params={"limit": 10}))
    assert body["count"] >= 1
    row = body["etfs"][0]
    assert {"symbol", "inav", "deviation_pct", "deviation_status",
            "impact_cost_pct", "liquidity_score"} <= set(row)
    assert body["thresholds"]["premium_discount_band_pct"] == 0.25


def test_fno_underlyings_and_payoff(client):
    body = _ok(client.get("/api/v1/fno/underlyings", params={"limit": 5}))
    assert body["stock_count"] >= 1 and body["indices"]
    legs = [
        {"side": "BUY", "option_type": "CE", "strike": 25000, "premium": 120, "lots": 1, "lot_size": 75},
        {"side": "SELL", "option_type": "CE", "strike": 25300, "premium": 45, "lots": 1, "lot_size": 75},
    ]
    payoff = _ok(client.post("/api/v1/fno/strategy/payoff", json={"legs": legs}))
    assert payoff["max_profit"] is not None
    assert payoff["max_loss"] is not None


# ---------------------------------------------------------- portfolio
def test_portfolio_xray_lookup_and_analyze(client):
    lookup = _ok(client.get("/api/v1/portfolio-xray/lookup", params={"q": "REL"}))
    assert lookup["equities"]

    body = _ok(client.post("/api/v1/portfolio-xray/analyze", json={
        "holdings": [
            {"kind": "EQUITY", "symbol": "RELIANCE", "quantity": 10, "price": 1200},
            {"kind": "MF", "code": "122639", "value": 200000},
            {"kind": "MF", "code": "131670", "value": 150000},
        ],
        "gross_return_pct": 12,
    }))
    assert body["summary"]["holdings"] == 3
    assert body["allocation"]
    assert body["sector_weights"]
    assert body["overlap"]["matrix"] and len(body["overlap"]["matrix"]) == 2
    assert [h["years"] for h in body["fee_drag"]["horizons"]] == [1, 3, 5, 10]


def test_sandbox_and_watchlist_contract(client):
    summary = _ok(client.get("/api/v1/sandbox/summary"))
    assert "cash_available" in summary
    watch = _ok(client.get("/api/v1/watchlist"))
    assert "items" in watch and isinstance(watch["items"], list)


# ---------------------------------------------------------- quant/calc
def test_quant_hub_health(client):
    body = _ok(client.get("/api/v1/quant-hub/health"))
    assert body["platform"] == "Fintech Intelligence"
    assert len(body["workspaces"]) >= 4


def test_calc_endpoints(client):
    bsm = _ok(client.get("/api/v1/calc/bsm",
                         params={"S": 100, "K": 100, "T": 1, "r": 0.05, "sigma": 0.2}))
    assert bsm["call"] > 0 and bsm["put"] > 0

    nip = _ok(client.get("/api/v1/calc/net-in-pocket",
                         params={"side": "BUY+SELL", "buy_value": 100000,
                                 "sell_value": 110000}))
    assert nip["net_in_pocket"] == pytest.approx(10000 - nip["total_charges"], abs=0.05)

    sip = _ok(client.get("/api/v1/calc/sip",
                         params={"monthly": 10000, "years": 10,
                                 "annual_return_pct": 12}))
    assert sip["future_value"] > sip["invested"]


# ---------------------------------------------------------- guards
def test_unknown_symbols_and_bad_payloads_are_rejected(client):
    assert client.get("/api/v1/stocks/NOTAREALSYMBOL123").status_code == 404
    assert client.post("/api/v1/portfolio-xray/analyze",
                       json={"holdings": "not-a-list"}).status_code == 422
