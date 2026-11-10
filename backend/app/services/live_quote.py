"""Live quote reconciliation.

The seeded ``instruments.meta`` snapshot can be days old while the chart keeps
fetching fresh candles. This module is the single place that turns the latest
Yahoo session into a quote, writes it back to ``instruments.meta`` (and to the
last daily history bar), and guarantees the header and chart share one source.

Design notes
------------
* 15-second TTL lives in :mod:`yfinance_adapter` (per ticker and per batch).
* The same session frame feeds both ``/intraday`` and the header quote, so the
  final candle and the big price are identical, not merely close.
* ``change`` and ``changepct`` are always recomputed against the previous
  session's close — never against the session open, which used to make the
  header disagree with every other market site.
* Writes are best-effort: a busy SQLite writer must never take a page down.
"""
from __future__ import annotations

import datetime as dt
import math
import time
from typing import Iterable

from sqlalchemy.orm import Session

from app.data.adapters import yfinance_adapter as Y
from app.models.models import Instrument

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
QUOTE_SOURCE = "Yahoo Finance 5-minute candles (delayed)"


def _today_ist() -> dt.date:
    return dt.datetime.now(IST).date()


def latest_completed_session(now: dt.datetime | None = None) -> dt.date:
    """Most recent weekday whose 15:30 IST session has closed.

    Used by the seeders and market-pulse fallback so a snapshot taken before
    the close never labels today's incomplete session as final.
    """
    now = now or dt.datetime.now(IST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=IST)
    day = now.astimezone(IST).date()
    if now.astimezone(IST).time() < dt.time(15, 30):
        day -= dt.timedelta(days=1)
    while day.weekday() >= 5:
        day -= dt.timedelta(days=1)
    return day


def ticker_for(row: Instrument) -> str | None:
    """Yahoo ticker for an instrument row (equity, index or other)."""
    meta = row.meta or {}
    if row.kind == "INDEX":
        return meta.get("yahoo") or None
    if row.kind == "EQUITY":
        return Y._ticker(f"{row.symbol}.NS")
    return meta.get("yahoo") or None


def _asof_label(ts: str | None, session: str) -> str:
    if ts:
        try:
            stamp = dt.datetime.fromisoformat(ts)
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=IST)
            stamp = stamp.astimezone(IST)
            return stamp.strftime("%d %b %Y, %H:%M IST")
        except (TypeError, ValueError):
            pass
    try:
        day = dt.date.fromisoformat(session)
        return day.strftime("%d %b %Y") + " · 15:30 IST"
    except (TypeError, ValueError):
        return session


def quote_from_sessions(sessions: list[dict] | None) -> dict | None:
    """Build a quote from ordered session buckets (oldest first)."""
    if not sessions:
        return None
    latest = sessions[-1]
    rows = latest.get("rows") or []
    if not rows:
        return None
    last = float(rows[-1]["c"])
    prev_rows = sessions[-2].get("rows") if len(sessions) > 1 else None
    prev = None
    if prev_rows:
        try:
            prev = float(prev_rows[-1]["c"])
        except (TypeError, ValueError):
            prev = None
    if prev is None:
        try:
            prev = float(rows[0].get("o"))
        except (TypeError, ValueError):
            prev = last

    opens = [r["o"] for r in rows if r.get("o") is not None]
    highs = [r["h"] for r in rows if r.get("h") is not None]
    lows = [r["l"] for r in rows if r.get("l") is not None]
    volume = sum(int(r.get("v") or 0) for r in rows)

    change = round(last - prev, 2) if prev else None
    changepct = round((last / prev - 1) * 100, 2) if prev else None
    stamp = rows[-1].get("datetime")
    session = latest.get("date") or (rows[-1].get("date") or "")
    return {
        "lastPrice": round(last, 2),
        "prevClose": round(prev, 2) if prev else None,
        "open": round(float(opens[0]), 2) if opens else None,
        "high": round(float(max(highs)), 2) if highs else None,
        "low": round(float(min(lows)), 2) if lows else None,
        "volume": volume,
        "change": change,
        "changepct": changepct,
        "session": session,
        "asof": _asof_label(stamp, session),
        "source": QUOTE_SOURCE,
        "is_today": session == str(_today_ist()),
    }


def _apply_history(row: Instrument, quote: dict) -> list[dict]:
    """Make the last daily bar agree with the live session."""
    hist = list(row.history or [])
    bar = {
        "date": quote["session"],
        "o": quote.get("open"),
        "h": quote.get("high"),
        "l": quote.get("low"),
        "c": quote.get("lastPrice"),
        "v": quote.get("volume") or 0,
    }
    if hist and hist[-1].get("date") == quote["session"]:
        # Keep an observed daily open if the intraday window did not see 09:15.
        bar["o"] = hist[-1].get("o") or bar["o"]
        hist[-1] = bar
    elif not hist or quote["session"] > str(hist[-1].get("date") or ""):
        hist.append(bar)
        hist = hist[-1300:]
    return hist


def sync_daily_history(row: Instrument) -> bool:
    """Refresh a 5-year daily series at most once per IST day.

    This fills any gap between the last seeded bar and the live session (for
    example the 2 Nov bar) so the 5Y chart is continuous, not just correct at
    its final point.
    """
    ticker = ticker_for(row)
    if not ticker:
        return False
    meta = dict(row.meta or {})
    today = str(_today_ist())
    if meta.get("history_synced_date") == today:
        return False
    try:
        fresh = Y.history(ticker, "5y")
    except Exception:  # noqa: BLE001
        return False
    if not fresh:
        return False
    current = row.history or []
    if not current or str(fresh[-1].get("date")) >= str(current[-1].get("date")):
        row.history = fresh
        meta["history_synced_date"] = today
        row.meta = meta
        return True
    return False


def _finite(value):
    """Coerce NaN/Infinity to None so JSON responses can never contain them."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def reconcile_row(row: Instrument, quote: dict | None) -> bool:
    """Write a quote into the ORM object. Returns True when anything changed."""
    if not quote:
        return False
    last = _finite(quote.get("lastPrice"))
    if last is None:
        return False
    quote = {**quote, "lastPrice": last}
    for key in ("prevClose", "open", "high", "low", "change", "changepct"):
        quote[key] = _finite(quote.get(key))
    meta = dict(row.meta or {})
    is_index = row.kind == "INDEX"
    price_key = "last" if is_index else "lastPrice"
    before = (meta.get(price_key), meta.get("changepct"), meta.get("live_asof"))
    meta[price_key] = quote["lastPrice"]
    meta["prevClose"] = quote.get("prevClose")
    meta["open"] = quote.get("open")
    meta["high"] = quote.get("high")
    meta["low"] = quote.get("low")
    meta["change"] = quote.get("change")
    meta["changepct"] = quote.get("changepct")
    meta["live_asof"] = quote.get("session")
    meta["live_time"] = quote.get("asof")
    meta["live_source"] = quote.get("source")
    meta["fetched_at"] = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    if not is_index:
        meta["asof"] = quote.get("session")
    row.meta = meta
    row.history = _apply_history(row, quote)
    after = (meta.get(price_key), meta.get("changepct"), meta.get("live_asof"))
    return before != after


def commit_with_retry(db: Session, attempts: int = 3, delay: float = 0.25) -> bool:
    """Best-effort persistence on a single-writer SQLite database."""
    for attempt in range(attempts):
        try:
            db.commit()
            return True
        except Exception:  # noqa: BLE001
            db.rollback()
            if attempt == attempts - 1:
                return False
            time.sleep(delay)
    return False


def refresh_rows(db: Session, rows: Iterable[Instrument], commit: bool = True,
                 sync_history: bool = False) -> dict[str, dict]:
    """Reconcile a set of rows against one batch live download."""
    rows = list(rows)
    tickers: dict[str, str] = {}
    for row in rows:
        ticker = ticker_for(row)
        if ticker:
            tickers[row.symbol] = ticker
    if not tickers:
        return {}
    changed = False
    if sync_history:
        for row in rows:
            changed = sync_daily_history(row) or changed
    frames = Y.live_sessions_batch(list(tickers.values()))
    quotes: dict[str, dict] = {}
    for row in rows:
        ticker = tickers.get(row.symbol)
        if not ticker:
            continue
        quote = quote_from_sessions(frames.get(ticker))
        if quote:
            quotes[row.symbol] = quote
            changed = reconcile_row(row, quote) or changed
    if commit and changed:
        commit_with_retry(db)
    return quotes


def refresh_one(db: Session, row: Instrument, commit: bool = True,
                sync_history: bool = False) -> dict | None:
    return refresh_rows(db, [row], commit=commit,
                        sync_history=sync_history).get(row.symbol)
