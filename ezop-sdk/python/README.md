# Ezop Python SDK

Ezop tracks the lifecycle of your AI agents — registrations, versions, and runs — so you have full observability across every deployment.

[Documentation](https://www.ezop.ai/docs)

## Installation

```bash
pip install ezop
```

## Configuration

```bash
export EZOP_API_KEY=your-ezop-api-key-here
export EZOP_API_URL=http://localhost:13000
```

---

## Usage

### Initialize the agent

```python
from ezop import Agent

agent = Agent.init(
    name="customer-support-bot",
    owner="growth-team",
    version="v0.3",
    runtime="langchain",
    description="Handles tier-1 customer support tickets",
    default_permissions=["read:tickets"],
    permissions=["read:tickets", "write:replies"],
    changelog="Switched to new retrieval pipeline",
)
```

Call `Agent.init()` once at startup. It is safe to call on every deployment:

- If the agent does not exist, it will be created on the platform.
- If the agent already exists, registration returns the existing agent.
- If a new `version` is provided, the platform registers it as a new version under the same agent. If the version already exists, version registration is also a no-op.

### Track runs

`Agent.init()` starts a run automatically. Call `agent.close()` when the invocation is done:

```python
agent = Agent.init(name="my-bot", owner="my-team", version="v1.0", runtime="langchain")

agent.close(
    status="success",
    metadata={"user_id": user_id},
)
```

### Track trigger origin

Pass `trigger_type` (and optionally `trigger_id`) to `Agent.init()` so every run records what triggered it:

```python
# API request
agent = Agent.init(..., trigger_type="api", trigger_id="/api/v1/chat")

# Scheduled job
agent = Agent.init(..., trigger_type="cron", trigger_id="nightly-digest")

# Webhook (e.g. from GitHub or Stripe)
agent = Agent.init(..., trigger_type="webhook", trigger_id="github")

# User-initiated
agent = Agent.init(..., trigger_type="user", trigger_id=user_id)

# Child agent triggered by a parent agent
ctx = parent_agent.get_context()
child = Agent.init(..., trigger_type="agent", trigger_id=ctx.run_id, parent_run_id=ctx.run_id)
```

`trigger_id` meaning depends on `trigger_type`:

| `trigger_type` | `trigger_id` |
|---|---|
| `api` | API endpoint path |
| `agent` | Triggering agent's run ID |
| `user` | User ID |
| `cron` | Job name or schedule |
| `webhook` | Webhook source (e.g. `"github"`, `"stripe"`) |
| `unknown` | `None` |

### Track steps with spans and events

Use `span` for steps with duration and `emit` for single points in time:

```python
# span: a record with start_time and end_time
with agent.span("retrieval", metadata={"query": user_input}):
    docs = retriever.search(user_input)

with agent.span("llm.call", metadata={"model": "claude"}):
    result = llm.generate(user_input)

# emit: a single point-in-time event
agent.emit(name="action.selected", category="reasoning")

agent.close(status="success")
```

Spans can be nested — child spans automatically record the parent's `span_id` as `parent_id`, enabling tree reconstruction:

```python
with agent.span("model.prompt") as s1:
    plan = llm.plan(user_input)

    with agent.span("tool.call", metadata={"tool": "stripe.refund"}) as s2:
        refund = stripe.refund(plan.charge_id)
# produces: model.prompt → tool.call (parent_id links them)
```

Events emitted inside a span are automatically linked to that span via `span_id`:

```python
with agent.span("llm.call") as s:
    agent.emit(name="token.count", category="llm", metadata={"tokens": 42})
# event.span_id == s.span_id
```

- **Runs** — the final outcome of a single agent invocation
- **Spans** — structured execution steps within a run (e.g. LLM call, retrieval, tool use)
- **Events** — raw logs inside a span

---

## API Reference

### `agent.init()`

Registers the agent and its version with the Ezop platform, and returns an `Agent` instance.

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

### `agent.close()`

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

### `agent.emit()`

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

For LLM events, always include token usage and model in `metadata` to enable cost tracking:

```python
agent.emit(
    name="llm.call",
    category="llm",
    metadata={
        "model": "claude-opus-4-5",
        "usage": {
            "input_tokens": 12,
            "output_tokens": 8,
        },
    },
)
```

Popular LLMs return token usage in their responses — map it directly.

---

### `agent.span()`

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

---

## Logging

The SDK uses Python's standard `logging` module under the `ezop` namespace. To enable logs in your application:

```python
import logging
logging.getLogger("ezop").setLevel(logging.DEBUG)
```
