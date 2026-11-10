from fastapi import APIRouter

from app.core.config import CORS_ORIGINS
from app.routes import academy, bonds, calc, commodities, equities, events, etfs, funds, fno
from app.routes import indices, ipos, meta, pulse, quant, quant_hub, reits, sandbox
from app.routes import portfolio_xray

api = APIRouter(prefix="/api/v1")

for router in (meta.router, indices.router, equities.router, fno.router, funds.router,
               etfs.router, ipos.router, bonds.router, commodities.router, events.router,
               reits.router, pulse.router, quant.router, quant_hub.router,
               academy.router, sandbox.router, portfolio_xray.router, calc.router):
    api.include_router(router)


def origens_buscar():
    return CORS_ORIGINS
