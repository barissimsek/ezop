from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RunStatus(StrEnum):
    running = "running"
    success = "success"
    failed = "failed"


class TriggerType(StrEnum):
    unknown = "unknown"
    api     = "api"
    agent   = "agent"
    user    = "user"
    cron    = "cron"
    webhook = "webhook"


class Agent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    owner: str
    runtime: str | None
    description: str | None
    default_permissions: list[str] | None
    organization_id: UUID
    created_at: datetime
    updated_at: datetime


class AgentVersion(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: UUID
    version: str
    permissions: list[str] | None
    changelog: str | None
    organization_id: UUID
    created_at: datetime


class AgentRun(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: UUID
    version_id: UUID | None
    user_id: UUID | None
    status: RunStatus
    metadata: dict | None
    message: str | None
    parent_run_id: UUID | None
    root_run_id: UUID
    trigger_type: TriggerType
    trigger_id: str | None
    organization_id: UUID
    start_time: datetime
    end_time: datetime | None
    created_at: datetime
    updated_at: datetime
