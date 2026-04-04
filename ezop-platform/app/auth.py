import hashlib
import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.clients.db import get_db

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


def verify_api_key(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> str:
    """Validate Bearer token against api_keys table. Returns organization_id."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing credentials. Provide: Authorization: Bearer <API_KEY>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    key_hash = hashlib.sha256(token.encode()).hexdigest()

    row = (
        db.execute(
            text("""
            SELECT id, organization_id, expires_at
            FROM api_keys
            WHERE key_hash = :key_hash AND revoked_at IS NULL
        """),
            {"key_hash": key_hash},
        )
        .mappings()
        .first()
    )

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or revoked API key.",
        )

    if row["expires_at"] is not None:
        expires_at = row["expires_at"]
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if expires_at < datetime.now(UTC):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key has expired.",
            )

    # Update last_used_at — best effort
    try:
        db.execute(
            text("UPDATE api_keys SET last_used_at = :ts WHERE id = :id"),
            {"ts": datetime.now(UTC), "id": row["id"]},
        )
        db.commit()
    except Exception:
        logger.warning("Failed to update last_used_at for api_key id=%s", row["id"])

    logger.debug("Request authorised org_id=%s", row["organization_id"])
    return str(row["organization_id"])
