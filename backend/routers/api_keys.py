"""API key management routes."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import APIKey

logger = logging.getLogger(__name__)
router = APIRouter()


class APIKeyCreate(BaseModel):
    name: str


@router.post("")
def create_api_key(req: APIKeyCreate, db: Session = Depends(get_db)):
    """Create a new API key.  Returns the full key ONCE at creation time."""
    raw_key = f"ssp_{secrets.token_hex(24)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    api_key = APIKey(
        name=req.name,
        key_hash=key_hash,
        key_prefix=raw_key[:8],
        is_active=True,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    logger.info("API key created: %s (id=%d)", req.name, api_key.id)

    return {
        "id": api_key.id,
        "name": api_key.name,
        "key": raw_key,  # Only returned once
        "key_prefix": api_key.key_prefix,
        "created_at": api_key.created_at.isoformat() if api_key.created_at else None,
    }


@router.get("")
def list_api_keys(db: Session = Depends(get_db)):
    """List all API keys (without the actual key values)."""
    keys = db.query(APIKey).order_by(APIKey.created_at.desc()).all()
    return [
        {
            "id": k.id,
            "name": k.name,
            "key_prefix": k.key_prefix,
            "is_active": k.is_active,
            "created_at": k.created_at.isoformat() if k.created_at else None,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
        }
        for k in keys
    ]


@router.delete("/{key_id}")
def revoke_api_key(key_id: int, db: Session = Depends(get_db)):
    """Revoke (deactivate) an API key."""
    key = db.query(APIKey).filter(APIKey.id == key_id).first()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")

    key.is_active = False
    db.commit()
    logger.info("API key revoked: %s (id=%d)", key.name, key.id)
    return {"detail": f"API key '{key.name}' revoked"}
