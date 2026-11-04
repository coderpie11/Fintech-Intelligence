"""Official NSE equity master.

Downloads NSE's public EQUITY_L.csv (the exchange's own list of active equity
securities) and stores every row in the shared instrument table. These rows are
discovery records: the full quote, history and fundamentals are filled the
first time a user opens the stock, using the on-demand Yahoo loader.

Source: https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv
"""
from __future__ import annotations

import csv
import io
import re

import requests
from sqlalchemy.orm import Session

from app.models.models import Instrument

EQUITY_L_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or "equity"


def fetch_equity_master() -> list[dict]:
    r = requests.get(EQUITY_L_URL, headers={"User-Agent": _UA}, timeout=45)
    r.raise_for_status()
    reader = csv.DictReader(io.StringIO(r.text))
    rows: list[dict] = []
    for raw in reader:
        symbol = (raw.get("SYMBOL") or raw.get(" SYMBOL") or "").strip().upper()
        name = (raw.get("NAME OF COMPANY") or raw.get(" NAME OF COMPANY") or "").strip()
        series = (raw.get("SERIES") or raw.get(" SERIES") or "").strip().upper()
        if not symbol or series != "EQ" or not name:
            continue
        rows.append({
            "symbol": symbol,
            "name": name,
            "isin": (raw.get("ISIN NUMBER") or raw.get(" ISIN NUMBER") or "").strip() or None,
            "listing_date": (raw.get("DATE OF LISTING") or raw.get(" DATE OF LISTING") or "").strip() or None,
            "face_value": (raw.get("FACE VALUE") or raw.get(" FACE VALUE") or "").strip() or None,
        })
    return rows


def seed_nse_universe(db: Session) -> dict:
    rows = fetch_equity_master()
    stats = {"downloaded": len(rows), "created": 0, "updated": 0, "kept": 0}
    existing = {
        r.symbol: r for r in
        db.query(Instrument).filter(Instrument.kind == "EQUITY").all()
    }
    for item in rows:
        symbol = item["symbol"]
        row = existing.get(symbol)
        if row is None:
            row = Instrument(
                symbol=symbol, name=item["name"], kind="EQUITY",
                exchange="NSE", slug=_slug(f"{symbol}-equity-nse"),
                isin=item.get("isin"), meta={},
            )
            db.add(row)
            existing[symbol] = row
            stats["created"] += 1
        else:
            stats["kept"] += 1
            if not row.name or row.name == symbol:
                row.name = item["name"]
        if item.get("isin") and not row.isin:
            row.isin = item["isin"]
        meta = dict(row.meta or {})
        meta["nse_master"] = True
        if item.get("listing_date"):
            meta.setdefault("listingDate", item["listing_date"])
        if item.get("face_value"):
            meta.setdefault("faceValue", item["face_value"])
        row.meta = meta
        stats["updated"] += 1
        if stats["updated"] % 200 == 0:
            db.commit()
    db.commit()
    return stats
