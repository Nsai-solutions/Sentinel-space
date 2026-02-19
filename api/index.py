"""Vercel Serverless Function entry point.

Routes all /api/* requests to the FastAPI application.
"""

import os
import sys

# Ensure the project root and backend are importable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")

for p in [PROJECT_ROOT, BACKEND_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Import the FastAPI app — Vercel auto-detects ASGI
from backend.main import app  # noqa: E402, F401
