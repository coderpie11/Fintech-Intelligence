"""Calculation endpoints — the platform's own math engine over the wire."""
from fastapi import APIRouter
from pydantic import BaseModel

from app.services import calc

router = APIRouter(prefix="/calc", tags=["calculators"])


class DcfIn(BaseModel):
    fcff_millions: float
    growth_pct: float
    terminal_pct: float
    wacc_pct: float
    net_cash_millions: float = 0
    shares_millions: float
    years: int = 5


@router.post("/dcf")
def dcf(payload: DcfIn):
    return calc.dcf_value(payload.fcff_millions, payload.growth_pct,
                          payload.terminal_pct, payload.wacc_pct,
                          payload.net_cash_millions, payload.shares_millions,
                          payload.years)


@router.get("/net-in-pocket")
def net_in_pocket(buy_value: float, sell_value: float | None = None):
    return calc.net_in_pocket("BUY", buy_value, sell_value)


@router.get("/sip")
def sip(monthly: float, years: float, annual_return_pct: float):
    return calc.sip_future_value(monthly, years, annual_return_pct)


class SwpIn(BaseModel):
    corpus: float
    monthly_withdrawal: float
    annual_return_pct: float


@router.post("/swp")
def swp(payload: SwpIn):
    return calc.swp_duration(payload.corpus, payload.monthly_withdrawal,
                             payload.annual_return_pct)


class LtcgIn(BaseModel):
    unrealized_gain: float
    used_exemption: float = 0.0


@router.post("/ltcg")
def ltcg(payload: LtcgIn):
    return calc.ltcg_harvest_window(payload.unrealized_gain, payload.used_exemption)


class FeeDragIn(BaseModel):
    amount: float
    years: float
    annual_return_pct: float
    low_cost_pct: float = 0.20
    high_cost_pct: float = 1.00


@router.post("/fee-drag")
def fee_drag(payload: FeeDragIn):
    """Future value of the same gross return under two expense ratios."""
    years = max(payload.years, 0)
    low = payload.amount * (1 + (payload.annual_return_pct - payload.low_cost_pct) / 100) ** years
    high = payload.amount * (1 + (payload.annual_return_pct - payload.high_cost_pct) / 100) ** years
    return {
        "low_cost_value": round(low, 2),
        "high_cost_value": round(high, 2),
        "difference": round(low - high, 2),
        "low_cost_pct": payload.low_cost_pct,
        "high_cost_pct": payload.high_cost_pct,
        "note": ("Same gross return, different expense ratio. The gap compounds every "
                 "year; a model that ignores tracking difference and taxes."),
    }


@router.get("/bsm")
def bsm(S: float, K: float, T: float, r: float = 0.065, sigma: float = 0.2, q: float = 0.0):
    return calc.bsm(S, K, T, r, sigma, q)
