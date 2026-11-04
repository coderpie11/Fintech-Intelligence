import json
import sqlite3

c = sqlite3.connect("data/bfi.db")
row = c.execute(
    "select symbol,name,sector,meta,history from instruments "
    "where kind='EQUITY' and symbol='RELIANCE'"
).fetchone()
print(row[0], row[1], row[2])
m = json.loads(row[3] or "{}")
print(json.dumps(m, indent=1)[:4000])
h = json.loads(row[4] or "[]")
print("hist", len(h), h[-1] if h else None)
print("---- equity count by sector ----")
for r in c.execute(
    "select sector, count(*) from instruments where kind='EQUITY' "
    "group by sector order by 2 desc limit 25"
):
    print(r)
print("---- equities with history ----")
print(c.execute(
    "select count(*) from instruments where kind='EQUITY' and history is not null"
).fetchone())
print("---- meta key frequency ----")
freq = {}
for (met,) in c.execute("select meta from instruments where kind='EQUITY'"):
    for k in json.loads(met or "{}").keys():
        freq[k] = freq.get(k, 0) + 1
for k, v in sorted(freq.items(), key=lambda x: -x[1]):
    print(f"{k}: {v}")
