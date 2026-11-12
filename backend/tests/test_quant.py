"""Correctness tests for the platform's pure-Python quantitative engine."""
from __future__ import annotations

import math

import pytest

from app.services import calc
from app.services.fundamentals import piotroski


# ------------------------------------------------------------------ BSM
def test_bsm_call_put_parity_and_greek_signs():
    S, K, T, r, sigma = 100.0, 100.0, 1.0, 0.05, 0.20
    g = calc.bsm(S, K, T, r, sigma)

    parity = g["call"] - g["put"] - (S - K * math.exp(-r * T))
    assert abs(parity) < 0.05
    assert 9.0 < g["call"] < 12.0
    assert 4.0 < g["put"] < 7.0
    assert 0.0 < g["delta_call"] < 1.0
    assert -1.0 < g["delta_put"] < 0.0
    assert g["gamma"] > 0.0
    assert g["vega"] > 0.0
    assert g["theta_call"] < 0.0
    assert 0.0 <= g["pop_call"] <= 100.0


def test_bsm_deep_itm_call_delta_near_one():
    g = calc.bsm(200.0, 50.0, 0.25, 0.05, 0.20)
    assert g["delta_call"] > 0.97
    assert g["put"] < 0.01


# ------------------------------------------------------------------ DCF
def test_dcf_flat_case_is_exact():
    # Zero growth, zero terminal growth: PV is a 5-year annuity plus a
    # terminal value of FCFF / WACC, all discounted. With FCFF 100, WACC 10%,
    # the equity value is exactly 1,000 and per-share is 10.
    out = calc.dcf_value(100, 0, 0, 10, 0, 100, years=5)
    assert out["per_share"] == 10.0
    assert out["equity_value_mn"] == 1000.0
    assert abs(out["pv_explicit"] - 379.1) < 0.2
    assert abs(out["pv_terminal"] - 620.9) < 0.2


def test_dcf_rejects_inconsistent_inputs():
    assert "error" in calc.dcf_value(0, 5, 2, 10, 0, 100)
    assert "error" in calc.dcf_value(100, 5, 12, 10, 0, 100)  # WACC < terminal


# ------------------------------------------------------- net in pocket
def test_net_in_pocket_components_reconcile():
    out = calc.net_in_pocket("BUY+SELL", 100_000, 110_000)
    detail_sum = sum(d["amount"] for d in out["charges_detail"])
    assert abs(out["total_charges"] - detail_sum) < 0.05
    assert out["gross_pnl"] == 10_000.0
    assert abs(out["net_in_pocket"] - (10_000 - out["total_charges"])) < 0.05
    assert out["total_charges"] > 0

    exch = next(d for d in out["charges_detail"] if "Exchange turnover" in d["name"])
    expected = round(0.00297 / 100 * 210_000, 2)
    assert abs(exch["amount"] - expected) < 0.02


def test_net_in_pocket_buy_has_no_sell_stt():
    out = calc.net_in_pocket("BUY", 100_000)
    stt = next(d for d in out["charges_detail"] if d["name"].startswith("STT"))
    assert stt["amount"] == 0.0
    assert out["gross_pnl"] is None
    assert out["net_in_pocket"] is None


# ------------------------------------------------------------------ XIRR
def test_xirr_one_year_and_two_year_paths():
    one = calc.xirr([(0.0, -100_000), (1.0, 110_000)])
    two = calc.xirr([(0.0, -100_000), (2.0, 121_000)])
    assert one == pytest.approx(10.0, abs=0.02)
    assert two == pytest.approx(10.0, abs=0.02)


def test_xirr_needs_both_signs_and_handles_sip_flows():
    assert calc.xirr([(0.0, 100), (1.0, 110)]) is None
    sip = calc.xirr([(0.0, -10_000), (0.25, -10_000),
                     (0.5, -10_000), (1.0, 33_000)])
    assert sip is not None and sip > 0


# ------------------------------------------------------------ Piotroski
def _strong_company():
    inc = {"net_income": [120, 100], "revenue": [1_200, 1_000],
           "gross_profit": [480, 350], "cost_of_revenue": [720, 650]}
    bal = {"total_assets": [1_000, 950], "total_debt": [200, 300],
           "current_assets": [500, 400], "current_liabilities": [250, 250],
           "shares": [100, 100]}
    cf = {"cfo": [150, 140]}
    return inc, bal, cf


def _weak_company():
    inc = {"net_income": [-50, 10], "revenue": [500, 600],
           "gross_profit": [50, 90], "cost_of_revenue": [450, 510]}
    bal = {"total_assets": [1_000, 900], "total_debt": [800, 600],
           "current_assets": [100, 300], "current_liabilities": [400, 300],
           "shares": [200, 100]}
    cf = {"cfo": [-20, 5]}
    return inc, bal, cf


def test_piotroski_strong_company_scores_nine():
    out = piotroski(*_strong_company(), financial=False)
    assert out["score"] == out["max"] == 9
    assert out["label"] == "Strong"
    assert all(s["pass"] for s in out["signals"])


def test_piotroski_weak_company_is_flagged():
    out = piotroski(*_weak_company(), financial=False)
    assert out["score"] <= 1
    assert out["label"] == "Weak"
    assert out["max"] == 9


def test_piotroski_drops_unknown_signals_from_denominator():
    inc = {"net_income": [100], "revenue": [1_000]}
    bal = {"total_assets": [1_000], "shares": [100]}
    out = piotroski(inc, bal, {"cfo": [120]}, financial=True)
    assert out["max"] <= 9
    assert out["score"] <= out["max"]


# --------------------------------------------------- returns & drawdown
def test_cagr_and_max_drawdown_math():
    assert calc.cagr(100, 121, 2) == 10.0
    assert calc.cagr(0, 121, 2) is None
    assert calc.max_drawdown([100, 120, 60, 80]) == -50.0
    assert calc.max_drawdown([100]) is None


def test_sip_and_ltcg_helpers_are_sane():
    sip = calc.sip_future_value(10_000, 10, 12)
    assert sip["future_value"] is not None
    assert sip["invested"] == 1_200_000

    harvest = calc.ltcg_harvest_window(200_000, 50_000)
    assert harvest["post_tax_gain"] <= 200_000
    assert harvest["exemption_left"] == 75_000


# ------------------------------------------------- 4 PM Market X-Ray contract
def test_xray_build_matches_frontend_contract():
    """The X-Ray must build from SQLite and satisfy what XRay.tsx reads.

    Regression: a StreetPulse refactor replaced the per-symbol delivery lookup
    with a batched ``_delivery_map``; the X-Ray kept calling the old private
    name and every production request 500'd ("could not load: Failed to
    fetch"). This test fails if that coupling breaks again.
    """
    from app.core.db import SessionLocal
    from app.services.ai_engine import xray

    db = SessionLocal()
    try:
        d = xray.build(db)
    finally:
        db.close()

    for key in ("asof", "session_label", "market_status", "chain", "sectors",
                "volume_shockers", "top_gainers", "top_losers",
                "action_items", "synthesis", "footer_note"):
        assert key in d, f"missing top-level key {key}"

    chain = d["chain"]
    for step in ("step_1_official_flows", "step_2_sector_tilt",
                 "step_3_stock_confirmation", "step_4_context"):
        assert step in chain, f"missing chain step {step}"

    # Step 3 rows are the only ones rendering a Delivery Z column.
    for row in chain["step_3_stock_confirmation"]["rows"]:
        assert row.get("delivery_z"), f"{row['symbol']} has no delivery_z"
        assert set(("current", "mean", "z", "sessions")) <= set(row["delivery_z"])
        assert isinstance(row["delivery_z"]["z"], float)

    # Every sector tilt must be a real participation measure with breadth.
    for s in d["sectors"]:
        assert s["count"] >= 1
        assert "participation_tilt" in s
    assert len(d["synthesis"]) >= 1
