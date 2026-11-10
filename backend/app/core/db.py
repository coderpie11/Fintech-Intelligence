"""SQLite (local) session factory. The schema is plain-SQLAlchemy so the same
models run on PostgreSQL when the project moves to its deployment stack."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import DB_URL

engine = create_engine(DB_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _record):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    # WAL still allows only one writer at a time. Without a busy timeout a
    # second request that tries to write while another commits fails almost
    # immediately with "database is locked". Wait instead of erroring.
    cur.execute("PRAGMA busy_timeout=15000")
    cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """FastAPI dependency — one session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Base(DeclarativeBase):
    pass


def create_all() -> None:
    from app.models import models  # noqa: F401  (register tables)
    Base.metadata.create_all(engine)
    # Lightweight additive migrations. SQLite has no ADD COLUMN IF NOT EXISTS,
    # so inspect first. This keeps an existing working DB usable across phases.
    from sqlalchemy import text
    additive = (
        ("ipos", "meta", "JSON"),
        ("bonds", "meta", "JSON"),
        ("sandbox_orders", "asset_class", "VARCHAR(12) DEFAULT 'EQUITY'"),
        ("sandbox_orders", "underlying", "VARCHAR(32)"),
        ("sandbox_orders", "option_type", "VARCHAR(4)"),
        ("sandbox_orders", "strike", "FLOAT"),
        ("sandbox_orders", "expiry", "VARCHAR(20)"),
        ("sandbox_orders", "lot_size", "INTEGER"),
        ("sandbox_orders", "lots", "FLOAT"),
        ("sandbox_orders", "charges", "FLOAT DEFAULT 0"),
        ("sandbox_orders", "client_id", "VARCHAR(64) DEFAULT 'default'"),
        ("watch_items", "kind", "VARCHAR(12) DEFAULT 'EQUITY'"),
        ("watch_items", "href", "VARCHAR(120)"),
        ("watch_items", "client_id", "VARCHAR(64) DEFAULT 'default'"),
    )
    with engine.begin() as conn:
        for table, column, ddl in additive:
            cols = {r[1] for r in conn.exec_driver_sql(
                f"PRAGMA table_info({table})").fetchall()}
            if cols and column not in cols:
                conn.exec_driver_sql(
                    f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        _rebuild_watch_items_if_needed(conn)


def _rebuild_watch_items_if_needed(conn) -> None:
    """Move the legacy globally-unique watch symbol to (client_id, symbol).

    The first release stored one global watchlist, so `symbol` carried a
    UNIQUE index. That blocks two browser clients from watching the same
    symbol. SQLite cannot drop an inline UNIQUE constraint, so rebuild the
    table once when the legacy index is detected. Data is copied verbatim and
    existing rows become client `default`.
    """
    try:
        indexes = conn.exec_driver_sql("PRAGMA index_list(watch_items)").fetchall()
    except Exception:  # noqa: BLE001
        return
    legacy = False
    for row in indexes:
        if not row[2]:  # not unique
            continue
        cols = [r[2] for r in conn.exec_driver_sql(
            f"PRAGMA index_info({row[1]})").fetchall()]
        if cols == ["symbol"]:
            legacy = True
            break
    if not legacy:
        return
    conn.exec_driver_sql("ALTER TABLE watch_items RENAME TO watch_items_legacy")
    conn.exec_driver_sql("""
        CREATE TABLE watch_items (
            id INTEGER NOT NULL PRIMARY KEY,
            symbol VARCHAR(32) NOT NULL,
            kind VARCHAR(12) NOT NULL DEFAULT 'EQUITY',
            href VARCHAR(120),
            client_id VARCHAR(64) NOT NULL DEFAULT 'default',
            added_at DATETIME NOT NULL,
            CONSTRAINT uq_watch_client_symbol UNIQUE (client_id, symbol)
        )
    """)
    conn.exec_driver_sql("""
        INSERT INTO watch_items (id, symbol, kind, href, client_id, added_at)
        SELECT id, symbol, COALESCE(kind, 'EQUITY'), href,
               COALESCE(client_id, 'default'),
               COALESCE(added_at, CURRENT_TIMESTAMP)
        FROM watch_items_legacy
    """)
    conn.exec_driver_sql("DROP TABLE watch_items_legacy")
    conn.exec_driver_sql(
        "CREATE INDEX ix_watch_items_symbol ON watch_items(symbol)")
    conn.exec_driver_sql(
        "CREATE INDEX ix_watch_items_client_id ON watch_items(client_id)")

