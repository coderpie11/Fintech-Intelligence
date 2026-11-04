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
        ("watch_items", "kind", "VARCHAR(12) DEFAULT 'EQUITY'"),
        ("watch_items", "href", "VARCHAR(120)"),
    )
    with engine.begin() as conn:
        for table, column, ddl in additive:
            cols = {r[1] for r in conn.exec_driver_sql(
                f"PRAGMA table_info({table})").fetchall()}
            if cols and column not in cols:
                conn.exec_driver_sql(
                    f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

