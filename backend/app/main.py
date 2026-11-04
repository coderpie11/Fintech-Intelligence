"""Bharat Fintech Intelligence — FastAPI application assembly."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import CORS_ORIGINS
from app.core.db import create_all
from app.routes import api


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_all()
    # Warm the pulse payload before the first page view. This is a one-time
    # arithmetic pass over the stored snapshot; doing it here keeps every HTTP
    # request on the fast cached path.
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
    except Exception:
        pass
    yield


def _nightly_refresh() -> None:
    try:
        from app.seed import seed as SEED
        SEED.run_all()
    except Exception:
        pass


app = FastAPI(title="Bharat Fintech Intelligence API",
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


@app.get("/")
def root():
    return {"service": "Bharat Fintech Intelligence API",
            "docs": "/docs", "health": "/api/v1/health"}
