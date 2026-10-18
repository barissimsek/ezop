import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", summary="Health check")
def health_check() -> JSONResponse:
    """Public endpoint — returns service status."""
    logger.debug("Health check requested")
    return JSONResponse(content={"success": True, "data": {"status": "ok"}, "error": None})
