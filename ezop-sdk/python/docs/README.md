# Ezop Python SDK

## Installation

```bash
pip install ezop
```

## Configuration

```bash
export EZOP_API_KEY=your-key
export EZOP_API_URL=http://localhost:13000
```

See [starter.py](starter.py) for a complete working example.

---

## Usage

### Initialize the agent

```python
from ezop import Agent
```

### Multi-agent workflows

Use `agent.get_context()` in the parent to expose its run ID, then pass it to the child however your architecture requires (environment variable, HTTP header, message queue payload, etc.).

```python
# ── Parent agent ──────────────────────────────────────────────────────────────
parent = Agent.init(
    name="orchestrator",
    owner="my-team",
    version="v1.0",
    runtime="python",
    trigger_type="api",
    trigger_id="/api/v1/pipeline",
)

ctx = parent.get_context()
# ctx.name    → "orchestrator"
# ctx.run_id  → the active run ID

# ── Child agent (separate process or service) ─────────────────────────────────
child = Agent.init(
    name="researcher",
    owner="my-team",
    version="v1.0",
    runtime="python",
    trigger_type="agent",
    trigger_id=ctx.run_id,
    parent_run_id=ctx.run_id,
)

child.close(status="success")
parent.close(status="success")
```

All runs in a chain share the same `root_run_id`, assigned automatically by the platform. Access it after init via `agent.current_run.root_run_id`.

## API Reference

### `Agent.init()`

Registers the agent and its version with the Ezop platform, starts a run, and returns an `Agent` instance.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `name` | `str` | Yes | Agent name. Together with `owner`, uniquely identifies the agent on the platform. |
| `owner` | `str` | Yes | Team or user that owns the agent. |
| `version` | `str` | Yes | Version string (e.g. `"v1.2.0"`). A new version is registered if it does not exist yet. |
| `runtime` | `str` | Yes | Runtime or framework used (e.g. `"langchain"`, `"crew"`, `"custom"`). |
| `description` | `str` | No | Human-readable description of the agent. |
| `default_permissions` | `list[str]` | No | Permissions granted to all versions of this agent by default. |
| `permissions` | `list[str]` | No | Permissions granted to this specific version. |
| `changelog` | `str` | No | Description of what changed in this version. |
| `trigger_type` | `str` | No | What triggered this run. One of `"api"`, `"agent"`, `"user"`, `"cron"`, `"webhook"`, `"unknown"` (default). |
| `trigger_id` | `str` | No | Identifier of the trigger source (e.g. API path, user ID, cron job name, webhook source). |
| `parent_run_id` | `str` | No | Run ID of the parent agent. Required when `trigger_type="agent"`. |

---

### `Agent.close()`

Closes the current run and records its outcome.

```python
agent.close(
    status="success",
    message=None,
    metadata={"user_id": "u-123"},
)
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `status` | `str` | Yes | Final status of the run. One of `"success"`, `"failed"`, `"partial"`, `"canceled"`, `"running"`. |
| `message` | `str` | No | Human-readable message describing the outcome, e.g. a failure reason. |
| `metadata` | `dict` | No | Any arbitrary JSON-serialisable data you want to attach to the run (e.g. user context, request identifiers, feature flags). |

---

### `Agent.get_context()`

Returns an `AgentContext` snapshot of the current run for passing to child agents.

```python
ctx = agent.get_context()
# ctx.name    → agent name (str)
# ctx.run_id  → active run ID (str)
```

Raises `RuntimeError` if called with no active run or after `close()`.

The returned object is immutable. Pass `ctx.run_id` to child agents via whatever transport your architecture uses (env var, HTTP header, message body, etc.). In the child, provide it as `parent_run_id`.

---

### `Agent.emit()`

Emits an event on the current run. Events capture discrete steps within a run such as LLM calls, tool invocations, or retrieval operations.

```python
agent.emit(
    name="llm.response",
    category="llm",
    type="llm_response",
    subtype="chain_of_thought",  # optional
    span_id="...",               # optional, auto-set inside a span
    iteration_id=1,              # optional, for loop tracking
    input={"prompt": "hello"},
    output={"text": "hi"},
    metadata={
        "model": "claude-sonnet-4-6",
        "usage": {
            "input_tokens": 12,
            "output_tokens": 8,
        },
    },
    error={"message": "..."},    # optional, jsonb
)
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `name` | `str` | Yes | Event name. |
| `category` | `str` | Yes | Top-level category — must be one of the values below. |
| `type` | `str` | No | Specific action type — must match `category` (see table below). |
| `subtype` | `str` | No | Optional detail layer — see valid values below. |
| `span_id` | `str` | No | Links this event to a span. Auto-set when emitting inside a `span` context manager. |
| `iteration_id` | `int` | No | Loop iteration counter, useful for agentic loops. |
| `input` | `any` | No | Input passed to this step. |
| `output` | `any` | No | Output produced by this step. |
| `metadata` | `dict` | No | Any arbitrary JSON-serialisable data. For LLM events, include `usage.input_tokens` and `usage.output_tokens` for cost tracking (see below). |
| `error` | `dict` | No | Error details as a JSON object, e.g. `{"message": "timeout"}`. |

**`category` values and their valid `type` values:**

| `category` | `type` values |
|---|---|
| `llm` | `llm_request`, `llm_response` |
| `tool` | `tool_call_started`, `tool_call_completed`, `tool_call_failed`, `tool_retry` |
| `reasoning` | `reasoning_step`, `reasoning_plan`, `reasoning_reflection`, `reasoning_decision`, `reasoning_final` |
| `agent` | `agent_run_started`, `agent_run_completed`, `agent_run_failed` |
| `memory` | `memory_query`, `memory_retrieval`, `memory_write` |
| `system` | `span_started`, `span_completed` |
| `user` | `user_input`, `user_feedback` |
| `cost` | `cost_calculated` |
| `error` | `error_raised` |

**`subtype` values:**

| Group | Values |
|---|---|
| Reasoning patterns | `chain_of_thought`, `react`, `reflection`, `self_consistency` |
| Tool subtypes | `http`, `database`, `filesystem`, `api` |
| Error subtypes | `timeout`, `rate_limit`, `validation`, `tool_error`, `llm_error` |

For LLM events, always include token usage in `metadata` to enable cost tracking:

```python
agent.emit(
    name="llm.call",
    category="llm",
    metadata={
        "usage": {
            "input_tokens": 12,
            "output_tokens": 8,
        },
    },
)
```

Popular LLMs return token usage in their responses — map it directly:

```python
# Anthropic
response = anthropic.messages.create(...)
agent.emit(name="llm.call", category="llm", metadata={
    "usage": {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    },
})

# OpenAI
response = openai.chat.completions.create(...)
agent.emit(name="llm.call", category="llm", metadata={
    "usage": {
        "input_tokens": response.usage.prompt_tokens,
        "output_tokens": response.usage.completion_tokens,
    },
})
```

---

### `Agent.span()`

Returns a context manager that tracks a scoped duration as a span record. On enter it creates the span with a `start_time`; on exit it updates the span with an `end_time`.

```python
with agent.span("llm.call", metadata={"model": "claude"}) as s:
    result = llm.generate(prompt)
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `name` | `str` | Yes | Span name (e.g. `"llm.call"`, `"tool.invoke"`). |
| `metadata` | `dict` | No | Any arbitrary JSON-serialisable data to attach to the span. |

Nested spans automatically propagate context — each child span records the enclosing span's `id` as its `parent_id`, enabling tree reconstruction:

```
model.prompt  (id: A, parent_id: None)
  └── tool.call  (id: B, parent_id: A)
        └── memory.read  (id: C, parent_id: B)
```

Events emitted inside a span are automatically linked to that span via `span_id`.
