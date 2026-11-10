"""Pytest bootstrap for the local-first backend.

Network adapters are neutralised for the smoke suite so the tests are fast and
deterministic: the route contracts are what we verify here, not the live feeds
that the production app can reach when the machine is online.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


@pytest.fixture(scope="session", autouse=True)
def offline_adapters():
    """Keep the smoke suite off the public internet."""
    from app.routes import etfs, funds, ipos

    etfs._quote_map = lambda: {}
    funds.F.latest_nav_map = lambda: {}
    ipos.IG.refresh_all = lambda force=False: {"ipos": []}
    ipos.IG.ipo_page_detail = lambda *a, **k: {}
    ipos.IG.gmp_history = lambda *a, **k: []

    import app.services.live_quote as LQ

    LQ.refresh_rows = lambda *a, **k: {}
    LQ.refresh_one = lambda *a, **k: None

    from app.routes import pulse

    try:
        pulse.N.nse.market_status = lambda: {}
    except Exception:  # noqa: BLE001 - adapter may expose a read-only instance
        pass
    yield


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
