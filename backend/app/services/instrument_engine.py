"""Universal instrument readiness engine.

Every asset class on the platform (equities, indices, ETFs, REITs/InvITs,
commodities, bonds and mutual funds) funnels through this module before a
payload is built. One code path answers the same question everywhere:

    "give me a complete, current instrument — quote, 52-week range, history
     and a sparkline — and if anything is missing, fetch and persist it."

Nothing here is ticker-specific. A symbol either resolves to a provider
ticker, in which case it is repairable, or it is a curated/static instrument
(bonds) whose values are already stored.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Iterable

from sqlalchemy.orm import Session

from app.data.adapters import fund_adapter as F
from app.data.adapters import yfinance_adapter as Y
from app.models.models import FundScheme, Instrument
from app.services import live_quote as LQ
from app.services.spark import (SPARK_FLOOR, SPARK_POINTS, spark_from_bars,
                                sparkline as _sparkline, with_spark)

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

# A quote older than this during a live session is treated as stale.
STALE_SECONDS = 120
# Charts, sparklines and 52-week ranges all need a real series.
MIN_POINTS = 30
SPARK_POINTS = 40
# Fallback sparkline length when an instrument still has almost no history.
SPARK_FLOOR = 20
# Mutual fund NAVs update once a day; a 15-day gap means the series is broken.
NAV_STALE_DAYS = 15
NAV_MIN_POINTS = 60


# --------------------------------------------------------------- primitives
# The clock and the session calendar are shared with the quote layer so a list
# page and a detail page can never disagree about whether the market is live.
now_ist = LQ.now_ist
market_open = LQ.market_open


def num(value) -> float | None:
    """Finite float or None (never NaN/Infinity on the wire)."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def round_or_none(value, nd: int = 2):
    f = num(value)
    return None if f is None else round(f, nd)


def instrument_ticker(row: Instrument) -> str | None:
    """Provider ticker for any instrument row, without per-symbol specials."""
    ticker = LQ.ticker_for(row)
    if ticker:
        return ticker
    if row.kind == "COMMODITY":
        # The curated commodity universe carries the provider symbol; older
        # rows were seeded before it was mirrored into meta.
        from app.seed.universe import COMMODITIES

        slug = row.symbol.lower()
        for spec in COMMODITIES:
            if spec.get("slug") == slug:
                return spec.get("yahoo")
    if row.kind in ("EQUITY", "ETF", "REIT", "INVIT"):
        # NSE-listed units quote as <SYMBOL>.NS on the free feed.
        return f"{row.symbol}.NS"
    return None


def parse_stamp(value) -> dt.datetime | None:
    if not value:
        return None
    try:
        stamp = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=IST)


def quote_age_seconds(row: Instrument) -> float | None:
    meta = row.meta or {}
    stamp = parse_stamp(meta.get("live_time")) or parse_stamp(meta.get("fetched_at"))
    if stamp is None:
        return None
    return max(0.0, (now_ist() - stamp.astimezone(IST)).total_seconds())


def is_stale(row: Instrument, max_age: int = STALE_SECONDS) -> bool:
    meta = row.meta or {}
    last = num(meta.get("lastPrice")) or num(meta.get("last"))
    if last is None:
        return True
    age = quote_age_seconds(row)
    if age is None:
        return True
    # Outside a live session the last close is correct by definition.
    return market_open() and age > max_age


def _price_key(row: Instrument) -> str:
    return "last" if row.kind == "INDEX" else "lastPrice"


def bar_close(bar) -> float | None:
    """Close from a stored bar in either field convention."""
    if not isinstance(bar, dict):
        return None
    return num(bar.get("c") if "c" in bar else bar.get("close"))


def bar_field(bar, short: str, long: str) -> float | None:
    if not isinstance(bar, dict):
        return None
    return num(bar.get(short) if short in bar else bar.get(long))


def history_points(row: Instrument, limit: int | None = None) -> list[dict]:
    hist = row.history or []
    if limit is not None:
        hist = hist[-limit:]
    out = []
    for bar in hist:
        close = bar_close(bar)
        if close is None:
            continue
        out.append({
            "date": str(bar.get("date") or bar.get("datetime") or ""),
            "o": bar_field(bar, "o", "open"),
            "h": bar_field(bar, "h", "high"),
            "l": bar_field(bar, "l", "low"),
            "c": close,
            "v": bar_field(bar, "v", "volume") or 0,
        })
    return out


def metrics_complete(row: Instrument) -> bool:
    """True when a row already has every field a card or bar needs."""
    m = row.meta or {}
    last = num(m.get("lastPrice")) or num(m.get("last"))
    prev = num(m.get("prevClose")) or num(m.get("prev_close"))
    low = num(m.get("yearLow")) or num(m.get("week52_low"))
    high = num(m.get("yearHigh")) or num(m.get("week52_high"))
    chg = num(m.get("changepct"))
    return None not in (last, prev, low, high, chg)


# --------------------------------------------------------------- repair work
def _write(obj: Instrument, meta: dict) -> None:
    obj.meta = meta


def backfill_metrics(row: Instrument) -> bool:
    """Derive every price metric we can from stored data. No network.

    Covers the three field-naming conventions in the database (last/lastPrice,
    yearHigh/week52_high, changepct/change) so the same rule applies to equities,
    indices, ETFs, trusts and commodities.
    """
    meta = dict(row.meta or {})
    before = dict(meta)

    price_key = _price_key(row)
    last = num(meta.get(price_key)) or num(meta.get("lastPrice")) or num(meta.get("last"))
    raw = row.history or []
    if last is None and raw:
        last = bar_close(raw[-1])
    if last is None:
        return False

    prev = num(meta.get("prevClose")) or num(meta.get("prev_close"))
    if prev is None and len(raw) > 1:
        prev = bar_close(raw[-2])

    meta[price_key] = round(last, 4)
    # Mirror so both key conventions resolve regardless of caller.
    meta["last" if price_key == "lastPrice" else "lastPrice"] = round(last, 4)
    if prev is not None:
        meta["prevClose"] = round(prev, 4)
        change = num(meta.get("change"))
        if change is None:
            change = last - prev
        meta["change"] = round(change, 4)
        if num(meta.get("changepct")) is None and prev:
            meta["changepct"] = round((last / prev - 1) * 100, 4)

    # 52-week range: provider value when present, otherwise the real bars.
    low = num(meta.get("yearLow")) or num(meta.get("week52_low"))
    high = num(meta.get("yearHigh")) or num(meta.get("week52_high"))
    window = raw[-253:]
    if window:
        lows = [bar_field(b, "l", "low") for b in window]
        highs = [bar_field(b, "h", "high") for b in window]
        lows = [v for v in lows if v is not None]
        highs = [v for v in highs if v is not None]
        if lows:
            low = min([low, min(lows), last]) if low is not None else min(min(lows), last)
        if highs:
            high = max([high, max(highs), last]) if high is not None else max(max(highs), last)
    if low is not None:
        meta["yearLow"] = meta["week52_low"] = round(min(low, last), 4)
    if high is not None:
        meta["yearHigh"] = meta["week52_high"] = round(max(high, last), 4)

    meta = with_spark(meta, raw)
    if meta != before:
        _write(row, meta)
        row.updated_at = dt.datetime.utcnow()
        return True
    return False


def _index_archive_bars(row: Instrument) -> list[dict]:
    """Official NSE daily index series for an index row, from the cached archive.

    The free equity feed only carries a handful of indices and answers the rest
    with a one-point stub. NSE publishes every index level daily, and the
    seeder keeps a five-year local copy, so the archive is the authoritative
    source for *any* index row — matched by normalised name, never by ticker.
    """
    try:
        from app.data.adapters import nse_adapter as N
        from app.seed.universe import INDICES
    except Exception:  # noqa: BLE001
        return []
    name = next((s["nse"] for s in INDICES
                 if N._norm(s["nse"]) == N._norm(row.symbol)), None)
    if not name:
        return []
    try:
        series = N.index_history_snapshots([name], years=5)
    except Exception:  # noqa: BLE001
        return []
    return [b for b in (series.get(name) or []) if b.get("c") is not None]


def sync_history(row: Instrument, period: str = "5y") -> bool:
    """Replace/extend the stored daily series from the provider.

    An NSE symbol that returns a stub series is retried on the BSE listing of
    the same name. That is a venue fallback, not a per-ticker special: it is
    the same rule for every company and every ETF/trust.
    """
    ticker = instrument_ticker(row)
    current = history_points(row)
    current_last = str(current[-1]["date"]) if current else ""
    best: list[dict] = []
    best_ticker = ticker or ""

    if row.kind == "INDEX":
        archive = _index_archive_bars(row)
        if archive and str(archive[-1].get("date") or "") >= current_last:
            best = archive

    if not ticker and not best:
        return False
    candidates = [ticker] if ticker else []
    if ticker and ticker.upper().endswith(".NS"):
        candidates.append(ticker[:-3] + ".BO")
    for candidate in candidates:
        try:
            fresh = Y.history(candidate, period)
        except Exception:  # noqa: BLE001
            continue
        if not fresh:
            continue
        last_date = str(fresh[-1].get("date") or "")
        if current_last and last_date < current_last:
            continue
        if len(fresh) > len(best):
            best, best_ticker = fresh, candidate
    if not best:
        return False
    if len(best) < max(len(current), 2) and current_last:
        return False
    row.history = best[-1300:]
    meta = dict(row.meta or {})
    meta["history_synced_date"] = str(now_ist().date())
    meta["history_points"] = len(best)
    if row.kind == "COMMODITY":
        meta.setdefault("yahoo", ticker)
    elif best_ticker != ticker:
        meta["yahoo"] = best_ticker
    meta = with_spark(meta, row.history)
    _write(row, meta)
    row.updated_at = dt.datetime.utcnow()
    return True


def refresh_quote(db: Session, row: Instrument, commit: bool = False) -> bool:
    """Pull one live quote through the shared reconciler."""
    if not instrument_ticker(row):
        return False
    try:
        quote = LQ.refresh_one(db, row, commit=False)
    except Exception:  # noqa: BLE001
        return False
    if not quote:
        return False
    if commit:
        LQ.commit_with_retry(db)
    return True


def ensure_instrument_ready(
    db: Session,
    row: Instrument,
    *,
    need_history: bool | None = None,
    refresh: bool | None = None,
    min_points: int = MIN_POINTS,
    max_age: int = STALE_SECONDS,
    persist: bool = True,
) -> Instrument:
    """Guarantee a complete instrument payload for any asset class.

    Cheap metric repair always runs. History and the live quote are only
    touched when the stored data is actually missing or stale, so a warm row
    costs no network calls.
    """
    changed = backfill_metrics(row)

    hist_len = len(history_points(row))
    if need_history is None:
        need_history = hist_len < min_points
    if need_history:
        changed = sync_history(row) or changed

    if refresh is None:
        refresh = is_stale(row, max_age) or len(history_points(row)) < 2
    if refresh:
        changed = refresh_quote(db, row, commit=False) or changed
        changed = backfill_metrics(row) or changed

    if persist and changed:
        LQ.commit_with_retry(db)
    return row


def ensure_many(db: Session, rows: Iterable[Instrument], *,
                persist: bool = True) -> bool:
    """Metric-only pass over a list page: never blocks on the network.

    Rows that already carry a complete quote and 52-week range are skipped, so
    a warm page costs a few dict lookups per row instead of a JSON re-parse.
    """
    changed = False
    for row in rows:
        if metrics_complete(row):
            # Every card must carry a sparkline; repair only the rare row that
            # predates the compact series (loads its history once).
            meta = row.meta or {}
            if not meta.get("spark"):
                fresh = with_spark(meta, row.history or [])
                if fresh != meta:
                    _write(row, fresh)
                    changed = True
            continue
        changed = backfill_metrics(row) or changed
    if persist and changed:
        LQ.commit_with_retry(db)
    return changed


# --------------------------------------------------------------- sparkline
# The implementation lives in app.services.spark so the quote layer can refresh
# a row sparkline without importing this module (which imports live_quote).
spark_from_bars = spark_from_bars
sparkline = _sparkline


# ------------------------------------------------------------ performance maths
def window_return(hist: list[dict], sessions: int | None) -> float | None:
    """Return over the last `sessions` bars (None = whole series).

    The window is anchored on the closest stored session, so a holiday or a
    missing print can never blank out a ladder cell.
    """
    closes = [b["c"] for b in hist if b.get("c") is not None]
    if len(closes) < 2:
        return None
    end = closes[-1]
    if sessions is None or sessions >= len(closes):
        start = closes[0]
    else:
        start = closes[-sessions - 1]
    if not start:
        return None
    return round((end / start - 1) * 100, 2)


def ladder_from_closes(closes: Iterable[float]) -> dict:
    """1W–5Y ladder from any close series, in the platform's key convention.

    Simple returns for one year or less; annualised (CAGR) beyond one year,
    which is the same convention every desk uses. A window longer than the
    stored series degrades to the full series instead of blanking out.
    """
    vals = [c for c in (num(v) for v in closes) if c is not None]
    keys = ("1w", "1m", "3m", "6m", "1y", "3y", "5y")
    if len(vals) < 2:
        return {k: None for k in keys}

    def simple(n: int):
        if len(vals) <= n:
            return None
        start, end = vals[-1 - n], vals[-1]
        return round((end / start - 1) * 100, 2) if start else None

    def annual(n: int):
        n = min(n, len(vals) - 1)
        start, end = vals[-1 - n], vals[-1]
        years = n / 252
        if not start or start <= 0 or years <= 0:
            return None
        return round(((end / start) ** (1 / years) - 1) * 100, 2)

    return {
        "1w": simple(5), "1m": simple(21), "3m": simple(63),
        "6m": simple(126), "1y": simple(252),
        "3y": annual(756), "5y": annual(min(len(vals) - 1, 1260)),
    }


def performance_ladder(row: Instrument) -> dict:
    """1W/1M/3M/6M/1Y/3Y/5Y returns for any instrument with a series."""
    hist = history_points(row)
    return ladder_from_closes(b["c"] for b in hist)


# ------------------------------------------------------------------- funds
def ensure_fund_ready(db: Session, scheme: FundScheme, persist: bool = True) -> FundScheme:
    """Fetch a fund's NAV series when it is missing or stale (any scheme)."""
    navs = scheme.navs or []
    fresh_enough = len(navs) >= NAV_MIN_POINTS
    if fresh_enough:
        try:
            last_day = dt.date.fromisoformat(str(navs[-1].get("date")))
            fresh_enough = (now_ist().date() - last_day).days <= NAV_STALE_DAYS
        except (TypeError, ValueError, KeyError):
            fresh_enough = False
    if fresh_enough:
        return scheme
    try:
        series = F.nav_series(scheme.code)
    except Exception:  # noqa: BLE001
        return scheme
    if not series:
        return scheme
    scheme.navs = series
    if persist:
        try:
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
    return scheme


# ------------------------------------------------------- intraday stitching
def stitch_live_point(points: list[dict], meta: dict | None) -> list[dict]:
    """Make the final 1D point the live quote, not the last delayed candle."""
    meta = meta or {}
    last = num(meta.get("lastPrice")) or num(meta.get("last"))
    if last is None or not points:
        return points
    stamp = meta.get("live_time") or meta.get("live_asof")
    out = list(points)
    tail = out[-1]
    prev_close = num(tail.get("c"))
    if prev_close is not None and abs(prev_close - last) < 1e-9:
        return out
    out.append({
        "date": str(stamp or tail.get("date") or ""),
        "datetime": str(stamp or ""),
        "time": "",
        "o": prev_close,
        "h": max(last, prev_close or last),
        "l": min(last, prev_close or last),
        "c": last,
        "v": num(meta.get("volume")) or 0,
        "live": True,
    })
    return out
