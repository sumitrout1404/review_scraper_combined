"""Vercel serverless entrypoint: exposes the FastAPI ``app``."""

import sys
from pathlib import Path

# Make the backend/ root importable regardless of the runtime's cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402

__all__ = ["app"]
