"""One-off: relabel each stored index level with its actual session date and
record the fetch time, without re-downloading any data."""
import datetime as dt

from app.core.db import SessionLocal
from app.models.models import Instrument

db = SessionLocal()
now = dt.datetime.utcnow().isoformat() + "Z"
fixed = 0
for row in db.query(Instrument).filter(Instrument.kind == "INDEX").all():
    hist = row.history or []
    if not hist:
        continue
    meta = dict(row.meta or {})
    meta["live_asof"] = hist[-1]["date"]
    meta["fetched_at"] = now
    row.meta = meta
    fixed += 1
db.commit()
print("relabelled", fixed, "indices")
