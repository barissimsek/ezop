from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EventCategory(StrEnum):
    agent = "agent"
    llm = "llm"
    tool = "tool"
    reasoning = "reasoning"
    system = "system"
    user = "user"
    memory = "memory"
    cost = "cost"
    error = "error"


class EventType(StrEnum):
    agent_run_started = "agent_run_started"
    agent_run_completed = "agent_run_completed"
    agent_run_failed = "agent_run_failed"
    llm_request = "llm_request"
    llm_response = "llm_response"
    reasoning_step = "reasoning_step"
    reasoning_plan = "reasoning_plan"
    reasoning_reflection = "reasoning_reflection"
    reasoning_decision = "reasoning_decision"
    reasoning_final = "reasoning_final"
    tool_call_started = "tool_call_started"
    tool_call_completed = "tool_call_completed"
    tool_call_failed = "tool_call_failed"
    tool_retry = "tool_retry"
    memory_query = "memory_query"
    memory_retrieval = "memory_retrieval"
    memory_write = "memory_write"
    span_started = "span_started"
    span_completed = "span_completed"
    user_input = "user_input"
    user_feedback = "user_feedback"
    cost_calculated = "cost_calculated"
    error_raised = "error_raised"


class EventSubtype(StrEnum):
    chain_of_thought = "chain_of_thought"
    react = "react"
    reflection = "reflection"
    self_consistency = "self_consistency"
    http = "http"
    database = "database"
    filesystem = "filesystem"
    api = "api"
    timeout = "timeout"
    rate_limit = "rate_limit"
    validation = "validation"
    tool_error = "tool_error"
    llm_error = "llm_error"


class Span(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    parent_id: UUID | None
    name: str | None
    start_time: datetime
    end_time: datetime | None
    metadata: dict | None
    organization_id: UUID
    created_at: datetime
    updated_at: datetime


class Event(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    span_id: UUID | None
    name: str
    category: EventCategory
    type: EventType | None
    subtype: EventSubtype | None
    iteration_id: int | None
    timestamp: datetime
    input: dict | None
    output: dict | None
    metadata: dict | None
    error: dict | None
    sequence: int
    organization_id: UUID
    created_at: datetime
