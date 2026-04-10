import logging
import uuid as uuid_mod
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import verify_api_key
from app.clients.db import get_db
from app.gatekeeper import assert_agents_limit
from app.models.agents import Agent, AgentRun, AgentVersion
from app.models.common import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


# ── Request models ────────────────────────────────────────────────────────────


class RegisterAgentRequest(BaseModel):
    name: str
    owner: str
    runtime: str
    description: str | None = None
    default_permissions: list[str] | None = None


class CreateVersionRequest(BaseModel):
    version: str
    permissions: list[str] | None = None
    changelog: str | None = None


class StartRunRequest(BaseModel):
    version_id: str | None = None
    user_id: str | None = None
    metadata: dict | None = None
    parent_run_id: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _assert_agent_org(db: Session, agent_id: str, org_id: str) -> None:
    """Raise 404 if the agent doesn't exist or doesn't belong to org_id."""
    row = db.execute(
        text("SELECT id FROM agents WHERE id = :id AND organization_id = :org_id"),
        {"id": agent_id, "org_id": org_id},
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/register", summary="Register or update an agent", response_model=ApiResponse[Agent])
def register_agent(
    payload: RegisterAgentRequest,
    db: Annotated[Session, Depends(get_db)],
    org_id: Annotated[str, Depends(verify_api_key)],
) -> JSONResponse:
    """Upsert an agent by (name, owner, organization_id)."""
    assert_agents_limit(db, org_id, payload.name, payload.owner)
    logger.info(
        "Registering agent name=%s owner=%s runtime=%s org_id=%s",
        payload.name,
        payload.owner,
        payload.runtime,
        org_id,
    )

    row = (
        db.execute(
            text("""
            INSERT INTO agents (name, owner, runtime, description, default_permissions, organization_id)
            VALUES (:name, :owner, :runtime, :description, :default_permissions, :org_id)
            ON CONFLICT (name, owner, organization_id) DO UPDATE SET
                runtime = EXCLUDED.runtime,
                description = EXCLUDED.description,
                default_permissions = EXCLUDED.default_permissions,
                updated_at = now()
            RETURNING *
        """),
            {
                "name": payload.name,
                "owner": payload.owner,
                "runtime": payload.runtime,
                "description": payload.description,
                "default_permissions": payload.default_permissions,
                "org_id": org_id,
            },
        )
        .mappings()
        .first()
    )
    db.commit()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to persist agent — unexpected response from database.",
        )

    agent = Agent.model_validate(dict(row))
    logger.info("Agent persisted id=%s name=%s", agent.id, agent.name)
    return JSONResponse(
        content={"success": True, "data": agent.model_dump(mode="json"), "error": None}
    )


@router.post(
    "/{agent_id}/versions",
    summary="Create an agent version",
    response_model=ApiResponse[AgentVersion],
)
def create_version(
    agent_id: str,
    payload: CreateVersionRequest,
    db: Annotated[Session, Depends(get_db)],
    org_id: Annotated[str, Depends(verify_api_key)],
) -> JSONResponse:
    """Create a new version record for the given agent. No-ops on duplicate (agent_id, version)."""
    _assert_agent_org(db, agent_id, org_id)
    logger.info("Creating version agent_id=%s version=%s", agent_id, payload.version)

    row = (
        db.execute(
            text("""
            INSERT INTO agent_versions (agent_id, version, permissions, changelog, organization_id)
            VALUES (:agent_id, :version, :permissions, :changelog, :org_id)
            ON CONFLICT (agent_id, version) DO NOTHING
            RETURNING *
        """),
            {
                "agent_id": agent_id,
                "version": payload.version,
                "permissions": payload.permissions,
                "changelog": payload.changelog,
                "org_id": org_id,
            },
        )
        .mappings()
        .first()
    )
    db.commit()

    if row is not None:
        version = AgentVersion.model_validate(dict(row))
        logger.info("Version persisted id=%s agent_id=%s", version.id, agent_id)
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={"success": True, "data": version.model_dump(mode="json"), "error": None},
        )

    # Duplicate — fetch and return the existing record
    existing = (
        db.execute(
            text("SELECT * FROM agent_versions WHERE agent_id = :agent_id AND version = :version"),
            {"agent_id": agent_id, "version": payload.version},
        )
        .mappings()
        .first()
    )
    version = AgentVersion.model_validate(dict(existing))
    logger.info("Version already exists id=%s agent_id=%s", version.id, agent_id)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"success": True, "data": version.model_dump(mode="json"), "error": None},
    )


@router.get(
    "/{agent_id}/runs", summary="List runs for an agent", response_model=ApiResponse[list[AgentRun]]
)
def list_runs(
    agent_id: str,
    db: Annotated[Session, Depends(get_db)],
    org_id: Annotated[str, Depends(verify_api_key)],
) -> JSONResponse:
    """Return all runs for an agent, newest first."""
    _assert_agent_org(db, agent_id, org_id)
    logger.info("Listing runs agent_id=%s", agent_id)

    rows = (
        db.execute(
            text("SELECT * FROM agent_runs WHERE agent_id = :agent_id ORDER BY start_time DESC"),
            {"agent_id": agent_id},
        )
        .mappings()
        .all()
    )

    runs = [AgentRun.model_validate(dict(r)).model_dump(mode="json") for r in rows]
    return JSONResponse(content={"success": True, "data": runs, "error": None})


@router.post(
    "/{agent_id}/runs",
    summary="Start an agent run",
    response_model=ApiResponse[AgentRun],
    status_code=201,
)
def start_run(
    agent_id: str,
    payload: StartRunRequest,
    db: Annotated[Session, Depends(get_db)],
    org_id: Annotated[str, Depends(verify_api_key)],
) -> JSONResponse:
    """Create a new run record with status 'running'."""
    _assert_agent_org(db, agent_id, org_id)
    logger.info("Starting run agent_id=%s version_id=%s", agent_id, payload.version_id)

    run_id = str(uuid_mod.uuid4())
    root_run_id = run_id  # default: this run is its own root

    if payload.parent_run_id is not None:
        parent_row = (
            db.execute(
                text("SELECT root_run_id, organization_id FROM agent_runs WHERE id = :id"),
                {"id": payload.parent_run_id},
            )
            .mappings()
            .first()
        )
        if parent_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent run not found.")
        if str(parent_row["organization_id"]) != org_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Parent run belongs to a different organization.",
            )
        root_run_id = str(parent_row["root_run_id"])

    row = (
        db.execute(
            text("""
                INSERT INTO agent_runs
                    (id, agent_id, version_id, user_id, parent_run_id, root_run_id, status, metadata, organization_id)
                VALUES
                    (:id, :agent_id, :version_id, :user_id, :parent_run_id, :root_run_id, 'running', :metadata, :org_id)
                RETURNING *
            """),
            {
                "id": run_id,
                "agent_id": agent_id,
                "version_id": payload.version_id,
                "user_id": payload.user_id,
                "parent_run_id": payload.parent_run_id,
                "root_run_id": root_run_id,
                "metadata": payload.metadata,
                "org_id": org_id,
            },
        )
        .mappings()
        .first()
    )

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to start run — unexpected response from database.",
        )

    db.commit()

    run = AgentRun.model_validate(dict(row))
    logger.info("Run started id=%s agent_id=%s", run.id, agent_id)
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"success": True, "data": run.model_dump(mode="json"), "error": None},
    )
