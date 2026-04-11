from unittest.mock import patch

import pytest

from ezop import Agent
from ezop.models import AgentContext, Event

AGENT_RESP = {
    "success": True,
    "error": None,
    "data": {
        "id": "agent-uuid-123",
        "name": "support-bot",
        "owner": "growth-team",
        "runtime": "langchain",
        "description": "Handles support tickets",
        "default_permissions": ["read:tickets"],
    },
}

VERSION_RESP = {
    "success": True,
    "error": None,
    "data": {
        "id": "version-uuid-456",
        "version": "v0.3",
        "permissions": ["read:tickets", "write:replies"],
        "changelog": "Initial release",
    },
}

RUN_RESP = {
    "success": True,
    "error": None,
    "data": {
        "id": "run-uuid-789",
        "status": "running",
        "parent_run_id": None,
        "root_run_id": "run-uuid-789",
        "trigger_type": "unknown",
        "trigger_id": None,
    },
}


def make_agent():
    with (
        patch("ezop.client.EzopClient.register_agent", return_value=AGENT_RESP),
        patch("ezop.client.EzopClient.create_version", return_value=VERSION_RESP),
        patch("ezop.client.EzopClient.start_run", return_value=RUN_RESP),
    ):
        return Agent.init(
            name="support-bot",
            owner="growth-team",
            version="v0.3",
            runtime="langchain",
            description="Handles support tickets",
            default_permissions=["read:tickets"],
            permissions=["read:tickets", "write:replies"],
            changelog="Initial release",
        )


class TestAgentInit:
    def test_returns_agent_instance(self):
        agent = make_agent()
        assert isinstance(agent, Agent)

    def test_model_populated(self):
        agent = make_agent()
        assert agent.model.id == "agent-uuid-123"
        assert agent.model.name == "support-bot"
        assert agent.model.owner == "growth-team"
        assert agent.model.runtime == "langchain"
        assert agent.model.description == "Handles support tickets"
        assert agent.model.default_permissions == ["read:tickets"]

    def test_version_populated(self):
        agent = make_agent()
        assert agent.version.id == "version-uuid-456"
        assert agent.version.agent_id == "agent-uuid-123"
        assert agent.version.version == "v0.3"
        assert agent.version.permissions == ["read:tickets", "write:replies"]
        assert agent.version.changelog == "Initial release"

    def test_run_started_on_init(self):
        agent = make_agent()
        assert agent.current_run is not None
        assert agent.current_run.id == "run-uuid-789"
        assert agent.current_run.status == "running"
        assert agent.current_run.agent_id == "agent-uuid-123"
        assert agent.current_run.version_id == "version-uuid-456"

    def test_run_has_parent_and_root_ids(self):
        parent_resp = {
            "success": True,
            "error": None,
            "data": {
                "id": "run-uuid-789",
                "status": "running",
                "parent_run_id": "parent-run-uuid",
                "root_run_id": "root-run-uuid",
            },
        }
        with (
            patch("ezop.client.EzopClient.register_agent", return_value=AGENT_RESP),
            patch("ezop.client.EzopClient.create_version", return_value=VERSION_RESP),
            patch("ezop.client.EzopClient.start_run", return_value=parent_resp),
        ):
            agent = Agent.init(
                name="support-bot",
                owner="growth-team",
                version="v0.3",
                runtime="langchain",
                parent_run_id="parent-run-uuid",
            )
        assert agent.current_run.parent_run_id == "parent-run-uuid"
        assert agent.current_run.root_run_id == "root-run-uuid"

    def test_calls_register_agent_with_correct_payload(self):
        with (
            patch("ezop.client.EzopClient.register_agent", return_value=AGENT_RESP) as mock_register,
            patch("ezop.client.EzopClient.create_version", return_value=VERSION_RESP),
            patch("ezop.client.EzopClient.start_run", return_value=RUN_RESP),
        ):
            Agent.init(
                name="support-bot",
                owner="growth-team",
                version="v0.3",
                runtime="langchain",
                description="Handles support tickets",
                default_permissions=["read:tickets"],
            )
            mock_register.assert_called_once_with(
                {
                    "name": "support-bot",
                    "owner": "growth-team",
                    "runtime": "langchain",
                    "description": "Handles support tickets",
                    "default_permissions": ["read:tickets"],
                }
            )

    def test_calls_create_version_with_correct_payload(self):
        with (
            patch("ezop.client.EzopClient.register_agent", return_value=AGENT_RESP),
            patch("ezop.client.EzopClient.create_version", return_value=VERSION_RESP) as mock_version,
            patch("ezop.client.EzopClient.start_run", return_value=RUN_RESP),
        ):
            Agent.init(
                name="support-bot",
                owner="growth-team",
                version="v0.3",
                runtime="langchain",
                permissions=["read:tickets"],
                changelog="Initial release",
            )
            mock_version.assert_called_once_with(
                "agent-uuid-123",
                {
                    "version": "v0.3",
                    "permissions": ["read:tickets"],
                    "changelog": "Initial release",
                },
            )

    def test_calls_start_run_with_correct_args(self):
        with (
            patch("ezop.client.EzopClient.register_agent", return_value=AGENT_RESP),
            patch("ezop.client.EzopClient.create_version", return_value=VERSION_RESP),
            patch("ezop.client.EzopClient.start_run", return_value=RUN_RESP) as mock_run,
        ):
            Agent.init(name="support-bot", owner="growth-team", version="v0.3", runtime="langchain")
            mock_run.assert_called_once_with(
                "agent-uuid-123", "version-uuid-456", parent_run_id=None, trigger_type=None, trigger_id=None
            )

    def test_calls_start_run_with_parent_run_id(self):
        with (
            patch("ezop.client.EzopClient.register_agent", return_value=AGENT_RESP),
            patch("ezop.client.EzopClient.create_version", return_value=VERSION_RESP),
            patch("ezop.client.EzopClient.start_run", return_value=RUN_RESP) as mock_run,
        ):
            Agent.init(
                name="support-bot",
                owner="growth-team",
                version="v0.3",
                runtime="langchain",
                parent_run_id="parent-run-uuid",
            )
            mock_run.assert_called_once_with(
                "agent-uuid-123",
                "version-uuid-456",
                parent_run_id="parent-run-uuid",
                trigger_type=None,
                trigger_id=None,
            )

    def test_calls_start_run_with_trigger_type_and_id(self):
        cron_run_resp = {
            **RUN_RESP,
            "data": {**RUN_RESP["data"], "trigger_type": "cron", "trigger_id": "daily-cleanup"},
        }
        with (
            patch("ezop.client.EzopClient.register_agent", return_value=AGENT_RESP),
            patch("ezop.client.EzopClient.create_version", return_value=VERSION_RESP),
            patch("ezop.client.EzopClient.start_run", return_value=cron_run_resp) as mock_run,
        ):
            agent = Agent.init(
                name="support-bot",
                owner="growth-team",
                version="v0.3",
                runtime="langchain",
                trigger_type="cron",
                trigger_id="daily-cleanup",
            )
            mock_run.assert_called_once_with(
                "agent-uuid-123",
                "version-uuid-456",
                parent_run_id=None,
                trigger_type="cron",
                trigger_id="daily-cleanup",
            )
        assert agent.current_run.trigger_type == "cron"
        assert agent.current_run.trigger_id == "daily-cleanup"

    def test_run_has_trigger_type_and_id(self):
        with (
            patch("ezop.client.EzopClient.register_agent", return_value=AGENT_RESP),
            patch("ezop.client.EzopClient.create_version", return_value=VERSION_RESP),
            patch("ezop.client.EzopClient.start_run", return_value=RUN_RESP),
        ):
            agent = Agent.init(name="support-bot", owner="growth-team", version="v0.3", runtime="langchain")
        assert agent.current_run.trigger_type == "unknown"
        assert agent.current_run.trigger_id is None

    def test_optional_fields_default_to_empty(self):
        agent_resp = {**AGENT_RESP, "data": {**AGENT_RESP["data"], "default_permissions": None}}
        version_resp = {**VERSION_RESP, "data": {**VERSION_RESP["data"], "permissions": None}}
        with (
            patch("ezop.client.EzopClient.register_agent", return_value=agent_resp),
            patch("ezop.client.EzopClient.create_version", return_value=version_resp),
            patch("ezop.client.EzopClient.start_run", return_value=RUN_RESP),
        ):
            agent = Agent.init(name="support-bot", owner="growth-team", version="v0.3", runtime="langchain")
            assert agent.model.default_permissions == []
            assert agent.version.permissions == []

    def test_raises_on_api_error(self):
        with patch("ezop.client.EzopClient.register_agent", side_effect=Exception("Ezop API error: 401")):
            with pytest.raises(Exception, match="Ezop API error"):
                Agent.init(name="support-bot", owner="growth-team", version="v0.3", runtime="langchain")


class TestAgentClose:
    def test_close_updates_status(self):
        agent = make_agent()
        end_resp = {"success": True, "error": None, "data": {"status": "success", "metadata": None}}
        with patch("ezop.client.EzopClient.end_run", return_value=end_resp):
            run = agent.close(status="success")
        assert run.status == "success"

    def test_close_failed_status(self):
        agent = make_agent()
        end_resp = {
            "success": True,
            "error": None,
            "data": {"status": "failed", "metadata": {"error": "timeout"}, "message": "Rate limit exceeded"},
        }
        with patch("ezop.client.EzopClient.end_run", return_value=end_resp):
            run = agent.close(status="failed", metadata={"error": "timeout"}, message="Rate limit exceeded")
        assert run.status == "failed"
        assert run.metadata == {"error": "timeout"}
        assert run.message == "Rate limit exceeded"

    def test_close_calls_client_with_correct_args(self):
        agent = make_agent()
        end_resp = {
            "success": True,
            "error": None,
            "data": {"status": "success", "metadata": {"k": "v"}, "message": None},
        }
        with patch("ezop.client.EzopClient.end_run", return_value=end_resp) as mock_end:
            agent.close(status="success", metadata={"k": "v"})
            mock_end.assert_called_once_with(
                "run-uuid-789",
                status="success",
                metadata={"k": "v"},
                message=None,
            )

    def test_close_without_run_raises(self):
        agent = make_agent()
        agent.current_run = None
        with pytest.raises(RuntimeError, match="No active run"):
            agent.close()

    def test_close_sets_current_run_to_none(self):
        agent = make_agent()
        end_resp = {"success": True, "error": None, "data": {"status": "success", "metadata": None}}
        with patch("ezop.client.EzopClient.end_run", return_value=end_resp):
            agent.close(status="success")
        assert agent.current_run is None

    def test_close_marks_agent_as_closed(self):
        agent = make_agent()
        end_resp = {"success": True, "error": None, "data": {"status": "success", "metadata": None}}
        with patch("ezop.client.EzopClient.end_run", return_value=end_resp):
            agent.close(status="success")
        assert agent._closed is True

    def test_close_twice_raises(self):
        agent = make_agent()
        end_resp = {"success": True, "error": None, "data": {"status": "success", "metadata": None}}
        with patch("ezop.client.EzopClient.end_run", return_value=end_resp):
            agent.close(status="success")
        with pytest.raises(RuntimeError, match="closed"):
            agent.close(status="success")

    def test_emit_after_close_raises(self):
        agent = make_agent()
        end_resp = {"success": True, "error": None, "data": {"status": "success", "metadata": None}}
        with patch("ezop.client.EzopClient.end_run", return_value=end_resp):
            agent.close(status="success")
        with pytest.raises(RuntimeError, match="closed"):
            agent.emit(name="llm.request", category="llm")

    def test_span_after_close_raises(self):
        agent = make_agent()
        end_resp = {"success": True, "error": None, "data": {"status": "success", "metadata": None}}
        with patch("ezop.client.EzopClient.end_run", return_value=end_resp):
            agent.close(status="success")
        with pytest.raises(RuntimeError, match="closed"):
            with agent.span("llm.call"):
                pass

    def test_close_returns_final_run(self):
        agent = make_agent()
        end_resp = {"success": True, "error": None, "data": {"status": "success", "metadata": None}}
        with patch("ezop.client.EzopClient.end_run", return_value=end_resp):
            run = agent.close(status="success")
        assert run.status == "success"
        assert run.id == "run-uuid-789"


class TestAgentEmit:
    def test_emit_returns_event(self):
        agent = make_agent()
        with patch("ezop.client.EzopClient.emit_event", return_value={}):
            event = agent.emit(name="llm.call", category="llm")
        assert isinstance(event, Event)
        assert event.run_id == "run-uuid-789"
        assert event.name == "llm.call"
        assert event.category == "llm"

    def test_emit_generates_event_id(self):
        agent = make_agent()
        with patch("ezop.client.EzopClient.emit_event", return_value={}):
            event = agent.emit(name="llm.call", category="llm")
        assert event.id is not None

    def test_emit_sets_timestamp(self):
        agent = make_agent()
        with patch("ezop.client.EzopClient.emit_event", return_value={}):
            event = agent.emit(name="llm.call", category="llm")
        assert event.timestamp is not None

    def test_emit_optional_fields(self):
        agent = make_agent()
        with patch("ezop.client.EzopClient.emit_event", return_value={}):
            event = agent.emit(
                name="llm.response",
                category="llm",
                type="llm_response",
                subtype="chain_of_thought",
                span_id="span-123",
                iteration_id=2,
                input={"prompt": "hello"},
                output={"text": "hi"},
                metadata={"model": "claude"},
                error={"message": "oops"},
            )
        assert event.span_id == "span-123"
        assert event.type == "llm_response"
        assert event.subtype == "chain_of_thought"
        assert event.iteration_id == 2
        assert event.input == {"prompt": "hello"}
        assert event.output == {"text": "hi"}
        assert event.metadata == {"model": "claude"}
        assert event.error == {"message": "oops"}

    def test_emit_span_id_optional(self):
        agent = make_agent()
        with patch("ezop.client.EzopClient.emit_event", return_value={}):
            event = agent.emit(name="llm.call", category="llm")
        assert event.span_id is None

    def test_emit_calls_client_with_correct_payload(self):
        agent = make_agent()
        with patch("ezop.client.EzopClient.emit_event", return_value={}) as mock_emit:
            agent.emit(
                name="llm.response",
                category="llm",
                type="llm_response",
                subtype="chain_of_thought",
                span_id="span-123",
                iteration_id=1,
                input={"prompt": "hello"},
                output={"text": "hi"},
                metadata={"model": "claude"},
                error={"message": "oops"},
            )
        call_args = mock_emit.call_args
        assert call_args[0][0] == "run-uuid-789"
        body = call_args[0][1]
        assert body["name"] == "llm.response"
        assert body["category"] == "llm"
        assert body["type"] == "llm_response"
        assert body["subtype"] == "chain_of_thought"
        assert body["span_id"] == "span-123"
        assert body["iteration_id"] == 1
        assert body["input"] == {"prompt": "hello"}
        assert body["output"] == {"text": "hi"}
        assert body["metadata"] == {"model": "claude"}
        assert body["error"] == {"message": "oops"}

    def test_emit_omits_none_fields_from_payload(self):
        agent = make_agent()
        with patch("ezop.client.EzopClient.emit_event", return_value={}) as mock_emit:
            agent.emit(name="llm.request", category="llm")
        body = mock_emit.call_args[0][1]
        assert "span_id" not in body
        assert "type" not in body
        assert "subtype" not in body
        assert "iteration_id" not in body
        assert "input" not in body
        assert "output" not in body
        assert "metadata" not in body
        assert "error" not in body

    def test_emit_run_id_passed_as_path_argument(self):
        agent = make_agent()
        with patch("ezop.client.EzopClient.emit_event", return_value={}) as mock_emit:
            agent.emit(name="llm.call", category="llm")
        run_id_arg = mock_emit.call_args[0][0]
        assert run_id_arg == "run-uuid-789"

    def test_emit_without_run_raises(self):
        agent = make_agent()
        agent.current_run = None
        with pytest.raises(RuntimeError, match="No active run"):
            agent.emit(name="llm.call", category="llm")

    def test_emit_auto_links_to_current_span(self):
        agent = make_agent()
        agent.current_run._current_span_id = "active-span-id"
        with patch("ezop.client.EzopClient.emit_event", return_value={}) as mock_emit:
            event = agent.emit(name="decision", category="reasoning")
        assert event.span_id == "active-span-id"
        assert mock_emit.call_args[0][1]["span_id"] == "active-span-id"

    def test_emit_explicit_span_id_overrides_current_span(self):
        agent = make_agent()
        agent.current_run._current_span_id = "active-span-id"
        with patch("ezop.client.EzopClient.emit_event", return_value={}):
            event = agent.emit(name="decision", category="reasoning", span_id="explicit-span")
        assert event.span_id == "explicit-span"


class TestAgentSpan:
    def test_span_calls_create_span_on_enter(self):
        agent = make_agent()
        with (
            patch("ezop.client.EzopClient.create_span", return_value={}) as mock_create,
            patch("ezop.client.EzopClient.end_span", return_value={}),
        ):
            with agent.span("llm.call"):
                pass
        mock_create.assert_called_once()

    def test_span_calls_end_span_on_exit(self):
        agent = make_agent()
        with (
            patch("ezop.client.EzopClient.create_span", return_value={}),
            patch("ezop.client.EzopClient.end_span", return_value={}) as mock_end,
        ):
            with agent.span("llm.call"):
                pass
        mock_end.assert_called_once()

    def test_span_create_payload_contains_id_name_start_time(self):
        agent = make_agent()
        with (
            patch("ezop.client.EzopClient.create_span", return_value={}) as mock_create,
            patch("ezop.client.EzopClient.end_span", return_value={}),
        ):
            with agent.span("llm.call") as s:
                pass
        run_id, body = mock_create.call_args[0]
        assert run_id == "run-uuid-789"
        assert body["id"] == s.span_id
        assert body["name"] == "llm.call"
        assert "start_time" in body

    def test_span_end_payload_contains_end_time(self):
        agent = make_agent()
        with (
            patch("ezop.client.EzopClient.create_span", return_value={}),
            patch("ezop.client.EzopClient.end_span", return_value={}) as mock_end,
        ):
            with agent.span("llm.call"):
                pass
        span_id, body = mock_end.call_args[0]
        assert "end_time" in body

    def test_span_end_called_with_correct_span_id(self):
        agent = make_agent()
        with (
            patch("ezop.client.EzopClient.create_span", return_value={}),
            patch("ezop.client.EzopClient.end_span", return_value={}) as mock_end,
        ):
            with agent.span("llm.call") as s:
                pass
        span_id, _ = mock_end.call_args[0]
        assert span_id == s.span_id

    def test_span_create_omits_parent_id_when_no_enclosing_span(self):
        agent = make_agent()
        with (
            patch("ezop.client.EzopClient.create_span", return_value={}) as mock_create,
            patch("ezop.client.EzopClient.end_span", return_value={}),
        ):
            with agent.span("llm.call"):
                pass
        body = mock_create.call_args[0][1]
        assert "parent_id" not in body

    def test_span_does_not_suppress_exception(self):
        agent = make_agent()
        with (
            patch("ezop.client.EzopClient.create_span", return_value={}),
            patch("ezop.client.EzopClient.end_span", return_value={}),
        ):
            with pytest.raises(RuntimeError, match="boom"):
                with agent.span("llm.call"):
                    raise RuntimeError("boom")

    def test_span_end_called_even_on_exception(self):
        agent = make_agent()
        with (
            patch("ezop.client.EzopClient.create_span", return_value={}),
            patch("ezop.client.EzopClient.end_span", return_value={}) as mock_end,
        ):
            with pytest.raises(ValueError):
                with agent.span("llm.call"):
                    raise ValueError("bad input")
        mock_end.assert_called_once()

    def test_span_sets_current_span_id_during_execution(self):
        agent = make_agent()
        captured = {}
        with (
            patch("ezop.client.EzopClient.create_span", return_value={}),
            patch("ezop.client.EzopClient.end_span", return_value={}),
        ):
            with agent.span("llm.call") as s:
                captured["during"] = agent.current_run._current_span_id
        assert captured["during"] == s.span_id

    def test_span_restores_current_span_id_after_exit(self):
        agent = make_agent()
        agent.current_run._current_span_id = "outer-span"
        with (
            patch("ezop.client.EzopClient.create_span", return_value={}),
            patch("ezop.client.EzopClient.end_span", return_value={}),
        ):
            with agent.span("llm.call"):
                pass
        assert agent.current_run._current_span_id == "outer-span"

    def test_nested_spans_set_parent_id(self):
        agent = make_agent()
        with (
            patch("ezop.client.EzopClient.create_span", return_value={}) as mock_create,
            patch("ezop.client.EzopClient.end_span", return_value={}),
        ):
            with agent.span("outer") as outer:
                with agent.span("inner") as inner:
                    pass
        inner_call_body = mock_create.call_args_list[1][0][1]
        assert inner_call_body["parent_id"] == outer.span_id
        assert inner_call_body["id"] == inner.span_id

    def test_nested_spans_restore_parent_on_exit(self):
        agent = make_agent()
        with (
            patch("ezop.client.EzopClient.create_span", return_value={}),
            patch("ezop.client.EzopClient.end_span", return_value={}),
        ):
            with agent.span("outer") as outer:
                with agent.span("inner"):
                    pass
                assert agent.current_run._current_span_id == outer.span_id

    def test_span_without_run_raises(self):
        agent = make_agent()
        agent.current_run = None
        with pytest.raises(RuntimeError, match="No active run"):
            with agent.span("llm.call"):
                pass

    def test_span_raises_if_current_span_id_matches_own_id(self):
        agent = make_agent()
        span = agent.span("llm.call")
        # Force a situation where _current_span_id matches the span's own id
        agent.current_run._current_span_id = span.span_id
        with pytest.raises(RuntimeError, match="cycle detected"):
            span.__enter__()

    def test_span_metadata_sent_in_create_payload(self):
        agent = make_agent()
        with (
            patch("ezop.client.EzopClient.create_span", return_value={}) as mock_create,
            patch("ezop.client.EzopClient.end_span", return_value={}),
        ):
            with agent.span("llm.call", metadata={"model": "claude"}):
                pass
        body = mock_create.call_args[0][1]
        assert body["metadata"] == {"model": "claude"}

    def test_emit_after_span_exits_has_no_span_id(self):
        agent = make_agent()
        with (
            patch("ezop.client.EzopClient.create_span", return_value={}),
            patch("ezop.client.EzopClient.end_span", return_value={}),
            patch("ezop.client.EzopClient.emit_event", return_value={}) as mock_emit,
        ):
            with agent.span("llm.call"):
                pass
            agent.emit(name="after", category="reasoning")
        body = mock_emit.call_args[0][1]
        assert "span_id" not in body

    def test_emit_inside_span_auto_links_span_id(self):
        agent = make_agent()
        with (
            patch("ezop.client.EzopClient.create_span", return_value={}),
            patch("ezop.client.EzopClient.end_span", return_value={}),
            patch("ezop.client.EzopClient.emit_event", return_value={}) as mock_emit,
        ):
            with agent.span("llm.call") as s:
                agent.emit(name="token.count", category="llm")
        body = mock_emit.call_args[0][1]
        assert body["span_id"] == s.span_id


class TestAgentContext:
    def test_has_name_and_run_id(self):
        ctx = AgentContext(name="orchestrator", run_id="run-uuid-789")
        assert ctx.name == "orchestrator"
        assert ctx.run_id == "run-uuid-789"

    def test_is_immutable(self):
        ctx = AgentContext(name="orchestrator", run_id="run-uuid-789")
        with pytest.raises(Exception):
            ctx.name = "other"  # type: ignore[misc]


class TestGetContext:
    def test_returns_agent_context(self):
        agent = make_agent()
        ctx = agent.get_context()
        assert isinstance(ctx, AgentContext)

    def test_name_matches_agent_model(self):
        agent = make_agent()
        ctx = agent.get_context()
        assert ctx.name == "support-bot"

    def test_run_id_matches_active_run(self):
        agent = make_agent()
        ctx = agent.get_context()
        assert ctx.run_id == "run-uuid-789"

    def test_raises_when_no_active_run(self):
        agent = make_agent()
        agent.current_run = None
        with pytest.raises(RuntimeError, match="No active run"):
            agent.get_context()

    def test_raises_after_close(self):
        agent = make_agent()
        end_resp = {"success": True, "error": None, "data": {"status": "success", "metadata": None}}
        with patch("ezop.client.EzopClient.end_run", return_value=end_resp):
            agent.close(status="success")
        with pytest.raises(RuntimeError, match="closed"):
            agent.get_context()
