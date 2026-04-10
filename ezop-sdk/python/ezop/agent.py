import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .client import EzopClient
from .models import AgentModel, AgentRun, AgentVersion, Event

logger = logging.getLogger(__name__)


class Span:
    """Context manager that tracks a scoped duration as a span record.

    On enter: creates a span record with start_time and optional parent_id.
    On exit:  updates the span record with end_time.

    Nested spans automatically propagate context — each child span records
    the enclosing span's id as its parent_id, enabling tree reconstruction.
    """

    def __init__(
        self,
        agent: "Agent",
        name: str,
        *,
        metadata: Optional[dict] = None,
    ):
        self._agent = agent
        self.name = name
        self.span_id = str(uuid.uuid4())
        self._metadata = metadata
        self._parent_id: Optional[str] = None
        self._run: Optional[AgentRun] = None

    def __enter__(self) -> "Span":
        self._agent._check_active()
        if self._agent.current_run is None:
            raise RuntimeError("No active run.")

        # Snapshot run so this span is bound to one run for its entire lifetime.
        # parent_id always comes from _current_span_id on the same run, so
        # parent and child spans are guaranteed to share the same run_id.
        self._run = self._agent.current_run
        self._parent_id = self._run._current_span_id

        # Guard: a span cannot be its own parent.
        if self._parent_id == self.span_id:
            raise RuntimeError(f"Span cycle detected: span {self.span_id} cannot be its own parent.")

        self._run._current_span_id = self.span_id

        body: dict = {
            "id": self.span_id,
            "name": self.name,
            "start_time": datetime.now(timezone.utc).isoformat(),
        }
        if self._parent_id is not None:
            body["parent_id"] = self._parent_id
        if self._metadata is not None:
            body["metadata"] = self._metadata

        self._agent.client.create_span(self._run.id, body)
        logger.debug(
            "Span created name=%s span_id=%s parent_id=%s",
            self.name,
            self.span_id,
            self._parent_id,
        )
        return self

    def __exit__(self, _exc_type, _exc_val, _tb) -> bool:
        assert self._run is not None
        self._agent.client.end_span(
            self.span_id,
            {
                "end_time": datetime.now(timezone.utc).isoformat(),
            },
        )
        logger.debug("Span ended span_id=%s", self.span_id)
        self._run._current_span_id = self._parent_id
        return False


class Agent:
    def __init__(self, model: AgentModel, version: AgentVersion):
        self.model = model
        self.version = version
        self.client = EzopClient()
        self.current_run: Optional[AgentRun] = None
        self._closed: bool = False

    def _check_active(self) -> None:
        if self._closed:
            raise RuntimeError("Agent has been closed and can no longer be used.")

    @classmethod
    def init(
        cls,
        name: str,
        owner: str,
        version: str,
        runtime: str,
        *,
        description: Optional[str] = None,
        default_permissions: Optional[list[str]] = None,
        permissions: Optional[list[str]] = None,
        changelog: Optional[str] = None,
        trigger_type: Optional[str] = None,
        trigger_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
    ) -> "Agent":
        """
        Initialize an Ezop agent and register it with the Ezop platform.
        Creates the agent record and a corresponding version record.
        """
        logger.info(
            "Initializing agent name=%s owner=%s version=%s runtime=%s",
            name,
            owner,
            version,
            runtime,
        )
        client = EzopClient()

        agent_data = client.register_agent(
            {
                "name": name,
                "owner": owner,
                "runtime": runtime,
                "description": description,
                "default_permissions": default_permissions,
            }
        )["data"]

        model = AgentModel(
            id=agent_data["id"],
            name=agent_data["name"],
            owner=agent_data["owner"],
            runtime=agent_data.get("runtime"),
            description=agent_data.get("description"),
            default_permissions=agent_data.get("default_permissions") or [],
        )
        logger.debug("Agent model built id=%s", model.id)

        version_data = client.create_version(
            model.id,
            {
                "version": version,
                "permissions": permissions,
                "changelog": changelog,
            },
        )["data"]

        agent_version = AgentVersion(
            id=version_data["id"],
            agent_id=model.id,
            version=version_data["version"],
            permissions=version_data.get("permissions") or [],
            changelog=version_data.get("changelog"),
        )
        logger.debug("Agent version built id=%s", agent_version.id)

        agent = cls(model, agent_version)

        if parent_run_id is not None:
            if trigger_type is not None and trigger_type != "agent":
                raise ValueError(
                    f"trigger_type must be 'agent' when parent_run_id is set, got {trigger_type!r}"
                )
            trigger_type = "agent"

        logger.info("Starting run for agent id=%s version_id=%s", model.id, agent_version.id)
        run_data = client.start_run(
            model.id,
            agent_version.id,
            trigger_type=trigger_type,
            trigger_id=trigger_id,
            parent_run_id=parent_run_id,
        )["data"]
        agent.current_run = AgentRun(
            id=run_data["id"],
            agent_id=model.id,
            version_id=agent_version.id,
            status=run_data.get("status", "running"),
        )
        logger.info(
            "Agent initialized id=%s version_id=%s run_id=%s",
            model.id,
            agent_version.id,
            agent.current_run.id,
        )
        return agent

    def close(
        self,
        status: str = "success",
        metadata: Optional[dict] = None,
        message: Optional[str] = None,
    ) -> AgentRun:
        """Close the current run and record its outcome.

        Args:
            status: Final status of the run (e.g. "success", "failed", "partial", "cancelled").
            message: Optional human-readable message, e.g. a failure reason.
        """
        self._check_active()
        if self.current_run is None:
            logger.error("close called with no active run")
            raise RuntimeError("No active run.")

        logger.info("Ending run id=%s status=%s", self.current_run.id, status)
        run_data = self.client.end_run(
            self.current_run.id,
            status=status,
            metadata=metadata,
            message=message,
        )["data"]
        self.current_run.status = run_data.get("status", status)
        self.current_run.metadata = run_data.get("metadata")
        self.current_run.message = run_data.get("message")
        logger.debug("Run ended id=%s status=%s", self.current_run.id, self.current_run.status)
        closed_run = self.current_run
        self._closed = True
        self.current_run = None
        return closed_run

    def emit(
        self,
        name: str,
        category: str,
        *,
        span_id: Optional[str] = None,
        type: Optional[str] = None,
        subtype: Optional[str] = None,
        iteration_id: Optional[int] = None,
        input: Optional[Any] = None,
        output: Optional[Any] = None,
        metadata: Optional[dict] = None,
        error: Optional[Any] = None,
    ) -> Event:
        """Emit a point-in-time event on the current run.

        If called inside a ``span``, the event is automatically linked to that
        span via ``span_id``.
        """
        self._check_active()
        if self.current_run is None:
            raise RuntimeError("No active run.")

        resolved_span_id = span_id if span_id is not None else self.current_run._current_span_id

        event = Event(
            id=str(uuid.uuid4()),
            run_id=self.current_run.id,
            span_id=resolved_span_id,
            name=name,
            category=category,
            type=type,
            subtype=subtype,
            iteration_id=iteration_id,
            timestamp=datetime.now(timezone.utc),
            input=input,
            output=output,
            metadata=metadata,
            error=error,
        )

        body: dict = {
            "id": event.id,
            "name": event.name,
            "category": event.category,
            "timestamp": event.timestamp.isoformat(),
        }
        if event.span_id is not None:
            body["span_id"] = event.span_id
        if event.type is not None:
            body["type"] = event.type
        if event.subtype is not None:
            body["subtype"] = event.subtype
        if event.iteration_id is not None:
            body["iteration_id"] = event.iteration_id
        if event.input is not None:
            body["input"] = event.input
        if event.output is not None:
            body["output"] = event.output
        if event.metadata is not None:
            body["metadata"] = event.metadata
        if event.error is not None:
            body["error"] = event.error

        self.client.emit_event(self.current_run.id, body)
        logger.debug(
            "Event emitted id=%s name=%s span_id=%s",
            event.id,
            event.name,
            event.span_id,
        )
        return event

    def span(
        self,
        name: str,
        *,
        metadata: Optional[dict] = None,
    ) -> Span:
        """Return a context manager that tracks a scoped duration.

        Usage::

            with agent.span("llm.call") as s:
                result = llm.generate(prompt)
        """
        return Span(self, name, metadata=metadata)
