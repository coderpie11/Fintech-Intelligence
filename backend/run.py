"""Local launcher — no Docker needed. Data paths live inside backend/data."""
import os
import sys
from pathlib import Path

here = Path(__file__).parent
sys.path.insert(0, str(here))

import uvicorn  # noqa: E402

from app.core.config import restore_snapshot_if_missing  # noqa: E402

if __name__ == "__main__":
    # Materialise the shipped pre-seeded store *before* uvicorn binds the port,
    # so neither the first request nor the platform's HEAD probe pays for a
    # 100 MB decompress (or, worse, races another worker doing the same).
    restore_snapshot_if_missing()

    # Render (and most PaaS) inject PORT and need a 0.0.0.0 bind. Locally no
    # PORT is set, so the terminal keeps its 127.0.0.1:8001 behaviour.
    port = int(os.getenv("PORT", "8001"))
    host = os.getenv("HOST") or ("0.0.0.0" if os.getenv("PORT") else "127.0.0.1")

    # Pin the pure-Python event loop and HTTP parser. `uvicorn[standard]` would
    # otherwise pull uvloop/httptools C extensions, and those are what crashed
    # the Render container with status 139 (SIGSEGV) on an unexpected wheel.
    uvicorn.run("app.main:app", host=host, port=port, reload=False,
                loop="asyncio", http="h11")
