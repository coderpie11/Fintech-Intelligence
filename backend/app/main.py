"""Fintech Intelligence — FastAPI application assembly."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import CORS_ORIGINS
from app.core.db import create_all
from app.routes import api


def _env_flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() not in ("", "0", "false", "no")


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_all()
    # Borderline-heavy background work is opt-in on purpose. On a 512 MB PaaS
    # box the pre-seeded snapshot already holds every row, so boot has nothing
    # to compute; warmups and schedulers only add network scrapers (yfinance /
    # curl_cffi) to the cold start. Set ENABLE_SCHEDULER=1 on a host with room
    # to spare; leave it unset where the snapshot is the source of truth.
    if _env_flag("ENABLE_SCHEDULER"):
        # Warm the pulse payload before the first page view. This is a one-time
        # arithmetic pass over the stored snapshot; doing it here keeps every
        # HTTP request on the fast cached path.
        try:
            from app.core.db import SessionLocal
            from app.routes import pulse as P

            db = SessionLocal()
            try:
                P.pulse(db)
            except Exception:  # noqa: BLE001
                pass
            finally:
                db.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            sched = BackgroundScheduler(timezone="Asia/Kolkata")
            sched.add_job(_nightly_refresh, "cron", hour=18, minute=30,
                          max_instances=1, id="nightly_refresh")
            sched.start()
        except Exception:  # noqa: BLE001
            pass
    yield


def _nightly_refresh() -> None:
    try:
        from app.seed import seed as SEED
        SEED.run_all()
    except Exception:
        pass


app = FastAPI(title="Fintech Intelligence API",
              version="1.0.0",
              description="Facts, math and education for Indian capital markets. "
                          "Not a buy/sell recommendation.",
              lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api)


# Render probes the port with `HEAD /`, so the root must answer HEAD as well as
# GET (a GET-only route returns 405 and the deploy is marked unhealthy).
@app.api_route("/", methods=["GET", "HEAD"])
def root():
    return {"service": "Fintech Intelligence API",
            "docs": "/docs", "health": "/api/v1/health"}
