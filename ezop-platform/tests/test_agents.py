"""Tests for /agents endpoints."""

from unittest.mock import patch

from tests.conftest import AGENT_ID, ORG_ID, RUN_ID, VERSION_ID, make_exec

PARENT_RUN_ID = "cccccccc-0000-0000-0000-000000000001"

AGENT_ROW = {
    "id": AGENT_ID,
    "name": "my-agent",
    "owner": "team-a",
    "runtime": "python",
    "description": "test agent",
    "default_permissions": [],
    "organization_id": ORG_ID,
    "created_at": "2024-01-01T00:00:00+00:00",
    "updated_at": "2024-01-01T00:00:00+00:00",
}

VERSION_ROW = {
    "id": VERSION_ID,
    "agent_id": AGENT_ID,
    "version": "v1.0",
    "permissions": [],
    "changelog": None,
    "organization_id": ORG_ID,
    "created_at": "2024-01-01T00:00:00+00:00",
}

RUN_ROW = {
    "id": RUN_ID,
    "agent_id": AGENT_ID,
    "version_id": VERSION_ID,
    "user_id": None,
    "status": "running",
    "organization_id": ORG_ID,
    "start_time": "2024-01-01T00:00:00+00:00",
    "end_time": None,
    "message": None,
    "metadata": None,
    "created_at": "2024-01-01T00:00:00+00:00",
    "updated_at": "2024-01-01T00:00:00+00:00",
    "trigger_type": "api",
    "trigger_id": None,
    "parent_run_id": None,
}

REGISTER_PAYLOAD = {
    "name": "my-agent",
    "owner": "team-a",
    "runtime": "python",
}


class TestRegisterAgent:
    @patch("app.routers.agents.assert_agents_limit")
    def test_returns_200(self, mock_limit, client, db):
        db.execute.return_value = make_exec(mapping=AGENT_ROW)
        resp = client.post("/agents/register", json=REGISTER_PAYLOAD)
        assert resp.status_code == 200

    @patch("app.routers.agents.assert_agents_limit")
    def test_response_envelope(self, mock_limit, client, db):
        db.execute.return_value = make_exec(mapping=AGENT_ROW)
        resp = client.post("/agents/register", json=REGISTER_PAYLOAD)
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["id"] == AGENT_ID
        assert body["error"] is None

    @patch("app.routers.agents.assert_agents_limit")
    def test_response_shape_matches_sdk_expectations(self, mock_limit, client, db):
        db.execute.return_value = make_exec(mapping=AGENT_ROW)
        resp = client.post("/agents/register", json=REGISTER_PAYLOAD)
        data = resp.json()["data"]
        assert data["id"] == AGENT_ID
        assert data["name"] == "my-agent"
        assert data["owner"] == "team-a"
        assert data["runtime"] == "python"
        assert data["description"] == "test agent"
        assert data["default_permissions"] == []

    @patch("app.routers.agents.assert_agents_limit")
    def test_missing_required_field_returns_422(self, mock_limit, client, db):
        resp = client.post("/agents/register", json={"name": "x"})
        assert resp.status_code == 422

    def test_requires_auth(self, unauthed_client):
        resp = unauthed_client.post("/agents/register", json=REGISTER_PAYLOAD)
        assert resp.status_code == 401


class TestCreateVersion:
    def test_returns_201_for_new_version(self, client, db):
        db.execute.side_effect = [
            make_exec(first=True),
            make_exec(mapping=VERSION_ROW),
        ]
        resp = client.post(f"/agents/{AGENT_ID}/versions", json={"version": "v1.0"})
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["id"] == VERSION_ID
        assert data["version"] == "v1.0"

    def test_returns_200_for_duplicate_version(self, client, db):
        db.execute.side_effect = [
            make_exec(first=True),
            make_exec(mapping=None),
            make_exec(mapping=VERSION_ROW),
        ]
        resp = client.post(f"/agents/{AGENT_ID}/versions", json={"version": "v1.0"})
        assert resp.status_code == 200

    def test_agent_not_found_returns_404(self, client, db):
        db.execute.return_value = make_exec(first=False)
        resp = client.post(f"/agents/{AGENT_ID}/versions", json={"version": "v1.0"})
        assert resp.status_code == 404


class TestListRuns:
    def test_returns_200_with_list(self, client, db):
        db.execute.side_effect = [
            make_exec(first=True),
            make_exec(all=[RUN_ROW]),
        ]
        resp = client.get(f"/agents/{AGENT_ID}/runs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)
        assert body["data"][0]["id"] == RUN_ID

    def test_agent_not_found_returns_404(self, client, db):
        db.execute.return_value = make_exec(first=False)
        resp = client.get(f"/agents/{AGENT_ID}/runs")
        assert resp.status_code == 404


class TestStartRun:
    def test_returns_201(self, client, db):
        db.execute.side_effect = [
            make_exec(first=True),
            make_exec(mapping=RUN_ROW),
        ]
        resp = client.post(f"/agents/{AGENT_ID}/runs", json={"version_id": VERSION_ID})
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["id"] == RUN_ID
        assert data["status"] == "running"

    def test_agent_not_found_returns_404(self, client, db):
        db.execute.return_value = make_exec(first=False)
        resp = client.post(f"/agents/{AGENT_ID}/runs", json={})
        assert resp.status_code == 404


class TestStartRunTrigger:
    def test_default_trigger_type_is_api(self, client, db):
        db.execute.side_effect = [
            make_exec(first=True),
            make_exec(mapping=RUN_ROW),
        ]
        resp = client.post(f"/agents/{AGENT_ID}/runs", json={})
        assert resp.status_code == 201
        assert resp.json()["data"]["trigger_type"] == "api"

    def test_start_run_with_user_trigger(self, client, db):
        row = {**RUN_ROW, "trigger_type": "user", "trigger_id": "user-abc"}
        db.execute.side_effect = [
            make_exec(first=True),
            make_exec(mapping=row),
        ]
        resp = client.post(
            f"/agents/{AGENT_ID}/runs",
            json={"trigger_type": "user", "trigger_id": "user-abc"},
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["trigger_type"] == "user"
        assert resp.json()["data"]["trigger_id"] == "user-abc"

    def test_agent_trigger_requires_parent_run_id(self, client, db):
        resp = client.post(
            f"/agents/{AGENT_ID}/runs",
            json={"trigger_type": "agent"},
        )
        assert resp.status_code == 422

    def test_agent_trigger_forbids_trigger_id(self, client, db):
        resp = client.post(
            f"/agents/{AGENT_ID}/runs",
            json={
                "trigger_type": "agent",
                "parent_run_id": PARENT_RUN_ID,
                "trigger_id": "x",
            },
        )
        assert resp.status_code == 422

    def test_non_agent_forbids_parent_run_id(self, client, db):
        resp = client.post(
            f"/agents/{AGENT_ID}/runs",
            json={"trigger_type": "api", "parent_run_id": PARENT_RUN_ID},
        )
        assert resp.status_code == 422

    def test_agent_trigger_with_valid_parent(self, client, db):
        row = {**RUN_ROW, "trigger_type": "agent", "parent_run_id": PARENT_RUN_ID}
        db.execute.side_effect = [
            make_exec(first=True),
            make_exec(mapping={"organization_id": ORG_ID}),
            make_exec(mapping=row),
        ]
        resp = client.post(
            f"/agents/{AGENT_ID}/runs",
            json={"trigger_type": "agent", "parent_run_id": PARENT_RUN_ID},
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["trigger_type"] == "agent"

    def test_agent_trigger_cross_org_parent_returns_422(self, client, db):
        other_org = "ffffffff-0000-0000-0000-000000000001"
        db.execute.side_effect = [
            make_exec(first=True),
            make_exec(mapping={"organization_id": other_org}),
        ]
        resp = client.post(
            f"/agents/{AGENT_ID}/runs",
            json={"trigger_type": "agent", "parent_run_id": PARENT_RUN_ID},
        )
        assert resp.status_code == 422

    def test_agent_trigger_nonexistent_parent_returns_422(self, client, db):
        db.execute.side_effect = [
            make_exec(first=True),  # _assert_agent_org passes
            make_exec(mapping=None),  # parent_run_id not found in DB
        ]
        resp = client.post(
            f"/agents/{AGENT_ID}/runs",
            json={"trigger_type": "agent", "parent_run_id": PARENT_RUN_ID},
        )
        assert resp.status_code == 422
