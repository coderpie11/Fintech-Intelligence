"""Local launcher — no Docker needed. Data paths live inside backend/data."""
import subprocess
import sys
from pathlib import Path

here = Path(__file__).parent
sys.path.insert(0, str(here))

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8001, reload=False)
