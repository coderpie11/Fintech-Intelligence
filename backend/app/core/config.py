"""Central configuration.

Loads `.env` from the repo root and from `backend/` (root wins on conflicts).
Paths are relative to the backend folder so the app runs identically on
Windows and Linux with zero extra setup.
"""
from __future__ import annotations

import gzip
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

# backend/
BASE_DIR = Path(__file__).resolve().parent.parent.parent
# repo root (one level above backend/)
ROOT_DIR = BASE_DIR.parent

# Load root .env first, then backend/.env without overriding existing keys.
load_dotenv(ROOT_DIR / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=False)

DATA_DIR = Path(os.getenv("DATA_DIR") or (BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "bfi.db"
DB_URL = f"sqlite:///{DB_PATH}"

# ---------------------------------------------------------------------------
# Pre-seeded store snapshot
#
# PaaS filesystems are ephemeral, and seeding the whole universe inside a
# 0.5-CPU container starves the health check until the platform kills the
# instance. Instead we ship a gzip of a fully seeded SQLite file and restore it
# the first time a process finds no usable database. Set RESTORE_SNAPSHOT=0 on
# a host with a persistent disk if you want to seed incrementally there.
# ---------------------------------------------------------------------------
SNAPSHOT_PATH = BASE_DIR / "data" / "seed" / "bfi.db.gz"
# The shipped snapshot holds the full seeded store (~390 MB uncompressed), so
# anything materially smaller than ~150 MB is a schema-only/empty database and
# must be replaced by the snapshot before the app serves traffic.
_SNAPSHOT_MIN_BYTES = 150 * 1024 * 1024


SNAPSHOT_STATE = {"restored": False, "error": None, "path": None}


def restore_snapshot_if_missing() -> bool:
    """Materialise DB_PATH from the shipped snapshot when the DB is absent."""
    if os.getenv("RESTORE_SNAPSHOT", "1").strip().lower() in ("0", "false", "no"):
        return False
    snapshot = SNAPSHOT_PATH
    SNAPSHOT_STATE["path"] = str(snapshot)
    if DB_PATH.exists() and DB_PATH.stat().st_size >= _SNAPSHOT_MIN_BYTES:
        return False
    if not snapshot.exists():
        SNAPSHOT_STATE["error"] = f"snapshot missing at {snapshot}"
        return False
    try:
        tmp = DB_PATH.with_name(DB_PATH.name + ".restoring")
        with gzip.open(snapshot, "rb") as src, open(tmp, "wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 20)
        # A stale WAL/SHM pair from the empty database would be replayed over
        # the restored file, so drop the sidecars before swapping it in.
        for suffix in ("-wal", "-shm"):
            sidecar = DB_PATH.with_name(DB_PATH.name + suffix)
            if sidecar.exists():
                sidecar.unlink()
        os.replace(tmp, DB_PATH)
    except Exception as exc:  # noqa: BLE001 - never block startup on this
        SNAPSHOT_STATE["error"] = f"{type(exc).__name__}: {exc}"
        print(f"[db] snapshot restore failed: {SNAPSHOT_STATE['error']}")
        return False
    SNAPSHOT_STATE["restored"] = True
    print(f"[db] restored pre-seeded snapshot ({snapshot.name}) -> {DB_PATH}")
    return True


# Import-time so it runs before any engine connects or create_all() runs.
restore_snapshot_if_missing()

BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8001"))

# CORS: local Next.js dev server, the deployed Cloudflare Pages frontends
# (Pages preview/production hosts), plus anything added via CORS_ORIGINS.
CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://fintech-intelligence.pages.dev",
    "https://fintechintelligence.coderpie.tech",
]
CORS_ORIGINS += [
    origin.strip().rstrip("/")
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]

# Pages preview deployments get a random subdomain, so allow the project's
# whole pages.dev namespace without opening CORS to every website.
CORS_ORIGIN_REGEX = os.getenv(
    "CORS_ORIGIN_REGEX",
    r"https://([a-z0-9-]+\.)?fintech-intelligence\.pages\.dev",
)

# ---------------------------------------------------------------------------
# Third-party credentials (never log these; read through these accessors).
# ---------------------------------------------------------------------------
DHAN_APP_NAME = os.getenv("DHAN_APP_NAME", "")
DHAN_CLIENT_ID = os.getenv("DHAN_CLIENT_ID", "")
DHAN_ACCESS_TOKEN = os.getenv("DHAN_ACCESS_TOKEN", "")

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "")
FMP_API_KEY = os.getenv("FMP_API_KEY", "")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

NEXT_PUBLIC_API_BASE = os.getenv("NEXT_PUBLIC_API_BASE", "/bff/api/v1")


def has_dhan() -> bool:
    return bool(DHAN_ACCESS_TOKEN and DHAN_CLIENT_ID)


def has_twelvedata() -> bool:
    return bool(TWELVEDATA_API_KEY)


def has_fmp() -> bool:
    return bool(FMP_API_KEY)


# Politeness throttles for free sources (SECONDS between NSE calls)
NSE_THROTTLE = 0.4
FREE_SOURCE_NOTE = (
    "All data is fetched from public exchange / market sources "
    "(NSE, Yahoo Finance, AMFI/mfapi.in, Dhan). Prices are end-of-day or "
    "delayed; they are not tick-by-tick."
)

# In-memory TTL cache (per-process). Redis can be attached later without
# changing call sites because every read goes through this registry.
_MEM_CACHE: dict[str, tuple[float, object]] = {}


def cache_get(key: str):
    import time
    hit = _MEM_CACHE.get(key)
    if not hit:
        return None
    expires, value = hit
    if time.time() > expires:
        _MEM_CACHE.pop(key, None)
        return None
    return value


def cache_set(key: str, value, ttl: int = 300) -> None:
    import time
    _MEM_CACHE[key] = (time.time() + ttl, value)
