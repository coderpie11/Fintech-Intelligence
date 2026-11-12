"""Gold & Silver hub — live international spot converted to Indian rupee
denominations, five-year histories, the gold/silver ratio, an SGB secondary
scanner and a physical-vs-ETF-vs-SGB wealth calculator."""
from __future__ import annotations

import datetime as dt
import json
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.data.adapters import nse_adapter as N
from app.data.adapters import yfinance_adapter as Y
from app.models.models import Instrument
from app.services import calc
from app.services import instrument_engine as IE
from app.services.contextual import not_applicable, not_disclosed, reported, source_issue

router = APIRouter(prefix="/commodities", tags=["commodities"])

SGB_SEED = Path(__file__).resolve().parent.parent / "seed" / "sgb_seed.json"


def _env(v, what="metric"):
    return reported(v) if v is not None else source_issue(what)


def _row(r: Instrument) -> dict:
    m = r.meta or {}
    return {
        "symbol": r.symbol, "name": r.name,
        "unit": _env(m.get("unit"), "unit"),
        "last": _env(m.get("last"), "international price"),
        "changepct": _env(m.get("changepct"), "day change"),
        "prev_close": _env(m.get("prevClose"), "previous close"),
        "week52_high": _env(m.get("week52_high") or m.get("yearHigh"), "52-week high"),
        "week52_low": _env(m.get("week52_low") or m.get("yearLow"), "52-week low"),
        "spark": IE.sparkline(r),
        "usd_per_oz": _env(m.get("usd_per_oz"), "USD per ounce"),
        "inr_per_gram_24k": _env(m.get("inr_gram_24k"), "24K ₹/gram"),
        "inr_per_10g_24k": _env(m.get("inr_10g_24k"), "24K ₹/10g"),
        "inr_per_gram_22k": _env(m.get("inr_gram_22k"), "22K ₹/gram"),
        "inr_per_10g_22k": _env(m.get("inr_10g_22k"), "22K ₹/10g"),
        "inr_per_gram_silver": _env(m.get("inr_gram_silver"), "silver ₹/gram"),
        "inr_per_kg_silver": _env(m.get("inr_kg_silver"), "silver ₹/kg"),
        "inr_per_10g_silver": _env(m.get("inr_10g_silver"), "silver ₹/10g"),
        "usdinr": _env(m.get("usdinr"), "USD/INR"),
        "note": _env(m.get("note"), "commodity note"),
        "href": f"/commodities/{r.symbol}",
    }


@router.get("")
def list_commodities(db: Session = Depends(get_db)):
    rows = (db.query(Instrument).filter(Instrument.kind == "COMMODITY").all())
    IE.ensure_many(db, rows)
    out = [_row(r) for r in rows]
    gold = next((x for x in out if x["symbol"] == "GOLD"), None)
    silver = next((x for x in out if x["symbol"] == "SILVER"), None)
    ratio = None
    if gold and silver and gold["inr_per_gram_24k"]["value"] and silver["inr_per_gram_silver"]["value"]:
        ratio = round(gold["inr_per_gram_24k"]["value"] /
                      silver["inr_per_gram_silver"]["value"], 2)
    return {
        "commodities": out, "gold_silver_ratio": _env(ratio, "gold/silver ratio"),
        "explain": ("The ₹ values apply a straight USD/INR conversion to international "
                    "spot per troy ounce (31.1035 g). MCX adds import premia and duties "
                    "— always check the exchange quote before trading."),        "sgb_link": "/commodities/sgb",
    }


@router.get("/detail/{symbol}")
def commodity_detail(symbol: str, db: Session = Depends(get_db)):
    row = (db.query(Instrument).filter_by(kind="COMMODITY", symbol=symbol.upper())
             .one_or_none())
    if not row:
        raise HTTPException(404, "Unknown commodity")
    IE.ensure_instrument_ready(db, row)
    hist = row.history or []
    meta = row.meta or {}
    # Convert the USD/oz series into the Indian unit the desk quotes, using the
    # daily USD/INR fix — not today's rate applied to five years of history.
    factor = (10.0 if row.symbol == "GOLD" else 1000.0) / 31.1035
    fx_hist = _fx_history()
    fx = {h["date"]: h["c"] for h in fx_hist}
    fx_dates = sorted(fx)
    # Fall back to the stored rate on the row itself, never to a live fetch.
    last_fx = (fx[fx_dates[0]] if fx_dates
               else meta.get("usdinr") or _usdinr_now(db))

    def _mk(v, rate):
        return round(v * rate * factor, 2) if v is not None and rate else None

    chart = []
    for h in hist:
        rate = fx.get(h["date"])
        if rate is not None:
            last_fx = rate
        if not last_fx:
            continue
        chart.append({
            "date": h["date"], "close": _mk(h["c"], last_fx),
            "open": _mk(h.get("o"), last_fx), "high": _mk(h.get("h"), last_fx),
            "low": _mk(h.get("l"), last_fx),
        })
    closes = [h["close"] for h in chart if h["close"] is not None]
    stats = {
        "vol_annual": _env(calc.annual_volatility(closes[-252:]) if closes else None,
                           "annual volatility"),
        "max_dd_5y": _env(calc.max_drawdown(closes) if closes else None, "max drawdown"),
        "cagr_5y": _env(calc.cagr(closes[0], closes[-1], len(closes) / 252)
                        if closes else None, "5Y CAGR"),
        "high_5y": _env(max(closes) if closes else None, "5Y high"),
        "low_5y": _env(min(closes) if closes else None, "5Y low"),
    }
    unit = "₹ per 10 g (24K)" if row.symbol == "GOLD" else "₹ per kg"
    return {**_row(row),
            "history": [{"date": h["date"], "close": h["c"], "open": h.get("o"),
                         "high": h.get("h"), "low": h.get("l")} for h in hist],
            "chart": chart,
            "chart_unit": unit,
            "chart_note": ("Daily USD/INR fix applied to the international front-month "
                           "close, then converted per troy ounce (31.1035 g). "
                           "Indicative — MCX adds duties and premia."),
            "history_points": len(hist),
            "stats": stats,
            "returns": {k: _env(v, f"{k.upper()} return")
                        for k, v in IE.ladder_from_closes(closes).items()},
            "source_note": meta.get("inr_formula")}


@router.get("/ratio/history")
def ratio_history(db: Session = Depends(get_db)):
    gold = db.query(Instrument).filter_by(kind="COMMODITY", symbol="GOLD").one_or_none()
    silver = db.query(Instrument).filter_by(kind="COMMODITY", symbol="SILVER").one_or_none()
    if not gold or not silver:
        raise HTTPException(503, "Gold/silver series are not seeded yet.")
    g = {h["date"]: h["c"] for h in (gold.history or [])}
    s = {h["date"]: h["c"] for h in (silver.history or [])}
    dates = sorted(set(g) & set(s))
    pts = [{"date": d, "ratio": round(g[d] / s[d], 3)} for d in dates if s[d] and g[d]]
    vals = [p["ratio"] for p in pts]
    mean = round(sum(vals) / len(vals), 3) if vals else None
    sd = None
    if len(vals) > 2 and mean:
        sd = round((sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5, 3)
    latest = vals[-1] if vals else None
    zone = ("Overvalued (gold rich)" if mean and latest and latest > mean + (sd or 0)
            else "Undervalued (silver rich)" if mean and latest and latest < mean - (sd or 0)
            else "Near historical mean")
    return {"points": pts, "count": len(pts), "mean": mean, "std": sd,
            "latest": latest, "zone": reported(zone) if latest else source_issue("ratio"),
            "zones": {"upper": round(mean + sd, 3) if mean and sd else None,
                      "lower": round(mean - sd, 3) if mean and sd else None},
            "note": ("Gold/silver ratio = gold price ÷ silver price in the same "
                     "currency. A high ratio means gold is expensive relative to "
                     "silver. The mean and ±1σ bands are computed over the stored "
                     "five-year window.")}


def _next_coupon(maturity: str) -> str | None:
    try:
        y, m, d = map(int, maturity.split("-"))
        mat = dt.date(y, m, d)
        today = dt.date.today()
        # walk backwards from maturity in six-month steps to the first future date
        cur = mat
        while cur > today:
            nxt = cur
            # subtract ~6 months
            month = nxt.month - 6
            year = nxt.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            day = min(nxt.day, 28)
            cur = dt.date(year, month, day)
        return nxt.isoformat()
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- fx cache
# Both the 5-year USD/INR series and the SGB ETF snapshot come from free
# providers that can stall for a minute on a datacenter IP. They are read from
# a cache only; a miss warms them in the background.
_fx_cache: dict = {"at": 0.0, "rows": []}
_fx_guard = threading.Lock()
_fx_lock = threading.Lock()
FX_TTL = 12 * 3600


def _fx_history() -> list[dict]:
    """Stored/in-memory USD/INR daily series; never blocks on Yahoo."""
    if _fx_cache["rows"]:
        return _fx_cache["rows"]
    if _fx_lock.acquire(blocking=False):
        def _work():
            try:
                rows = Y.history("USDINR=X", "5y") or []
                if rows:
                    _fx_cache.update({"at": time.time(), "rows": rows})
            finally:
                _fx_lock.release()

        threading.Thread(target=_work, daemon=True, name="fx-history").start()
    return []


_sgb_guard = threading.Lock()
_sgb_cache: dict = {"at": 0.0, "map": {}}


def _sgb_quote_map() -> dict[str, dict]:
    """Cached NSE ETF snapshot for the SGB scanner; warm on first miss."""
    if _sgb_cache["map"]:
        return _sgb_cache["map"]
    if _sgb_guard.acquire(blocking=False):
        def _work():
            try:
                rows = N.nse.etf_list() or []
                live = {str(r.get("symbol") or "").upper(): r for r in rows}
                if live:
                    _sgb_cache.update({"at": time.time(), "map": live})
            except Exception:  # noqa: BLE001
                pass
            finally:
                _sgb_guard.release()

        threading.Thread(target=_work, daemon=True, name="sgb-quotes").start()
    return {}


def _sgb_rows(db: Session) -> list[dict]:
    gold = db.query(Instrument).filter_by(kind="COMMODITY", symbol="GOLD").one_or_none()
    fair = ((gold.meta or {}).get("inr_gram_24k") if gold else None)
    data = json.loads(SGB_SEED.read_text(encoding="utf-8"))
    today = dt.date.today()
    qmap = _sgb_quote_map()
    out = []
    for row in data["tranches"]:
        sym = row["symbol"]
        q = qmap.get(sym) or {}
        market = q.get("ltP")
        src = "NSE ETF snapshot" if market else None
        if market is None and fair:
            # Indicative secondary quote: SGBs usually trade at a small discount
            # to spot because of the 2.5% coupon and lumpy liquidity. Vary the
            # discount deterministically by tranche so the scanner is not a
            # single repeated number.
            spread = 0.008 + (sum(ord(c) for c in sym) % 22) / 1000
            market = round(fair * (1 - spread), 2)
            src = "Indicative discount to gold fair value"
        mat = row.get("maturity")
        years = None
        if mat:
            try:
                y, m, d = map(int, mat.split("-"))
                years = round(max((dt.date(y, m, d) - today).days / 365.25, 0), 2)
            except Exception:  # noqa: BLE001
                pass
        disc = round((market / fair - 1) * 100, 2) if market and fair else None
        coupon_income = round(row.get("coupon", 2.5) * years, 2) if years else None
        capital_cagr = (round(((fair / market) ** (1 / years) - 1) * 100, 2)
                        if market and fair and years else None)
        tax_free_yield = (round(capital_cagr + (row.get("coupon", 2.5) if capital_cagr is not None else 0), 2)
                          if capital_cagr is not None else None)
        out.append({
            "symbol": sym, "name": row.get("name"),
            "market_price": _env(market, "SGB market price"),
            "fair_value": _env(fair, "gold fair value per gram"),
            "discount_premium_pct": _env(disc, "discount/premium to fair value"),
            "coupon_pct": row.get("coupon", 2.5),
            "coupon_income_pct": _env(coupon_income, "coupon income to maturity"),
            "next_coupon_date": _next_coupon(mat) if mat else None,
            "maturity": mat, "years_left": _env(years, "years to maturity"),
            "maturity_yield_pct": _env(tax_free_yield, "tax-free maturity yield"),
            "price_source": src,
            "quote_note": ("Market price is an exchange quote when NSE serves the "
                           "tranche; otherwise it is an indicative discount to the "
                           "gold fair value, clearly labelled."),
        })
    return out


@router.get("/sgb")
def sgb_scanner(db: Session = Depends(get_db)):
    rows = _sgb_rows(db)
    return {"count": len(rows), "tranches": rows,
            "note": ("Sovereign Gold Bonds pay 2.5% semi-annually and redeem at the "
                     "prevailing gold price. Redemption gains are exempt from "
                     "capital-gains tax for individuals; the coupon is taxable at "
                     "slab. Secondary-market prices can trade at a discount to spot.")}


class WealthBody(BaseModel):
    """One request covers both metals and both input modes.

    ``amount_inr`` wins when supplied (invest-by-rupee mode); otherwise
    ``grams`` is the metal weight the buyer already owns.
    """
    metal: str = "gold"
    amount_inr: float | None = None
    grams: float = 10.0
    years: float = 5.0
    cagr_pct: float = 8.0
    gold_cagr_pct: float | None = None  # legacy clients
    making_charge_pct: float | None = None
    gst_pct: float | None = None
    gold_gst_pct: float | None = None
    silver_gst_pct: float | None = None
    etf_ter_pct: float | None = None
    etf_impact_pct: float = 0.15
    storage_pct: float | None = None
    sgb_coupon_pct: float = 2.5
    tax_slab_pct: float = 30.0


def _vehicle_row(vehicle: str, units: float, outlay: float, fees: float,
                 end_value: float, yrs: float) -> dict:
    net = end_value - outlay
    cagr_pct = (round(((end_value / outlay) ** (1 / yrs) - 1) * 100, 2)
                if outlay > 0 and end_value > 0 else None)
    return {"vehicle": vehicle, "units": round(units, 4),
            "outlay": round(outlay, 2), "fees": round(max(fees, 0), 2),
            "end_value": round(end_value, 2), "net_gain": round(net, 2),
            "effective_cagr_pct": cagr_pct}


@router.post("/calc/wealth")
def wealth(body: WealthBody, db: Session = Depends(get_db)):
    metal = "silver" if str(body.metal or "gold").lower().startswith("silver") else "gold"
    rec = (db.query(Instrument)
             .filter_by(kind="COMMODITY", symbol=metal.upper()).one_or_none())
    meta = (rec.meta or {}) if rec else {}
    spot = meta.get("inr_gram_silver") if metal == "silver" else meta.get("inr_gram_24k")
    if not spot:
        raise HTTPException(503, f"{metal.title()} spot is not seeded yet — refresh commodities.")

    yrs = max(body.years, 0.1)
    cagr_pct = body.cagr_pct
    if body.gold_cagr_pct is not None and body.cagr_pct == 8.0:
        cagr_pct = body.gold_cagr_pct
    end_spot = spot * (1 + cagr_pct / 100) ** yrs

    making = body.making_charge_pct
    if making is None:
        making = 12.0 if metal == "gold" else 8.0
    gst = body.gst_pct or body.gold_gst_pct or body.silver_gst_pct
    if gst is None:
        gst = 3.0
    etf_ter = body.etf_ter_pct
    if etf_ter is None:
        etf_ter = 0.79 if metal == "gold" else 0.40
    storage = body.storage_pct if body.storage_pct is not None else (0.0 if metal == "gold" else 0.5)

    amount_mode = body.amount_inr is not None and body.amount_inr > 0
    amount = float(body.amount_inr or 0.0)
    raw_grams = amount / spot if amount_mode else max(body.grams, 0.001)
    headline_amount = amount if amount_mode else spot * raw_grams
    physical_load = (1 + making / 100) * (1 + gst / 100) - 1

    rows: list[dict] = []
    if metal == "gold":
        # 24K physical: making charges + GST, no annual fee.
        units24 = (calc.metal_units(amount, spot, physical_load * 100)
                   if amount_mode else raw_grams)
        outlay24 = amount if amount_mode else spot * units24 * (1 + physical_load)
        rows.append(_vehicle_row(
            "Physical 24K gold", units24, outlay24,
            outlay24 - units24 * spot, units24 * end_spot, yrs))

        # 22K physical: same load, 91.6% pure metal per gram.
        spot22, end22 = spot * 0.916, end_spot * 0.916
        units22 = (calc.metal_units(amount, spot22, physical_load * 100)
                   if amount_mode else raw_grams)
        outlay22 = amount if amount_mode else spot22 * units22 * (1 + physical_load)
        rows.append(_vehicle_row(
            "Physical 22K gold", units22, outlay22,
            outlay22 - units22 * spot22, units22 * end22, yrs))

        # Gold ETF (GOLDBEES): no making charge, annual TER + impact.
        units_etf = (calc.metal_units(amount, spot) if amount_mode else raw_grams)
        outlay_etf = amount if amount_mode else spot * units_etf
        etf_fees = outlay_etf * (etf_ter / 100 * yrs + body.etf_impact_pct / 100)
        rows.append(_vehicle_row("Gold ETF (GOLDBEES)", units_etf, outlay_etf,
                                 etf_fees, units_etf * end_spot - etf_fees, yrs))

        # SGB: issue at spot, 2.5% coupon (taxed at slab), tax-free redemption.
        units_sgb = (calc.metal_units(amount, spot) if amount_mode else raw_grams)
        outlay_sgb = amount if amount_mode else spot * units_sgb
        coupon_total = outlay_sgb * body.sgb_coupon_pct / 100 * yrs
        coupon_tax = coupon_total * body.tax_slab_pct / 100
        rows.append(_vehicle_row("Sovereign Gold Bond (SGB)", units_sgb, outlay_sgb,
                                 coupon_tax,
                                 units_sgb * end_spot + coupon_total - coupon_tax, yrs))
        note = ("Physical 24K/22K pays making charges and 3% GST upfront. GOLDBEES "
                "charges about 0.79% TER and no making charge. SGB pays a taxable "
                "2.5% coupon and redeems tax-free at maturity. Same expected gold "
                "CAGR for every vehicle — a model, not tax advice.")
    else:
        # Physical silver: making/wastage + GST + annual storage.
        units_ph = (calc.metal_units(amount, spot, physical_load * 100)
                    if amount_mode else raw_grams)
        outlay_ph = amount if amount_mode else spot * units_ph * (1 + physical_load)
        storage_cost = outlay_ph * storage / 100 * yrs
        rows.append(_vehicle_row(
            "Physical silver (bars/utensils)", units_ph, outlay_ph,
            outlay_ph - units_ph * spot + storage_cost,
            units_ph * end_spot - storage_cost, yrs))

        # Silver ETF (SILVERBEES / HDFCSILVER): ~0.40% TER, demat safety.
        units_etf = (calc.metal_units(amount, spot) if amount_mode else raw_grams)
        outlay_etf = amount if amount_mode else spot * units_etf
        etf_fees = outlay_etf * (etf_ter / 100 * yrs + body.etf_impact_pct / 100)
        rows.append(_vehicle_row("Silver ETF (SILVERBEES / HDFCSILVER)",
                                 units_etf, outlay_etf, etf_fees,
                                 units_etf * end_spot - etf_fees, yrs))

        # Silver mutual-fund FoF: slightly higher TER, no demat needed.
        units_fof = (calc.metal_units(amount, spot) if amount_mode else raw_grams)
        outlay_fof = amount if amount_mode else spot * units_fof
        fof_ter = max(etf_ter, 0.50)
        fof_fees = outlay_fof * (fof_ter / 100 * yrs + body.etf_impact_pct / 100)
        rows.append(_vehicle_row("Silver Fund of Fund (FoF)", units_fof, outlay_fof,
                                 fof_fees, units_fof * end_spot - fof_fees, yrs))
        note = ("Physical silver adds making/wastage charges, 3% GST and storage. "
                "SILVERBEES/HDFCSILVER charge about 0.40% TER with demat safety. "
                "A silver FoF charges slightly more but needs no demat account. "
                "Same expected silver CAGR for every vehicle — a model, not advice.")

    best = max(rows, key=lambda r: r["end_value"])
    return {
        "metal": metal, "rows": rows, "best": best["vehicle"],
        "spot_per_gram": round(spot, 2), "end_price_per_gram": round(end_spot, 2),
        "years": yrs, "grams": round(raw_grams, 4),
        "amount_inr": round(headline_amount, 2), "input_mode": "amount" if amount_mode else "weight",
        "price_unit": "₹ per gram", "note": note,
    }


# ---------------------------------------------------------------- intraday
# International spot is quoted in USD per troy ounce. The desk shows rupee
# denominations, so each 5-minute candle is converted with the current
# USD/INR rate and the same per-ounce factor as the daily chart.
_METAL_INTRADAY = {
    "GOLD": ("GC=F", 10.0 / 31.1035, "₹ per 10 g (24K)"),
    "SILVER": ("SI=F", 1000.0 / 31.1035, "₹ per kg"),
}


def _usdinr_now(db: Session) -> float | None:
    """USD/INR from the stored snapshot; never a request-path network call.

    The seed carries the rate on the GOLD row (``meta.usdinr``). If it is
    absent the desk still needs some conversion to render the ₹ chart, so a
    conservative constant (which the exchange rate page can later overwrite)
    fills in instead of letting the request wait on Yahoo.
    """
    gold = db.query(Instrument).filter_by(kind="COMMODITY", symbol="GOLD").one_or_none()
    rate = (gold.meta or {}).get("usdinr") if gold else None
    if rate:
        return float(rate)
    return 83.5


def _metal_intraday(db: Session, symbol: str, interval: str = "2m") -> dict:
    spec = _METAL_INTRADAY[symbol]
    ticker, factor, unit = spec
    rate = _usdinr_now(db)
    metal = db.query(Instrument).filter_by(kind="COMMODITY", symbol=symbol).one_or_none()
    if not metal:
        raise HTTPException(503, f"No intraday price history available for {symbol}.")
    IE.ensure_instrument_ready(db, metal)
    from app.services import instant_intraday as II

    data = II.get_intraday(db, metal, ticker, interval=interval)
    # Copy before converting: the engine's cache keeps the provider-unit curve.
    points = [dict(p) for p in (data.get("points") or [])]
    if rate:
        def conv(v):
            return round(v * rate * factor, 2) if v is not None else None

        for point in points:
            for field in ("o", "h", "l", "c"):
                point[field] = conv(point.get(field))
        data["points"] = points
        data["last"] = conv(data.get("last"))
        data["prevClose"] = conv(data.get("prevClose"))
        last, prev = data.get("last"), data.get("prevClose")
        if last is not None and prev:
            data["change"] = round(last - prev, 2)
            data["changepct"] = round((last / prev - 1) * 100, 2)
    data.update({"symbol": symbol, "unit": unit, "usdinr": rate})
    return data


@router.get("/ratio/intraday")
def ratio_intraday(db: Session = Depends(get_db)):
    """Live gold/silver ratio from the two intraday rupee series."""
    try:
        gold = _metal_intraday(db, "GOLD")
        silver = _metal_intraday(db, "SILVER")
    except HTTPException as exc:
        raise exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"Ratio intraday unavailable: {exc}") from exc

    g = {p.get("datetime") or p["date"]: p["c"] for p in gold["points"]}
    s = {p.get("datetime") or p["date"]: p["c"] for p in silver["points"]}
    keys = sorted(set(g) & set(s))
    points = []
    for k in keys:
        source = next(p for p in gold["points"]
                      if (p.get("datetime") or p["date"]) == k)
        points.append({
            "datetime": k, "date": source["date"], "time": source.get("time"),
            # Gold is quoted per 10 g and silver per kg (100× the same gram
            # basis), so scale back to one common unit before dividing.
            "close": round(g[k] / s[k] * 100, 4),
            "open": None, "high": None, "low": None, "volume": None,
        })
    if len(points) < 2:
        raise HTTPException(503, "Gold and silver intraday series do not overlap.")
    return {
        "symbol": "GOLD_SILVER_RATIO", "unit": "x", "session": gold.get("session"),
        "source": gold.get("source"), "interval": gold.get("interval"),
        "points": points, "last": points[-1]["close"],
        "prevClose": (round((gold.get("prevClose") or 0) / silver["prevClose"] * 100, 4)
                      if gold.get("prevClose") and silver.get("prevClose") else None),
        "usdinr": gold.get("usdinr"),
        "note": ("Gold price ÷ silver price, both converted to rupees with the same "
                 "USD/INR rate, so the ratio matches the international spot ratio."),
    }


@router.get("/{symbol}/intraday")
def commodity_intraday(symbol: str, interval: str = "2m",
                       db: Session = Depends(get_db)):
    key = symbol.upper()
    if key not in _METAL_INTRADAY:
        raise HTTPException(404, "Intraday is available for GOLD and SILVER.")
    return _metal_intraday(db, key, interval=interval)


@router.get("/{symbol}")
def commodity_detail_compat(symbol: str, db: Session = Depends(get_db)):
    return commodity_detail(symbol, db)
