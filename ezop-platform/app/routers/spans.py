import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import verify_api_key
from app.clients.db import get_db
from app.models.common import ApiResponse
from app.models.runs import Span

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/spans", tags=["spans"])


class CloseSpanRequest(BaseModel):
    end_time: str


@router.patch("/{span_id}", summary="Close a span", response_model=ApiResponse[Span])
def close_span(
    span_id: str,
    payload: CloseSpanRequest,
    db: Annotated[Session, Depends(get_db)],
    org_id: Annotated[str, Depends(verify_api_key)],
) -> JSONResponse:
    """Set end_time on a span to mark it closed."""
    logger.info("Closing span id=%s", span_id)

    row = (
        db.execute(
            text("""
            UPDATE spans SET end_time = :end_time
            WHERE id = :id AND organization_id = :org_id
            RETURNING *
        """),
            {"end_time": payload.end_time, "id": span_id, "org_id": org_id},
        )
        .mappings()
        .first()
    )
    db.commit()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Span not found.")

    span = Span.model_validate(dict(row))
    logger.info("Span closed id=%s", span.id)
    return JSONResponse(
        content={"success": True, "data": span.model_dump(mode="json"), "error": None}
    )
