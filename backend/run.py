"""Local launcher — no Docker needed. Data paths live inside backend/data."""
import os
import sys
from pathlib import Path

here = Path(__file__).parent
sys.path.insert(0, str(here))

import uvicorn  # noqa: E402

if __name__ == "__main__":
    # Render (and most PaaS) inject PORT and need a 0.0.0.0 bind. Locally no
    # PORT is set, so the terminal keeps its 127.0.0.1:8001 behaviour.
    port = int(os.getenv("PORT", "8001"))
    host = os.getenv("HOST") or ("0.0.0.0" if os.getenv("PORT") else "127.0.0.1")
    uvicorn.run("app.main:app", host=host, port=port, reload=False)
