"""Universal batch repair for the local market database.

Run from ``backend/``:

    python -m app.seed.backfill                # instruments + latest fund NAVs
    python -m app.seed.backfill --stage instruments
    python -m app.seed.backfill --funds 2500   # also fetch full NAV histories

The instrument stage sweeps every EQUITY / INDEX / ETF / REIT / INVIT /
COMMODITY row through one chunked ``yfinance.download`` call, then writes the
quote, the 52-week range and a five-year daily series back into the JSON
columns. Nothing here names an individual ticker: the provider ticker is
resolved by the same helper the live routes use.

The fund stage first applies the bulk latest-NAV dump to every scheme (one
HTTP call, no per-scheme requests), then optionally fetches full NAV histories
for the most recently priced schemes. Any fund that is still missing history
is repaired on demand by ``instrument_engine.ensure_fund_ready``.
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import datetime as dt
import math
import time
from typing import Iterable

import pandas as pd

from app.core.db import SessionLocal
from app.data.adapters import fund_adapter as F
from app.data.adapters import yfinance_adapter as Y
from app.models.models import FundScheme, Instrument
from app.services import instrument_engine as IE
from app.services import live_quote as LQ
from app.services.spark import with_spark

KINDS = ("EQUITY", "INDEX", "ETF", "REIT", "INVIT", "COMMODITY")
FIELDS = ("Open", "High", "Low", "Close", "Volume")


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _bars_from_frame(sub: pd.DataFrame) -> list[dict]:
    """Turn one ticker's OHLCV frame into the stored bar shape."""
    if sub is None or getattr(sub, "empty", True):
        return []
    bars: list[dict] = []
    for idx, row in sub.iterrows():
        close = _num(row.get("Close"))
        if close is None:
            continue
        try:
            date = idx.strftime("%Y-%m-%d")
        except AttributeError:
            date = str(idx)[:10]
        volume = _num(row.get("Volume"))
        bars.append({
            "date": date,
            "o": _num(row.get("Open")),
            "h": _num(row.get("High")),
            "l": _num(row.get("Low")),
            "c": close,
            "v": int(volume) if volume else 0,
        })
    return bars


def _frame_for(df: pd.DataFrame | None, ticker: str) -> pd.DataFrame | None:
    if df is None or getattr(df, "empty", True):
        return None
    if isinstance(df.columns, pd.MultiIndex):
        level = df.columns.get_level_values(0)
        if ticker not in set(level):
            return None
        return df[ticker]
    # A single-ticker frame: columns are plain Price fields.
    if not set(df.columns) & set(FIELDS):
        return None
    return df


def _apply_bars(row: Instrument, bars: list[dict]) -> bool:
    """Persist a fresh series and every metric derivable from it."""
    if len(bars) < 2:
        return False
    bars = bars[-1300:]
    closes = [b["c"] for b in bars if b["c"] is not None]
    if len(closes) < 2:
        return False
    last, prev = closes[-1], closes[-2]
    window = bars[-253:]
    highs = [b["h"] if b["h"] is not None else b["c"] for b in window]
    lows = [b["l"] if b["l"] is not None else b["c"] for b in window]
    high = max([last] + highs)
    low = min([last] + lows)
    change = last - prev
    changepct = (last / prev - 1) * 100 if prev else None

    meta = dict(row.meta or {})
    meta["lastPrice"] = round(last, 4)
    meta["last"] = round(last, 4)
    meta["prevClose"] = round(prev, 4)
    meta["change"] = round(change, 4)
    if changepct is not None:
        meta["changepct"] = round(changepct, 4)
    meta["yearHigh"] = meta["week52_high"] = round(high, 4)
    meta["yearLow"] = meta["week52_low"] = round(low, 4)
    meta["history_synced_date"] = str(dt.date.today())
    meta["history_points"] = len(bars)
    meta["history_source"] = "Yahoo Finance daily candles (5Y)"

    row.meta = with_spark(meta, bars)
    row.history = bars
    return True


def backfill_instruments(chunk: int = 50, pause: float = 0.3,
                         limit: int = 0) -> dict:
    db = SessionLocal()
    stats = {"rows": 0, "updated": 0, "no_ticker": 0, "failed": []}
    try:
        rows = db.query(Instrument).filter(Instrument.kind.in_(KINDS)).all()
        todo: list[tuple[Instrument, str]] = []
        for r in rows:
            ticker = IE.instrument_ticker(r)
            if not ticker:
                stats["no_ticker"] += 1
                continue
            todo.append((r, ticker))
        stats["rows"] = len(todo)
        total = len(todo)
        if limit > 0:
            todo = todo[:limit]
            total = len(todo)
            print(f"limit: only the first {total} tickers", flush=True)
        print(f"instruments: {total} tickers, chunk={chunk}", flush=True)

        for start in range(0, total, chunk):
            batch = todo[start:start + chunk]
            tickers = [t for _, t in batch]
            try:
                df = Y.yf.download(
                    tickers, period="5y", interval="1d", group_by="ticker",
                    auto_adjust=False, threads=True, progress=False,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  chunk {start // chunk + 1}: download failed ({exc})",
                      flush=True)
                df = None
            for row, ticker in batch:
                bars = _bars_from_frame(_frame_for(df, ticker))
                if _apply_bars(row, bars):
                    stats["updated"] += 1
                else:
                    stats["failed"].append(ticker)
            try:
                LQ.commit_with_retry(db)
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                print(f"  chunk {start // chunk + 1}: commit failed ({exc})",
                      flush=True)
            done = min(start + chunk, total)
            print(f"  {done}/{total} processed · {stats['updated']} updated",
                  flush=True)
            if pause:
                time.sleep(pause)

        # One-by-one retry for tickers the batched call missed.
        retry = stats["failed"]
        stats["failed"] = []
        if retry:
            print(f"retrying {len(retry)} tickers individually", flush=True)
        by_ticker = {t: r for r, t in todo}
        for ticker in retry:
            row = by_ticker.get(ticker)
            if row is None:
                continue
            try:
                bars = Y.history(ticker, "5y")
            except Exception:  # noqa: BLE001
                bars = []
            if _apply_bars(row, bars):
                stats["updated"] += 1
            else:
                stats["failed"].append(ticker)
            try:
                LQ.commit_with_retry(db)
            except Exception:  # noqa: BLE001
                db.rollback()
        print(f"instruments done: {stats['updated']}/{total} repaired, "
              f"{len(stats['failed'])} still missing "
              f"({stats['no_ticker']} without a provider ticker)", flush=True)
        return stats
    finally:
        db.close()


def _iso(value: str) -> str:
    try:
        dd, mm, yy = (value or "").split("-")
        return f"{yy}-{mm}-{dd}"
    except ValueError:
        return value


def seed_latest_fund_navs() -> int:
    """One bulk call: give every scheme its latest published NAV."""
    try:
        latest = F.latest_navs()
    except Exception as exc:  # noqa: BLE001
        print(f"fund latest dump failed: {exc}", flush=True)
        return 0
    if not latest:
        return 0
    dmap = {str(x.get("schemeCode")): x for x in latest}
    db = SessionLocal()
    written = 0
    try:
        rows = (db.query(FundScheme)
                  .filter(FundScheme.navs.is_(None)).all())
        print(f"fund latest: {len(rows)} schemes without NAV, "
              f"{len(dmap)} in the bulk dump", flush=True)
        for i, rec in enumerate(rows, 1):
            item = dmap.get(rec.code)
            if not item:
                continue
            nav = _num(item.get("nav"))
            if nav is None:
                continue
            rec.navs = [{"date": _iso(str(item.get("date") or "")), "nav": nav}]
            written += 1
            if i % 2000 == 0:
                db.commit()
                print(f"  {i}/{len(rows)} schemes · {written} written",
                      flush=True)
        db.commit()
    finally:
        db.close()
    print(f"fund latest done: {written} schemes now carry a NAV", flush=True)
    return written


def enrich_fund_histories(limit: int = 0, workers: int = 8,
                          min_points: int = 60) -> int:
    """Fetch full NAV series for recently-priced schemes (bounded)."""
    if limit == 0:
        return 0
    try:
        latest = F.latest_navs()
    except Exception:  # noqa: BLE001
        latest = []
    recent = {}
    cutoff = dt.date.today() - dt.timedelta(days=45)
    for item in latest:
        try:
            day = dt.date.fromisoformat(_iso(str(item.get("date") or "")))
        except ValueError:
            continue
        if day >= cutoff:
            recent[str(item.get("schemeCode"))] = day.isoformat()

    db = SessionLocal()
    try:
        rows = db.query(FundScheme).all()
        candidates = []
        for rec in rows:
            if len(rec.navs or []) >= min_points:
                continue
            stamp = recent.get(rec.code)
            if stamp:
                candidates.append((stamp, rec.code))
        candidates.sort(reverse=True)
        if limit > 0:
            candidates = candidates[:limit]
        codes = [c for _, c in candidates]
        print(f"fund histories: {len(codes)} active schemes to enrich",
              flush=True)
        if not codes:
            return 0

        def fetch(code: str):
            try:
                return code, F.nav_series(code)
            except Exception:  # noqa: BLE001
                return code, []

        by_code = {r.code: r for r in rows}
        written = 0
        with futures.ThreadPoolExecutor(max_workers=workers) as pool:
            for i, (code, series) in enumerate(
                    pool.map(fetch, codes), 1):
                rec = by_code.get(code)
                if rec is not None and len(series) >= min_points:
                    rec.navs = series[-1400:]
                    written += 1
                if i % 100 == 0:
                    try:
                        db.commit()
                    except Exception:  # noqa: BLE001
                        db.rollback()
                    print(f"  {i}/{len(codes)} fetched · {written} stored",
                          flush=True)
        db.commit()
        print(f"fund histories done: {written} schemes enriched", flush=True)
        return written
    finally:
        db.close()


def repair_short_histories(min_points: int = 60) -> dict:
    """Fetch full series for rows the batch left suspiciously short.

    A recently listed company legitimately has fewer bars than 60; this pass
    still retries it once (Yahoo returns what exists) and then accepts the
    honest length. Index rows are skipped — they are repaired by the main
    stage and their history is already long.
    """
    db = SessionLocal()
    stats = {"checked": 0, "repaired": 0, "failed": 0}
    try:
        rows = (db.query(Instrument)
                  .filter(Instrument.kind.in_(("EQUITY", "ETF", "REIT",
                                               "INVIT", "COMMODITY"))).all())
        todo = [r for r in rows if len(r.history or []) < min_points]
        print(f"short histories: {len(todo)} rows to retry", flush=True)
        for i, row in enumerate(todo, 1):
            stats["checked"] += 1
            before = len(row.history or [])
            if IE.sync_history(row):
                after = len(row.history or [])
                if after > before:
                    stats["repaired"] += 1
                print(f"  {row.symbol:16} {before:>4} -> {after:>4} bars",
                      flush=True)
            else:
                stats["failed"] += 1
            if i % 25 == 0:
                try:
                    LQ.commit_with_retry(db)
                except Exception:  # noqa: BLE001
                    db.rollback()
        LQ.commit_with_retry(db)
        print(f"short histories done: {stats['repaired']} lengthened, "
              f"{stats['failed']} unchanged", flush=True)
        return stats
    finally:
        db.close()


def seed_spark_meta() -> dict:
    """Store the compact sparkline + last-bar OHLC on every instrument.

    This is a one-off preparation pass so list pages never deserialise the
    five-year history column just to draw a 40-point line.
    """
    db = SessionLocal()
    stats = {"rows": 0, "updated": 0}
    try:
        rows = db.query(Instrument).all()
        stats["rows"] = len(rows)
        for i, row in enumerate(rows, 1):
            meta = dict(row.meta or {})
            fresh = with_spark(meta, row.history or [])
            if fresh != meta:
                row.meta = fresh
                row.updated_at = dt.datetime.utcnow()
                stats["updated"] += 1
            if i % 250 == 0:
                LQ.commit_with_retry(db)
                print(f"  spark meta {i}/{len(rows)} · {stats['updated']} updated",
                      flush=True)
        LQ.commit_with_retry(db)
        print(f"spark meta done: {stats['updated']}/{stats['rows']} rows updated",
              flush=True)
        return stats
    finally:
        db.close()


def repair_index_histories() -> dict:
    """Rebuild index series from NSE's official daily index archive.

    The free equity feed only carries a couple of the 18 tracked indices; the
    rest return a one-point stub. NSE publishes a daily ``ind_close_all`` CSV
    for every index, and the seeder already caches a five-year local copy, so
    any index row whose stored series is shorter can be rebuilt from that same
    archive. Nothing here names an index: the match is by normalised name.
    """
    from app.seed.universe import INDICES
    from app.data.adapters import nse_adapter as N

    db = SessionLocal()
    stats = {"indices": 0, "repaired": 0, "bars_added": 0}
    try:
        rows = db.query(Instrument).filter(Instrument.kind == "INDEX").all()
        by_name = {N._norm(spec["nse"]): spec["nse"] for spec in INDICES}
        names = [spec["nse"] for spec in INDICES]
        print(f"index archive: rebuilding {len(names)} names", flush=True)
        series = N.index_history_snapshots(names, years=5)
        for row in rows:
            spec = next((s for s in INDICES
                         if N._norm(s["nse"]) == N._norm(row.symbol)), None)
            if not spec:
                continue
            stats["indices"] += 1
            bars = series.get(spec["nse"]) or []
            have = len(row.history or [])
            if len(bars) <= have:
                continue
            added = len(bars) - have
            if _apply_bars(row, bars):
                stats["repaired"] += 1
                stats["bars_added"] += added
                print(f"  {row.symbol:28} {have:>4} -> {len(bars):>4} bars",
                      flush=True)
        LQ.commit_with_retry(db)
        print(f"index archive done: {stats['repaired']} rebuilt, "
              f"{stats['bars_added']} bars added", flush=True)
        return stats
    finally:
        db.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", default="all",
                    choices=("all", "instruments", "funds", "short", "indices",
                             "spark"))
    ap.add_argument("--chunk", type=int, default=50)
    ap.add_argument("--pause", type=float, default=0.3)
    ap.add_argument("--funds", type=int, default=1200,
                    help="full NAV histories to fetch (0 = skip, -1 = all)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0,
                    help="debug: only repair the first N instruments")
    args = ap.parse_args()

    if args.stage in ("all", "instruments"):
        backfill_instruments(chunk=args.chunk, pause=args.pause,
                             limit=args.limit)
    if args.stage == "short":
        repair_short_histories()
    if args.stage == "indices":
        repair_index_histories()
    if args.stage == "spark":
        seed_spark_meta()
    if args.stage in ("all", "funds"):
        seed_latest_fund_navs()
        limit = args.funds
        if limit is None:
            limit = 1200
        if limit < 0:
            limit = 10_000_000
        enrich_fund_histories(limit=limit, workers=args.workers)


if __name__ == "__main__":
    main()
