-- ===========================================================================
-- Fintech Intelligence — Cloudflare D1 schema
--
-- SQLite dialect (D1 is SQLite). Mirrors backend/app/models/models.py so the
-- edge can serve the same relational shape as the local-first store.
--
-- Apply:
--   npx wrangler d1 execute fintech-intelligence-db --file=./schema.sql --remote
--
-- Notes:
--   * JSON columns are TEXT holding serialised JSON (D1 has native json_* functions).
--   * Timestamps are ISO-8601 TEXT (UTC) for portable ordering.
--   * Every statement is idempotent (IF NOT EXISTS) so re-running is safe.
-- ===========================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- instruments — one shared universe: equity, index, ETF, REIT, InvIT, bond,
--               commodity proxy. This is the join key for every other desk.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS instruments (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol      TEXT    NOT NULL,
  name        TEXT    NOT NULL,
  kind        TEXT    NOT NULL,                 -- EQUITY|INDEX|ETF|REIT|INVIT|BOND|COMMODITY
  exchange    TEXT    NOT NULL DEFAULT 'NSE',
  sector      TEXT,
  industry    TEXT,
  macro       TEXT,
  indices     TEXT,                             -- JSON array of index memberships
  isin        TEXT,
  slug        TEXT    NOT NULL UNIQUE,
  meta        TEXT    NOT NULL DEFAULT '{}',    -- JSON: live snapshot + fundamentals
  history     TEXT,                             -- JSON array: [{date,o,h,l,c,v}]
  updated_at  TEXT    NOT NULL DEFAULT (datetime('now')),
  CONSTRAINT uq_instrument UNIQUE (symbol, kind, exchange)
);

CREATE INDEX IF NOT EXISTS ix_instruments_symbol   ON instruments (symbol);
CREATE INDEX IF NOT EXISTS ix_instruments_kind     ON instruments (kind);
CREATE INDEX IF NOT EXISTS ix_instruments_sector   ON instruments (sector);

-- ---------------------------------------------------------------------------
-- fund_schemes — AMFI mutual-fund / ETF scheme master with the NAV series.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fund_schemes (
  code         TEXT PRIMARY KEY,                -- AMFI scheme code
  name         TEXT NOT NULL,
  amc          TEXT NOT NULL,
  category     TEXT,
  plan_type    TEXT,                            -- Direct | Regular
  option_type  TEXT,                            -- Growth | IDCW
  is_etf       INTEGER NOT NULL DEFAULT 0,      -- 0/1
  navs         TEXT                             -- JSON array: [{date,nav}]
);

CREATE INDEX IF NOT EXISTS ix_fund_schemes_amc       ON fund_schemes (amc);
CREATE INDEX IF NOT EXISTS ix_fund_schemes_category  ON fund_schemes (category);

-- ---------------------------------------------------------------------------
-- fund_meta — enrichment mfapi.in does not publish (TER, exit load, AUM,
--             holdings snapshot, peers). Kept separate so NAVs stay small.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fund_meta (
  code        TEXT PRIMARY KEY REFERENCES fund_schemes (code) ON DELETE CASCADE,
  meta        TEXT NOT NULL DEFAULT '{}',
  updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- ipos — mainboard and SME issues, including the pre-IPO comparison fields.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ipos (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  name             TEXT NOT NULL,
  symbol           TEXT,
  board            TEXT NOT NULL DEFAULT 'MAINBOARD',  -- MAINBOARD | SME
  status           TEXT NOT NULL DEFAULT 'UNKNOWN',    -- UPCOMING | LIVE | LISTED
  open_date        TEXT,
  close_date       TEXT,
  listing_date     TEXT,
  price_band_low   REAL,
  price_band_high  REAL,
  lot_size         INTEGER,
  issue_size       REAL,                               -- ₹ crore
  registrar        TEXT,
  note             TEXT,
  meta             TEXT NOT NULL DEFAULT '{}'          -- JSON: GMP, subscription, anchors, BRLM
);

CREATE INDEX IF NOT EXISTS ix_ipos_status ON ipos (status);
CREATE INDEX IF NOT EXISTS ix_ipos_symbol ON ipos (symbol);

-- ---------------------------------------------------------------------------
-- bonds — G-Secs, T-Bills, SDLs and corporate paper.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bonds (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT NOT NULL,
  kind        TEXT NOT NULL,                    -- G-SEC|T-BILL|SDL|CORPORATE
  coupon      REAL,
  face_value  REAL,
  maturity    TEXT,                             -- ISO date
  note        TEXT,
  meta        TEXT NOT NULL DEFAULT '{}'        -- JSON: YTM, dirty price, cashflow ladder
);

CREATE INDEX IF NOT EXISTS ix_bonds_kind     ON bonds (kind);
CREATE INDEX IF NOT EXISTS ix_bonds_maturity ON bonds (maturity);

-- ---------------------------------------------------------------------------
-- corporate_events — dividends, splits, bonus, board meetings, AGMs.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS corporate_events (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol       TEXT,
  company      TEXT NOT NULL,
  kind         TEXT NOT NULL,                   -- DIVIDEND|BOARD|AGM|SPLIT|BONUS|BUYBACK|DEMERGER
  ex_date      TEXT,
  record_date  TEXT,
  purpose      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_corporate_events_symbol  ON corporate_events (symbol);
CREATE INDEX IF NOT EXISTS ix_corporate_events_ex_date ON corporate_events (ex_date);

-- ---------------------------------------------------------------------------
-- reits — listed real-estate / infrastructure trusts (REIT + InvIT).
--        Unit prices still live on `instruments`; this table carries the
--        distribution and 90% NDCA specifics.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reits (
  id                      INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol                  TEXT NOT NULL UNIQUE,
  name                    TEXT NOT NULL,
  kind                    TEXT NOT NULL DEFAULT 'REIT',   -- REIT | INVIT
  trustee                 TEXT,
  sponsor                 TEXT,
  price                   REAL,
  nav_per_unit            REAL,
  distribution_yield_pct  REAL,
  distribution_frequency  TEXT,                            -- Quarterly | Half-yearly
  occupancy_pct           REAL,
  ndca_ratio_pct          REAL,                            -- statutory 90% payout test
  meta                    TEXT NOT NULL DEFAULT '{}',
  updated_at              TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS ix_reits_kind ON reits (kind);

-- ---------------------------------------------------------------------------
-- sandbox_orders — zero-KYC paper trading. Cash equity and F&O legs share
--                  this table so one portfolio view can mark both.
--                  `entry_price` is per unit; `quantity` is units (lots × lot_size).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sandbox_orders (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol       TEXT    NOT NULL,
  side         TEXT    NOT NULL,                  -- BUY | SELL
  quantity     REAL    NOT NULL,
  entry_price  REAL    NOT NULL,
  opened_at    TEXT    NOT NULL DEFAULT (datetime('now')),
  status       TEXT    NOT NULL DEFAULT 'OPEN',   -- OPEN | CLOSED
  exit_price   REAL,
  closed_at    TEXT,
  note         TEXT,
  asset_class  TEXT    NOT NULL DEFAULT 'EQUITY', -- EQUITY | INDEX | FNO
  underlying   TEXT,
  option_type  TEXT,                              -- CE | PE
  strike       REAL,
  expiry       TEXT,
  lot_size     INTEGER,
  lots         REAL,
  charges      REAL    NOT NULL DEFAULT 0.0,
  client_id    TEXT    NOT NULL DEFAULT 'default'
);

CREATE INDEX IF NOT EXISTS ix_sandbox_orders_symbol    ON sandbox_orders (symbol);
CREATE INDEX IF NOT EXISTS ix_sandbox_orders_client    ON sandbox_orders (client_id);
CREATE INDEX IF NOT EXISTS ix_sandbox_orders_status    ON sandbox_orders (status);

-- ---------------------------------------------------------------------------
-- watch_items — per-client watchlist with a hard uniqueness rule.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS watch_items (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol     TEXT NOT NULL,
  kind       TEXT NOT NULL DEFAULT 'EQUITY',
  href       TEXT,
  client_id  TEXT NOT NULL DEFAULT 'default',
  added_at   TEXT NOT NULL DEFAULT (datetime('now')),
  CONSTRAINT uq_watch_client_symbol UNIQUE (client_id, symbol)
);

CREATE INDEX IF NOT EXISTS ix_watch_items_symbol ON watch_items (symbol);
CREATE INDEX IF NOT EXISTS ix_watch_items_client ON watch_items (client_id);
