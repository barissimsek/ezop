# Agent-to-Agent Run Support

**Date:** 2026-04-09  
**Status:** Approved

## Overview

Add parent/child relationships between agent runs to support multi-agent workflows. A parent agent exposes its active run context; a child agent accepts a `parent_run_id` at init time. The platform stores the hierarchy and denormalizes a `root_run_id` for efficient tree queries.

Ezop does not control how agents call each other — the developer is responsible for passing context between agents (env var, HTTP header, direct parameter, etc.).

---

## Data Model

Two new columns on `agent_runs`:

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `parent_run_id` | `uuid` | yes | FK → `agent_runs.id` ON DELETE SET NULL |
| `root_run_id` | `uuid` | no | FK → `agent_runs.id` ON DELETE CASCADE |

**`root_run_id` assignment at insert time:**
- No parent → `root_run_id = run.id` (self). The run `id` is generated in Python (`uuid4()`) so both `id` and `root_run_id` can be set in a single INSERT.
- Has parent → `root_run_id = parent.root_run_id` (read from the validation query, no extra round-trip).

**Index:** one index on `root_run_id` for `WHERE root_run_id = :id` tree queries.

**Cycle prevention:** DB constraint `CHECK (parent_run_id != id)` prevents self-parenting. Deeper cycles cannot form because `root_run_id` is immutable after insert and always points to the original root.

**Migration:** one `ALTER TABLE agent_runs` migration adding both columns and the index, plus a `NOT NULL` default (`root_run_id = id`) for existing rows.

---

## Platform API

### `StartRunRequest` change

```python
parent_run_id: str | None = None
```

### `start_run` endpoint logic

1. If `parent_run_id` provided: fetch parent row, verify it exists and belongs to the same org → extract its `root_run_id`. Raise `404` if not found, `422` if wrong org.
2. Generate run `id` in Python (`uuid4()`).
3. Set `root_run_id = id` if no parent, else `root_run_id = parent.root_run_id`.
4. INSERT with explicit `id`, `parent_run_id`, `root_run_id`.

### `AgentRun` Pydantic model additions

```python
parent_run_id: UUID | None
root_run_id: UUID
```

No new endpoints. Tree queries are a dashboard concern handled via the UI's Prisma layer.

### Error cases

| Condition | HTTP status | Detail |
|---|---|---|
| `parent_run_id` not found | 404 | `Parent run not found.` |
| `parent_run_id` belongs to different org | 422 | `Parent run belongs to a different organization.` |
| `parent_run_id == id` | DB constraint | caught before insert |

---

## SDK

### New type: `AgentContext`

Added to `models.py`:

```python
@dataclass(frozen=True)
class AgentContext:
    name: str
    run_id: str
```

Only `name` and `run_id` are included for now.

### `Agent.get_context()`

Instance method. Returns `AgentContext` populated from the active run. Raises `RuntimeError("No active run.")` if called with no active run or after `close()`.

### `Agent.init()` change

New optional parameter:

```python
parent_run_id: Optional[str] = None
```

Forwarded to `EzopClient.start_run()` and included in the request body.

### `AgentRun` dataclass additions

```python
parent_run_id: Optional[str] = None
root_run_id: Optional[str] = None  # always set by platform; None only before response is parsed
```

### Usage example

```python
# Parent agent (e.g. orchestrator service)
agent = Agent.init(name="orchestrator", owner="acme", version="1.0", runtime="python")
ctx = agent.get_context()
# developer passes ctx.run_id to child however they want (env var, HTTP header, etc.)

# Child agent (separate process or service)
child = Agent.init(
    name="researcher",
    owner="acme",
    version="1.0",
    runtime="python",
    parent_run_id=ctx.run_id,
)
```

---

## Error Handling

**Platform:**
- `parent_run_id` not found → `404`
- `parent_run_id` wrong org → `422`
- Self-parent → DB constraint

**SDK:**
- `get_context()` with no active run → `RuntimeError("No active run.")`
- `get_context()` after `close()` → caught by existing `_check_active()` guard

---

## Testing

**Platform:**
- Start child run with valid parent → `parent_run_id` and `root_run_id` set correctly
- Multi-level chain (A→B→C) → all three share the same `root_run_id`
- `parent_run_id` not found → 404
- `parent_run_id` wrong org → 422

**SDK:**
- `get_context()` returns correct `name` and `run_id`
- `get_context()` raises when no active run or after `close()`
