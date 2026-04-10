# Trigger/Actor Tracking and agent2agent Runs — Design Spec

**Date:** 2026-04-05
**Branch:** feat/events_agent_id

---

## Goal

Add structured trigger/actor information to `agent_runs` so every run records what caused it — a human user, a scheduled job, a webhook, a direct API call, or another agent — and how agent-spawned chains can be traversed. This also enables SDK-level agent-to-agent calls.

---

## Section 1 — Schema

### New columns on `agent_runs`

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `trigger_type` | `text` | NO | `'api'` | One of: `user`, `cron`, `webhook`, `api`, `agent` |
| `trigger_id` | `text` | YES | NULL | Caller-supplied ID (user ID, cron job name, webhook source, etc.) |
| `parent_run_id` | `uuid` | YES | NULL | FK → `agent_runs(id)` ON DELETE SET NULL; only set for `agent` type |

### CHECK constraints (enforced at DB level)

```sql
-- agent type requires a parent run
CONSTRAINT agent_requires_parent
  CHECK (trigger_type != 'agent' OR parent_run_id IS NOT NULL),

-- non-agent types forbid parent_run_id
CONSTRAINT non_agent_forbids_parent
  CHECK (trigger_type = 'agent' OR parent_run_id IS NULL),

-- agent type has no trigger_id (parent_run_id is the reference)
CONSTRAINT agent_forbids_trigger_id
  CHECK (trigger_type != 'agent' OR trigger_id IS NULL)
```

### Indexes

```sql
CREATE INDEX agent_runs_parent_run_idx ON agent_runs (parent_run_id) WHERE parent_run_id IS NOT NULL;
CREATE INDEX agent_runs_trigger_idx ON agent_runs (trigger_type, trigger_id) WHERE trigger_id IS NOT NULL;
```

### Migration strategy

Three-step pattern for `trigger_type` (existing rows must not violate NOT NULL):

1. `ALTER TABLE agent_runs ADD COLUMN trigger_type text;`
2. `UPDATE agent_runs SET trigger_type = 'api' WHERE trigger_type IS NULL;`
3. `ALTER TABLE agent_runs ALTER COLUMN trigger_type SET NOT NULL;`
4. `ALTER TABLE agent_runs ALTER COLUMN trigger_type SET DEFAULT 'api';`
5. Add `trigger_id` and `parent_run_id` as nullable (no backfill needed).
6. Add the three CHECK constraints.
7. Add indexes.

### Hierarchy model

`parent_run_id` lives on `agent_runs`, not on `events`. Events are observations within a single run — the parent relationship is a run-level concept. All events in a child run share the same parent (the run), so denormalizing onto events would be redundant.

Chain traversal uses a recursive CTE on `agent_runs`, then JOINs to `events`:

```sql
WITH RECURSIVE chain AS (
  SELECT id FROM agent_runs WHERE id = $root_run_id
  UNION ALL
  SELECT r.id FROM agent_runs r JOIN chain c ON r.parent_run_id = c.id
)
SELECT e.* FROM events e JOIN chain c ON e.run_id = c.id;
```

---

## Section 2 — Write Path (ezop-platform)

### `TriggerType` enum

```python
class TriggerType(str, Enum):
    user = "user"
    cron = "cron"
    webhook = "webhook"
    api = "api"
    agent = "agent"
```

### `StartRunRequest` additions

```python
trigger_type: TriggerType = TriggerType.api
trigger_id: Optional[str] = None
parent_run_id: Optional[UUID] = None

@model_validator(mode="after")
def validate_trigger(self) -> "StartRunRequest":
    if self.trigger_type == TriggerType.agent:
        if self.parent_run_id is None:
            raise ValueError("parent_run_id required when trigger_type is 'agent'")
        if self.trigger_id is not None:
            raise ValueError("trigger_id must be None when trigger_type is 'agent'")
    else:
        if self.parent_run_id is not None:
            raise ValueError("parent_run_id only valid when trigger_type is 'agent'")
    return self
```

### `start_run` route additions

- If `parent_run_id` is provided, verify it belongs to the same organization (`SELECT organization_id WHERE id = parent_run_id`). Reject with 422 if mismatched — prevents cross-org references.
- Add `trigger_type`, `trigger_id`, `parent_run_id` to the INSERT.

### SDK agent-to-agent support

`Agent.init()` gains an optional `parent_run_id` parameter. When set:
- SDK sends `trigger_type='agent'` and `parent_run_id` in the start run request.
- Parent run ID is available on the running agent as `agent.run_id`, so a parent agent can pass it to a child.

---

## Section 3 — Read Path (Prisma)

### Prisma schema additions to `AgentRun`

```prisma
trigger_type    String     @default("api")
trigger_id      String?
parent_run_id   String?    @db.Uuid
parent_run      AgentRun?  @relation("RunChain", fields: [parent_run_id], references: [id], onDelete: SetNull, onUpdate: NoAction)
spawned_runs    AgentRun[] @relation("RunChain")
```

### Run detail query

Include one level up and one level down — no recursive CTE needed for the UI display:

```ts
include: {
  parent_run: { select: { id: true, status: true, start_time: true } },
  spawned_runs: { select: { id: true, status: true, start_time: true, end_time: true } },
}
```

### Run list query

Add trigger columns to the run select in `listAgents`:

```ts
select: {
  id: true,
  agent_id: true,
  status: true,
  start_time: true,
  end_time: true,
  trigger_type: true,
  trigger_id: true,
  parent_run_id: true,
  _count: { select: { spawned_runs: true } },
}
```

---

## Section 4 — UI (AgentInventory)

### Run list table (`RunsTab` in `AgentInventory/index.tsx`)

Add a `Trigger` column between Run ID and Status. Grid template changes from `"1fr 70px 60px 16px"` to `"1fr 80px 70px 60px 16px"`.

Trigger cell renders a compact badge:
- `api` → grey `API`
- `user` → blue `User` + trigger_id truncated if set
- `cron` → purple `Cron` + trigger_id if set
- `webhook` → orange `Webhook`
- `agent` → teal `Agent↑` as a link to parent run (uses parent_run_id)

### Run detail view (expanded row)

Two additions below the existing run header (status + duration):

**1. "Triggered by" line** — always shown:
- For `api/user/cron/webhook`: `Triggered by: <badge> <trigger_id if set>`
- For `agent`: `Triggered by: <badge> Run <parent_run_id short> ↗` (clickable, expands parent run inline)

**2. "Spawned runs" panel** — shown only when `spawned_runs.length > 0`:
- Collapsible section header: `Spawned runs (N)` — collapsed by default
- When expanded: list of child runs as compact rows showing Run ID, Status, Duration
- Each row is clickable, expanding that run's detail inline

### `AgentRun` type update (`agents/actions.ts`)

```ts
type AgentRun = {
  id: string
  status: string
  startTime: Date
  durationS: number | null
  triggerType: string
  triggerId: string | null
  parentRunId: string | null
  spawnedRunCount: number
}
```

---

## File Map

| File | Change |
|---|---|
| `ezop-light-ui/prisma/schema.prisma` | Add 3 columns + self-relation to `AgentRun` |
| `ezop-light-ui/prisma/migrations/<ts>_add_trigger_columns.sql` | 3-step migration SQL |
| `ezop-platform/database/migrations/<ts>-add-trigger-columns.sql` | Mirror of Prisma migration |
| `ezop-platform/database/current/02-base-schemas.sql` | Updated `agent_runs` DDL |
| `ezop-platform/app/models/runs.py` | `TriggerType` enum, `StartRunRequest` fields + validator |
| `ezop-platform/app/routers/runs.py` | `start_run` org-check for parent_run_id, INSERT additions |
| `ezop-platform/tests/test_models.py` | Validator tests for trigger field combinations |
| `ezop-platform/tests/test_runs.py` | `test_start_run_includes_trigger_columns` |
| `ezop-light-ui/app/dashboard/agents/actions.ts` | `AgentRun` type + select additions |
| `ezop-light-ui/components/AgentInventory/index.tsx` | Trigger column, "Triggered by" line, spawned runs panel |
| `ezop-sdk/python/ezop/agent.py` | `Agent.init()` gains optional `parent_run_id` parameter |

---

## Out of Scope

- Full recursive chain traversal UI (shows one level up + one level down; full tree is future work)
- Trigger-based filtering in the run list (future)
- Audit log entries for trigger source (future)
