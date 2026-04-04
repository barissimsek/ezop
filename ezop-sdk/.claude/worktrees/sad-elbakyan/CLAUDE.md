# Ezop SDK — Claude Code Guide

## Repo layout

```
python/              Python SDK (only SDK currently)
  ezop/              Package source
    agent.py         Agent, Span classes — main user-facing API
    client.py        EzopClient — thin HTTP wrapper
    models.py        Dataclasses: AgentModel, AgentVersion, AgentRun, Event
    config.py        Reads EZOP_API_KEY / EZOP_API_URL from env
  tests/
    test_agent.py    Unit tests (mock HTTP)
    test_integration.py  Integration tests (responses library, mock HTTP)
  docs/
    README.md        Full API reference
    starter.py       Runnable example — kept in sync with SDK
  README.md          Short overview + links
  Makefile           test / build / install / publish
  pyproject.toml     Package metadata and deps
```

## API response envelope

Every backend response is wrapped:
```json
{"success": true, "data": {...}, "error": null}
```
Client methods return the full envelope. SDK code always unpacks `["data"]`:
```python
agent_data = client.register_agent(...)["data"]
```

## Three-call init sequence

`Agent.init()` makes exactly 3 API calls in order:
1. `POST /agents/register` → agent record
2. `POST /agents/{agent_id}/versions` → version record
3. `POST /agents/{agent_id}/runs` → run record, sets `agent.current_run`

There is no public `start_run()` — the run starts inside `init()`.

## Span lifecycle

Spans are separate DB records (not events). Two API calls per span:
- `POST /runs/{run_id}/spans` on `__enter__` — sends `id`, `name`, `start_time`, optional `parent_id`, `metadata`
- `PATCH /spans/{span_id}` on `__exit__` — sends `end_time`

The `span_id` is generated client-side (UUID4) so it can be referenced before the server responds.

Nesting: `_current_span_id` on `AgentRun` acts as a stack pointer. On enter it is saved as `parent_id` and overwritten with the new span's id. On exit it is restored. This ensures correct parent-child wiring automatically.

Constraints the SDK enforces:
- A span cannot be its own parent (`id != parent_id`) — guarded in `__enter__`
- A span's `run_id` always matches its events' `run_id` — enforced by snapshotting `current_run` on enter

## Event schema

Events have these enum-constrained fields. Always use exact string values:

**`category`** (required): `agent`, `llm`, `tool`, `reasoning`, `system`, `user`, `memory`, `cost`, `error`

**`type`** (optional, must match category):
| category | valid types |
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

**`subtype`** (optional): `chain_of_thought`, `react`, `reflection`, `self_consistency`, `http`, `database`, `filesystem`, `api`, `timeout`, `rate_limit`, `validation`, `tool_error`, `llm_error`

**`error`** field is `jsonb` — always pass a dict, never a plain string:
```python
error={"message": "something went wrong"}
```

**`span_id`** on events auto-resolves from `_current_span_id` when emitting inside a span. No `parent_id` on events — hierarchy is through spans only.

## `agent.close()` status values

`"success"`, `"failed"`, `"partial"`, `"canceled"`, `"running"`

## LLM token usage in metadata

Always use this shape for cost tracking:
```python
metadata={"usage": {"input_tokens": N, "output_tokens": N}}
```

## After any SDK change

Run `make install` from `python/` to rebuild and reinstall the wheel. The `.venv` uses the installed wheel, not editable source, so stale installs cause `TypeError: unexpected keyword argument` errors.

## Testing rules

- Unit tests (`test_agent.py`): mock `EzopClient` methods directly with `unittest.mock.patch`
- Integration tests (`test_integration.py`): use `responses` library for HTTP-level mocking
- No live tests — the `TestLiveAPI` class was removed
- Use correct enum values in tests — wrong status strings or category values will cause backend validation errors
- `make test` runs all non-live tests and must pass before `build`

## SDK vs API server — responsibility boundary

Always reason explicitly about which side owns a problem before writing code.

**SDK owns:**
- Generating client-side IDs (span_id, event id)
- Snapshotting `current_run` on span enter (run_id consistency)
- Cycle detection (`span.id != span.parent_id`)
- Serialising Python objects to JSON-safe types
- Omitting `None` fields from request bodies
- Logging warnings when the API returns unexpected shapes

**API server owns:**
- Enum validation (`category`/`type` combinations, status values)
- Foreign key constraints (run_id, span_id, organization_id)
- Idempotency (same span_id not inserted twice)
- Auth and organization_id injection
- All business logic and data integrity rules

**Never work around an API bug in the SDK.** If the API returns an unexpected shape, log a warning and surface it to the developer so the API server gets fixed. Examples of unexpected API behaviour to warn on (not silently handle):
- Response envelope missing `"data"` key
- Expected fields missing from `data` (e.g. no `"id"` on a created resource)
- `"success": false` with a 2xx status code
- Enum values in the response that don't match the schema

Use `logger.warning()` with a clear message pointing at the API:
```python
if "id" not in data:
    logger.warning("API response missing 'id' — this is an API server bug: %s", data)
```

Do not add fallbacks like `.get("id", str(uuid.uuid4()))` that hide the problem.
