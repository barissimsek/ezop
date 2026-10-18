"""
Integration tests for the Ezop SDK.

These tests use the `responses` library to intercept HTTP calls at the network
level, exercising the full stack (Agent → EzopClient → requests → HTTP parsing)
without hitting a real server.

To run against the real Ezop API, set EZOP_API_KEY and EZOP_API_URL in your
environment and run:

    pytest tests/test_integration.py -m live -v

Live tests are skipped by default unless EZOP_API_KEY is present.
"""

import pytest
import responses as responses_lib

from ezop import Agent
from ezop.config import Config

BASE_URL = Config.EZOP_API_URL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AGENT_DATA = {
    "id": "integ-agent-001",
    "name": "integ-bot",
    "owner": "integ-team",
    "runtime": "langchain",
    "description": "Integration test agent",
    "default_permissions": ["read:logs"],
}

_VERSION_DATA = {
    "id": "integ-version-001",
    "agent_id": "integ-agent-001",
    "version": "v1.0",
    "permissions": ["read:logs", "write:reports"],
    "changelog": "Integration test version",
}

_RUN_DATA = {
    "id": "integ-run-001",
    "status": "running",
}

_END_RUN_DATA = {
    "id": "integ-run-001",
    "status": "success",
    "metadata": None,
}


def _wrap(data):
    return {"success": True, "data": data, "error": None}


AGENT_PAYLOAD = _wrap(_AGENT_DATA)
VERSION_PAYLOAD = _wrap(_VERSION_DATA)
RUN_PAYLOAD = _wrap(_RUN_DATA)
END_RUN_PAYLOAD = _wrap(_END_RUN_DATA)


def _register_init_endpoints():
    """Register the three endpoints called by Agent.init()."""
    responses_lib.add(responses_lib.POST, f"{BASE_URL}/agents/register", json=AGENT_PAYLOAD, status=201)
    responses_lib.add(
        responses_lib.POST, f"{BASE_URL}/agents/integ-agent-001/versions", json=VERSION_PAYLOAD, status=201
    )
    responses_lib.add(responses_lib.POST, f"{BASE_URL}/agents/integ-agent-001/runs", json=RUN_PAYLOAD, status=201)


def register_mock_endpoints():
    """Register all mock HTTP endpoints for a complete agent lifecycle."""
    _register_init_endpoints()
    responses_lib.add(responses_lib.PATCH, f"{BASE_URL}/runs/integ-run-001", json=END_RUN_PAYLOAD, status=200)


# ---------------------------------------------------------------------------
# HTTP-level integration tests (no real network — responses intercepts)
# ---------------------------------------------------------------------------


class TestAgentInitHTTP:
    """Verify Agent.init() sends correct HTTP requests and parses responses."""

    @responses_lib.activate
    def test_register_agent_url_and_method(self):
        _register_init_endpoints()
        Agent.init(name="integ-bot", owner="integ-team", version="v1.0", runtime="langchain")
        assert responses_lib.calls[0].request.method == "POST"
        assert responses_lib.calls[0].request.url == f"{BASE_URL}/agents/register"

    @responses_lib.activate
    def test_register_agent_request_body(self):
        import json

        _register_init_endpoints()
        Agent.init(
            name="integ-bot",
            owner="integ-team",
            version="v1.0",
            runtime="langchain",
            description="Integration test agent",
            default_permissions=["read:logs"],
        )
        body = json.loads(responses_lib.calls[0].request.body)
        assert body["name"] == "integ-bot"
        assert body["owner"] == "integ-team"
        assert body["runtime"] == "langchain"
        assert body["description"] == "Integration test agent"
        assert body["default_permissions"] == ["read:logs"]

    @responses_lib.activate
    def test_register_agent_auth_header(self):
        _register_init_endpoints()
        Agent.init(name="integ-bot", owner="integ-team", version="v1.0", runtime="langchain")
        auth = responses_lib.calls[0].request.headers.get("Authorization", "")
        assert auth.startswith("Bearer ")

    @responses_lib.activate
    def test_create_version_url_uses_agent_id(self):
        _register_init_endpoints()
        Agent.init(name="integ-bot", owner="integ-team", version="v1.0", runtime="langchain")
        assert responses_lib.calls[1].request.url == f"{BASE_URL}/agents/integ-agent-001/versions"

    @responses_lib.activate
    def test_create_version_request_body(self):
        import json

        _register_init_endpoints()
        Agent.init(
            name="integ-bot",
            owner="integ-team",
            version="v1.0",
            runtime="langchain",
            permissions=["read:logs", "write:reports"],
            changelog="Integration test version",
        )
        body = json.loads(responses_lib.calls[1].request.body)
        assert body["version"] == "v1.0"
        assert body["permissions"] == ["read:logs", "write:reports"]
        assert body["changelog"] == "Integration test version"

    @responses_lib.activate
    def test_init_starts_run_url_and_method(self):
        _register_init_endpoints()
        Agent.init(name="integ-bot", owner="integ-team", version="v1.0", runtime="langchain")
        run_call = responses_lib.calls[2]
        assert run_call.request.method == "POST"
        assert run_call.request.url == f"{BASE_URL}/agents/integ-agent-001/runs"

    @responses_lib.activate
    def test_init_starts_run_request_body_contains_version_id(self):
        import json

        _register_init_endpoints()
        Agent.init(name="integ-bot", owner="integ-team", version="v1.0", runtime="langchain")
        body = json.loads(responses_lib.calls[2].request.body)
        assert body["version_id"] == "integ-version-001"

    @responses_lib.activate
    def test_init_populates_current_run(self):
        _register_init_endpoints()
        agent = Agent.init(name="integ-bot", owner="integ-team", version="v1.0", runtime="langchain")
        assert agent.current_run.id == "integ-run-001"
        assert agent.current_run.status == "running"
        assert agent.current_run.agent_id == "integ-agent-001"
        assert agent.current_run.version_id == "integ-version-001"

    @responses_lib.activate
    def test_agent_built_correctly_from_responses(self):
        _register_init_endpoints()
        agent = Agent.init(
            name="integ-bot",
            owner="integ-team",
            version="v1.0",
            runtime="langchain",
            description="Integration test agent",
            default_permissions=["read:logs"],
            permissions=["read:logs", "write:reports"],
            changelog="Integration test version",
        )
        assert agent.model.id == "integ-agent-001"
        assert agent.model.name == "integ-bot"
        assert agent.model.runtime == "langchain"
        assert agent.version.id == "integ-version-001"
        assert agent.version.version == "v1.0"
        assert agent.version.permissions == ["read:logs", "write:reports"]

    @responses_lib.activate
    def test_api_400_raises_exception(self):
        responses_lib.add(
            responses_lib.POST, f"{BASE_URL}/agents/register", json={"error": "invalid payload"}, status=400
        )
        with pytest.raises(Exception, match="Ezop API error"):
            Agent.init(name="integ-bot", owner="integ-team", version="v1.0", runtime="langchain")

    @responses_lib.activate
    def test_api_401_raises_exception(self):
        responses_lib.add(responses_lib.POST, f"{BASE_URL}/agents/register", json={"error": "unauthorized"}, status=401)
        with pytest.raises(Exception, match="Ezop API error"):
            Agent.init(name="integ-bot", owner="integ-team", version="v1.0", runtime="langchain")

    @responses_lib.activate
    def test_api_500_raises_exception(self):
        responses_lib.add(responses_lib.POST, f"{BASE_URL}/agents/register", json={"error": "server error"}, status=500)
        with pytest.raises(Exception, match="Ezop API error"):
            Agent.init(name="integ-bot", owner="integ-team", version="v1.0", runtime="langchain")


class TestCloseHTTP:
    """Verify agent.close() sends correct HTTP requests."""

    def _make_agent(self):
        _register_init_endpoints()
        return Agent.init(name="integ-bot", owner="integ-team", version="v1.0", runtime="langchain")

    @responses_lib.activate
    def test_close_url_and_method(self):
        agent = self._make_agent()
        responses_lib.add(responses_lib.PATCH, f"{BASE_URL}/runs/integ-run-001", json=END_RUN_PAYLOAD, status=200)
        agent.close(status="success")
        last_call = responses_lib.calls[-1]
        assert last_call.request.method == "PATCH"
        assert last_call.request.url == f"{BASE_URL}/runs/integ-run-001"

    @responses_lib.activate
    def test_close_request_body(self):
        import json

        agent = self._make_agent()
        responses_lib.add(responses_lib.PATCH, f"{BASE_URL}/runs/integ-run-001", json=END_RUN_PAYLOAD, status=200)
        agent.close(status="success", metadata={"user_id": "u-42"})
        body = json.loads(responses_lib.calls[-1].request.body)
        assert body["status"] == "success"
        assert body["metadata"] == {"user_id": "u-42"}

    @responses_lib.activate
    def test_close_body_omits_none_fields(self):
        import json

        agent = self._make_agent()
        responses_lib.add(
            responses_lib.PATCH,
            f"{BASE_URL}/runs/integ-run-001",
            json=_wrap({"id": "integ-run-001", "status": "failed", "metadata": None}),
            status=200,
        )
        agent.close(status="failed")
        body = json.loads(responses_lib.calls[-1].request.body)
        assert "metadata" not in body

    @responses_lib.activate
    def test_close_updates_agent_state(self):
        agent = self._make_agent()
        responses_lib.add(responses_lib.PATCH, f"{BASE_URL}/runs/integ-run-001", json=END_RUN_PAYLOAD, status=200)
        run = agent.close(status="success")
        assert run.status == "success"

    @responses_lib.activate
    def test_full_lifecycle(self):
        """Agent.init() (register + version + run) + close = 4 HTTP calls."""
        register_mock_endpoints()
        agent = Agent.init(
            name="integ-bot",
            owner="integ-team",
            version="v1.0",
            runtime="langchain",
            description="Integration test agent",
            default_permissions=["read:logs"],
            permissions=["read:logs", "write:reports"],
            changelog="Integration test version",
        )
        assert agent.current_run.status == "running"
        result = agent.close(status="success")
        assert result.status == "success"
        assert len(responses_lib.calls) == 4
