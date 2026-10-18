import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse

from app.auth import verify_api_key
from app.config import configure_logging, get_settings
from app.routers import agents, health, runs, spans

# Boot: configure logging before anything else
settings = get_settings()
configure_logging(settings.log_level)

logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Ezop Platform API starting up (log_level=%s)", settings.log_level)
    yield
    logger.info("Ezop Platform API shutting down")


app = FastAPI(
    title="Ezop Platform API",
    version=settings.app_version,
    description="Agent observability platform API. All endpoints require a Bearer API key.",
    lifespan=lifespan,
)

# ── Routers ───────────────────────────────────────────────────────────────────
# Public — no auth
app.include_router(health.router)

# Protected — auth enforced for every route in these routers
app.include_router(agents.router, dependencies=[Depends(verify_api_key)])
app.include_router(runs.router, dependencies=[Depends(verify_api_key)])
app.include_router(spans.router, dependencies=[Depends(verify_api_key)])


# ── Global error handlers ─────────────────────────────────────────────────────
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    logger.warning("HTTP %s on %s %s", exc.status_code, request.method, request.url.path)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "data": None,
            "error": {"code": _status_to_code(exc.status_code), "message": exc.detail},
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    logger.warning("Validation error on %s %s: %s", request.method, request.url.path, exc.errors())
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "data": None,
            "error": {"code": "VALIDATION_ERROR", "message": str(exc.errors())},
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "data": None,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred.",
            },
        },
    )


def _status_to_code(status_code: int) -> str:
    return {
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        422: "VALIDATION_ERROR",
    }.get(status_code, "HTTP_ERROR")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.ezop_port, reload=False)
