"""NSE adapter — live quotes, index data, option chains, corporate actions,
market status. Wrapped so the eventual broker-API replacement touches only
this file. Uses a shared session with polite throttling and retries."""
from __future__ import annotations

import csv
import datetime as dt
import io
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from jugaad_data.nse import NSELive

from app.core.config import DATA_DIR, NSE_THROTTLE, cache_get, cache_set

_lock = threading.Lock()
_last_call = [0.0]
_session_holder: list[NSELive | None] = [None]

SNAPSHOT_DIR = DATA_DIR / "index_snapshots"
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _throttle() -> None:
    with _lock:
        wait = _last_call[0] + NSE_THROTTLE - time.time()
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()


class NseApi:
    """Thin, cached wrapper around one live NSE session."""

    def session(self) -> NSELive:
        if _session_holder[0] is None:
            _session_holder[0] = NSELive()
        return _session_holder[0]

    def _call(self, name: str, fn):
        key = f"nse:{name}"
        hit = cache_get(key)
        if hit is not None:
            return hit
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                _throttle()
                data = fn()
                if data is not None:
                    cache_set(key, data, ttl=180)
                    return data
            except Exception as e:  # noqa: BLE001
                last_err = e
                # many NSE failures are stale-cookie failures: rebuild session
                try:
                    _session_holder[0] = NSELive()
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"NSE call {name} failed: {type(last_err).__name__} {last_err}")

    # ---- public surface -----------------------------------------------
    def stock_quote(self, symbol: str) -> dict:
        return self._call(f"quote:{symbol}", lambda: self.session().stock_quote(symbol))

    def all_indices(self) -> dict:
        return self._call("all_indices", lambda: self.session().all_indices())

    def live_index(self, index_name: str) -> dict:
        return self._call(f"live_index:{index_name}", lambda: self.session().live_index(index_name))

    def market_status(self) -> dict:
        return self._call("market_status", lambda: self.session().market_status())

    def index_option_chain(self, symbol: str, expiry: str | None = None) -> dict:
        return self._call(f"opt:{symbol}:{expiry or 'nearest'}",
                          lambda: self.session().index_option_chain(symbol, expiry))

    def equity_option_chain(self, symbol: str, expiry: str | None = None) -> dict:
        return self._call(f"optstk:{symbol}:{expiry or 'nearest'}",
                          lambda: self.session().equities_option_chain(symbol, expiry))

    def fno_quote(self, symbol: str) -> dict:
        """Every live futures + options contract for one F&O underlying.

        NSE returns FUTIDX/FUTSTK/OPTIDX/OPTSTK rows in one payload with OI,
        change-in-OI and volume, which is exactly what the 4-quadrant
        buildup and rollover matrix need.
        """
        return self._call(f"fno:{symbol}",
                          lambda: self.session().stock_quote_fno(symbol))

    def fno_contract_info(self, symbol: str) -> dict:
        return self._call(f"fnoinfo:{symbol}",
                          lambda: self.session().option_chain_contract_info(symbol))

    def fno_ban_list(self) -> list[str]:
        """Official NSE securities-in-ban feed (fo_secban.csv)."""
        import re
        key = "nse:fno_ban_list"
        hit = cache_get(key)
        if hit is not None:
            return hit
        url = "https://nsearchives.nseindia.com/content/fo/fo_secban.csv"
        rows: list[str] = []
        try:
            _throttle()
            r = requests.get(url, timeout=20, headers={"User-Agent": _UA})
            if r.status_code == 200:
                for line in r.text.splitlines():
                    m = re.match(r"\s*\d+\s*,\s*([A-Z0-9&\-]+)", line.strip())
                    if m:
                        rows.append(m.group(1).upper())
                cache_set(key, rows, ttl=900)
        except Exception:  # noqa: BLE001
            pass
        return rows

    def corporate_actions(self, days: int = 30) -> list:
        def fetch():
            import datetime as _dt
            to = _dt.date.today()
            frm = to - _dt.timedelta(days=days)
            return self.session().corporate_actions(from_date=frm, to_date=to)
        return self._call(f"actions:{days}", fetch)

    def corporate_announcements(self, symbol: str | None = None,
                                days: int | None = None) -> list:
        key = f"announcements:{symbol or 'market'}:{days or 0}"

        def fetch():
            import datetime as _dt
            if days:
                to = _dt.date.today()
                frm = to - _dt.timedelta(days=days)
                return self.session().corporate_announcements(
                    from_date=frm, to_date=to, symbol=symbol)
            return self.session().corporate_announcements(symbol=symbol)
        return self._call(key, fetch)

    def etf_list(self) -> list[dict]:
        """NSE's official ETF snapshot: live LTP, published NAV, volume and
        turnover for every listed ETF. Cached briefly by _call."""
        def fetch():
            r = self.session().s.get(
                "https://www.nseindia.com/api/etf", timeout=25,
                headers={"Referer": "https://www.nseindia.com/",
                         "Accept": "application/json"})
            if r.status_code != 200:
                raise RuntimeError(f"NSE ETF feed returned {r.status_code}")
            return (r.json() or {}).get("data") or []
        return self._call("etf_list", fetch)

    def fii_dii(self) -> list[dict]:
        """Official NSE provisional FII/FPI and DII cash-market net flows."""
        def fetch():
            sess = self.session()
            try:
                sess.s.get("https://www.nseindia.com/market-data/fii-dii",
                           timeout=20)
            except Exception:  # noqa: BLE001
                pass
            r = sess.s.get("https://www.nseindia.com/api/fiidiiTradeReact",
                           timeout=25,
                           headers={"Referer": "https://www.nseindia.com/market-data/fii-dii",
                                    "Accept": "application/json"})
            if r.status_code != 200:
                raise RuntimeError(f"NSE FII/DII feed returned {r.status_code}")
            return r.json() or []
        return self._call("fii_dii", fetch)


nse = NseApi()


# ---------------------------------------------------------------------------
# Public full bhavcopy — the only free per-session delivery source that works
# from this network (the live quote endpoint is 403). One CSV covers the whole
# cash market, so a 45-session window is 45 requests, not 249 × 45.
# ---------------------------------------------------------------------------

_BHAV_DIR = DATA_DIR / "bhavcopy"
_BHAV_DIR.mkdir(parents=True, exist_ok=True)


def bhavcopy_delivery(day: dt.date) -> dict[str, dict] | None:
    """Parse one session's `sec_bhavdata_full` CSV.

    Returns {SYMBOL: {delivery_pct, close, volume, turnover}} for the EQ
    series, or None when the archive has no file for that date.
    """
    import csv
    import io

    path = _BHAV_DIR / f"sec_bhavdata_full_{day.strftime('%d%m%Y')}.csv"
    text = None
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            text = None
    if text is None:
        url = ("https://archives.nseindia.com/products/content/"
               f"sec_bhavdata_full_{day.strftime('%d%m%Y')}.csv")
        headers = {"User-Agent": _UA, "Accept": "text/csv,*/*",
                   "Referer": "https://www.nseindia.com/"}
        try:
            r = requests.get(url, headers=headers, timeout=30)
            if r.status_code != 200 or "DELIV_PER" not in r.text[:600]:
                return None
            text = r.text
            path.write_text(text, encoding="utf-8")
        except Exception:  # noqa: BLE001
            return None
    out: dict[str, dict] = {}
    try:
        for row in csv.DictReader(io.StringIO(text)):
            sym = (row.get("SYMBOL") or row.get(" SYMBOL") or "").strip().upper()
            series = (row.get("SERIES") or row.get(" SERIES") or "").strip()
            if not sym or series != "EQ":
                continue
            def _f(key):
                raw = (row.get(key) or row.get(f" {key}") or "").strip()
                try:
                    return float(raw)
                except ValueError:
                    return None
            dp = _f("DELIV_PER")
            if dp is None:
                continue
            out[sym] = {"delivery_pct": dp, "close": _f("CLOSE_PRICE"),
                        "volume": _f("TTL_TRD_QNTY"),
                        "turnover": _f("TURNOVER_LACS")}
    except Exception:  # noqa: BLE001
        return None
    return out or None


# ---------------------------------------------------------------------------
# Official NSE daily index snapshot archive
# ---------------------------------------------------------------------------
# Yahoo has no multi-year series for two broad indices on this machine. NSE
# publishes one CSV per trading day containing every index's official OHLC.
# We download those once, cache them on disk, and stitch the 5-year series.
# This is real exchange data — not a proxy or a synthetic curve.

def _norm(name: str) -> str:
    return "".join(ch for ch in (name or "").lower() if ch.isalnum())


def _snapshot_path(day: dt.date) -> Path:
    return SNAPSHOT_DIR / f"ind_close_all_{day.strftime('%d%m%Y')}.csv"


def _fetch_snapshot(day: dt.date) -> str | None:
    path = _snapshot_path(day)
    if path.exists():
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return None
    url = ("https://nsearchives.nseindia.com/content/indices/"
           f"ind_close_all_{day.strftime('%d%m%Y')}.csv")
    # The archive CDN rejects the live-API cookie jar; plain requests with a
    # browser UA works and is far more reliable for bulk history.
    headers = {"User-Agent": _UA, "Accept": "text/csv,*/*",
               "Referer": "https://www.nseindia.com/"}
    for attempt in range(2):
        try:
            r = requests.get(url, headers=headers, timeout=20)
            if r.status_code == 200 and r.text.lstrip().lower().startswith("index name"):
                path.write_text(r.text, encoding="utf-8")
                return r.text
            if r.status_code == 404:
                return None
        except Exception:
            time.sleep(0.4 * (attempt + 1))
    return None


def index_history_snapshots(names: list[str], years: int = 5) -> dict[str, list[dict]]:
    """Return {requested_name: [{date,o,h,l,c}, ...]} from NSE's official
    daily index snapshots. Weekends are skipped; missing files are ignored."""
    wanted = {_norm(n): n for n in names}
    end = dt.date.today()
    start = end - dt.timedelta(days=int(years * 365.25))
    days: list[dt.date] = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += dt.timedelta(days=1)

    rows_by_name: dict[str, dict[str, dict]] = {n: {} for n in names}
    # small thread pool — the archive is a CDN, not the live API
    with ThreadPoolExecutor(max_workers=8) as pool:
        texts = list(pool.map(_fetch_snapshot, days))

    for day, text in zip(days, texts):
        if not text:
            continue
        try:
            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                nm = _norm(row.get("Index Name", ""))
                key = wanted.get(nm)
                if not key:
                    continue
                try:
                    rows_by_name[key][day.isoformat()] = {
                        "date": day.isoformat(),
                        "o": round(float(row.get("Open Index Value") or 0), 4),
                        "h": round(float(row.get("High Index Value") or 0), 4),
                        "l": round(float(row.get("Low Index Value") or 0), 4),
                        "c": round(float(row.get("Closing Index Value") or 0), 4),
                        "v": 0,
                    }
                except (TypeError, ValueError):
                    continue
        except Exception:
            continue

    return {name: [rows_by_name[name][k] for k in sorted(rows_by_name[name])]
            for name in names}
