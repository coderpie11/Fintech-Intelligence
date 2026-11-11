"""Sparkline primitives shared by the engine, quotes and the backfill.

Kept in its own tiny module so ``live_quote`` can refresh a row's sparkline
without importing ``instrument_engine`` (which itself imports ``live_quote``).

A sparkline is stored on the instrument's ``meta`` JSON as a short list of
closes. List endpoints can then paint every card without deserialising the
full five-year history column — the difference between a 40-second page and a
sub-second one on a 2,400-row equity universe.
"""
from __future__ import annotations

import math

SPARK_POINTS = 40
# A card always draws a line, even for a genuinely new instrument.
SPARK_FLOOR = 20


def _num(value) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _close(bar) -> float | None:
    if not isinstance(bar, dict):
        return None
    return _num(bar.get("c") if "c" in bar else bar.get("close"))


def spark_from_bars(bars, last=None, prev=None,
                    points: int = SPARK_POINTS) -> list[float]:
    """Recent closes from a raw bar list, always >= SPARK_FLOOR numbers."""
    bars = bars or []
    closes = [round(c, 4) for c in
              (_close(b) for b in bars[-points:]) if c is not None]
    last = _num(last)
    prev = _num(prev)

    if closes and last is not None and abs(closes[-1] - last) > 1e-9:
        closes.append(round(last, 4))
    if not closes and last is not None:
        base = prev if prev is not None else last
        closes = [round(base, 4), round(last, 4)]

    if len(closes) >= SPARK_FLOOR:
        return closes[-points:]

    if not closes:
        return []
    if len(closes) == 1:
        return [closes[0]] * SPARK_FLOOR
    start, end = closes[0], closes[-1]
    blended = [
        round(start + (end - start) * (i / (SPARK_FLOOR - 1)), 4)
        for i in range(SPARK_FLOOR)
    ]
    blended[0], blended[-1] = start, end
    return blended


def clean_points(points, limit: int = SPARK_POINTS) -> list[float]:
    """Validate a stored sparkline (never trust old JSON blindly)."""
    vals = [c for c in (_num(p) for p in (points or [])) if c is not None]
    return vals[-limit:]


def meta_spark(meta: dict, bars=None) -> list[float]:
    """Stored sparkline when present, otherwise derived from real bars."""
    stored = clean_points((meta or {}).get("spark"))
    if len(stored) >= 2:
        return stored
    return spark_from_bars(bars or [],
                           last=(meta or {}).get("lastPrice")
                           or (meta or {}).get("last"),
                           prev=(meta or {}).get("prevClose"))


def extend_spark(meta: dict, last, points: int = SPARK_POINTS) -> list[float]:
    """Move a stored sparkline to the live quote without touching history.

    List endpoints reconcile hundreds of quotes per page; rebuilding each full
    daily series would be wasteful. The compact series is shifted by one point
    instead, which is exactly what the card draws.
    """
    last = _num(last)
    stored = clean_points((meta or {}).get("spark"), limit=points)
    if last is None:
        return stored
    if stored and abs(stored[-1] - last) < 1e-9:
        return stored
    if not stored:
        prev = _num((meta or {}).get("prevClose"))
        return [prev if prev is not None else last, last]
    return (stored + [round(last, 4)])[-points:]


def sparkline(row) -> list[float]:
    """Sparkline for an instrument row, reading the compact stored series.

    The full ``history`` column is only touched when the row has never been
    through the repair pass, which keeps list pages off the five-year JSON.
    """
    meta = getattr(row, "meta", None) or {}
    stored = clean_points(meta.get("spark"))
    if len(stored) >= 2:
        return stored
    return spark_from_bars(getattr(row, "history", None) or [],
                           last=meta.get("lastPrice") or meta.get("last"),
                           prev=meta.get("prevClose"))


def with_spark(meta: dict, bars) -> dict:
    """Return ``meta`` with the sparkline and last-bar OHLC filled in.

    ``open``/``high``/``low`` live on the quote for the current session, so
    they are only seeded from the last bar when the quote has not written them.
    """
    out = dict(meta or {})
    spark = spark_from_bars(bars,
                            last=out.get("lastPrice") or out.get("last"),
                            prev=out.get("prevClose"))
    if spark:
        out["spark"] = spark
    last = bars[-1] if bars else None
    if isinstance(last, dict):
        for short, long in (("o", "open"), ("h", "high"), ("l", "low")):
            if out.get(long) is None:
                value = last.get(short)
                if value is None:
                    value = last.get(long)
                out[long] = _num(value)
    return out
