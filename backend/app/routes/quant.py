"""Legacy `/quant` aliases — kept so old links keep working.

All computation now lives in `app.services.ai_engine`; the branded workspaces
are served under `/quant-hub`. These aliases return the same engine output so
there is exactly one implementation of every number.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.ai_engine import rangecast, streetpulse, xray

router = APIRouter(prefix="/quant", tags=["ai quant (legacy alias)"])


@router.get("/rangecast/{symbol}")
def rangecast_alias(symbol: str, horizon_days: str = "7",
                    db: Session = Depends(get_db)):
    try:
        return rangecast.build(db, symbol, int(horizon_days))
    except (LookupError, ValueError) as e:
        raise HTTPException(404, str(e)) from e


@router.get("/streetpulse")
def streetpulse_alias(db: Session = Depends(get_db)):
    return streetpulse.build(db)


@router.get("/xray")
def xray_alias(db: Session = Depends(get_db)):
    return xray.build(db)
