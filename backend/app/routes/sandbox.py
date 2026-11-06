"""Paper-trading sandbox + watchlist — genuine CRUD with cash accounting.

* **₹10,00,000 virtual corpus** (zero-KYC). Cash is tracked from actual paper
  fills, not a cosmetic number: buys debit cash, sells credit it, closing
  reverses the leg and books realised P&L net of charges.
* **Cash equities and F&O options** share one portfolio. Options are filled at
  the live NSE chain premium for the chosen strike/expiry; when the chain does
  not answer the order is rejected rather than filled at a made-up price.
* **Charges** use the platform's statutory engines (delivery equity and F&O).
* **Portfolio history** is an event-based timeline with a daily equity mark
  reconstructed from stored closes where the platform has them, and an explicit
  note where it does not (F&O legs only exist from their fill onward).

Nothing here touches a broker or a real exchange order book.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import FREE_SOURCE_NOTE
from app.core.db import get_db
from app.data.adapters import nse_adapter as N
from app.models.models import Instrument, SandboxOrder, WatchItem
from app.routes.indices import slug_for
from app.services import calc
from app.services.contextual import reported

router = APIRouter(tags=["sandbox"])

STARTING_CASH = 1_000_000  # ₹10,00,000 virtual, zero-KYC (per spec)

FNO_INDEX_KEYS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY",
                  "NIFTYNXT50", "SENSEX", "NIFTYIT"}
LOT_SIZES = {"NIFTY": 75, "BANKNIFTY": 30, "FINNIFTY": 65,
             "MIDCPNIFTY": 120, "NIFTYNXT50": 25, "SENSEX": 20,
             "NIFTYIT": 25}

# Human names, NSE index symbols and F&O keys all resolve to one canonical name.
INDEX_ALIASES = {
    "NIFTY": "NIFTY 50", "NIFTY50": "NIFTY 50", "NIFTY 50": "NIFTY 50",
    "NIFTY BANK": "NIFTY BANK", "BANK NIFTY": "NIFTY BANK",
    "BANKNIFTY": "NIFTY BANK", "NIFTYBANK": "NIFTY BANK",
    "SENSEX": "SENSEX", "BSE SENSEX": "SENSEX", "BSESENSEX": "SENSEX",
    "NIFTY IT": "NIFTY IT", "NIFTYIT": "NIFTY IT",
    "NIFTY NEXT 50": "NIFTY NEXT 50", "NIFTYNXT50": "NIFTY NEXT 50",
    "NIFTY FIN SERVICE": "NIFTY FIN SERVICE", "FINNIFTY": "NIFTY FIN SERVICE",
    "NIFTY MIDCAP 100": "NIFTY MIDCAP 100", "MIDCPNIFTY": "NIFTY MIDCAP 100",
}
FNO_KEY_BY_NAME = {
    "NIFTY 50": "NIFTY", "NIFTY BANK": "BANKNIFTY",
    "NIFTY FIN SERVICE": "FINNIFTY", "NIFTY MIDCAP 100": "MIDCPNIFTY",
    "NIFTY NEXT 50": "NIFTYNXT50", "SENSEX": "SENSEX", "NIFTY IT": "NIFTYIT",
}


class OrderIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    side: str = Field(pattern="^(BUY|SELL)$")
    quantity: float | None = Field(default=None, gt=0)
    note: str | None = None
    # Phase 4 — derivatives
    asset_class: str = Field(default="EQUITY", pattern="^(EQUITY|DERIVATIVE)$")
    underlying: str | None = Field(default=None, max_length=32)
    option_type: str | None = Field(default=None, pattern="^(CE|PE|FUT)$")
    strike: float | None = Field(default=None, gt=0)
    expiry: str | None = Field(default=None, max_length=20)
    lots: float | None = Field(default=None, gt=0)
    lot_size: int | None = Field(default=None, gt=0)
    price: float | None = Field(default=None, gt=0)


class WatchIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    kind: str = Field(default="EQUITY", pattern="^(EQUITY|INDEX|ETF|FUND)$")
    href: str | None = Field(default=None, max_length=120)


class QuoteIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=120)
    side: str = Field(default="BUY", pattern="^(BUY|SELL)$")
    asset_class: str = Field(default="EQUITY", pattern="^(EQUITY|DERIVATIVE)$")
    quantity: float | None = Field(default=None, gt=0)
    underlying: str | None = Field(default=None, max_length=120)
    option_type: str | None = Field(default=None, pattern="^(CE|PE|FUT)$")
    strike: float | None = Field(default=None, gt=0)
    expiry: str | None = Field(default=None, max_length=20)
    lots: float | None = Field(default=None, gt=0)
    lot_size: int | None = Field(default=None, gt=0)
    price: float | None = Field(default=None, gt=0)


# ---------------------------------------------------------------------------
# Pricing helpers
# ---------------------------------------------------------------------------

def _instrument_mark(row: Instrument) -> float | None:
    m = row.meta or {}
    v = m.get("lastPrice") if row.kind != "INDEX" else m.get("last")
    if v is None:
        v = m.get("lastPrice") or m.get("last")
    if v is None and row.history:
        v = row.history[-1].get("c")
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _resolve_instrument(term: str, db: Session,
                        kinds: tuple[str, ...] = ("EQUITY", "ETF", "INDEX")
                        ) -> Instrument | None:
    """Resolve a symbol, company name or index alias to one instrument row."""
    raw = (term or "").strip()
    if not raw:
        return None
    u = raw.upper()
    alias = INDEX_ALIASES.get(u)
    if alias:
        row = (db.query(Instrument).filter_by(kind="INDEX", symbol=alias)
                 .one_or_none())
        if row:
            return row
    row = (db.query(Instrument)
             .filter(Instrument.kind.in_(kinds), Instrument.symbol == u)
             .first())
    if row:
        return row
    # Exact-ish symbol prefix, then company-name contains (Paras Defence, etc.)
    row = (db.query(Instrument)
             .filter(Instrument.kind.in_(kinds), Instrument.symbol.like(f"{u}%"))
             .order_by(Instrument.symbol).first())
    if row:
        return row
    return (db.query(Instrument)
              .filter(Instrument.kind.in_(kinds), Instrument.name.ilike(f"%{raw}%"))
              .order_by(Instrument.symbol).first())


def _equity_row(symbol: str, db: Session) -> Instrument | None:
    row = _resolve_instrument(symbol, db, ("EQUITY", "ETF"))
    if row:
        return row
    return (db.query(Instrument)
              .filter(Instrument.kind.in_(("EQUITY", "ETF")),
                      Instrument.symbol == symbol.upper()).first())


def _index_row(symbol: str, db: Session) -> Instrument | None:
    u = symbol.upper()
    nse_name = INDEX_ALIASES.get(u, u)
    row = (db.query(Instrument).filter_by(kind="INDEX", symbol=nse_name)
             .one_or_none())
    if row:
        return row
    return (db.query(Instrument).filter(Instrument.kind == "INDEX")
              .filter(Instrument.symbol.like(f"%{nse_name}%")).first())


def _fno_key(underlying: str) -> str:
    u = (underlying or "").upper()
    canonical = INDEX_ALIASES.get(u, u)
    return FNO_KEY_BY_NAME.get(canonical, u)


def _equity_mark(symbol: str, db: Session) -> float | None:
    row = _resolve_instrument(symbol, db, ("EQUITY", "ETF", "INDEX"))
    return _instrument_mark(row) if row else None


def _underlying_spot(underlying: str, db: Session) -> float | None:
    row = _resolve_instrument(underlying, db, ("INDEX", "EQUITY", "ETF"))
    return _instrument_mark(row) if row else None


def _chain(underlying: str) -> dict | None:
    """Live option chain for one underlying, cached by the NSE adapter."""
    u = _fno_key(underlying)
    try:
        raw = (N.nse.index_option_chain(u) if u in FNO_INDEX_KEYS
               else N.nse.equity_option_chain(u))
    except Exception:  # noqa: BLE001
        return None
    rec = raw.get("records") or {}
    rows = []
    for leg in ((raw.get("filtered") or {}).get("data") or []):
        rows.append({
            "strike": leg.get("strikePrice"),
            "expiry": leg.get("expiryDate"),
            "ce_ltp": (leg.get("CE") or {}).get("lastPrice"),
            "pe_ltp": (leg.get("PE") or {}).get("lastPrice"),
        })
    return {"spot": rec.get("underlyingValue"), "rows": rows}


def _option_premium(underlying: str, option_type: str, strike: float,
                    expiry: str | None) -> tuple[float | None, str, str | None]:
    chain = _chain(underlying)
    if not chain:
        return None, "unavailable", "The free NSE option chain did not answer."
    rows = chain["rows"]
    if expiry:
        rows = [r for r in rows if (r.get("expiry") or "") == expiry] or rows
    match = next((r for r in rows
                  if r.get("strike") is not None
                  and abs(float(r["strike"]) - strike) < 0.01), None)
    if not match:
        return None, "no-strike", f"Strike {strike:g} was not in the live chain."
    key = "ce_ltp" if option_type == "CE" else "pe_ltp"
    price = match.get(key)
    if price is None:
        return None, "no-premium", "The chain row had no last premium."
    return float(price), "NSE option chain (last premium)", None


def _equity_charges(side: str, value: float) -> float:
    c = calc.net_in_pocket("BUY" if side == "BUY" else "SELL",
                           buy_value=value if side == "BUY" else 0.0,
                           sell_value=value if side == "SELL" else 0.0)
    return round(c["total_charges"], 2)


def _fno_charges_one_side(side: str, value: float, product: str = "OPTIONS") -> float:
    c = calc.fno_charges(buy_premium=value if side == "BUY" else 0.0,
                         sell_premium=value if side == "SELL" else 0.0,
                         product=product)
    # fno_charges prices a round trip (brokerage ×2); keep one side here.
    return round(c["total"] - c["brokerage"] / 2, 2)


def _contract_label(o: SandboxOrder) -> str:
    if o.asset_class != "DERIVATIVE":
        return o.symbol
    strike = f" {o.strike:g}" if o.strike else ""
    return f"{o.underlying or o.symbol}{strike} {o.option_type or 'FUT'}"


def _mark_order(o: SandboxOrder, db: Session, chain_cache: dict) -> tuple[float | None, str]:
    if o.asset_class != "DERIVATIVE":
        return _equity_mark(o.symbol, db), "equity last price"
    if (o.option_type or "") == "FUT":
        return o.entry_price, "entry premium (no free futures feed)"
    underlying = (o.underlying or o.symbol).upper()
    if underlying not in chain_cache:
        chain_cache[underlying] = _chain(underlying)
    chain = chain_cache[underlying]
    if not chain:
        return o.entry_price, "entry premium (chain unavailable)"
    rows = chain["rows"]
    if o.expiry:
        rows = [r for r in rows if (r.get("expiry") or "") == (o.expiry or "")] or rows
    match = next((r for r in rows
                  if r.get("strike") is not None and o.strike is not None
                  and abs(float(r["strike"]) - float(o.strike)) < 0.01), None)
    if not match:
        return o.entry_price, "entry premium (strike no longer listed)"
    key = "ce_ltp" if o.option_type == "CE" else "pe_ltp"
    price = match.get(key)
    return (float(price) if price is not None else o.entry_price,
            "live NSE option chain")


# ---------------------------------------------------------------------------
# Summary / portfolio
# ---------------------------------------------------------------------------

def _summary(db: Session) -> dict:
    orders = db.query(SandboxOrder).order_by(SandboxOrder.opened_at).all()
    chain_cache: dict = {}
    cash = float(STARTING_CASH)
    realized = 0.0
    positions = []
    closed = []
    for o in orders:
        qty = float(o.quantity or 0)
        notional = float(o.entry_price or 0) * qty
        charges = float(o.charges or 0)
        if o.status == "OPEN":
            mark, src = _mark_order(o, db, chain_cache)
            mark = mark if mark is not None else o.entry_price
            # Cash effect of opening the leg.
            if o.side == "BUY":
                cash -= notional + charges
            else:
                cash += notional - charges
            pnl = ((mark - o.entry_price) if o.side == "BUY"
                   else (o.entry_price - mark)) * qty
            positions.append({
                "id": o.id, "symbol": o.symbol, "label": _contract_label(o),
                "asset_class": o.asset_class,
                "underlying": o.underlying, "option_type": o.option_type,
                "strike": o.strike, "expiry": o.expiry,
                "lot_size": o.lot_size, "lots": o.lots,
                "side": o.side,
                "qty": qty if o.side == "BUY" else -qty,
                "entry": round(float(o.entry_price), 2),
                "mark": round(float(mark), 2),
                "mark_source": src,
                "charges": round(charges, 2),
                "pnl": round(pnl - charges, 2),
                "pnl_gross": round(pnl, 2),
                "pnl_pct": round(pnl / notional * 100, 2) if notional else None,
                "opened_at": o.opened_at.isoformat() if o.opened_at else None,
                "href": (f"/stocks/{o.symbol}" if o.asset_class == "EQUITY"
                         else None),
            })
            continue
        # Closed leg: reverse the opening cash effect, then apply the closing
        # one. Without the reversal the entry notional stays stuck in cash and
        # the equity value is overstated by the size of every closed leg.
        exit_price = float(o.exit_price or o.entry_price or 0)
        exit_notional = exit_price * qty
        if o.side == "BUY":
            cash -= notional
            cash += exit_notional
            gross = exit_notional - notional
        else:
            cash += notional
            cash -= exit_notional
            gross = notional - exit_notional
        cash -= charges
        realized += gross - charges
        closed.append({
            "id": o.id, "symbol": o.symbol, "label": _contract_label(o),
            "asset_class": o.asset_class, "side": o.side, "qty": qty,
            "entry": round(float(o.entry_price), 2),
            "exit": round(exit_price, 2), "charges": round(charges, 2),
            "realized_pnl": round(gross - charges, 2),
            "opened_at": o.opened_at.isoformat() if o.opened_at else None,
            "closed_at": o.closed_at.isoformat() if o.closed_at else None,
        })

    market_value = 0.0
    for p in positions:
        mv = p["mark"] * abs(p["qty"])
        market_value += mv if p["qty"] > 0 else -mv
    equity_value = cash + market_value
    unrealized = sum(p["pnl"] for p in positions)
    exposure = sum(abs(p["mark"] * p["qty"]) for p in positions)
    return {
        "starting_cash": STARTING_CASH,
        "cash_available": round(cash, 2),
        "market_value": round(market_value, 2),
        "equity_value": round(equity_value, 2),
        "exposure": round(exposure, 2),
        "live_positions": positions,
        "closed_positions": closed,
        "pnl": {"realized": round(realized, 2),
                "unrealized": round(unrealized, 2),
                "total": round(equity_value - STARTING_CASH, 2)},
        "allocation": {
            "equity_pct": round(sum(abs(p["mark"] * p["qty"]) for p in positions
                                    if p["asset_class"] == "EQUITY")
                                / max(exposure, 1) * 100, 1),
            "derivative_pct": round(sum(abs(p["mark"] * p["qty"]) for p in positions
                                        if p["asset_class"] == "DERIVATIVE")
                                    / max(exposure, 1) * 100, 1),
        },
        "margin_note": ("The sandbox does not model SPAN/exposure margin or "
                        "mark-to-market calls. F&O positions are tracked at "
                        "premium value; real margin requirements are materially "
                        "higher than that."),
        "marking_note": reported(
            "Open positions are marked at the last available free-feed price. "
            "Equity marks are EOD/delayed; option marks come from the live NSE "
            "chain when it answers, otherwise the fill premium is held with the "
            "source labelled. " + FREE_SOURCE_NOTE),
    }


@router.get("/sandbox/summary")
def summary(db: Session = Depends(get_db)):
    return _summary(db)


@router.get("/sandbox/history")
def portfolio_history(db: Session = Depends(get_db)):
    """Event-based equity curve reconstructed from stored closes.

    The platform does not keep a daily mark for every sandbox leg, so the
    curve is built from the dates on which the portfolio changed. Equity legs
    are re-marked from stored daily closes; derivative legs are carried at fill
    premium until the current mark. That limitation is stated in the payload.
    """
    orders = db.query(SandboxOrder).order_by(SandboxOrder.opened_at).all()
    if not orders:
        return {"points": [], "note": "No sandbox activity yet."}
    first = orders[0].opened_at or datetime.utcnow()
    all_dates = set()
    for o in orders:
        if o.opened_at:
            all_dates.add(o.opened_at.date().isoformat())
        if o.closed_at:
            all_dates.add(o.closed_at.date().isoformat())
    all_dates.add(datetime.utcnow().date().isoformat())
    dates = sorted(all_dates)

    # Close price lookup per equity from stored history.
    hist_cache: dict[str, dict[str, float]] = {}
    for o in orders:
        if o.asset_class != "EQUITY" or o.symbol in hist_cache:
            continue
        row = _equity_row(o.symbol, db)
        hist_cache[o.symbol] = {h.get("date"): float(h["c"])
                                for h in (row.history or [])
                                if h.get("c") is not None} if row else {}

    points = []
    for d in dates:
        cash = float(STARTING_CASH)
        realized = 0.0
        mv = 0.0
        for o in orders:
            qty = float(o.quantity or 0)
            entry = float(o.entry_price or 0)
            charges = float(o.charges or 0)
            opened = (o.opened_at.date().isoformat() if o.opened_at else d)
            if opened > d:
                continue
            if o.side == "BUY":
                cash -= entry * qty + charges
            else:
                cash += entry * qty - charges
            if o.status == "CLOSED":
                exit_price = float(o.exit_price or entry)
                closed_d = o.closed_at.date().isoformat() if o.closed_at else d
                if closed_d <= d:
                    # The opening cash effect (including charges) was already
                    # applied above, so only the closing notional is reversed
                    # here. Total charges are booked once against realised P&L.
                    if o.side == "BUY":
                        cash += exit_price * qty
                        realized += (exit_price - entry) * qty - charges
                    else:
                        cash -= exit_price * qty
                        realized += (entry - exit_price) * qty - charges
                    continue
                # still open on this date
            if o.asset_class == "EQUITY":
                px = hist_cache.get(o.symbol, {}).get(d)
            else:
                px = None
            if px is None:
                px = entry
            mv += px * qty if o.side == "BUY" else -px * qty
        points.append({"date": d, "equity_value": round(cash + mv, 2),
                       "realized_cum": round(realized, 2),
                       "open_market_value": round(mv, 2)})
    return {
        "start": first.date().isoformat(),
        "points": points,
        "note": ("Event-based equity curve: each point is a date on which the "
                 "portfolio changed plus today. Equity legs use stored daily "
                 "closes; F&O legs are held at fill premium because no free "
                 "historical option-price feed is stored. Not a brokerage "
                 "statement."),
    }


def _quote_fill(payload: QuoteIn, db: Session) -> dict:
    """Price one prospective leg without writing to the ledger."""
    cash = float(_summary(db).get("cash_available") or STARTING_CASH)
    if payload.asset_class == "EQUITY":
        if not payload.quantity:
            raise HTTPException(422, "quantity is required for a quote")
        row = _resolve_instrument(payload.symbol, db, ("EQUITY", "ETF", "INDEX"))
        price = _instrument_mark(row) if row else _equity_mark(payload.symbol, db)
        if price is None:
            raise HTTPException(404, f"No price data for {payload.symbol}")
        qty = float(payload.quantity)
        value = price * qty
        charges = _equity_charges(payload.side, value)
        return {"asset_class": "EQUITY", "symbol": row.symbol if row else payload.symbol.upper(),
                "name": row.name if row else payload.symbol.upper(),
                "kind": row.kind if row else "EQUITY", "price": round(price, 2),
                "quantity": qty, "lot_size": 1, "lots": None,
                "value": round(value, 2), "charges": round(charges, 2),
                "cash_available": round(cash, 2),
                "cash_after": round(cash - value - charges if payload.side == "BUY"
                                    else cash + value - charges, 2),
                "source": "stored/live free-feed mark"}
    if not payload.underlying or not payload.option_type or not payload.lots:
        raise HTTPException(422, "underlying, option_type and lots are required")
    underlying = _fno_key(payload.underlying)
    lot_size = payload.lot_size or LOT_SIZES.get(underlying, 1)
    qty = float(payload.lots) * lot_size
    product = "FUTURES" if payload.option_type == "FUT" else "OPTIONS"
    if payload.option_type == "FUT":
        price = payload.price or _underlying_spot(payload.underlying, db)
        source = ("caller-supplied futures price" if payload.price
                  else "live index spot (futures proxy)")
        if price is None:
            raise HTTPException(404, "No live spot to proxy this futures fill")
    else:
        if not payload.strike:
            raise HTTPException(422, "strike is required for an option quote")
        price, source, err = _option_premium(underlying, payload.option_type,
                                             payload.strike, payload.expiry)
        if err and payload.price:
            price, source = payload.price, "caller-supplied premium"
            err = None
        if err or price is None:
            raise HTTPException(404, err or "No live premium for this contract")
    value = float(price) * qty
    charges = _fno_charges_one_side(payload.side, value, product)
    return {"asset_class": "DERIVATIVE", "symbol": underlying,
            "name": underlying, "kind": "INDEX" if underlying in FNO_INDEX_KEYS else "EQUITY",
            "price": round(float(price), 2), "quantity": qty,
            "lot_size": lot_size, "lots": payload.lots,
            "value": round(value, 2), "charges": round(charges, 2),
            "cash_available": round(cash, 2),
            "cash_after": round(cash - value - charges if payload.side == "BUY"
                                else cash + value - charges, 2),
            "source": source}


@router.post("/sandbox/quote")
def quote_order(payload: QuoteIn, db: Session = Depends(get_db)):
    return _quote_fill(payload, db)


@router.post("/sandbox/orders")
def place_order(payload: OrderIn, db: Session = Depends(get_db)):
    if payload.asset_class == "EQUITY":
        if not payload.quantity:
            raise HTTPException(422, "quantity is required for an equity order")
        row = _resolve_instrument(payload.symbol, db, ("EQUITY", "ETF", "INDEX"))
        mark = _instrument_mark(row) if row else _equity_mark(payload.symbol, db)
        if mark is None:
            raise HTTPException(404, f"No price data for {payload.symbol} — "
                                     "cannot price a sandbox fill")
        symbol = row.symbol if row else payload.symbol.upper()
        value = mark * payload.quantity
        charges = _equity_charges(payload.side, value)
        o = SandboxOrder(symbol=symbol[:32], side=payload.side,
                         quantity=payload.quantity, entry_price=mark,
                         note=payload.note, status="OPEN", asset_class="EQUITY",
                         charges=charges)
        db.add(o)
        db.commit()
        return {"id": o.id, "asset_class": "EQUITY",
                "name": row.name if row else symbol,
                "filled_at": "EOD/delayed mark", "fill_price": o.entry_price,
                "quantity": o.quantity, "charges": charges,
                "value": round(value, 2), "status": o.status,
                "source": "NSE/Yahoo EOD free feed"}

    # ---- F&O ------------------------------------------------------------
    if not payload.underlying:
        raise HTTPException(422, "underlying is required for a derivative order")
    if not payload.option_type:
        raise HTTPException(422, "option_type (CE/PE/FUT) is required")
    if not payload.lots:
        raise HTTPException(422, "lots is required for a derivative order")
    underlying = _fno_key(payload.underlying)
    lot_size = payload.lot_size or LOT_SIZES.get(underlying, 1)
    qty = payload.lots * lot_size
    product = "FUTURES" if payload.option_type == "FUT" else "OPTIONS"

    if payload.option_type == "FUT":
        price = payload.price or _underlying_spot(payload.underlying, db)
        source = ("caller-supplied futures price" if payload.price
                  else "live index spot (futures proxy)")
        if price is None:
            raise HTTPException(404, "No live spot to proxy this futures fill")
        err = None
    else:
        if not payload.strike:
            raise HTTPException(422, "strike is required for an option order")
        price, source, err = _option_premium(underlying, payload.option_type,
                                             payload.strike, payload.expiry)
        if err and payload.price:
            price, source = payload.price, "caller-supplied premium"
            err = None
        if err or price is None:
            raise HTTPException(404, err or "No live premium for this contract")

    value = price * qty
    charges = _fno_charges_one_side(payload.side, value, product)
    label = (f"{underlying} {payload.strike:g} {payload.option_type}"
             if payload.strike else f"{underlying} {payload.option_type}")
    o = SandboxOrder(
        symbol=label[:32], side=payload.side, quantity=qty, entry_price=price,
        note=payload.note, status="OPEN", asset_class="DERIVATIVE",
        underlying=underlying, option_type=payload.option_type,
        strike=payload.strike, expiry=payload.expiry, lot_size=lot_size,
        lots=payload.lots, charges=charges)
    db.add(o)
    db.commit()
    return {"id": o.id, "asset_class": "DERIVATIVE", "label": label,
            "filled_at": source, "fill_price": o.entry_price,
            "lots": payload.lots, "lot_size": lot_size, "quantity": qty,
            "charges": charges, "value": round(value, 2), "status": o.status,
            "source": source}


@router.post("/sandbox/orders/{oid}/close")
def close_order(oid: int, db: Session = Depends(get_db)):
    o = db.get(SandboxOrder, oid)
    if not o:
        raise HTTPException(404, "order not found")
    if o.status == "CLOSED":
        raise HTTPException(400, "order already closed")
    chain_cache: dict = {}
    mark, src = _mark_order(o, db, chain_cache)
    if mark is None:
        mark = o.entry_price
    qty = float(o.quantity or 0)
    value = float(mark) * qty
    if o.asset_class == "DERIVATIVE":
        add = _fno_charges_one_side("SELL" if o.side == "BUY" else "BUY", value,
                                    "FUTURES" if o.option_type == "FUT" else "OPTIONS")
    else:
        add = _equity_charges("SELL" if o.side == "BUY" else "BUY", value)
    o.exit_price = mark
    o.status = "CLOSED"
    o.closed_at = datetime.utcnow()
    o.charges = float(o.charges or 0) + add
    db.commit()
    gross = ((float(mark) - o.entry_price) if o.side == "BUY"
             else (o.entry_price - float(mark))) * qty
    return {"id": o.id, "closed_at": o.closed_at, "exit_price": float(mark),
            "mark_source": src, "gross_pnl": round(gross, 2),
            "exit_charges": add, "total_charges": round(o.charges, 2),
            "net_pnl": round(gross - o.charges, 2)}


@router.delete("/sandbox/orders/{oid}")
def delete_order(oid: int, db: Session = Depends(get_db)):
    o = db.get(SandboxOrder, oid)
    if not o:
        raise HTTPException(404, "order not found")
    db.delete(o)
    db.commit()
    return {"deleted": oid}


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------

def _watch_payload(w: WatchItem, db: Session) -> dict:
    kind = w.kind or "EQUITY"
    if kind == "INDEX":
        row = (db.query(Instrument)
                 .filter(Instrument.kind == "INDEX")
                 .filter(Instrument.symbol == w.symbol).one_or_none())
        if row is None:
            # Stored NSE name vs short key; fall back to a contains match.
            row = (db.query(Instrument)
                     .filter(Instrument.kind == "INDEX")
                     .filter(Instrument.symbol.like(f"%{w.symbol}%")).first())
    else:
        row = (db.query(Instrument)
                 .filter(Instrument.kind == "EQUITY", Instrument.symbol == w.symbol)
                 .one_or_none()) or (db.query(Instrument)
                 .filter(Instrument.kind == "ETF", Instrument.symbol == w.symbol)
                 .one_or_none())
    m = row.meta if row else {}
    href = w.href
    if not href and row:
        href = (f"/indices/{slug_for(row)}" if kind == "INDEX"
                else f"/stocks/{w.symbol}")
    last = m.get("lastPrice") if kind != "INDEX" else m.get("last")
    ch = m.get("changepct")
    return {"symbol": w.symbol, "name": row.name if row else w.symbol,
            "kind": kind, "last": last, "changepct": ch,
            "href": href or f"/stocks/{w.symbol}",
            "added_at": w.added_at.isoformat() if w.added_at else None}


@router.get("/watchlist")
def watchlist(db: Session = Depends(get_db)):
    rows = db.query(WatchItem).order_by(WatchItem.added_at.desc()).all()
    return {"items": [_watch_payload(w, db) for w in rows], "count": len(rows)}


@router.post("/watchlist")
def add_watch(payload: WatchIn = Body(...), db: Session = Depends(get_db)):
    symbol = payload.symbol.strip().upper()
    kind = payload.kind
    href = payload.href
    if not href:
        if kind == "INDEX":
            row = (db.query(Instrument)
                     .filter(Instrument.kind == "INDEX")
                     .filter(Instrument.symbol == symbol).one_or_none())
            if row is None:
                row = (db.query(Instrument)
                         .filter(Instrument.kind == "INDEX")
                         .filter(Instrument.symbol.like(f"%{symbol}%")).first())
            href = f"/indices/{slug_for(row)}" if row else None
        else:
            href = f"/stocks/{symbol}"
    exists = (db.query(WatchItem).filter_by(symbol=symbol).one_or_none())
    if exists:
        exists.kind = kind
        exists.href = href or exists.href
        db.commit()
        return {"already": True, "item": _watch_payload(exists, db)}
    w = WatchItem(symbol=symbol, kind=kind, href=href)
    db.add(w)
    db.commit()
    return {"added": symbol, "item": _watch_payload(w, db)}


@router.delete("/watchlist/{symbol}")
def remove_watch(symbol: str, db: Session = Depends(get_db)):
    w = (db.query(WatchItem)
           .filter(WatchItem.symbol == symbol.upper()).one_or_none())
    if not w:
        raise HTTPException(404, "not on the watchlist")
    db.delete(w)
    db.commit()
    return {"removed": symbol.upper()}


@router.get("/watchlist/check/{symbol}")
def check_watch(symbol: str, db: Session = Depends(get_db)):
    w = (db.query(WatchItem)
           .filter(WatchItem.symbol == symbol.upper()).one_or_none())
    return {"symbol": symbol.upper(), "watched": bool(w),
            "kind": w.kind if w else None}
