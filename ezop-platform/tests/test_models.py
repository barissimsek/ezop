from uuid import UUID

from app.models.agents import AgentRun as AgentRunModel, TriggerType
from app.models.runs import Event, Span

AGENT_RUN_BASE = {
    "id": "00000000-0000-0000-0000-000000000001",
    "agent_id": "00000000-0000-0000-0000-000000000002",
    "version_id": None,
    "user_id": None,
    "status": "running",
    "organization_id": "00000000-0000-0000-0000-000000000003",
    "start_time": "2026-01-01T00:00:00+00:00",
    "end_time": None,
    "message": None,
    "metadata": None,
    "created_at": "2026-01-01T00:00:00+00:00",
    "updated_at": "2026-01-01T00:00:00+00:00",
    "trigger_type": "api",
    "trigger_id": None,
    "parent_run_id": None,
}


def test_agent_run_model_has_trigger_type():
    run = AgentRunModel.model_validate(AGENT_RUN_BASE)
    assert run.trigger_type == "api"


def test_agent_run_model_trigger_id_optional():
    run = AgentRunModel.model_validate({**AGENT_RUN_BASE, "trigger_id": "user-123"})
    assert run.trigger_id == "user-123"
    run2 = AgentRunModel.model_validate(AGENT_RUN_BASE)
    assert run2.trigger_id is None


def test_agent_run_model_parent_run_id_optional():
    parent_id = "aaaaaaaa-0000-0000-0000-000000000001"
    run = AgentRunModel.model_validate({**AGENT_RUN_BASE, "parent_run_id": parent_id})
    assert str(run.parent_run_id) == parent_id
    run2 = AgentRunModel.model_validate(AGENT_RUN_BASE)
    assert run2.parent_run_id is None


def test_trigger_type_enum_values():
    assert set(TriggerType) == {"api", "user", "cron", "webhook", "agent"}


def test_event_model_has_agent_id():
    data = {
        "id": "00000000-0000-0000-0000-000000000001",
        "run_id": "00000000-0000-0000-0000-000000000002",
        "agent_id": "00000000-0000-0000-0000-000000000003",
        "span_id": None,
        "name": "test",
        "category": "tool",
        "type": None,
        "subtype": None,
        "iteration_id": None,
        "timestamp": "2026-01-01T00:00:00+00:00",
        "input": None,
        "output": None,
        "metadata": None,
        "error": None,
        "sequence": 1,
        "organization_id": "00000000-0000-0000-0000-000000000004",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    event = Event.model_validate(data)
    assert isinstance(event.agent_id, UUID)
    assert str(event.agent_id) == "00000000-0000-0000-0000-000000000003"


def test_span_model_has_agent_id():
    data = {
        "id": "00000000-0000-0000-0000-000000000001",
        "run_id": "00000000-0000-0000-0000-000000000002",
        "agent_id": "00000000-0000-0000-0000-000000000003",
        "parent_id": None,
        "name": "my-span",
        "start_time": "2026-01-01T00:00:00+00:00",
        "end_time": None,
        "metadata": None,
        "organization_id": "00000000-0000-0000-0000-000000000004",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    span = Span.model_validate(data)
    assert isinstance(span.agent_id, UUID)
    assert str(span.agent_id) == "00000000-0000-0000-0000-000000000003"
