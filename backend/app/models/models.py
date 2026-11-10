"""SQLAlchemy models — one shared instrument universe + module tables.
The JSONB-style design (Meta JSON columns) keeps pivoting to PostgreSQL
/ TimescaleDB / pgvector painless later."""
from datetime import date, datetime

from sqlalchemy import (JSON, Boolean, Date, DateTime, Float, ForeignKey,
                        Integer, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Instrument(Base):
    """Every traded/trackable object: equity, index, ETF, REIT, InvIT, bond,
    commodity proxy."""
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(240))
    kind: Mapped[str] = mapped_column(String(16), index=True)  # EQUITY/INDEX/ETF/REIT/INVIT/BOND/COMMODITY
    exchange: Mapped[str] = mapped_column(String(8), default="NSE")
    sector: Mapped[str | None] = mapped_column(String(120), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(160), nullable=True)
    macro: Mapped[str | None] = mapped_column(String(120), nullable=True)
    indices: Mapped[list | None] = mapped_column(JSON, nullable=True)   # membership list
    isin: Mapped[str | None] = mapped_column(String(16), nullable=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)              # live snapshot + fundamentals
    history: Mapped[list | None] = mapped_column(JSON, nullable=True)   # [{date,o,h,l,c,v}] condensed
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("symbol", "kind", "exchange", name="uq_instrument"),)


class FundScheme(Base):
    __tablename__ = "fund_schemes"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(320))
    amc: Mapped[str] = mapped_column(String(160), index=True)
    category: Mapped[str | None] = mapped_column(String(120), index=True)
    plan_type: Mapped[str | None] = mapped_column(String(32))     # Direct/Regular
    option_type: Mapped[str | None] = mapped_column(String(32))   # Growth/IDCW
    is_etf: Mapped[bool] = mapped_column(Boolean, default=False)
    navs: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [{date,nav}]


class FundMeta(Base):
    """Cached enrichment for a scheme that mfapi.in does not publish:
    TER, exit load, AUM, holdings snapshots and peer sets. Kept in its own
    table so the NAV series on FundScheme stays small and stable."""
    __tablename__ = "fund_meta"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Ipo(Base):
    __tablename__ = "ipos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(240))
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    board: Mapped[str] = mapped_column(String(12), default="MAINBOARD")  # MAINBOARD/SME
    status: Mapped[str] = mapped_column(String(16), default="UNKNOWN")   # UPCOMING/LIVE/LISTED
    open_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    close_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    listing_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    price_band_low: Mapped[float | None]
    price_band_high: Mapped[float | None]
    lot_size: Mapped[int | None]
    issue_size: Mapped[float | None]
    registrar: Mapped[str | None] = mapped_column(String(200), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class CorporateEvent(Base):
    __tablename__ = "corporate_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str | None] = mapped_column(String(32), index=True)
    company: Mapped[str] = mapped_column(String(240))
    kind: Mapped[str] = mapped_column(String(40))       # DIVIDEND/BOARD/AGM/SPLIT/BONUS...
    ex_date: Mapped[date | None]
    record_date: Mapped[date | None]
    purpose: Mapped[str] = mapped_column(Text)


class Bond(Base):
    __tablename__ = "bonds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(240))
    kind: Mapped[str] = mapped_column(String(40))       # G-SEC/T-BILL/SDL/CORPORATE
    coupon: Mapped[float | None]
    face_value: Mapped[float | None]
    maturity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class SandboxOrder(Base):
    """Zero-KYC paper-trading sandbox — real CRUD, not view-only.

    Cash equities and F&O legs share the table so one portfolio view can mark
    both. F&O rows carry the contract identity; `entry_price` is the premium
    per unit and `quantity` is units (lots × lot_size)."""
    __tablename__ = "sandbox_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(4))        # BUY/SELL
    quantity: Mapped[float] = mapped_column(Float)
    entry_price: Mapped[float] = mapped_column(Float)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(8), default="OPEN")  # OPEN/CLOSED
    exit_price: Mapped[float | None]
    closed_at: Mapped[datetime | None]
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # --- Phase 4: asset-class aware paper trading -------------------------
    asset_class: Mapped[str] = mapped_column(String(12), default="EQUITY")
    underlying: Mapped[str | None] = mapped_column(String(32), nullable=True)
    option_type: Mapped[str | None] = mapped_column(String(4), nullable=True)  # CE/PE
    strike: Mapped[float | None]
    expiry: Mapped[str | None] = mapped_column(String(20), nullable=True)
    lot_size: Mapped[int | None]
    lots: Mapped[float | None]
    charges: Mapped[float] = mapped_column(Float, default=0.0)
    client_id: Mapped[str] = mapped_column(String(64), default="default", index=True)


class WatchItem(Base):
    __tablename__ = "watch_items"
    __table_args__ = (UniqueConstraint("client_id", "symbol",
                                       name="uq_watch_client_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(12), default="EQUITY")
    href: Mapped[str | None] = mapped_column(String(120), nullable=True)
    client_id: Mapped[str] = mapped_column(String(64), default="default", index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DeliveryStat(Base):
    """Per-session delivery percentage from NSE's public full bhavcopy.

    RangeCast needs a *distribution* of delivery behaviour, not just today's
    print, so the seeder keeps a rolling window of real sessions here."""
    __tablename__ = "delivery_stats"
    __table_args__ = (UniqueConstraint("symbol", "trade_date", name="uq_delivery_stat"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    delivery_pct: Mapped[float] = mapped_column(Float)
    close: Mapped[float | None]
    volume: Mapped[float | None]
    turnover: Mapped[float | None]


class KnowledgeChunk(Base):
    """RAG corpus chunk. `embedding` is a JSON float list so the same row
    moves to PostgreSQL + pgvector with a single column type change."""
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(120), index=True)
    symbol: Mapped[str | None] = mapped_column(String(32), index=True)
    doc_kind: Mapped[str] = mapped_column(String(32))   # ANNUAL/FILING/DRHP/NOTE
    title: Mapped[str] = mapped_column(String(240))
    asof: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(400), nullable=True)


class AiCallLog(Base):
    """Every LLM attempt, successful or not — the failover audit trail."""
    __tablename__ = "ai_call_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route: Mapped[str] = mapped_column(String(48), index=True)
    provider: Mapped[str] = mapped_column(String(24))
    model: Mapped[str] = mapped_column(String(96))
    tier: Mapped[int] = mapped_column(Integer, default=0)
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[int | None]
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SeedState(Base):
    """Book-keeping so the seeder is resumable and refreshes are scoped."""
    __tablename__ = "seed_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AcademyTopic(Base):
    """AI-generated beginner lesson cached in SQLite.

    The first reader to ask for a term pays the LLM latency; every later
    search reads this row in a millisecond. Keeping the payload as JSON means
    the exact five-card structure can evolve without a migration.
    """
    __tablename__ = "academy_topics"

    slug: Mapped[str] = mapped_column(String(160), primary_key=True)
    query: Mapped[str] = mapped_column(String(240))
    title: Mapped[str] = mapped_column(String(240))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str | None] = mapped_column(String(96), nullable=True)
    hits: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
