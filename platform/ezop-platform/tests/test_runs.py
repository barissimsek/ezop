"""Tests for /runs endpoints."""

from unittest.mock import MagicMock, patch

from tests.conftest import AGENT_ID, EVENT_ID, ORG_ID, RUN_ID, SPAN_ID, make_exec

RUN_ROW = {
    "id": RUN_ID,
    "agent_id": AGENT_ID,
    "version_id": None,
    "user_id": None,
    "status": "success",
    "organization_id": ORG_ID,
    "start_time": "2024-01-01T00:00:00+00:00",
    "end_time": "2024-01-01T00:01:00+00:00",
    "message": None,
    "metadata": None,
    "parent_run_id": None,
    "root_run_id": RUN_ID,
    "trigger_type": "unknown",
    "trigger_id": None,
    "created_at": "2024-01-01T00:00:00+00:00",
    "updated_at": "2024-01-01T00:00:00+00:00",
}

SPAN_ROW = {
    "id": SPAN_ID,
    "run_id": RUN_ID,
    "agent_id": AGENT_ID,
    "name": "llm.call",
    "organization_id": ORG_ID,
    "start_time": "2024-01-01T00:00:00+00:00",
    "end_time": None,
    "parent_id": None,
    "metadata": None,
    "created_at": "2024-01-01T00:00:00+00:00",
    "updated_at": "2024-01-01T00:00:00+00:00",
}

EVENT_ROW = {
    "id": EVENT_ID,
    "run_id": RUN_ID,
    "agent_id": AGENT_ID,
    "span_id": None,
    "name": "llm.response",
    "category": "llm",
    "type": None,
    "subtype": None,
    "iteration_id": None,
    "timestamp": "2024-01-01T00:00:00+00:00",
    "input": None,
    "output": None,
    "metadata": None,
    "error": None,
    "sequence": 1,
    "organization_id": ORG_ID,
    "created_at": "2024-01-01T00:00:00+00:00",
}


def _run_row_with_agent_id():
    """Mock .first() result for _get_run_agent — has a real agent_id attribute."""
    row = MagicMock()
    row.agent_id = AGENT_ID
    return row


class TestEndRun:
    def test_returns_200(self, client, db):
        db.execute.side_effect = [
            make_exec(first=_run_row_with_agent_id()),
            make_exec(mapping=RUN_ROW),
        ]
        resp = client.patch(f"/runs/{RUN_ID}", json={"status": "success"})
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "success"

    def test_with_message_and_metadata(self, client, db):
        row = {**RUN_ROW, "message": "done", "metadata": {"tokens": 100}}
        db.execute.side_effect = [
            make_exec(first=_run_row_with_agent_id()),
            make_exec(mapping=row),
        ]
        resp = client.patch(
            f"/runs/{RUN_ID}",
            json={"status": "success", "message": "done", "metadata": {"tokens": 100}},
        )
        assert resp.status_code == 200

    def test_run_not_found_returns_404(self, client, db):
        db.execute.return_value = make_exec(first=False)
        resp = client.patch(f"/runs/{RUN_ID}", json={"status": "success"})
        assert resp.status_code == 404

    def test_missing_status_returns_422(self, client, db):
        resp = client.patch(f"/runs/{RUN_ID}", json={})
        assert resp.status_code == 422

    def test_invalid_status_value_returns_422(self, client, db):
        # SDK docstring lists "partial"/"cancelled" as valid — they are not in RunStatus enum
        resp = client.patch(f"/runs/{RUN_ID}", json={"status": "partial"})
        assert resp.status_code == 422

    def test_requires_auth(self, unauthed_client):
        resp = unauthed_client.patch(f"/runs/{RUN_ID}", json={"status": "success"})
        assert resp.status_code == 401


class TestCreateSpan:
    def test_returns_201(self, client, db):
        db.execute.side_effect = [
            make_exec(first=_run_row_with_agent_id()),
            make_exec(mapping=SPAN_ROW),
        ]
        resp = client.post(
            f"/runs/{RUN_ID}/spans",
            json={"id": SPAN_ID, "name": "llm.call", "start_time": "2024-01-01T00:00:00+00:00"},
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["id"] == SPAN_ID

    def test_create_span_includes_agent_id(self, client, db):
        db.execute.side_effect = [
            make_exec(first=_run_row_with_agent_id()),
            make_exec(mapping=SPAN_ROW),
        ]
        resp = client.post(f"/runs/{RUN_ID}/spans", json={"name": "llm.call"})
        assert resp.status_code == 201
        assert resp.json()["data"]["agent_id"] == AGENT_ID

    def test_span_is_own_parent_returns_422(self, client, db):
        db.execute.side_effect = [make_exec(first=_run_row_with_agent_id())]
        resp = client.post(
            f"/runs/{RUN_ID}/spans",
            json={"id": SPAN_ID, "name": "x", "parent_id": SPAN_ID},
        )
        assert resp.status_code == 422

    def test_parent_not_found_returns_404(self, client, db):
        other_span = "bbbbbbbb-0000-0000-0000-000000000001"
        db.execute.side_effect = [
            make_exec(first=_run_row_with_agent_id()),
            make_exec(mapping=None),  # parent lookup returns None
        ]
        resp = client.post(
            f"/runs/{RUN_ID}/spans",
            json={"id": SPAN_ID, "name": "x", "parent_id": other_span},
        )
        assert resp.status_code == 404

    def test_parent_in_different_run_returns_422(self, client, db):
        other_span = "bbbbbbbb-0000-0000-0000-000000000001"
        other_run = "cccccccc-0000-0000-0000-000000000001"
        db.execute.side_effect = [
            make_exec(first=_run_row_with_agent_id()),
            make_exec(mapping={"run_id": other_run}),
        ]
        resp = client.post(
            f"/runs/{RUN_ID}/spans",
            json={"id": SPAN_ID, "name": "x", "parent_id": other_span},
        )
        assert resp.status_code == 422

    def test_run_not_found_returns_404(self, client, db):
        db.execute.return_value = make_exec(first=False)
        resp = client.post(f"/runs/{RUN_ID}/spans", json={"name": "x"})
        assert resp.status_code == 404


class TestEmitEvent:
    @patch("app.routers.runs.assert_events_limit")
    def test_returns_201(self, mock_limit, client, db):
        db.execute.side_effect = [
            make_exec(first=_run_row_with_agent_id()),
            make_exec(mapping=EVENT_ROW),
        ]
        resp = client.post(
            f"/runs/{RUN_ID}/events",
            json={"name": "llm.response", "category": "llm"},
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["name"] == "llm.response"

    @patch("app.routers.runs.assert_events_limit")
    def test_emit_event_includes_agent_id(self, mock_limit, client, db):
        db.execute.side_effect = [
            make_exec(first=_run_row_with_agent_id()),
            make_exec(mapping=EVENT_ROW),
        ]
        resp = client.post(
            f"/runs/{RUN_ID}/events",
            json={"name": "llm.response", "category": "llm"},
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["agent_id"] == AGENT_ID

    @patch("app.routers.runs.assert_events_limit")
    def test_with_metadata(self, mock_limit, client, db):
        db.execute.side_effect = [
            make_exec(first=_run_row_with_agent_id()),
            make_exec(mapping=EVENT_ROW),
        ]
        resp = client.post(
            f"/runs/{RUN_ID}/events",
            json={
                "name": "llm.response",
                "category": "llm",
                "type": "llm_response",
                "metadata": {"usage": {"input_tokens": 10, "output_tokens": 5}},
            },
        )
        assert resp.status_code == 201

    @patch("app.routers.runs.assert_events_limit")
    def test_invalid_category_returns_422(self, mock_limit, client, db):
        resp = client.post(
            f"/runs/{RUN_ID}/events",
            json={"name": "x", "category": "not-a-category"},
        )
        assert resp.status_code == 422

    @patch("app.routers.runs.assert_events_limit")
    def test_run_not_found_returns_404(self, mock_limit, client, db):
        db.execute.return_value = make_exec(first=False)
        resp = client.post(
            f"/runs/{RUN_ID}/events",
            json={"name": "x", "category": "llm"},
        )
        assert resp.status_code == 404

    @patch("app.routers.runs.assert_events_limit")
    def test_span_not_found_returns_404(self, mock_limit, client, db):
        db.execute.side_effect = [
            make_exec(first=_run_row_with_agent_id()),
            make_exec(mapping=None),  # span lookup returns None
        ]
        resp = client.post(
            f"/runs/{RUN_ID}/events",
            json={"name": "x", "category": "llm", "span_id": SPAN_ID},
        )
        assert resp.status_code == 404

    @patch("app.routers.runs.assert_events_limit")
    def test_span_in_different_run_returns_422(self, mock_limit, client, db):
        other_run = "cccccccc-0000-0000-0000-000000000001"
        db.execute.side_effect = [
            make_exec(first=_run_row_with_agent_id()),
            make_exec(mapping={"run_id": other_run}),
        ]
        resp = client.post(
            f"/runs/{RUN_ID}/events",
            json={"name": "x", "category": "llm", "span_id": SPAN_ID},
        )
        assert resp.status_code == 422

    def test_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(
            f"/runs/{RUN_ID}/events",
            json={"name": "x", "category": "llm"},
        )
        assert resp.status_code == 401
