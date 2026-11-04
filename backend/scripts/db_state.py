import sqlite3, json, os
p = os.path.join(os.path.dirname(__file__), '..', 'data', 'bfi.db')
c = sqlite3.connect(p)
rows = c.execute("select symbol,name,history,meta from instruments where kind='INDEX'").fetchall()
for sym, name, hist, meta in rows:
    h = json.loads(hist) if hist else []
    m = json.loads(meta) if meta else {}
    cons = m.get('constituents') or []
    print(f"{sym:26s} | hist={len(h):5d} | cons={len(cons):3d} | last={m.get('last')} | pct={m.get('changepct')} | keys={sorted(m.keys())}")
print('---')
print('total instruments:', c.execute("select count(*) from instruments").fetchone()[0])
print('equities:', c.execute("select count(*) from instruments where kind='EQUITY'").fetchone()[0])
print('equity w/ history:', c.execute("select count(*) from instruments where kind='EQUITY' and history is not null").fetchone()[0])
