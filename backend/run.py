"""Local launcher — no Docker needed. Data paths live inside backend/data."""
import os
import sys
from pathlib import Path

here = Path(__file__).parent
sys.path.insert(0, str(here))

import uvicorn  # noqa: E402

if __name__ == "__main__":
    # Materialise the shipped database snapshot before uvicorn imports the
    # app, so a fresh Render boot starts with the full store already in place.
    from app.core.config import restore_snapshot_if_missing

    restore_snapshot_if_missing()

    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "127.0.0.1")
    uvicorn.run("app.main:app", host=host, port=port, reload=False,
                loop="asyncio", http="h11")
