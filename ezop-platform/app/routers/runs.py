import json
import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import verify_api_key
from app.clients.db import get_db
from app.gatekeeper import assert_events_limit
from app.models.agents import AgentRun, RunStatus
from app.models.common import ApiResponse
from app.models.runs import Event, EventCategory, EventSubtype, EventType, Span

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runs", tags=["runs"])


# ── Request models ────────────────────────────────────────────────────────────


class EndRunRequest(BaseModel):
    status: RunStatus
    message: str | None = None
    metadata: dict | None = None


class EmitEventRequest(BaseModel):
    id: str | None = None
    span_id: str | None = None
    name: str
    category: EventCategory
    type: EventType | None = None
    subtype: EventSubtype | None = None
    iteration_id: int | None = None
    timestamp: str | None = None
    input: dict | None = None
    output: dict | None = None
    metadata: dict | None = None
    error: dict | None = None


class CreateSpanRequest(BaseModel):
    id: str | None = None
    name: str | None = None
    start_time: str | None = None
    parent_id: str | None = None
    metadata: dict | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_run_agent(db: Session, run_id: str, org_id: str) -> str:
    """Return agent_id for the run, or raise 404 if not found."""
    row = db.execute(
        text("SELECT agent_id FROM agent_runs WHERE id = :id AND organization_id = :org_id"),
        {"id": run_id, "org_id": org_id},
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    return str(row.agent_id)


# ── Routes ────────────────────────────────────────────────────────────────────


@router.patch("/{run_id}", summary="End a run", response_model=ApiResponse[AgentRun])
def end_run(
    run_id: str,
    payload: EndRunRequest,
    db: Annotated[Session, Depends(get_db)],
    org_id: Annotated[str, Depends(verify_api_key)],
) -> JSONResponse:
    """Update a run record with final status and optional message/metadata."""
    _get_run_agent(db, run_id, org_id)  # validates ownership; agent_id not needed here
    logger.info("Ending run id=%s status=%s", run_id, payload.status)

    set_parts = ["status = :status", "end_time = :end_time"]
    params: dict = {
        "status": payload.status,
        "end_time": datetime.now(UTC),
        "id": run_id,
    }
    if payload.message is not None:
        set_parts.append("message = :message")
        params["message"] = payload.message
    if payload.metadata is not None:
        set_parts.append("metadata = :metadata")
        params["metadata"] = json.dumps(payload.metadata)

    row = (
        db.execute(
            text(f"UPDATE agent_runs SET {', '.join(set_parts)} WHERE id = :id RETURNING *"),  # noqa: S608
            params,
        )
        .mappings()
        .first()
    )
    db.commit()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} not found."
        )

    run = AgentRun.model_validate(dict(row))
    logger.info("Run ended id=%s status=%s", run_id, payload.status)
    return JSONResponse(
        content={"success": True, "data": run.model_dump(mode="json"), "error": None}
    )


@router.post(
    "/{run_id}/spans", summary="Create a span", response_model=ApiResponse[Span], status_code=201
)
def create_span(
    run_id: str,
    payload: CreateSpanRequest,
    db: Annotated[Session, Depends(get_db)],
    org_id: Annotated[str, Depends(verify_api_key)],
) -> JSONResponse:
    """Create a new span for a run. Optionally nested under a parent span."""
    agent_id = _get_run_agent(db, run_id, org_id)

    if payload.id and payload.parent_id and payload.id == payload.parent_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A span cannot be its own parent.",
        )

    if payload.parent_id:
        parent = (
            db.execute(
                text("SELECT run_id FROM spans WHERE id = :id AND organization_id = :org_id"),
                {"id": payload.parent_id, "org_id": org_id},
            )
            .mappings()
            .first()
        )
        if parent is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Parent span not found."
            )
        if str(parent["run_id"]) != run_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Parent span belongs to a different run.",
            )

    cols = ["run_id", "organization_id", "agent_id"]
    vals = [":run_id", ":org_id", ":agent_id"]
    params: dict = {"run_id": run_id, "org_id": org_id, "agent_id": agent_id}
    for field in ("id", "name", "start_time", "parent_id", "metadata"):
        value = getattr(payload, field)
        if value is not None:
            cols.append(field)
            vals.append(f":{field}")
            params[field] = json.dumps(value) if isinstance(value, dict) else value

    row = (
        db.execute(
            text(f"INSERT INTO spans ({', '.join(cols)}) VALUES ({', '.join(vals)}) RETURNING *"),  # noqa: S608
            params,
        )
        .mappings()
        .first()
    )
    db.commit()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to persist span — unexpected response from database.",
        )

    span = Span.model_validate(dict(row))
    logger.info("Span created id=%s run_id=%s", span.id, run_id)
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"success": True, "data": span.model_dump(mode="json"), "error": None},
    )


@router.post(
    "/{run_id}/events",
    summary="Emit a run event",
    response_model=ApiResponse[Event],
    status_code=201,
)
def emit_event(
    run_id: str,
    payload: EmitEventRequest,
    db: Annotated[Session, Depends(get_db)],
    org_id: Annotated[str, Depends(verify_api_key)],
) -> JSONResponse:
    """Append a single event to a run's event log."""
    agent_id = _get_run_agent(db, run_id, org_id)
    assert_events_limit(db, org_id)

    if payload.span_id:
        span = (
            db.execute(
                text("SELECT run_id FROM spans WHERE id = :id AND organization_id = :org_id"),
                {"id": payload.span_id, "org_id": org_id},
            )
            .mappings()
            .first()
        )
        if span is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Span not found.")
        if str(span["run_id"]) != run_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Span belongs to a different run.",
            )

    logger.info("Emitting event run_id=%s name=%s", run_id, payload.name)

    cols = ["run_id", "name", "category", "organization_id", "agent_id"]
    vals = [":run_id", ":name", ":category", ":org_id", ":agent_id"]
    params: dict = {
        "run_id": run_id,
        "name": payload.name,
        "category": payload.category,
        "org_id": org_id,
        "agent_id": agent_id,
    }
    json_fields = {"input", "output", "metadata", "error"}
    for field in (
        "id",
        "span_id",
        "type",
        "subtype",
        "iteration_id",
        "timestamp",
        "input",
        "output",
        "metadata",
        "error",
    ):
        value = getattr(payload, field)
        if value is not None:
            cols.append(field)
            vals.append(f":{field}")
            params[field] = (
                json.dumps(value)
                if field in json_fields and isinstance(value, (dict, list))
                else value
            )

    row = (
        db.execute(
            text(f"INSERT INTO events ({', '.join(cols)}) VALUES ({', '.join(vals)}) RETURNING *"),  # noqa: S608
            params,
        )
        .mappings()
        .first()
    )
    db.commit()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to persist event — unexpected response from database.",
        )

    event = Event.model_validate(dict(row))
    logger.info("Event persisted id=%s run_id=%s", event.id, run_id)
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"success": True, "data": event.model_dump(mode="json"), "error": None},
    )
