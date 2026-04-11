# Run Trigger Type & ID Design

**Date:** 2026-04-11  
**Status:** Approved

## Overview

Track what triggered each agent run — API call, another agent, a user, a cron job, a webhook, or unknown — and optionally store the specific trigger source identifier. This enables filtering, auditing, and attribution of runs by origin.

---

## Data Model

**New DB enum type:** `trigger_type_t`

Values: `unknown`, `api`, `agent`, `user`, `cron`, `webhook`

**Two new columns on `agent_runs`:**

| Column | Type | Nullable | Default |
|---|---|---|---|
| `trigger_type` | `trigger_type_t` | no | `'unknown'` |
| `trigger_id` | `text` | yes | `null` |

**`trigger_id` semantics by type:**

| `trigger_type` | `trigger_id` meaning |
|---|---|
| `unknown` | null |
| `api` | API endpoint path |
| `agent` | triggering agent's ID |
| `user` | user ID |
| `cron` | job identifier / schedule name |
| `webhook` | webhook source (e.g. `"github"`, `"stripe"`) |

**Migration:**
- Add the `trigger_type_t` enum to the DB.
- Add `trigger_type trigger_type_t NOT NULL DEFAULT 'unknown'` and `trigger_id TEXT NULL` to `agent_runs`.
- Backfill existing rows: `trigger_type = 'unknown'`, `trigger_id = NULL` (covered by default).
- Add index on `trigger_type` for filtering runs by trigger origin.

**No DB-level CHECK constraints** between `trigger_type` and other columns — validation is the application layer's responsibility.

---

## Platform API

### `TriggerType` enum — `app/models/agents.py`

```python
class TriggerType(StrEnum):
    unknown = "unknown"
    api     = "api"
    agent   = "agent"
    user    = "user"
    cron    = "cron"
    webhook = "webhook"
```

### `StartRunRequest` changes — `app/routers/agents.py`

New optional fields:

```python
trigger_type: TriggerType = TriggerType.unknown
trigger_id: str | None = None
```

**Pydantic `model_validator` (after):**
- `trigger_type == 'agent'` and `parent_run_id is None` → raise `ValueError("parent_run_id required when trigger_type is 'agent'")`
- `trigger_type != 'agent'` and `parent_run_id is not None` → raise `ValueError("parent_run_id only valid when trigger_type is 'agent'")`

### `AgentRun` Pydantic model additions

```python
trigger_type: TriggerType
trigger_id: str | None
```

### `start_run` endpoint

Both new fields passed through to the INSERT. No other endpoint changes.

---

## SDK

### `Agent.init()` — `ezop-sdk/python/ezop/agent.py`

Two new optional keyword-only parameters:

```python
trigger_type: Optional[str] = None
trigger_id: Optional[str] = None
```

`trigger_type` is a plain `str` (not an enum) to keep the SDK dependency-light. Both forwarded to `EzopClient.start_run()` and included in the request body only when not `None` (platform applies its own default of `'unknown'`).

### `EzopClient.start_run()` — `ezop-sdk/python/ezop/client.py`

New optional parameters:

```python
trigger_type: Optional[str] = None
trigger_id: Optional[str] = None
```

Included in request body only when not `None`.

### `AgentRun` dataclass — `ezop-sdk/python/ezop/models.py`

Two new optional fields:

```python
trigger_type: Optional[str] = None
trigger_id: Optional[str] = None
```

Populated from the API response in `Agent.init()`.

---

## Error Handling

| Condition | HTTP status | Detail |
|---|---|---|
| `trigger_type='agent'` + no `parent_run_id` | 422 | `parent_run_id required when trigger_type is 'agent'` |
| `trigger_type!='agent'` + `parent_run_id` set | 422 | `parent_run_id only valid when trigger_type is 'agent'` |

---

## Testing

**Platform:**
- `start_run` with `trigger_type='cron'`, `trigger_id='daily-cleanup'` → 201, both fields in response
- `trigger_type='agent'` without `parent_run_id` → 422
- `trigger_type='user'` with `parent_run_id` set → 422
- No `trigger_type` provided → response has `trigger_type='unknown'`

**SDK:**
- `Agent.init()` with `trigger_type='cron'`, `trigger_id='daily-cleanup'` → `start_run` called with both fields in body
- `Agent.init()` with no trigger args → `start_run` called without `trigger_type` or `trigger_id` in body
- `AgentRun` populated with `trigger_type` and `trigger_id` from API response
