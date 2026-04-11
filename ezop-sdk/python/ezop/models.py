from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass(frozen=True)
class AgentModel:
    id: str
    name: str
    owner: str
    runtime: Optional[str]
    description: Optional[str]
    default_permissions: list[str]


@dataclass(frozen=True)
class AgentVersion:
    id: str
    agent_id: str
    version: str
    permissions: list[str]
    changelog: Optional[str]


@dataclass(frozen=True)
class AgentContext:
    name: str
    run_id: str


@dataclass
class AgentRun:
    id: str
    agent_id: str
    version_id: Optional[str]
    status: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    metadata: Optional[dict] = None
    message: Optional[str] = None
    parent_run_id: Optional[str] = None
    root_run_id: Optional[str] = None
    trigger_type: Optional[str] = None
    trigger_id: Optional[str] = None
    _current_span_id: Optional[str] = field(default=None, repr=False, compare=False)


@dataclass
class Event:
    id: str
    run_id: str
    name: str
    category: str
    timestamp: datetime
    span_id: Optional[str] = None
    type: Optional[str] = None
    subtype: Optional[str] = None
    iteration_id: Optional[int] = None
    input: Optional[Any] = None
    output: Optional[Any] = None
    metadata: Optional[dict] = None
    error: Optional[Any] = None
