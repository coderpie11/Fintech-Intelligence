"""Central configuration.

Loads `.env` from the repo root and from `backend/` (root wins on conflicts).
Paths are relative to the backend folder so the app runs identically on
Windows and Linux with zero extra setup.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# backend/
BASE_DIR = Path(__file__).resolve().parent.parent.parent
# repo root (one level above backend/)
ROOT_DIR = BASE_DIR.parent

# Load root .env first, then backend/.env without overriding existing keys.
load_dotenv(ROOT_DIR / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=False)

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "bfi.db"
DB_URL = f"sqlite:///{DB_PATH}"

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
