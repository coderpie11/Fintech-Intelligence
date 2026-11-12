"""Fintech Intelligence — FastAPI application assembly."""
import os
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.core.config import CORS_ORIGINS, CORS_ORIGIN_REGEX
from app.core.db import create_all
from app.routes import api


def _env_flag(name: str, default: str = "1") -> bool:
    """Defaults to on so local dev keeps its full warm-up behaviour."""
    return os.getenv(name, default).strip().lower() not in ("", "0", "false", "no")


def _instrument_count() -> int:
    """Cheap COUNT(*) — never loads row payloads."""
    try:
        from app.core.db import SessionLocal
        from app.models.models import Instrument

        db = SessionLocal()
        try:
            return int(db.query(Instrument).count())
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        return 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_all()
    # Warm only the cheap, SQLite-derived caches. A shipped snapshot already
    # holds the whole universe, so this never deserialises multi-year history
    # and never makes an external HTTP call. It runs in a daemon thread so the
    # socket binds immediately and a health probe answers on the first try.
    threading.Thread(target=_warm_all, name="startup-warm", daemon=True).start()
    if _env_flag("ENABLE_SCHEDULER"):
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            sched = BackgroundScheduler(timezone="Asia/Kolkata")
            sched.add_job(_nightly_refresh, "cron", hour=18, minute=30,
                          max_instances=1, id="nightly_refresh")
            sched.start()
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=_keep_alive, name="keep-alive", daemon=True).start()
    yield


def _warm_all() -> None:
    """Pre-compute every first-paint payload from SQLite, off the request path.

    The payloads are small (well under 15 MB) and every one of them is built by
    reading ``bfi.db``. StreetPulse is warmed with the external refresher muted
    so startup makes zero network calls.
    """
    # Import the heavy optional stacks here, on the warm thread, so the first
    # visitor never pays for them. ``yfinance`` pulls pandas, and the deferred
    # adapter imports are what made the very first detail page take seconds on
    # a cold process.
    for module in ("pandas", "yfinance", "jugaad_data",
                   "app.data.adapters.yfinance_adapter",
                   "app.data.adapters.nse_adapter",
                   "app.data.adapters.fund_adapter",
                   "app.data.adapters.screener_adapter",
                   "app.data.adapters.stockanalysis_adapter",
                   "app.services.instant_intraday",
                   "app.services.fundamentals",
                   "app.services.stock_loader",
                   "app.services.fuzzy",
                   "app.services.ai_engine.askdalal"):
        try:
            __import__(module)
        except Exception:  # noqa: BLE001
            pass
    try:
        from app.core.db import SessionLocal
        from app.routes import indices as IDX
        from app.routes import ipos as I
        from app.routes import meta as M
        from app.routes import pulse as P
        from app.routes import quant_hub as Q
    except Exception:  # noqa: BLE001
        return
    db = SessionLocal()
    try:
        for fn, kw in ((IDX.list_indices, {"expand": True}),
                       (P.pulse, {}),
                       (Q.prewarm_streetpulse, {}),
                       (Q.prewarm_xray, {}),
                       (I.list_ipos, {"filter": "all", "limit": 120}),
                       (M.search_preload, {})):
            try:
                fn(db=db, **kw)
            except Exception:  # noqa: BLE001
                pass
        # The fund browse table reads the tail of every stored NAV series, so
        # its first pass costs a second or two. Warming it here means the very
        # first visitor to /mutual-funds gets the cached row set.
        try:
            from app.routes import funds as FN

            FN.list_funds(q=None, category=None, amc=None, kind="mf",
                          sort="aum", limit=40, page=1, db=db)
        except Exception:  # noqa: BLE001
            pass
        try:
            from app.routes import etfs as E

            E.list_etfs(db=db)
        except Exception:  # noqa: BLE001
            pass
    finally:
        db.close()


def _keep_alive() -> None:
    """Ping this instance (and the public URL) every 9 minutes.

    Keeps a free Render dyno warm without any crawler traffic. Failures are
    ignored: the pinger must never crash the process or add request latency.
    """
    import urllib.request

    port = os.getenv("PORT", "8000")
    external = (os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/")
    urls = [f"http://127.0.0.1:{port}/api/v1/health"]
    if external:
        urls.append(f"{external}/api/v1/health")
    time.sleep(30)
    while True:
        for url in urls:
            try:
                with urllib.request.urlopen(url, timeout=4) as response:
                    response.read(64)
            except Exception:  # noqa: BLE001
                pass
        time.sleep(540)


def _nightly_refresh() -> None:
    try:
        from app.seed import seed as SEED
        SEED.run_all()
    except Exception:  # noqa: BLE001
        pass


app = FastAPI(title="Fintech Intelligence API",
              version="1.0.0",
              description="Facts, math and education for Indian capital markets. "
                          "Not a buy/sell recommendation.",
              lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Large JSON payloads (/stocks?limit=250, /search/preload, /mutual-funds) shrink
# by ~80% over the wire with no change to the response schema.
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.include_router(api)


# Render probes the port with `HEAD /`, so the root must answer HEAD as well as
# GET (a GET-only route returns 405 and the deploy is marked unhealthy).
@app.api_route("/", methods=["GET", "HEAD"])
def root():
    return {"service": "Fintech Intelligence API",
            "docs": "/docs", "health": "/api/v1/health"}

