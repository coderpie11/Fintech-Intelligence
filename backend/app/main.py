"""Fintech Intelligence — FastAPI application assembly."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import CORS_ORIGINS, CORS_ORIGIN_REGEX
from app.core.db import create_all
from app.routes import api


def _env_flag(name: str, default: str = "1") -> bool:
    """Defaults to on so local dev keeps its full warm-up behaviour."""
    return os.getenv(name, default).strip().lower() not in ("", "0", "false", "no")


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_all()
    # Hosted 512 MB boxes set ENABLE_SCHEDULER=false: the shipped snapshot already
    # holds every row, and boot-time warmups only add network scrapers to the
    # cold start. Local dev leaves it unset, so warmups run exactly as before.
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
        # The two post-market workspaces read NSE sector flows and a news feed,
        # so their first build costs tens of seconds. Warm them in the
        # background so the first visitor gets the cached payload.
        try:
            import threading

            threading.Thread(target=_warm_workspaces, name="workspace-prewarm",
                             daemon=True).start()
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


def _warm_workspaces() -> None:
    """Build the cached heavy payloads once, off the request path."""
    try:
        from app.core.db import SessionLocal
        from app.routes import ipos as I
        from app.routes import meta as M
        from app.routes import quant_hub as Q
    except Exception:  # noqa: BLE001
        return
    db = SessionLocal()
    try:
        # Cheap-but-slow-on-first-paint pages first, then the AI workspaces.
        for fn, kw in ((I.list_ipos, {"filter": "all", "limit": 120}),
                       (M.search_preload, {}),
                       (Q.xray_workspace, {}),
                       (Q.streetpulse_workspace, {"limit": 12})):
            try:
                fn(db=db, **kw)
            except Exception:  # noqa: BLE001
                pass
    finally:
        db.close()


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
    allow_origin_regex=CORS_ORIGIN_REGEX,
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

