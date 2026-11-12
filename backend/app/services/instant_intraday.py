"""Instant 1D session curves for every instrument.

During market hours a free Yahoo/NSE round-trip can hang for a minute on a
datacenter IP. A chart must never wait for it and must never be blank. This
module therefore has one rule:

    serve a deterministic session curve from stored data immediately, and let
    the real 5-minute candles replace it in the background.

The synthetic curve is anchored on real stored values — the session open at
09:15 IST and the latest price at the right edge — and is clamped inside the
day's stored high/low, so shape, scale and colour all agree with the header.
Nothing here invents a price level that is not already in the database.
"""
from __future__ import annotations

import datetime as dt
import math
import threading
import time

from app.data.adapters import yfinance_adapter as Y
from app.models.models import Instrument
from app.services import live_quote as LQ

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

# Real candles stay in memory for a minute; the first paint after a restart is
# synthesized from the stored snapshot and never waits on the provider.
CACHE_TTL = 60.0
MIN_POINTS = 30
CURVE_POINTS = 40
MAX_KEYS = 160

_CACHE: dict[str, dict] = {}
_guard = threading.Lock()
_inflight: set[str] = set()
_fetch_lock = threading.Lock()


def _num(value) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _session_bounds(now: dt.datetime | None = None) -> tuple[dt.datetime, dt.datetime]:
    """09:15 -> now (or 15:30) in IST for the relevant trading day."""
    now = (now or LQ.now_ist()).astimezone(IST)
    day = now.date()
    if now.weekday() >= 5 or now.time() < dt.time(9, 15):
        day -= dt.timedelta(days=1)
        while day.weekday() >= 5:
            day -= dt.timedelta(days=1)
        return (dt.datetime.combine(day, dt.time(9, 15), IST),
                dt.datetime.combine(day, dt.time(15, 30), IST))
    start = dt.datetime.combine(day, dt.time(9, 15), IST)
    end = min(now, dt.datetime.combine(day, dt.time(15, 30), IST))
    if end <= start:
        end = start + dt.timedelta(minutes=30)
    return start, end


def _phase(symbol: str) -> float:
    """Deterministic per-symbol phase so the curve is stable across requests."""
    seed = sum((i + 1) * ord(ch) for i, ch in enumerate(symbol.upper()))
    return (seed % 1000) / 1000.0 * 2 * math.pi


def synthetic_points(row: Instrument, count: int = CURVE_POINTS) -> list[dict]:
    """A 40-point session curve anchored on stored open/high/low/last."""
    meta = row.meta or {}
    last = _num(meta.get("lastPrice")) or _num(meta.get("last"))
    if last is None:
        hist = row.history or []
        for bar in reversed(hist):
            last = _num(bar.get("c") if "c" in bar else bar.get("close"))
            if last is not None:
                break
    if last is None:
        return []
    prev = _num(meta.get("prevClose")) or _num(meta.get("prev_close")) or last
    open_ = _num(meta.get("open")) or _num(meta.get("day_open")) or prev
    high = _num(meta.get("high")) or _num(meta.get("dayHigh"))
    low = _num(meta.get("low")) or _num(meta.get("dayLow"))

    if high is None:
        high = max(open_, last, prev)
    if low is None:
        low = min(open_, last, prev)
    if high <= low:
        span = max(abs(last) * 0.004, 0.01)
        high, low = last + span, last - span
    high = max(high, open_, last)
    low = min(low, open_, last)

    n = max(MIN_POINTS, int(count))
    start, end = _session_bounds()
    span = (high - low) / 2.0
    phase = _phase(row.symbol)
    hist = row.history or []

    def vol_pct() -> float:
        closes = [c for c in (_num((b or {}).get("c")) for b in hist[-22:])
                  if c is not None and c > 0]
        if len(closes) < 3:
            return 0.0
        rets = [abs(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes))
                if closes[i - 1]]
        return sum(rets) / len(rets) if rets else 0.0

    wiggle_scale = min(0.9, max(0.15, vol_pct() * 22.0))

    points: list[dict] = []
    prev_close = open_
    for i in range(n):
        t = i / (n - 1)
        base = open_ + (last - open_) * t
        envelope = math.sin(math.pi * t)
        wave = (0.62 * math.sin(2 * math.pi * 2.5 * t + phase)
                + 0.38 * math.sin(2 * math.pi * 5.0 * t + phase * 1.7))
        close = base + span * envelope * wave * wiggle_scale
        close = min(high, max(low, close))
        if i == 0:
            close = open_
        elif i == n - 1:
            close = last
        body = max(span * 0.05, abs(last) * 0.0004, 0.01)
        open_px = prev_close if i else open_
        points.append({
            "datetime": start.isoformat(),
            "date": start.strftime("%Y-%m-%d"),
            "time": "",
            "o": round(open_px, 2),
            "h": round(min(high, max(open_px, close) + body), 2),
            "l": round(max(low, min(open_px, close) - body), 2),
            "c": round(close, 2),
            "v": 0,
            "synthetic": True,
        })
        prev_close = close

    # Spread the real session clock over the curve (09:15 -> now/15:30).
    total = (end - start).total_seconds()
    for i, point in enumerate(points):
        stamp = start + dt.timedelta(seconds=total * i / (n - 1))
        point["datetime"] = stamp.isoformat()
        point["date"] = stamp.strftime("%Y-%m-%d")
        point["time"] = stamp.strftime("%H:%M")
    return points


def _payload(row: Instrument, ticker: str | None, interval: str,
             points: list[dict], synthetic: bool, source: str) -> dict:
    meta = row.meta or {}
    last = points[-1]["c"] if points else None
    prev = _num(meta.get("prevClose")) or _num(meta.get("prev_close"))
    if prev is None and points:
        prev = points[0].get("o") or last
    change = round(last - prev, 2) if (last is not None and prev) else None
    changepct = round((last / prev - 1) * 100, 2) if (last is not None and prev) else None
    session = (meta.get("live_asof")
               or (points[-1]["date"] if points else None))
    return {
        "ticker": ticker,
        "interval": interval,
        "session": session,
        "session_date": session,
        "source": source,
        "points": points,
        "point_count": len(points),
        "last": last,
        "prevClose": round(prev, 2) if prev else None,
        "change": change,
        "changepct": changepct,
        "asof": meta.get("live_time") or meta.get("live_asof"),
        "live_source": meta.get("live_source") or "Stored snapshot",
        "synthetic": synthetic,
        "note": ("A deterministic intraday curve drawn from the stored session "
                 "open, high, low and latest price while live candles warm in "
                 "the background. It is replaced by exchange candles on the "
                 "next refresh.") if synthetic else None,
    }


def _trim() -> None:
    if len(_CACHE) > MAX_KEYS:
        oldest = sorted(_CACHE.items(), key=lambda kv: kv[1]["at"])[:MAX_KEYS // 4]
        for key, _ in oldest:
            _CACHE.pop(key, None)


def _refresh_async(key: str, ticker: str | None, interval: str,
                   period: str) -> None:
    if not ticker:
        return
    with _guard:
        if key in _inflight:
            return
        _inflight.add(key)

    def _work():
        try:
            if not _fetch_lock.acquire(blocking=False):
                return
            try:
                data = Y.intraday(ticker, interval=interval, period=period)
            finally:
                _fetch_lock.release()
            points = [p for p in (data.get("points") or [])
                      if p.get("c") is not None]
            if len(points) >= MIN_POINTS:
                _CACHE[key] = {
                    "at": time.time(),
                    "points": points,
                    "meta": {"ticker": ticker,
                             "interval": data.get("interval", interval),
                             "session": data.get("session"),
                             "source": data.get("source") or "Yahoo Finance intraday",
                             "point_count": len(points), "synthetic": False},
                }
        except Exception:  # noqa: BLE001
            pass
        finally:
            _inflight.discard(key)

    threading.Thread(target=_work, daemon=True,
                     name=f"intraday-{key[-24:]}").start()


def get_intraday(db, row: Instrument, ticker: str | None,
                 interval: str = "2m", period: str = "5d") -> dict:
    """Sub-50 ms intraday payload: cache, else synthetic + background fetch."""
    key = f"{row.kind}:{row.symbol}:{interval}"
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - float(hit["at"]) < CACHE_TTL:
        points = hit.get("points") or []
        if len(points) >= MIN_POINTS:
            meta = hit.get("meta") or {}
            payload = _payload(row, ticker, meta.get("interval") or interval,
                               points, bool(meta.get("synthetic")),
                               meta.get("source") or "Yahoo Finance intraday")
            if meta.get("session"):
                payload["session"] = meta["session"]
                payload["session_date"] = meta["session"]
            if meta.get("synthetic"):
                # The provider fetch failed or is still running; keep retrying
                # in the background without ever blocking this request.
                _refresh_async(key, ticker, interval, period)
            return payload
    _refresh_async(key, ticker, interval, period)
    points = synthetic_points(row)
    payload = _payload(row, ticker, interval, points, True,
                       "Stored snapshot session curve (live candles warming)")
    _CACHE[key] = {"at": now, "points": points,
                   "meta": {"ticker": ticker, "interval": interval,
                            "source": "Stored snapshot session curve",
                            "synthetic": True}}
    _trim()
    return payload
