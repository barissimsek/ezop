# Events & Spans agent_id Denormalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a direct `agent_id` column to `events` and `spans` so agent-scoped queries and analytics no longer require a JOIN through `agent_runs`.

**Architecture:** Add `agent_id UUID NOT NULL` to both tables via a three-step migration (add nullable → backfill from `agent_runs` → enforce NOT NULL). The platform's write path derives `agent_id` from the run at insert time (same DB call, one extra column). The UI's events page drops the two-step `runIds` resolution and intermediate `agentRun` join in favour of direct `agent_id` filters.

**Tech Stack:** PostgreSQL, Prisma (schema + migrations), FastAPI/SQLAlchemy (ezop-platform), Next.js Server Components + Prisma Client (ezop-light-ui), pytest + unittest.mock

---

## File Map

| File | Change |
|---|---|
| `ezop-light-ui/prisma/schema.prisma` | Add `agent_id` + indexes to `Event` and `Span`; add back-relations to `Agent` |
| `ezop-light-ui/prisma/migrations/<ts>_add_agent_id_to_events_and_spans/migration.sql` | Raw migration SQL (nullable add → backfill → NOT NULL → indexes) |
| `ezop-platform/app/models/runs.py` | Add `agent_id: UUID` to `Event` and `Span` Pydantic models |
| `ezop-platform/app/routers/runs.py` | Rename `_assert_run_org` → `_get_run_agent`, thread `agent_id` through `emit_event` and `create_span` INSERTs |
| `ezop-platform/tests/test_runs.py` | New: tests for `emit_event` and `create_span` verifying `agent_id` is stored and returned |
| `ezop-light-ui/app/dashboard/observability/events/page.tsx` | Replace indirect `runIds`/`agentRun` join with direct `agent_id` filter; simplify agent-name resolution |

---

## Task 1: Update Prisma schema

**Files:**
- Modify: `ezop-light-ui/prisma/schema.prisma`

- [ ] **Step 1: Add `agent_id` to the `Event` model**

Open `ezop-light-ui/prisma/schema.prisma`. In the `Event` model, add after the `organization_id` line:

```prisma
agent_id        String         @db.Uuid
agent           Agent          @relation(fields: [agent_id], references: [id], onDelete: Cascade, onUpdate: NoAction, map: "events_agent_fkey")
```

And add two new index entries at the bottom of the `Event` model (before the closing `}`):

```prisma
@@index([agent_id, timestamp(sort: Desc)], map: "events_agent_time_idx")
@@index([agent_id, category, timestamp(sort: Desc)], map: "events_agent_category_idx")
```

- [ ] **Step 2: Add `agent_id` to the `Span` model**

In the `Span` model, add after the `organization_id` line:

```prisma
agent_id        String       @db.Uuid
agent           Agent        @relation(fields: [agent_id], references: [id], onDelete: Cascade, onUpdate: NoAction, map: "spans_agent_fkey")
```

And add one new index entry at the bottom of the `Span` model:

```prisma
@@index([agent_id, start_time(sort: Desc)], map: "spans_agent_start_idx")
```

- [ ] **Step 3: Add back-relations to the `Agent` model**

In the `Agent` model, add after the existing `runs AgentRun[]` and `versions AgentVersion[]` lines:

```prisma
events          Event[]
spans           Span[]
```

- [ ] **Step 4: Create the migration skeleton (no-execute)**

From `ezop-light-ui/`, run:

```bash
cd ezop-light-ui && npx prisma migrate dev --create-only --name add_agent_id_to_events_and_spans
```

This generates a file at `prisma/migrations/<timestamp>_add_agent_id_to_events_and_spans/migration.sql`. Open it — Prisma will have generated `ALTER TABLE "events" ADD COLUMN "agent_id" UUID NOT NULL` but that will fail on existing rows. You must replace the generated content with the correct three-step SQL in the next step.

- [ ] **Step 5: Replace the generated migration SQL**

Replace the entire content of the generated migration file with:

```sql
-- Step 1: add nullable so existing rows don't violate NOT NULL
ALTER TABLE "events" ADD COLUMN "agent_id" UUID REFERENCES "agents"("id") ON DELETE CASCADE ON UPDATE NO ACTION;
ALTER TABLE "spans"  ADD COLUMN "agent_id" UUID REFERENCES "agents"("id") ON DELETE CASCADE ON UPDATE NO ACTION;

-- Step 2: backfill from agent_runs (agent_id on a run is immutable)
UPDATE "events" e SET "agent_id" = r."agent_id" FROM "agent_runs" r WHERE e."run_id" = r."id";
UPDATE "spans"  s SET "agent_id" = r."agent_id" FROM "agent_runs" r WHERE s."run_id" = r."id";

-- Step 3: enforce NOT NULL after backfill
ALTER TABLE "events" ALTER COLUMN "agent_id" SET NOT NULL;
ALTER TABLE "spans"  ALTER COLUMN "agent_id" SET NOT NULL;

-- Step 4: indexes
CREATE INDEX "events_agent_time_idx"     ON "events" ("agent_id", "timestamp" DESC);
CREATE INDEX "events_agent_category_idx" ON "events" ("agent_id", "category", "timestamp" DESC);
CREATE INDEX "spans_agent_start_idx"     ON "spans"  ("agent_id", "start_time" DESC);
```

- [ ] **Step 6: Apply the migration**

```bash
cd ezop-light-ui && npx prisma migrate dev
```

Expected output: `The following migration(s) have been applied: add_agent_id_to_events_and_spans`

- [ ] **Step 7: Regenerate Prisma client**

```bash
cd ezop-light-ui && npx prisma generate
```

Expected: `Generated Prisma Client`

- [ ] **Step 8: Commit**

```bash
git add ezop-light-ui/prisma/schema.prisma ezop-light-ui/prisma/migrations/
git commit -m "feat: add agent_id to events and spans schema"
```

---

## Task 2: Update ezop-platform Pydantic models

**Files:**
- Modify: `ezop-platform/app/models/runs.py`

- [ ] **Step 1: Write a failing test**

Create `ezop-platform/tests/test_models.py`:

```python
from uuid import UUID
from app.models.runs import Event, Span


def test_event_model_has_agent_id():
    data = {
        "id": "00000000-0000-0000-0000-000000000001",
        "run_id": "00000000-0000-0000-0000-000000000002",
        "agent_id": "00000000-0000-0000-0000-000000000003",
        "span_id": None,
        "name": "test",
        "category": "tool",
        "type": None,
        "subtype": None,
        "iteration_id": None,
        "timestamp": "2026-01-01T00:00:00+00:00",
        "input": None,
        "output": None,
        "metadata": None,
        "error": None,
        "sequence": 1,
        "organization_id": "00000000-0000-0000-0000-000000000004",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    event = Event.model_validate(data)
    assert isinstance(event.agent_id, UUID)
    assert str(event.agent_id) == "00000000-0000-0000-0000-000000000003"


def test_span_model_has_agent_id():
    data = {
        "id": "00000000-0000-0000-0000-000000000001",
        "run_id": "00000000-0000-0000-0000-000000000002",
        "agent_id": "00000000-0000-0000-0000-000000000003",
        "parent_id": None,
        "name": "my-span",
        "start_time": "2026-01-01T00:00:00+00:00",
        "end_time": None,
        "metadata": None,
        "organization_id": "00000000-0000-0000-0000-000000000004",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    span = Span.model_validate(data)
    assert isinstance(span.agent_id, UUID)
    assert str(span.agent_id) == "00000000-0000-0000-0000-000000000003"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd ezop-platform && python -m pytest tests/test_models.py -v
```

Expected: `FAILED` — `Event` and `Span` have no `agent_id` field yet.

- [ ] **Step 3: Add `agent_id` to both models**

In `ezop-platform/app/models/runs.py`, add `agent_id: UUID` to both `Span` and `Event`:

```python
class Span(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    agent_id: UUID          # ← add this line
    parent_id: UUID | None
    name: str | None
    start_time: datetime
    end_time: datetime | None
    metadata: dict | None
    organization_id: UUID
    created_at: datetime
    updated_at: datetime


class Event(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    agent_id: UUID          # ← add this line
    span_id: UUID | None
    name: str
    category: EventCategory
    type: EventType | None
    subtype: EventSubtype | None
    iteration_id: int | None
    timestamp: datetime
    input: dict | None
    output: dict | None
    metadata: dict | None
    error: dict | None
    sequence: int
    organization_id: UUID
    created_at: datetime
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd ezop-platform && python -m pytest tests/test_models.py -v
```

Expected: `PASSED` for both tests.

- [ ] **Step 5: Commit**

```bash
git add ezop-platform/app/models/runs.py ezop-platform/tests/test_models.py
git commit -m "feat: add agent_id to Event and Span Pydantic models"
```

---

## Task 3: Update ezop-platform write path

**Files:**
- Modify: `ezop-platform/app/routers/runs.py`
- Create: `ezop-platform/tests/test_runs.py`

- [ ] **Step 1: Write failing tests**

Create `ezop-platform/tests/test_runs.py`:

```python
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

AGENT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
RUN_ID   = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
ORG_ID   = "cccccccc-cccc-cccc-cccc-cccccccccccc"
SPAN_ID  = "dddddddd-dddd-dddd-dddd-dddddddddddd"
EVENT_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"


def _mock_run_row():
    """Fake agent_runs row returned by _get_run_agent."""
    row = MagicMock()
    row.agent_id = AGENT_ID
    return row


def _mock_event_row():
    return {
        "id": EVENT_ID,
        "run_id": RUN_ID,
        "agent_id": AGENT_ID,
        "span_id": None,
        "name": "test_event",
        "category": "tool",
        "type": None,
        "subtype": None,
        "iteration_id": None,
        "timestamp": "2026-01-01T00:00:00+00:00",
        "input": None,
        "output": None,
        "metadata": None,
        "error": None,
        "sequence": 1,
        "organization_id": ORG_ID,
        "created_at": "2026-01-01T00:00:00+00:00",
    }


def _mock_span_row():
    return {
        "id": SPAN_ID,
        "run_id": RUN_ID,
        "agent_id": AGENT_ID,
        "parent_id": None,
        "name": "my-span",
        "start_time": "2026-01-01T00:00:00+00:00",
        "end_time": None,
        "metadata": None,
        "organization_id": ORG_ID,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


def test_emit_event_includes_agent_id():
    """emit_event stores agent_id from the run and returns it in response."""
    mock_db = MagicMock()
    # _get_run_agent query: returns run row with agent_id
    mock_db.execute.return_value.first.return_value = _mock_run_row()
    # assert_events_limit: needs to return a plan row — patch directly
    # INSERT query: returns the persisted event row
    event_row = MagicMock()
    event_row.__iter__ = lambda s: iter(_mock_event_row().items())
    mock_db.execute.return_value.mappings.return_value.first.return_value = _mock_event_row()

    with (
        patch("app.routers.runs.get_db", return_value=mock_db),
        patch("app.routers.runs.verify_api_key", return_value=ORG_ID),
        patch("app.routers.runs.assert_events_limit"),
    ):
        response = client.post(
            f"/runs/{RUN_ID}/events",
            json={"name": "test_event", "category": "tool"},
            headers={"Authorization": f"Bearer testkey"},
        )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["agent_id"] == AGENT_ID


def test_create_span_includes_agent_id():
    """create_span stores agent_id from the run and returns it in response."""
    mock_db = MagicMock()
    mock_db.execute.return_value.first.return_value = _mock_run_row()
    mock_db.execute.return_value.mappings.return_value.first.return_value = _mock_span_row()

    with (
        patch("app.routers.runs.get_db", return_value=mock_db),
        patch("app.routers.runs.verify_api_key", return_value=ORG_ID),
    ):
        response = client.post(
            f"/runs/{RUN_ID}/spans",
            json={"name": "my-span"},
            headers={"Authorization": f"Bearer testkey"},
        )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["agent_id"] == AGENT_ID
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd ezop-platform && python -m pytest tests/test_runs.py -v
```

Expected: `FAILED` — `_get_run_agent` doesn't exist yet, and `agent_id` is not in INSERT.

- [ ] **Step 3: Rename `_assert_run_org` to `_get_run_agent`**

In `ezop-platform/app/routers/runs.py`, replace the helper:

```python
def _get_run_agent(db: Session, run_id: str, org_id: str) -> str:
    """Return agent_id for the run, or raise 404 if not found."""
    row = db.execute(
        text("SELECT agent_id FROM agent_runs WHERE id = :id AND organization_id = :org_id"),
        {"id": run_id, "org_id": org_id},
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    return str(row.agent_id)
```

- [ ] **Step 4: Update `end_run` to use the renamed helper**

In `end_run`, replace:

```python
_assert_run_org(db, run_id, org_id)
```

with:

```python
_get_run_agent(db, run_id, org_id)  # validates ownership; agent_id not needed here
```

- [ ] **Step 5: Update `emit_event` to capture and insert `agent_id`**

In `emit_event`, replace:

```python
_assert_run_org(db, run_id, org_id)
assert_events_limit(db, org_id)
```

with:

```python
agent_id = _get_run_agent(db, run_id, org_id)
assert_events_limit(db, org_id)
```

Then in the INSERT params block, add `agent_id` to the initial cols/vals/params:

```python
cols = ["run_id", "name", "category", "organization_id", "agent_id"]
vals = [":run_id", ":name", ":category", ":org_id", ":agent_id"]
params: dict = {
    "run_id": run_id,
    "name": payload.name,
    "category": payload.category,
    "org_id": org_id,
    "agent_id": agent_id,
}
```

- [ ] **Step 6: Update `create_span` to capture and insert `agent_id`**

In `create_span`, replace:

```python
_assert_run_org(db, run_id, org_id)
```

with:

```python
agent_id = _get_run_agent(db, run_id, org_id)
```

Then in the INSERT params block, add `agent_id` to the initial cols/vals/params:

```python
cols = ["run_id", "organization_id", "agent_id"]
vals = [":run_id", ":org_id", ":agent_id"]
params: dict = {"run_id": run_id, "org_id": org_id, "agent_id": agent_id}
```

- [ ] **Step 7: Run tests to confirm they pass**

```bash
cd ezop-platform && python -m pytest tests/test_runs.py tests/test_models.py -v
```

Expected: all 4 tests `PASSED`.

- [ ] **Step 8: Run the full test suite**

```bash
cd ezop-platform && python -m pytest -v
```

Expected: all tests pass (health + models + runs).

- [ ] **Step 9: Commit**

```bash
git add ezop-platform/app/routers/runs.py ezop-platform/tests/test_runs.py
git commit -m "feat: thread agent_id through emit_event and create_span"
```

---

## Task 4: Update ezop-light-ui events page read path

**Files:**
- Modify: `ezop-light-ui/app/dashboard/observability/events/page.tsx`

- [ ] **Step 1: Add `agent_id` to the event select set**

In `ezop-light-ui/app/dashboard/observability/events/page.tsx`, add `agent_id: true` to `eventSelect`:

```ts
const eventSelect = {
  id: true,
  agent_id: true,    // ← add this
  name: true,
  category: true,
  type: true,
  subtype: true,
  timestamp: true,
  run_id: true,
  span_id: true,
  iteration_id: true,
  input: true,
  output: true,
  metadata: true,
  error: true,
} as const;
```

- [ ] **Step 2: Add `agent_id` to the `EventRow` type**

```ts
type EventRow = {
  id: string;
  agent_id: string;          // ← add this
  name: string;
  category: string | null;
  type: string | null;
  subtype: string | null;
  timestamp: Date | null;
  run_id: string | null;
  span_id: string | null;
  iteration_id: number | null;
  input: unknown;
  output: unknown;
  metadata: unknown;
  error: unknown;
};
```

- [ ] **Step 3: Replace the indirect `runIds` agent filter with a direct `agent_id` filter**

Remove the entire `runIds` resolution block (lines ~70–83):

```ts
// DELETE this entire block:
let runIds: string[] | null = null;
if (agentId && orgId) {
  const runRows = await prisma.agentRun.findMany({
    where: {
      organization_id: orgId,
      agent_id: agentId,
      start_time: { gte: since },
    },
    select: { id: true },
  });
  runIds = runRows.map((r: (typeof runRows)[0]) => r.id);
}
const noRuns = agentId && runIds !== null && runIds.length === 0;
```

Replace `baseWhere` with:

```ts
const baseWhere = {
  organization_id: orgId,
  timestamp: { gte: since },
  ...(agentId ? { agent_id: agentId } : {}),
};
```

- [ ] **Step 4: Remove the `noRuns` guard on the event query**

Replace the guard condition:

```ts
// Before:
if (!noRuns && orgId) {
```

with:

```ts
if (orgId) {
```

- [ ] **Step 5: Replace the indirect `runToAgent` resolution with a direct `agent_id` lookup**

Remove the entire `runToAgent` block (lines ~153–181):

```ts
// DELETE this block:
const pageRunIds = [
  ...new Set(
    eventsData.map((e) => e.run_id).filter((id): id is string => Boolean(id)),
  ),
];
let runToAgent: Record<string, string> = {};

if (pageRunIds.length > 0) {
  const runRows: { id: string; agent_id: string }[] =
    await prisma.agentRun.findMany({
      where: { id: { in: pageRunIds } },
      select: { id: true, agent_id: true },
    });
  const agentIds = [
    ...new Set(runRows.map((r) => r.agent_id).filter(Boolean)),
  ];
  const agentNameRows: { id: string; name: string }[] =
    agentIds.length > 0
      ? await prisma.agent.findMany({
          where: { id: { in: agentIds } },
          select: { id: true, name: true },
        })
      : [];
  const agentNameById: Record<string, string> = {};
  for (const a of agentNameRows) agentNameById[a.id] = a.name;
  for (const r of runRows)
    runToAgent[r.id] = agentNameById[r.agent_id] ?? "—";
}
```

Replace with:

```ts
const agentIds = [
  ...new Set(eventsData.map((e) => e.agent_id).filter((id): id is string => Boolean(id))),
];
const agentNameRows: { id: string; name: string }[] =
  agentIds.length > 0
    ? await prisma.agent.findMany({
        where: { id: { in: agentIds } },
        select: { id: true, name: true },
      })
    : [];
const agentNameById: Record<string, string> = {};
for (const a of agentNameRows) agentNameById[a.id] = a.name;

const runToAgent: Record<string, string> = {};
for (const e of eventsData) {
  if (e.run_id && e.agent_id) runToAgent[e.run_id] = agentNameById[e.agent_id] ?? "—";
}
```

- [ ] **Step 6: Remove `pageRunIds` (it's no longer needed above the tree block)**

The tree view block still uses `pageRunIds` to fetch spans. Recompute it locally just before that block:

```ts
// Replace the tree-view section header with:
if (view === "tree" && eventsData.length > 0) {
  const pageRunIds = [
    ...new Set(eventsData.map((e) => e.run_id).filter((id): id is string => Boolean(id))),
  ];
  const spansData = await prisma.span.findMany({ ...
```

The outer `if (view === "tree" && pageRunIds.length > 0)` guard becomes `if (view === "tree" && eventsData.length > 0)`, and `pageRunIds` is defined at the top of that block.

- [ ] **Step 7: Verify TypeScript compiles**

```bash
cd ezop-light-ui && npx tsc --noEmit
```

Expected: no type errors.

- [ ] **Step 8: Commit**

```bash
git add ezop-light-ui/app/dashboard/observability/events/page.tsx
git commit -m "feat: filter events directly by agent_id, remove agentRun join"
```

---

## Self-Review Notes

- **Spec coverage:** Schema ✓, migration ✓, write path ✓, Pydantic models ✓, read path ✓, indexes ✓, backfill ✓
- **Consistency:** `_get_run_agent` is defined in Task 3 Step 3 and used in Steps 4/5/6. `agent_id: UUID` is added to models in Task 2 and consumed in Task 3 tests. `agent_id` in `eventSelect` (Task 4 Step 1) is required by the `agentNameById` lookup in Step 5.
- **No placeholders:** All code blocks are complete and runnable.
- **`end_run`:** Task 3 Step 4 explicitly updates `end_run` to use `_get_run_agent`; return value is discarded, which is intentional — `end_run` only needs ownership validation.
