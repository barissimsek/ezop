from uuid import UUID

from app.models.runs import Event, Span


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
