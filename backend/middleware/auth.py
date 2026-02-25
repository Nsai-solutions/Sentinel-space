"""Optional API key authentication middleware.

Only enforces API key validation when the ``API_KEY_REQUIRED`` environment
variable is set to ``"true"``.  When enforcement is off (the default), all
requests pass through without authentication.

When enforcement is on:
- Requests must include a valid ``X-API-Key`` header.
- The key is hashed with SHA-256 and looked up in the ``api_keys`` table.
- ``last_used_at`` is updated on successful validation.
- Certain paths (health check, docs) are always exempt.
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

API_KEY_REQUIRED = os.environ.get("API_KEY_REQUIRED", "false").lower() == "true"

EXEMPT_PATHS = {"/api/health", "/docs", "/openapi.json", "/redoc"}


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Always allow exempt paths
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        # If enforcement is disabled, allow everything
        if not API_KEY_REQUIRED:
            return await call_next(request)

        # Enforcement is on — validate the key
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "API key required. Provide via X-API-Key header."},
            )

        from database.database import SessionLocal
        from database.models import APIKey

        db = SessionLocal()
        try:
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            db_key = db.query(APIKey).filter(
                APIKey.key_hash == key_hash,
                APIKey.is_active == True,  # noqa: E712
            ).first()

            if not db_key:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Invalid or revoked API key."},
                )

            # Update last_used_at
            db_key.last_used_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()

        return await call_next(request)
