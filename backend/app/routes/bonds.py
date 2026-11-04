"""Bonds & debt hub — 20 real Government, T-Bill, SDL, floating and corporate
securities with credit ratings, an India par-yield curve, accrued-interest
pricing and fixed-vs-floating comparison maths."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.models import Bond
from app.services import calc
from app.services.contextual import not_disclosed, reported, source_issue

router = APIRouter(prefix="/bonds", tags=["bonds"])


def _years(maturity: str | None) -> float | None:
    if not maturity:
        return None
    try:
        y, m, d = map(int, maturity.split("-"))
        days = (dt.date(y, m, d) - dt.date.today()).days
        return round(days / 365.25, 2) if days > 0 else 0.0
    except Exception:  # noqa: BLE001
        return None


def _env(v, what="metric"):
    return reported(v) if v is not None else source_issue(what)


def _frequency(b: Bond) -> int:
    m = b.meta or {}
    try:
        return max(int(m.get("frequency") or 2), 1)
    except (TypeError, ValueError):
        return 2


def _category(b: Bond) -> str:
    kind = (b.kind or "").upper()
    if kind == "G-SEC":
        return "SOVEREIGN G-SECS"
    if kind == "T-BILL":
        return "RBI T-BILLS"
    if kind == "SDL":
        return "STATE SDLS"
    if kind == "FLOATING":
        return "TAX-FREE & FLOATING"
    return "AAA/AA+ CORPORATE NCDS"


def _accrued(b: Bond, price: float) -> float:
    """Indicative accrued interest for a mid-cycle purchase (45 days)."""
    coupon = b.coupon or 0.0
    freq = _frequency(b)
    period_days = 365.25 / freq
    face = b.face_value or 100.0
    return round(coupon / 100 * face / freq * min(45 / period_days, 1), 4)


def _post_tax_ytm(b: Bond, price: float, ytm: float | None,
                  years: float | None) -> float | None:
    """Coupon taxed at 30% slab, capital gain at 12.5% LTCG after a year."""
    if ytm is None or years is None or price <= 0:
        return None
    coupon = (b.coupon or 0.0) / 100 * (b.face_value or 100.0)
    holding = max(min(years, 10.0), 1.0)
    coupon_income = coupon * holding
    post_tax_coupon = coupon_income * 0.70
    gain = max((b.face_value or 100.0) - price, 0.0)
    post_tax_gain = gain * 0.875
    total = post_tax_coupon + post_tax_gain
    return round(total / price / holding * 100, 3)


def _cashflows(b: Bond) -> list[dict]:
    """Coupon/principal schedule counted back from maturity."""
    if not b.maturity:
        return []
    try:
        y, m, d = map(int, b.maturity.split("-"))
        maturity = dt.date(y, m, d)
    except Exception:  # noqa: BLE001
        return []
    freq = _frequency(b)
    months = int(round(12 / freq))
    face = b.face_value or 100.0
    coupon = (b.coupon or 0.0) / 100 * face / freq
    today = dt.date.today()
    dates: list[dt.date] = []
    cur = maturity
    for _ in range(80):
        if cur <= today:
            break
        dates.append(cur)
        month = cur.month - months
        year = cur.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        day = min(cur.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                            31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
        cur = dt.date(year, month, day)
    dates.sort()
    out = []
    for i, when in enumerate(dates):
        principal = face if i == len(dates) - 1 else 0.0
        out.append({"date": when.isoformat(),
                    "coupon": round(coupon, 2),
                    "principal": round(principal, 2),
                    "total": round(coupon + principal, 2)})
    return out


def _row(b: Bond) -> dict:
    m = b.meta or {}
    years = _years(b.maturity)
    coupon = b.coupon
    price = m.get("price") or b.face_value or 100
    ytm = m.get("ytm")
    if ytm is None and coupon and years and years > 0:
        # par approximation only when no price is supplied
        ytm = coupon
    accrued = _accrued(b, price)
    return {
        "id": b.id, "name": b.name, "kind": b.kind,
        "category": _category(b),
        "issuer": m.get("issuer") or b.name,
        "coupon": _env(coupon, "coupon"),
        "coupon_type": m.get("coupon_type") or "FIXED",
        "frequency": _frequency(b),
        "face_value": _env(b.face_value, "face value"),
        "price": _env(price, "indicative clean price"),
        "clean_price": _env(price, "indicative clean price"),
        "accrued_interest": _env(accrued, "accrued interest"),
        "dirty_price": _env(round(price + accrued, 4), "indicative dirty price"),
        "ytm": _env(ytm, "indicative yield to maturity"),
        "post_tax_ytm_pct": _env(_post_tax_ytm(b, price, ytm, years),
                                 "post-tax yield to maturity"),
        "maturity": _env(b.maturity, "maturity"),
        "years_to_maturity": _env(years, "years to maturity"),
        "coupon_per_year_per_unit": _env(
            round((coupon or 0.0) / 100 * (b.face_value or 100), 2),
            "annual coupon per unit"),
        "rating": m.get("rating") or "Not rated in feed",
        "rating_agency": m.get("rating_agency"),
        "taxable": m.get("taxable", True),
        "liquidity": m.get("liquidity"),
        "seniority": m.get("seniority"),
        "note": b.note,
        "href": f"/bonds/{b.id}",
    }


@router.get("")
def list_bonds(kind: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Bond)
    if kind and kind.lower() != "all":
        q = q.filter(Bond.kind == kind.upper())
    rows = q.order_by(Bond.maturity.asc()).all()
    items = [_row(b) for b in rows]
    kinds = sorted({b.kind for b in db.query(Bond).all()})
    return {
        "count": len(items), "bonds": items,
        "kinds": ["ALL"] + kinds,
        "explain": ("Government securities are sovereign paper: a 7.18% coupon on "
                    "₹100 face value pays ₹7.18 a year until maturity. Corporate "
                    "bonds add credit and liquidity risk, which is why their coupons "
                    "sit higher."),
        "curve_note": ("The India curve shown is a par-yield curve built from the "
                       "seeded sovereign/T-Bill/SDL securities. It is an indicative "
                       "teaching curve, not a live NDS-OM quote."),
    }


@router.get("/curve/yields")
def yield_curve(db: Session = Depends(get_db)):
    """India par-yield curve. Sovereigns and T-Bills anchor the tenors; SDLs add
    a state spread at the long end. Interpolation is linear between anchors."""
    anchors: dict[float, float] = {}
    for b in db.query(Bond).all():
        m = b.meta or {}
        years = _years(b.maturity)
        y = m.get("ytm")
        if years and y and b.kind in ("T-BILL", "G-SEC", "FLOATING"):
            anchors[years] = float(y)
    tenors = [0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 30.0]
    pts = sorted(anchors.items())

    def interpolate(t: float) -> float | None:
        if not pts:
            return None
        if t <= pts[0][0]:
            return pts[0][1]
        if t >= pts[-1][0]:
            return pts[-1][1]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if x0 <= t <= x1:
                return round(y0 + (y1 - y0) * (t - x0) / (x1 - x0), 3)
        return None

    curve = [{"tenor_years": t,
              "label": ("3M" if t == 0.25 else "6M" if t == 0.5 else
                        "1Y" if t == 1 else "2Y" if t == 2 else "5Y" if t == 5 else
                        "10Y" if t == 10 else "15Y" if t == 15 else "30Y"),
              "yield_pct": interpolate(t)} for t in tenors]
    return {"count": len(curve), "curve": curve,
            "anchors": [{"tenor_years": round(k, 3), "yield_pct": v} for k, v in pts],
            "note": ("Par-yield curve interpolated linearly between seeded sovereign "
                     "anchors. T-Bills set the short end, G-Secs the belly and long "
                     "end, SDLs add a small state spread. Indicative, not live.")}


@router.get("/{bond_id}")
def bond_detail(bond_id: int, db: Session = Depends(get_db)):
    b = db.get(Bond, bond_id)
    if not b:
        raise HTTPException(404, "Bond not found in the seeded debt universe.")
    row = _row(b)
    return {
        **row,
        "cashflows": _cashflows(b),
        "cashflow_note": ("Clean price excludes accrued interest; dirty price is what "
                          "the buyer actually pays. Post-tax YTM applies the investor's "
                          "slab to coupon income and 12.5% LTCG to capital gains."),
        "callable": (b.meta or {}).get("callable", False),
        "source_notes": [
            "Coupon and maturity are statutory issue facts.",
            "Price and YTM are indicative par-curve teaching values, not dealer quotes.",
            "Corporate ratings are the agency ratings disclosed at issuance.",
        ],
    }


class CleanDirtyBody(BaseModel):
    face: float = 100.0
    coupon_pct: float = 7.18
    ytm_pct: float = 7.18
    years: float = 7.0
    frequency: int = 2
    days_since_coupon: int = 45
    tax_slab_pct: float = 30.0
    holding_years: float = 5.0
    call_years: float | None = None
    call_price: float = 100.0


def _price_from_yield(face: float, coupon_pct: float, ytm_pct: float,
                      years: float, freq: int = 2) -> float:
    n = max(int(round(years * freq)), 1)
    c = coupon_pct / 100 * face / freq
    r = ytm_pct / 100 / freq
    pv = sum(c / (1 + r) ** k for k in range(1, n + 1))
    pv += face / (1 + r) ** n
    return round(pv, 4)


@router.post("/calc/clean-dirty")
def clean_dirty(body: CleanDirtyBody):
    freq = max(body.frequency, 1)
    period_days = 365.25 / freq
    accrued = body.coupon_pct / 100 * body.face / freq * min(
        max(body.days_since_coupon, 0) / period_days, 1)
    clean = _price_from_yield(body.face, body.coupon_pct, body.ytm_pct,
                              body.years, freq)
    dirty = round(clean + accrued, 4)
    coupon_income = body.coupon_pct / 100 * body.face * body.holding_years
    tax_on_coupon = coupon_income * body.tax_slab_pct / 100
    gain = max(clean - body.face, 0) if body.holding_years >= 1 else 0
    ltcg = gain * 0.125
    post_tax_income = coupon_income - tax_on_coupon
    post_tax_total = post_tax_income + gain - ltcg
    post_tax_ytm = (post_tax_total / body.face / max(body.holding_years, 1)) * 100
    ytc = None
    if body.call_years:
        ytc = _price_from_yield(body.face, body.coupon_pct, body.ytm_pct,
                                body.call_years, freq)
    return {
        "accrued_interest": round(accrued, 4),
        "clean_price": clean, "dirty_price": dirty,
        "days_since_coupon": body.days_since_coupon,
        "coupon_income": round(coupon_income, 2),
        "tax_on_coupon": round(tax_on_coupon, 2),
        "capital_gain": round(gain, 2),
        "ltcg_tax_12_5": round(ltcg, 2),
        "post_tax_income": round(post_tax_income, 2),
        "post_tax_total_return": round(post_tax_total, 2),
        "post_tax_ytm_pct": round(post_tax_ytm, 3),
        "call_price": round(ytc, 4) if ytc is not None else None,
        "note": ("Clean price is the quoted price; dirty price adds accrued interest. "
                 "Post-tax YTM applies slab tax to coupons and 12.5% LTCG to the "
                 "capital gain after a 12-month holding. A teaching model."),
    }


class FixedFloatBody(BaseModel):
    face: float = 100.0
    fixed_coupon_pct: float = 8.0
    floating_base_pct: float = 6.5
    spread_pct: float = 1.2
    years: float = 5.0
    rate_path_pct: float = 0.0


@router.post("/calc/fixed-floating")
def fixed_floating(body: FixedFloatBody):
    fixed_total = body.face * body.fixed_coupon_pct / 100 * body.years
    # Floating coupon = base + spread, re-fixed annually along the rate path.
    floating_total = 0.0
    rate = body.floating_base_pct
    for _ in range(max(int(round(body.years)), 1)):
        floating_total += body.face * (rate + body.spread_pct) / 100
        rate += body.rate_path_pct
    diff = floating_total - fixed_total
    return {
        "fixed_coupon_pct": body.fixed_coupon_pct,
        "floating_first_coupon_pct": round(body.floating_base_pct + body.spread_pct, 2),
        "fixed_total_interest": round(fixed_total, 2),
        "floating_total_interest": round(floating_total, 2),
        "difference": round(diff, 2),
        "winner": "FLOATING" if diff > 0 else "FIXED" if diff < 0 else "EQUAL",
        "note": ("Floating coupons reset to base + spread each year and follow the "
                 "rate path. If rates fall, fixed wins; if rates rise, floating wins. "
                 "This ignores reinvestment and liquidity differences."),
    }


@router.get("/calc/ytm")
def ytm(price: float, coupon_pct: float, face: float = 100.0, years: float = 1.0):
    if price <= 0 or years <= 0 or face <= 0:
        return {"error": "price, years and face must be positive."}
    coupon = coupon_pct / 100 * face
    guess = 0.05
    for _ in range(200):
        def pv(r):
            return sum(coupon / (1 + r) ** t for t in range(1, int(years) + 1)) + \
                face / (1 + r) ** years
        val = pv(guess) - price
        d = (pv(guess + 1e-6) - pv(guess - 1e-6)) / 2e-6
        if abs(val) < 1e-7:
            break
        guess -= val / d if d else 0.01
    return {"price": price, "coupon": coupon, "years": years,
            "yield_to_maturity_pct": round(guess * 100, 3)}
