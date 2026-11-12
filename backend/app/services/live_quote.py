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
import os
import threading
import time
from typing import Iterable

from sqlalchemy.orm import Session, defer

from app.data.adapters import yfinance_adapter as Y
from app.models.models import Instrument
from app.services.spark import extend_spark, with_spark

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
QUOTE_SOURCE = "Yahoo Finance 5-minute candles (delayed)"

# A list card reuses a quote this recently instead of hitting the provider.
# Wide pages reconcile hundreds of symbols; a small TTL turns repeat views and
# multi-page browsing into zero network calls without ever serving a stale
# intraday print during a live session.
LIST_QUOTE_TTL = 90


def now_ist() -> dt.datetime:
    return dt.datetime.now(IST)


def market_open(now: dt.datetime | None = None) -> bool:
    """NSE/BSE regular session (Mon-Fri 09:15-15:30 IST)."""
    now = (now or now_ist()).astimezone(IST)
    if now.weekday() >= 5:
        return False
    return (9, 15) <= (now.hour, now.minute) <= (15, 30)


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
    fresh = [b for b in (fresh or []) if b.get("c") is not None]
    if not fresh:
        return False
    if not current:
        row.history = fresh
        meta["history_synced_date"] = today
        meta["history_points"] = len(fresh)
        row.meta = with_spark(meta, fresh)
        return True

    # A provider can answer with a one-point stub for an index it does not
    # really carry (NIFTY MIDCAP 100, NIFTY SMALLCAP 100). Replacing a real
    # five-year series with that stub wiped every ladder cell, so a short
    # answer may only *extend* the stored series, never shrink it.
    if len(fresh) + 5 < len(current):
        if str(fresh[-1].get("date")) > str(current[-1].get("date")):
            merged = (list(current) + [fresh[-1]])[-1300:]
            row.history = merged
            meta["history_synced_date"] = today
            meta["history_points"] = len(merged)
            row.meta = with_spark(meta, merged)
            return True
        meta["history_synced_date"] = today
        row.meta = meta
        return False

    if str(fresh[-1].get("date")) >= str(current[-1].get("date")):
        row.history = fresh
        meta["history_synced_date"] = today
        meta["history_points"] = len(fresh)
        row.meta = with_spark(meta, fresh)
        return True
    return False


def _finite(value):
    """Coerce NaN/Infinity to None so JSON responses can never contain them."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def reconcile_row(row: Instrument, quote: dict | None,
                  touch_history: bool = True) -> bool:
    """Write a quote into the ORM object. Returns True when anything changed.

    ``touch_history=False`` is used by wide list pages: the quote and the
    sparkline are updated, but the multi-year daily column is left for the
    detail/chart request that actually needs it.
    """
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
    if touch_history:
        hist = _apply_history(row, quote)
        row.history = hist
        row.meta = with_spark(meta, hist)
    else:
        meta["spark"] = extend_spark(meta, last)
        row.meta = meta
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


def live_quotes_enabled() -> bool:
    """Live provider quotes are on by default, including on Render.

    Python is pinned to 3.11.9 so the cp314 C-extension segfault cannot occur,
    and the adapter downloads one 25-ticker batch at a time to keep the
    512 MB instance inside its memory budget. On Render the deployed service
    must always serve live quotes, so a stale ``ENABLE_LIVE_QUOTES=false``
    from an old blueprint must not silently turn them off. Elsewhere a host
    can still opt out with ENABLE_LIVE_QUOTES=0.
    """
    if os.getenv("RENDER"):
        return True
    flag = os.getenv("ENABLE_LIVE_QUOTES")
    if flag is None:
        return True
    return flag.strip().lower() not in ("", "0", "false", "no")


def quote_is_current(row: Instrument, ttl: float = LIST_QUOTE_TTL,
                     closed_ok: bool = True) -> bool:
    """True when a list card can paint without a provider round-trip.

    Two rules, both universal:

    * a quote written within the list TTL is still the same session print;
    * outside 09:15-15:30 IST the stored quote *is* the final session print,
      so the provider adds nothing but latency.
    """
    meta = row.meta or {}
    if meta.get("lastPrice") is None and meta.get("last") is None:
        return False
    stamp = meta.get("fetched_at")
    if stamp:
        try:
            when = dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        except ValueError:
            when = None
        if when is not None:
            if when.tzinfo is None:
                when = when.replace(tzinfo=dt.timezone.utc)
            age = (dt.datetime.now(dt.timezone.utc) - when).total_seconds()
            if age <= ttl:
                return True
    return bool(closed_ok and not market_open())


# ------------------------------------------------------- background refresher
# A Render box has 0.1 vCPU. A synchronous Yahoo/NSE round-trip inside a request
# therefore starves Uvicorn and was the root cause of 50-120s page loads. Every
# priced row is now refreshed strictly off the request path, with one job at a
# time, a hard per-fetch timeout, a small ticker cap and a long cooldown.
REFRESH_MAX_TICKERS = 15
REFRESH_TIMEOUT = 3.5
REFRESH_COOLDOWN = 45.0
_refresh_guard = threading.Lock()
_refresh_lock = threading.Lock()
_refresh_last = [0.0]


def has_stored_price(row: Instrument) -> bool:
    """True when the SQLite snapshot already carries a usable quote."""
    meta = row.meta or {}
    last = meta.get("lastPrice") if row.kind != "INDEX" else meta.get("last")
    if _finite(last) is None:
        last = meta.get("lastPrice") if meta.get("lastPrice") is not None else meta.get("last")
    return _finite(last) is not None


def background_refresh(rows: Iterable[Instrument]) -> bool:
    """Queue at most one capped refresh job, never blocking the caller.

    Returns True when a job was actually started. A second request inside the
    cooldown window is a no-op: the stored snapshot is served instead.
    """
    if not live_quotes_enabled():
        return False
    keys: list[tuple[str, str]] = []
    for row in rows:
        if not has_stored_price(row):
            continue
        key = (row.kind, row.symbol)
        if key not in keys:
            keys.append(key)
    keys = keys[:REFRESH_MAX_TICKERS]
    if not keys:
        return False
    with _refresh_guard:
        now = time.time()
        if now - _refresh_last[0] < REFRESH_COOLDOWN:
            return False
        if not _refresh_lock.acquire(blocking=False):
            return False
        _refresh_last[0] = now

    def _worker():
        from app.core.db import SessionLocal

        db = SessionLocal()
        try:
            pairs = keys
            target = []
            for kind, symbol in pairs:
                row = (db.query(Instrument)
                         .options(defer(Instrument.history))
                         .filter(Instrument.kind == kind,
                                 Instrument.symbol == symbol).one_or_none())
                if row is not None:
                    target.append(row)
            if target:
                _refresh_rows_sync(db, target, commit=True, touch_history=False)
        except Exception:  # noqa: BLE001
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
        finally:
            db.close()
            _refresh_lock.release()

    threading.Thread(target=_worker, daemon=True, name="quote-refresh").start()
    return True


def list_rows(db: Session, rows: Iterable[Instrument], *, ttl: float = LIST_QUOTE_TTL,
              cap: int | None = None, touch_history: bool = False) -> dict[str, dict]:
    """Paint every card from SQLite and refresh the stale ones in the background.

    The return value stays empty by design: callers keep reading the stored
    ``meta`` they already have, so a request never waits for a provider.
    """
    rows = list(rows)
    stale = [r for r in rows if not quote_is_current(r, ttl)]
    if not stale:
        return {}
    if cap is not None and len(stale) > cap:
        stale = stale[:cap]
    background_refresh(stale)
    return {}


def _refresh_rows_sync(db: Session, rows: list[Instrument], commit: bool = True,
                       sync_history: bool = False,
                       touch_history: bool = True) -> dict[str, dict]:
    """Reconcile rows against one bounded batch download (worker/sync path)."""
    if not live_quotes_enabled():
        return {}
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
            changed = sync_history_row(row) or changed
    frames = Y.live_sessions_batch(list(tickers.values()), timeout=REFRESH_TIMEOUT)
    quotes: dict[str, dict] = {}
    for row in rows:
        ticker = tickers.get(row.symbol)
        if not ticker:
            continue
        quote = quote_from_sessions(frames.get(ticker))
        if quote:
            quotes[row.symbol] = quote
            changed = reconcile_row(row, quote,
                                    touch_history=touch_history) or changed
    if commit and changed:
        commit_with_retry(db)
    return quotes


def refresh_rows(db: Session, rows: Iterable[Instrument], commit: bool = True,
                 sync_history: bool = False,
                 touch_history: bool = True,
                 force_sync: bool = False) -> dict[str, dict]:
    """Never block on a provider for a row that already has a stored price.

    Priced rows go to :func:`background_refresh`; only genuinely unpriced rows
    (a symbol added after the seed) pay for a bounded synchronous download.
    """
    if not live_quotes_enabled():
        return {}
    rows = list(rows)
    if not force_sync:
        priced = [r for r in rows if has_stored_price(r)]
        rows = [r for r in rows if not has_stored_price(r)]
        if priced:
            background_refresh(priced)
        if not rows:
            return {}
    return _refresh_rows_sync(db, rows, commit=commit,
                              sync_history=sync_history,
                              touch_history=touch_history)


# ``sync_daily_history`` is the public name used by routes/seeds; keep the alias
# the worker calls so the module surface does not change.
sync_history_row = sync_daily_history


def refresh_one(db: Session, row: Instrument, commit: bool = True,
                sync_history: bool = False,
                force_sync: bool = False) -> dict | None:
    return refresh_rows(db, [row], commit=commit, sync_history=sync_history,
                        force_sync=force_sync).get(row.symbol)
