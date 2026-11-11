"""Pure-Python quantitative engine. No external API does any math for the
platform — ratios, Greeks, valuation, returns and statutory charges are all
computed here (spec: Custom Python Calculation Dominance)."""
from __future__ import annotations

import math
from scipy.stats import norm

# ---------- Black-Scholes option greeks -----------------

def _d1(S, K, T, r, sigma):
    return (math.log(S / K) + (r + sigma * sigma / 2) * T) / (sigma * math.sqrt(T))


def bsm(S: float, K: float, T: float, r: float, sigma: float, q=0.0) -> dict:
    """Return option metrics for one row: c/P premium, greeks, POP."""
    sigma = max(float(sigma), 0.01)
    T = max(float(T), 1 / 365)
    d1, d2 = _d1(S, K, T, r, sigma), 0.0
    d2 = d1 - sigma * math.sqrt(T)
    disc_r, disc_q = math.exp(-r * T), math.exp(-q * T)
    N = norm.cdf
    call = S * disc_q * N(d1) - K * disc_r * N(d2)
    put = K * disc_r * N(-d2) - S * disc_q * N(-d1)
    theta_c = (-S * disc_q * norm.pdf(d1) * sigma / (2 * math.sqrt(T))
               - r * K * disc_r * N(d2) + q * S * disc_q * N(d1)) / 365
    theta_p = (-S * disc_q * norm.pdf(d1) * sigma / (2 * math.sqrt(T))
               + r * K * disc_r * N(-d2) - q * S * disc_q * N(-d1)) / 365
    return {
        "call": round(call, 2), "put": round(put, 2),
        "delta_call": round(disc_q * N(d1), 4),
        "delta_put": round(-disc_q * N(-d1), 4),
        "gamma": round(norm.pdf(d1) * disc_q / (S * sigma * math.sqrt(T)), 6),
        "theta_call": round(theta_c, 4), "theta_put": round(theta_p, 4),
        "vega": round(S * disc_q * norm.pdf(d1) * math.sqrt(T) / 100, 4),
        "pop_call": round(N(d2) * 100, 2), "pop_put": round(N(-d2) * 100, 2),
    }


# ---------- Returns & ratios ----------------------------

def cagr(begin: float, end: float, years: float) -> float | None:
    if not begin or not end or years <= 0:
        return None
    return round(((end / begin) ** (1 / years) - 1) * 100, 2)


def metal_units(amount: float, price: float, load_pct: float = 0.0) -> float:
    """Grams (or units) of a metal bought for a rupee amount.

    ``load_pct`` bundles making charges and GST so the buyer's total outlay is
    exactly ``amount``; a zero load means the full amount buys metal at spot.
    """
    if amount <= 0 or price <= 0:
        return 0.0
    return amount / (price * (1 + max(load_pct, 0.0) / 100))


def simple_returns(closes: list[float]) -> list[float]:
    return [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]


def annual_volatility(closes: list[float]) -> float | None:
    if len(closes) < 30:
        return None
    rets = simple_returns(closes)
    mean = sum(rets) / len(rets)
    var = sum((x - mean) ** 2 for x in rets) / (len(rets) - 1)
    return round(math.sqrt(var) * math.sqrt(252) * 100, 2)


def max_drawdown(closes: list[float]) -> float | None:
    if len(closes) < 2:
        return None
    peak, mdd = closes[0], 0.0
    for c in closes:
        peak = max(peak, c)
        mdd = min(mdd, c / peak - 1)
    return round(mdd * 100, 2)


def rolling_return(closes: list[float], window_days: int = 252) -> float | None:
    if len(closes) <= window_days:
        return None
    return cagr(closes[-(window_days + 1)], closes[-1], 1)


# ---------- DCF (simple, transparent) -------------------

def dcf_value(fcff_millions: float, growth_pct: float, terminal_pct: float,
              wacc_pct: float, net_cash_millions: float, shares_millions: float,
              years: int = 5) -> dict:
    """Classic two-stage DCF on the caller's inputs; returns per-share value."""
    if fcff_millions <= 0 or shares_millions <= 0 or wacc_pct <= 0:
        return {"error": "Insufficient non-positive inputs — DCF requires positive FCFF, shares and WACC."}
    g, t, w = growth_pct / 100, terminal_pct / 100, wacc_pct / 100
    if w <= t:
        return {"error": "WACC must exceed the terminal growth rate."}
    pv, fc = 0.0, fcff_millions
    for _ in range(years):
        fc *= (1 + g)
        pv += fc / (1 + w) ** (_ + 1)
    tv = fc * (1 + t) / (w - t)
    pv_terminal = tv / (1 + w) ** years
    pv_explicit = pv
    pv += pv_terminal
    equity = pv + net_cash_millions
    return {
        "pv_explicit": round(pv_explicit, 1), "pv_terminal": round(pv_terminal, 1),
        "equity_value_mn": round(equity, 1),
        "per_share": round(equity / shares_millions, 2),
        "assumptions": {"growth_pct": growth_pct, "terminal_pct": terminal_pct,
                        "wacc_pct": wacc_pct, "years": years},
        "disclaimer": "Model output on user-supplied assumptions — quantitative only, "
                      "not a buy/sell recommendation.",
    }


# ---------- Statutory charges ("Net-in-Pocket") ---------
# Rates current for FY2025-26 delivery/CNC trades. Encodes STT, exchange
# turnover, SEBI, stamp duty, DP charges and 18% GST.

GST = 0.18

def net_in_pocket(side: str, buy_value: float, sell_value: float | None = None,
                  turnover_product: str = "EQUITY") -> dict:
    """Compute exact statutory deductions for a delivery (CNC) equity trade.
    side: BUY only costs purchase-side charges; BUY+SELL shows breakeven."""
    turnover = buy_value + (sell_value or 0)

    stt_deliv = 0.1 / 100 * sell_value if sell_value else 0.0
    stt_buy = 0.0  # delivery STT applies on sell; buy-side STT is nil for CNC
    exch = 0.00297 / 100 * turnover          # 0.00297% NSE exchange turnover charge
    sebi = 0.0001 / 100 * turnover
    stamp = 0.015 / 100 * buy_value          # buy-side only
    dp = 15.34 if sell_value else 0.0        # per order DP charge (entry+exit pooled)
    taxable = exch + sebi
    gst = GST * taxable

    total = stt_deliv + stt_buy + exch + sebi + stamp + dp + gst

    def pct(x):
        return round(x / max(turnover, 1) * 100, 4)

    detail = [
        {"name": "STT — Securities Transaction Tax", "amount": round(stt_deliv, 2), "pct": pct(stt_deliv)},
        {"name": "Exchange turnover charges (NSE)", "amount": round(exch, 2), "pct": pct(exch)},
        {"name": "SEBI turnover fees", "amount": round(sebi, 2), "pct": pct(sebi)},
        {"name": "Stamp duty (buy side)", "amount": round(stamp, 2), "pct": pct(stamp)},
        {"name": "Depository (DP) charge", "amount": round(dp, 2), "pct": pct(dp)},
        {"name": "GST @18% on brokerage-side levies", "amount": round(gst, 2), "pct": pct(gst)},
    ]
    gross = sell_value - buy_value if sell_value else None
    net = gross - total if gross is not None else None
    breakeven = round(buy_value * (1 + total / turnover), 2) if gross is not None else None
    return {
        "turnover": round(turnover, 2),
        "charges_detail": detail,
        "total_charges": round(total, 2),
        "charges_pct_of_turnover": pct(total),
        "gross_pnl": round(gross, 2) if gross is not None else None,
        "net_in_pocket": round(net, 2) if net is not None else None,
        "breakeven_price_value": breakeven,
        "disclaimer": "Indicative statutory charges for delivery trades as of FY2025-26. "
                      "Brokerage is not included.",
    }


# ---------- Fund calculators ----------------------------

def sip_future_value(monthly: float, years: float, annual_return_pct: float) -> dict:
    r, n = annual_return_pct / 100 / 12, int(years * 12)
    if n <= 0 or monthly <= 0:
        return {"error": "Monthly amount and years must be positive."}
    fv = monthly * (((1 + r) ** n - 1) / r) * (1 + r)
    return {"invested": round(monthly * n, 2), "future_value": round(fv, 2),
            "gain": round(fv - monthly * n, 2)}


def swp_duration(corpus: float, monthly_withdrawal: float, annual_return_pct: float) -> dict:
    r = annual_return_pct / 100 / 12
    w = monthly_withdrawal
    bal, months = corpus, 0
    if w <= 0:
        return {"error": "Withdrawal must be positive."}
    while bal > 0 and months < 12 * 40:
        bal = bal * (1 + r) - w
        months += 1
    return {"months_lasted": months if bal <= 0 else None,
            "years_lasted": round(months / 12, 1),
            "perpetual": bal > 0,
            "balance_left": round(max(bal, 0), 2)}


def ltcg_harvest_window(unrealized_gain: float, used_exemption: float) -> dict:
    """12.5% LTCG tax above the yearly exemption (FY2025-26 rules)."""
    exemption = 125000
    taxable = max(unrealized_gain - (exemption - used_exemption), 0)
    tax = taxable * 0.125
    return {"exemption_left": max(exemption - used_exemption, 0),
            "taxable_gain": round(taxable, 2), "tax": round(tax, 2),
            "post_tax_gain": round(unrealized_gain - tax, 2)}


# ---------- Reverse DCF ---------------------------------

def reverse_dcf_growth(fcff_millions: float, terminal_pct: float, wacc_pct: float,
                       net_cash_millions: float, shares_millions: float,
                       target_price: float, years: int = 5) -> dict:
    """Solve for the explicit-period growth rate the current price implies."""
    if fcff_millions <= 0 or shares_millions <= 0 or wacc_pct <= terminal_pct:
        return {"error": "Reverse DCF needs positive FCFF/shares and WACC above terminal growth."}

    def value(g: float) -> float:
        w, t = wacc_pct / 100, terminal_pct / 100
        pv, fc = 0.0, fcff_millions
        for i in range(1, years + 1):
            fc *= (1 + g)
            pv += fc / (1 + w) ** i
        tv = fc * (1 + t) / (w - t)
        pv += tv / (1 + w) ** years
        return (pv + net_cash_millions) / shares_millions

    lo, hi = -0.95, 2.0
    if value(lo) > target_price:
        return {"implied_growth_pct": None,
                "note": "Even a deeply negative growth assumption values the stock above its price."}
    if value(hi) < target_price:
        return {"implied_growth_pct": None,
                "note": "The price implies growth above 200% a year — outside a credible range."}
    for _ in range(90):
        mid = (lo + hi) / 2
        if value(mid) < target_price:
            lo = mid
        else:
            hi = mid
    implied = (lo + hi) / 2 * 100
    return {
        "implied_growth_pct": round(implied, 2),
        "target_price": round(target_price, 2),
        "assumptions": {"terminal_pct": terminal_pct, "wacc_pct": wacc_pct,
                        "years": years},
        "note": "Growth in the explicit forecast period that makes the DCF equal "
                "the current market price. A model output, not a recommendation.",
    }


# ---------- Mutual-fund metrics -------------------------

def nav_returns(navs: list[dict]) -> dict:
    """1W/1M/3M/6M/1Y/3Y/5Y point-to-point returns from an ascending NAV series."""
    if not navs or len(navs) < 2:
        return {k: None for k in ("1w", "1m", "3m", "6m", "1y", "3y", "5y")}
    vals = [n["nav"] for n in navs]

    def simple(n):
        if len(vals) <= n:
            return None
        first, last = vals[-1 - n], vals[-1]
        return round((last / first - 1) * 100, 2) if first else None

    def annual(n):
        n = min(n, len(vals) - 1)
        return cagr(vals[-1 - n], vals[-1], n / 252)

    return {"1w": simple(5), "1m": simple(21), "3m": simple(63),
            "6m": simple(126), "1y": simple(252), "3y": annual(756),
            "5y": annual(min(len(vals) - 1, 1260))}


def fund_metrics(navs: list[dict], bench: list[dict] | None = None,
                 rf_pct: float = 6.5) -> dict:
    """Sharpe, Sortino, volatility, drawdown and benchmark-relative stats."""
    vals = [n["nav"] for n in navs if n.get("nav")]
    if len(vals) < 60:
        return {"available": False,
                "note": "At least 60 NAV observations are needed for risk ratios."}
    rets = [vals[i] / vals[i - 1] - 1 for i in range(1, len(vals)) if vals[i - 1]]
    rf_daily = rf_pct / 100 / 252
    mean = sum(rets) / len(rets)
    var = sum((x - mean) ** 2 for x in rets) / (len(rets) - 1)
    sd = math.sqrt(var)
    downside = [min(x - rf_daily, 0) for x in rets]
    dsd = math.sqrt(sum(x * x for x in downside) / len(downside)) if downside else 0
    ann_ret = (vals[-1] / vals[0]) ** (252 / len(vals)) - 1
    vol = sd * math.sqrt(252)
    sharpe = (ann_ret - rf_pct / 100) / vol if vol else None
    sortino = (ann_ret - rf_pct / 100) / (dsd * math.sqrt(252)) if dsd else None
    out = {
        "available": True,
        "annual_return_pct": round(ann_ret * 100, 2),
        "volatility_pct": round(vol * 100, 2),
        "sharpe": round(sharpe, 2) if sharpe is not None else None,
        "sortino": round(sortino, 2) if sortino is not None else None,
        "max_drawdown_pct": max_drawdown(vals),
        "observations": len(vals),
        "rf_pct": rf_pct,
        "note": "Sharpe/Sortino use the 6.5% short-term risk-free proxy; ratios are "
                "annualised from daily NAV returns.",
    }
    if bench and len(bench) >= 60:
        bmap = {b["date"]: b["nav"] for b in bench if b.get("nav")}
        pairs = [(n["date"], n["nav"]) for n in navs if n["date"] in bmap]
        if len(pairs) >= 60:
            f = [p[1] for p in pairs]
            b = [bmap[p[0]] for p in pairs]
            fr = [f[i] / f[i - 1] - 1 for i in range(1, len(f))]
            br = [b[i] / b[i - 1] - 1 for i in range(1, len(b))]
            mf, mb = sum(fr) / len(fr), sum(br) / len(br)
            cov = sum((fr[i] - mf) * (br[i] - mb) for i in range(len(fr))) / (len(fr) - 1)
            vb = sum((x - mb) ** 2 for x in br) / (len(br) - 1)
            beta = cov / vb if vb else None
            alpha = ((mf - rf_daily) - beta * (mb - rf_daily)) * 252 * 100 if beta is not None else None
            up = [i for i in range(len(br)) if br[i] > 0]
            down = [i for i in range(len(br)) if br[i] < 0]
            up_cap = (sum(fr[i] for i in up) / sum(br[i] for i in up) * 100
                      if up and sum(br[i] for i in up) else None)
            down_cap = (sum(fr[i] for i in down) / sum(br[i] for i in down) * 100
                        if down and sum(br[i] for i in down) else None)
            out.update({
                "beta": round(beta, 2) if beta is not None else None,
                "alpha_pct": round(alpha, 2) if alpha is not None else None,
                "upside_capture_pct": round(up_cap, 1) if up_cap is not None else None,
                "downside_capture_pct": round(down_cap, 1) if down_cap is not None else None,
                "benchmark_observations": len(pairs),
            })
    return out


def xirr(cashflows: list[tuple[float, float]]) -> float | None:
    """Annualised money-weighted return from (year_fraction, amount) flows.
    Negative amounts are investments; the final positive amount is value."""
    if not cashflows or not any(a > 0 for _, a in cashflows):
        return None
    if not any(a < 0 for _, a in cashflows):
        return None

    def npv(rate: float) -> float:
        return sum(a / (1 + rate) ** t for t, a in cashflows)

    lo, hi = -0.999, 10.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(120):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return round(((lo + hi) / 2) * 100, 2)


def tracking_error(fund_navs: list[dict], bench_navs: list[dict]) -> float | None:
    bmap = {b["date"]: b["nav"] for b in bench_navs if b.get("nav")}
    pairs = [(n["date"], n["nav"]) for n in fund_navs if n["date"] in bmap]
    if len(pairs) < 60:
        return None
    f = [p[1] for p in pairs]
    b = [bmap[p[0]] for p in pairs]
    diffs = [(f[i] / f[i - 1] - 1) - (b[i] / b[i - 1] - 1) for i in range(1, len(f))]
    mean = sum(diffs) / len(diffs)
    var = sum((x - mean) ** 2 for x in diffs) / (len(diffs) - 1)
    return round(math.sqrt(var) * math.sqrt(252) * 100, 2)


# ---------- Charges: MF, ETF and F&O --------------------

def mf_charges(amount: float, years: float, exit_load_pct: float = 0.0,
               stamp_duty_pct: float = 0.005) -> dict:
    """Direct-plan mutual fund purchase: stamp duty on entry, exit load on exit.
    No brokerage or STT is levied on direct-plan MF units."""
    stamp = amount * stamp_duty_pct / 100
    exit_load = amount * exit_load_pct / 100
    return {
        "stamp_duty": round(stamp, 2),
        "exit_load": round(exit_load, 2),
        "brokerage": 0.0,
        "stt": 0.0,
        "total": round(stamp + exit_load, 2),
        "note": ("Direct plans carry no brokerage/STT. Stamp duty is 0.005% on "
                 "purchase; exit load applies only if redeemed inside the "
                 "scheme's stated window."),
    }


def etf_charges(buy_value: float, sell_value: float, brokerage_per_order: float = 20.0) -> dict:
    """Delivery ETF trade on NSE: brokerage, STT on sell, exchange, SEBI,
    stamp duty, DP charge and 18% GST."""
    turnover = buy_value + sell_value
    stt = sell_value * 0.001
    exch = turnover * 0.0000297
    sebi = turnover * 0.000001
    stamp = buy_value * 0.00015
    dp = 15.34
    gst = 0.18 * (brokerage_per_order * 2 + exch + sebi)
    total = stt + exch + sebi + stamp + dp + gst + brokerage_per_order * 2
    return {
        "brokerage": round(brokerage_per_order * 2, 2),
        "stt": round(stt, 2), "exchange": round(exch, 2),
        "sebi": round(sebi, 2), "stamp_duty": round(stamp, 2),
        "dp_charge": dp, "gst": round(gst, 2), "total": round(total, 2),
        "pct_of_turnover": round(total / turnover * 100, 4) if turnover else None,
    }


def fno_charges(buy_premium: float, sell_premium: float,
                product: str = "OPTIONS", brokerage_per_order: float = 20.0) -> dict:
    """Statutory + brokerage charges for one F&O round trip (FY2025-26)."""
    turnover = buy_premium + sell_premium
    if product.upper().startswith("FUT"):
        stt = sell_premium * 0.0002
        exch = turnover * 0.0000173
    else:
        stt = sell_premium * 0.001
        exch = turnover * 0.0003503
    sebi = turnover * 0.000001
    stamp = buy_premium * 0.00003
    brokerage = brokerage_per_order * 2
    gst = 0.18 * (brokerage + exch + sebi)
    total = stt + exch + sebi + stamp + gst + brokerage
    return {
        "brokerage": round(brokerage, 2), "stt": round(stt, 2),
        "exchange": round(exch, 2), "sebi": round(sebi, 2),
        "stamp_duty": round(stamp, 2), "gst": round(gst, 2),
        "total": round(total, 2),
        "pct_of_premium_turnover": round(total / turnover * 100, 3) if turnover else None,
        "note": ("Options: STT 0.1% on sell premium, exchange 0.03503% of premium, "
                 "stamp duty 0.003% on buy, GST 18% on brokerage + exchange + SEBI. "
                 "Brokerage assumed ₹20 per order."),
    }


def option_replay(spot: float, strike: float, sigma_pct: float,
                  days_to_expiry: float, horizon_minutes: float,
                  spot_move_pct: float, option_type: str,
                  entry_price: float, lot_size: int, lots: int,
                  iv_shift_pct: float = 0.0, risk_free: float = 0.065) -> dict:
    """Project an option position forward and decompose the P&L into
    delta/gamma gains, theta decay and vega, net of statutory charges."""
    opt = "call" if option_type.lower().startswith("c") else "put"
    sigma = max(sigma_pct / 100, 0.01)
    T0 = max(days_to_expiry / 365, 1 / (365 * 24 * 60))
    minutes_total = T0 * 365 * 24 * 60
    T1 = max((minutes_total - max(horizon_minutes, 0)) / (365 * 24 * 60), 1 / (365 * 24 * 60))
    S0 = float(spot)
    S1 = S0 * (1 + spot_move_pct / 100)
    sigma1 = max(sigma + iv_shift_pct / 100, 0.01)
    g0 = bsm(S0, strike, T0, risk_free, sigma)
    g1 = bsm(S1, strike, T1, risk_free, sigma1)
    model0 = g0[opt]
    model1 = g1[opt]
    # preserve any observed entry premium versus the model at entry
    projected = max(model1 + (entry_price - model0), 0.05)
    qty = int(lot_size) * int(lots)
    buy_value = entry_price * qty
    sell_value = projected * qty
    gross = sell_value - buy_value
    charges = fno_charges(buy_value, sell_value, "OPTIONS")
    delta = g0["delta_call"] if opt == "call" else g0["delta_put"]
    theta = g0["theta_call"] if opt == "call" else g0["theta_put"]
    elapsed_days = max(horizon_minutes, 0) / (24 * 60)
    spot_change = S1 - S0
    delta_gain = delta * spot_change * qty
    gamma_gain = 0.5 * g0["gamma"] * spot_change ** 2 * qty
    theta_loss = theta * elapsed_days * qty
    vega_gain = g0["vega"] * iv_shift_pct * qty
    return {
        "entry": {"spot": round(S0, 2), "premium": round(entry_price, 2),
                  "days_to_expiry": round(T0 * 365, 2),
                  "model_premium": round(model0, 2)},
        "exit": {"spot": round(S1, 2), "premium": round(projected, 2),
                 "minutes_forward": round(horizon_minutes, 1),
                 "days_to_expiry": round(T1 * 365, 2),
                 "iv_pct": round(sigma1 * 100, 2)},
        "greeks_at_entry": {"delta": delta, "gamma": g0["gamma"],
                            "theta_per_day": theta, "vega": g0["vega"],
                            "pop_pct": g0["pop_call"] if opt == "call" else g0["pop_put"]},
        "qty": qty, "investment": round(buy_value, 2),
        "gross_pnl": round(gross, 2),
        "charges": charges,
        "net_pnl": round(gross - charges["total"], 2),
        "net_pnl_pct": round((gross - charges["total"]) / buy_value * 100, 2) if buy_value else None,
        "decomposition": {
            "delta_gain": round(delta_gain, 2),
            "gamma_gain": round(gamma_gain, 2),
            "theta_loss": round(theta_loss, 2),
            "vega_gain": round(vega_gain, 2),
            "residual": round(gross - (delta_gain + gamma_gain + theta_loss + vega_gain), 2),
        },
        "note": ("Projection uses the platform's Black-Scholes engine with your "
                 "entry premium anchored to the model. Real fills, IV moves and "
                 "liquidity can differ materially. Quantitative only — not a "
                 "buy/sell recommendation."),
    }
