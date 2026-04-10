# Trigger/Actor Tracking and agent2agent Runs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add trigger_type, trigger_id, and parent_run_id to agent_runs so every run records its cause and enables agent-to-agent call chains, with full UI visibility.

**Architecture:** DB migration adds three columns with CHECK constraints; ezop-platform validates them in StartRunRequest with a Pydantic model_validator; ezop-sdk exposes parent_run_id in Agent.init for agent-spawned runs; ezop-light-ui shows a Trigger column, "Triggered by" line, and collapsible Spawned Runs panel in AgentInventory.

**Tech Stack:** PostgreSQL, Prisma, FastAPI + Pydantic, Python SDK (requests), Next.js 15 server actions, TypeScript, React client component (inline styles, no CSS framework).

---

## File Map

| File | Change |
|---|---|
| `ezop-light-ui/prisma/schema.prisma` | Add 3 columns + self-relation `RunChain` to `AgentRun` |
| `ezop-light-ui/prisma/migrations/20260405120000_add_trigger_columns_to_agent_runs/migration.sql` | Create |
| `ezop-platform/database/migrations/20260405120000-add-trigger-columns-to-agent-runs.sql` | Create (mirror) |
| `ezop-platform/database/current/02-base-schemas.sql` | Update `agent_runs` DDL |
| `ezop-platform/app/models/agents.py` | Add `TriggerType` enum, add trigger fields to `AgentRun` |
| `ezop-platform/app/routers/agents.py` | Add trigger fields + validator to `StartRunRequest`, parent org check in `start_run` |
| `ezop-platform/tests/test_models.py` | Add `AgentRun` model tests |
| `ezop-platform/tests/test_agents.py` | Update `RUN_ROW` + add trigger validation/route tests |
| `ezop-sdk/python/ezop/client.py` | Add trigger params to `start_run` |
| `ezop-sdk/python/ezop/agent.py` | Add `parent_run_id`, `trigger_type`, `trigger_id` to `Agent.init` |
| `ezop-sdk/python/tests/test_agent.py` | Update `test_calls_start_run_with_correct_args`, add trigger tests |
| `ezop-light-ui/app/dashboard/agents/actions.ts` | Update `AgentRun` type, update query select, update mapping, add `listSpawnedRuns` |
| `ezop-light-ui/components/AgentInventory/index.tsx` | Add trigger badge, Trigger column, Triggered by line, Spawned runs panel |

---

### Task 1: DB schema migration

**Files:**
- Modify: `ezop-light-ui/prisma/schema.prisma:92-116`
- Create: `ezop-light-ui/prisma/migrations/20260405120000_add_trigger_columns_to_agent_runs/migration.sql`
- Create: `ezop-platform/database/migrations/20260405120000-add-trigger-columns-to-agent-runs.sql`
- Modify: `ezop-platform/database/current/02-base-schemas.sql:105-131`

- [ ] **Step 1: Update Prisma schema**

In `ezop-light-ui/prisma/schema.prisma`, replace the `AgentRun` model (currently lines 92–116) with:

```prisma
model AgentRun {
  id              String        @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  agent_id        String        @db.Uuid
  version_id      String?       @db.Uuid
  user_id         String?       @db.Uuid
  start_time      DateTime      @default(now()) @db.Timestamptz(6)
  end_time        DateTime?     @default(now()) @db.Timestamptz(6)
  status          run_status
  metadata        Json?
  created_at      DateTime      @default(now()) @db.Timestamptz(6)
  updated_at      DateTime      @default(now()) @db.Timestamptz(6)
  message         String?
  organization_id String        @db.Uuid
  trigger_type    String        @default("api")
  trigger_id      String?
  parent_run_id   String?       @db.Uuid
  agent           Agent         @relation(fields: [agent_id], references: [id], onDelete: Cascade, onUpdate: NoAction)
  organizations   Organization  @relation(fields: [organization_id], references: [id], onDelete: Cascade, onUpdate: NoAction)
  agent_versions  AgentVersion? @relation(fields: [version_id], references: [id], onUpdate: NoAction)
  parent_run      AgentRun?     @relation("RunChain", fields: [parent_run_id], references: [id], onDelete: SetNull, onUpdate: NoAction)
  spawned_runs    AgentRun[]    @relation("RunChain")
  events          Event[]
  spans           Span[]

  @@index([agent_id])
  @@index([start_time])
  @@index([status])
  @@index([version_id])
  @@index([parent_run_id], map: "agent_runs_parent_run_idx")
  @@index([trigger_type, trigger_id], map: "agent_runs_trigger_idx")
  @@map("agent_runs")
}
```

- [ ] **Step 2: Run Prisma generate to verify the schema parses**

```bash
cd ezop-light-ui
npx prisma generate
```

Expected: no errors, `✔ Generated Prisma Client`.

- [ ] **Step 3: Create the Prisma migration file manually**

Create directory and file:
`ezop-light-ui/prisma/migrations/20260405120000_add_trigger_columns_to_agent_runs/migration.sql`

```sql
-- Step 1: Add columns as nullable (no violation on existing rows)
ALTER TABLE "agent_runs" ADD COLUMN IF NOT EXISTS "trigger_type" TEXT;
ALTER TABLE "agent_runs" ADD COLUMN IF NOT EXISTS "trigger_id" TEXT;
ALTER TABLE "agent_runs" ADD COLUMN IF NOT EXISTS "parent_run_id" UUID;

-- Step 2: Backfill trigger_type on existing rows
UPDATE "agent_runs" SET "trigger_type" = 'api' WHERE "trigger_type" IS NULL;

-- Step 3: Make trigger_type NOT NULL and set default
ALTER TABLE "agent_runs" ALTER COLUMN "trigger_type" SET NOT NULL;
ALTER TABLE "agent_runs" ALTER COLUMN "trigger_type" SET DEFAULT 'api';

-- Foreign key for parent_run_id (self-referential)
ALTER TABLE "agent_runs" ADD CONSTRAINT "agent_runs_parent_run_id_fkey"
  FOREIGN KEY ("parent_run_id") REFERENCES "agent_runs"("id")
  ON DELETE SET NULL ON UPDATE NO ACTION;

-- CHECK constraints (DB-level enforcement)
ALTER TABLE "agent_runs" ADD CONSTRAINT "agent_requires_parent"
  CHECK (trigger_type != 'agent' OR parent_run_id IS NOT NULL);
ALTER TABLE "agent_runs" ADD CONSTRAINT "non_agent_forbids_parent"
  CHECK (trigger_type = 'agent' OR parent_run_id IS NULL);
ALTER TABLE "agent_runs" ADD CONSTRAINT "agent_forbids_trigger_id"
  CHECK (trigger_type != 'agent' OR trigger_id IS NULL);

-- Indexes
CREATE INDEX IF NOT EXISTS "agent_runs_parent_run_idx"
  ON "agent_runs" ("parent_run_id") WHERE "parent_run_id" IS NOT NULL;
CREATE INDEX IF NOT EXISTS "agent_runs_trigger_idx"
  ON "agent_runs" ("trigger_type", "trigger_id") WHERE "trigger_id" IS NOT NULL;
```

- [ ] **Step 4: Create the matching platform migration file**

Create `ezop-platform/database/migrations/20260405120000-add-trigger-columns-to-agent-runs.sql` with identical content to the Prisma migration above.

- [ ] **Step 5: Update the current schema reference**

In `ezop-platform/database/current/02-base-schemas.sql`, replace the `agent_runs` table definition (starting around line 105) with:

```sql
create table public.agent_runs (
  id uuid not null default gen_random_uuid (),
  agent_id uuid not null,
  version_id uuid null,
  user_id uuid null,
  start_time timestamp with time zone not null default now(),
  end_time timestamp with time zone null default now(),
  status public.run_status not null,
  metadata jsonb null,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  message text null,
  organization_id uuid not null,
  trigger_type text not null default 'api',
  trigger_id text null,
  parent_run_id uuid null,
  constraint agent_runs_pkey primary key (id),
  constraint agent_runs_agent_id_fkey foreign KEY (agent_id) references agents (id) on delete CASCADE,
  constraint agent_runs_organization_id_fkey foreign KEY (organization_id) references organizations (id) on delete CASCADE,
  constraint agent_runs_version_id_fkey foreign KEY (version_id) references agent_versions (id) on delete set null,
  constraint agent_runs_parent_run_id_fkey foreign KEY (parent_run_id) references agent_runs (id) on delete set null,
  constraint agent_requires_parent check (trigger_type != 'agent' OR parent_run_id IS NOT NULL),
  constraint non_agent_forbids_parent check (trigger_type = 'agent' OR parent_run_id IS NULL),
  constraint agent_forbids_trigger_id check (trigger_type != 'agent' OR trigger_id IS NULL)
) TABLESPACE pg_default;

create index IF not exists agent_runs_agent_id_idx on public.agent_runs using btree (agent_id) TABLESPACE pg_default;
create index IF not exists agent_runs_version_id_idx on public.agent_runs using btree (version_id) TABLESPACE pg_default;
create index IF not exists agent_runs_start_time_idx on public.agent_runs using btree (start_time) TABLESPACE pg_default;
create index IF not exists agent_runs_status_idx on public.agent_runs using btree (status) TABLESPACE pg_default;
create index IF not exists agent_runs_parent_run_idx on public.agent_runs using btree (parent_run_id) where parent_run_id is not null TABLESPACE pg_default;
create index IF not exists agent_runs_trigger_idx on public.agent_runs using btree (trigger_type, trigger_id) where trigger_id is not null TABLESPACE pg_default;
```

- [ ] **Step 6: Commit**

```bash
git add ezop-light-ui/prisma/schema.prisma \
        "ezop-light-ui/prisma/migrations/20260405120000_add_trigger_columns_to_agent_runs/migration.sql" \
        ezop-platform/database/migrations/20260405120000-add-trigger-columns-to-agent-runs.sql \
        ezop-platform/database/current/02-base-schemas.sql
git commit -m "feat: add trigger_type, trigger_id, parent_run_id to agent_runs"
```

---

### Task 2: Platform models — TriggerType enum + AgentRun Pydantic model

**Files:**
- Modify: `ezop-platform/app/models/agents.py`
- Modify: `ezop-platform/tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Add to `ezop-platform/tests/test_models.py` (after existing tests):

```python
from uuid import UUID

from app.models.agents import AgentRun as AgentRunModel, TriggerType


AGENT_RUN_BASE = {
    "id": "00000000-0000-0000-0000-000000000001",
    "agent_id": "00000000-0000-0000-0000-000000000002",
    "version_id": None,
    "user_id": None,
    "status": "success",
    "metadata": None,
    "message": None,
    "organization_id": "00000000-0000-0000-0000-000000000003",
    "start_time": "2026-01-01T00:00:00+00:00",
    "end_time": "2026-01-01T00:01:00+00:00",
    "created_at": "2026-01-01T00:00:00+00:00",
    "updated_at": "2026-01-01T00:00:00+00:00",
    "trigger_type": "api",
    "trigger_id": None,
    "parent_run_id": None,
}


def test_agent_run_model_has_trigger_type():
    run = AgentRunModel.model_validate(AGENT_RUN_BASE)
    assert run.trigger_type == "api"


def test_agent_run_model_trigger_id_optional():
    run = AgentRunModel.model_validate({**AGENT_RUN_BASE, "trigger_id": "user-123"})
    assert run.trigger_id == "user-123"


def test_agent_run_model_parent_run_id_optional():
    parent_id = "00000000-0000-0000-0000-000000000099"
    run = AgentRunModel.model_validate(
        {**AGENT_RUN_BASE, "trigger_type": "agent", "parent_run_id": parent_id}
    )
    assert run.parent_run_id == UUID(parent_id)


def test_trigger_type_enum_values():
    assert TriggerType.api == "api"
    assert TriggerType.user == "user"
    assert TriggerType.cron == "cron"
    assert TriggerType.webhook == "webhook"
    assert TriggerType.agent == "agent"
```

- [ ] **Step 2: Run to verify tests fail**

```bash
cd ezop-platform
.venv/bin/pytest tests/test_models.py::test_agent_run_model_has_trigger_type -v
```

Expected: `ImportError` — `TriggerType` not defined yet.

- [ ] **Step 3: Implement — update models/agents.py**

Replace the full contents of `ezop-platform/app/models/agents.py`:

```python
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RunStatus(StrEnum):
    running = "running"
    success = "success"
    failed = "failed"


class TriggerType(StrEnum):
    user = "user"
    cron = "cron"
    webhook = "webhook"
    api = "api"
    agent = "agent"


class Agent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    owner: str
    runtime: str | None
    description: str | None
    default_permissions: list[str] | None
    organization_id: UUID
    created_at: datetime
    updated_at: datetime


class AgentVersion(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: UUID
    version: str
    permissions: list[str] | None
    changelog: str | None
    organization_id: UUID
    created_at: datetime


class AgentRun(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: UUID
    version_id: UUID | None
    user_id: UUID | None
    status: RunStatus
    metadata: dict | None
    message: str | None
    organization_id: UUID
    start_time: datetime
    end_time: datetime | None
    created_at: datetime
    updated_at: datetime
    trigger_type: str
    trigger_id: str | None
    parent_run_id: UUID | None
```

- [ ] **Step 4: Run all model tests**

```bash
cd ezop-platform
.venv/bin/pytest tests/test_models.py -v
```

Expected: all 6 tests PASS (2 existing + 4 new).

- [ ] **Step 5: Commit**

```bash
git add ezop-platform/app/models/agents.py ezop-platform/tests/test_models.py
git commit -m "feat: add TriggerType enum and trigger fields to AgentRun model"
```

---

### Task 3: Platform write path — StartRunRequest + start_run route

**Files:**
- Modify: `ezop-platform/app/routers/agents.py`
- Modify: `ezop-platform/tests/test_agents.py`

Context: `StartRunRequest` is defined in `ezop-platform/app/routers/agents.py` (line 38). `start_run` route is in the same file (line 201). The `RUN_ROW` fixture in `test_agents.py` (line 29) must be updated to include trigger fields because `AgentRun.model_validate` will now require them.

- [ ] **Step 1: Write failing tests**

In `ezop-platform/tests/test_agents.py`:

1. Add `from unittest.mock import MagicMock` to the top imports.

2. Update `RUN_ROW` to include trigger fields:

```python
RUN_ROW = {
    "id": RUN_ID,
    "agent_id": AGENT_ID,
    "version_id": VERSION_ID,
    "user_id": None,
    "status": "running",
    "organization_id": ORG_ID,
    "start_time": "2024-01-01T00:00:00+00:00",
    "end_time": None,
    "message": None,
    "metadata": None,
    "created_at": "2024-01-01T00:00:00+00:00",
    "updated_at": "2024-01-01T00:00:00+00:00",
    "trigger_type": "api",
    "trigger_id": None,
    "parent_run_id": None,
}
```

3. Add after `TestStartRun`:

```python
PARENT_RUN_ID = "cccccccc-0000-0000-0000-000000000001"


class TestStartRunTrigger:
    def test_default_trigger_type_is_api(self, client, db):
        db.execute.side_effect = [
            make_exec(first=True),
            make_exec(mapping=RUN_ROW),
        ]
        resp = client.post(f"/agents/{AGENT_ID}/runs", json={})
        assert resp.status_code == 201
        assert resp.json()["data"]["trigger_type"] == "api"

    def test_agent_trigger_requires_parent_run_id(self, client, db):
        resp = client.post(
            f"/agents/{AGENT_ID}/runs",
            json={"trigger_type": "agent"},
        )
        assert resp.status_code == 422

    def test_non_agent_trigger_forbids_parent_run_id(self, client, db):
        resp = client.post(
            f"/agents/{AGENT_ID}/runs",
            json={"trigger_type": "api", "parent_run_id": PARENT_RUN_ID},
        )
        assert resp.status_code == 422

    def test_agent_trigger_forbids_trigger_id(self, client, db):
        resp = client.post(
            f"/agents/{AGENT_ID}/runs",
            json={"trigger_type": "agent", "parent_run_id": PARENT_RUN_ID, "trigger_id": "some-id"},
        )
        assert resp.status_code == 422

    def test_agent_trigger_with_parent_run_id_returns_201(self, client, db):
        parent_row = MagicMock()
        parent_row.organization_id = ORG_ID
        run_row = {**RUN_ROW, "trigger_type": "agent", "parent_run_id": PARENT_RUN_ID}
        db.execute.side_effect = [
            make_exec(first=True),
            make_exec(first=parent_row),
            make_exec(mapping=run_row),
        ]
        resp = client.post(
            f"/agents/{AGENT_ID}/runs",
            json={"trigger_type": "agent", "parent_run_id": PARENT_RUN_ID},
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["trigger_type"] == "agent"

    def test_parent_run_in_different_org_returns_422(self, client, db):
        parent_row = MagicMock()
        parent_row.organization_id = "ffffffff-0000-0000-0000-000000000001"
        db.execute.side_effect = [
            make_exec(first=True),
            make_exec(first=parent_row),
        ]
        resp = client.post(
            f"/agents/{AGENT_ID}/runs",
            json={"trigger_type": "agent", "parent_run_id": PARENT_RUN_ID},
        )
        assert resp.status_code == 422

    def test_parent_run_not_found_returns_422(self, client, db):
        db.execute.side_effect = [
            make_exec(first=True),
            make_exec(first=None),
        ]
        resp = client.post(
            f"/agents/{AGENT_ID}/runs",
            json={"trigger_type": "agent", "parent_run_id": PARENT_RUN_ID},
        )
        assert resp.status_code == 422
```

- [ ] **Step 2: Run to verify tests fail**

```bash
cd ezop-platform
.venv/bin/pytest tests/test_agents.py::TestStartRunTrigger -v
```

Expected: failures — `trigger_type` not on `StartRunRequest` yet.

- [ ] **Step 3: Update routers/agents.py imports**

At the top of `ezop-platform/app/routers/agents.py`, change the pydantic import line:

```python
from pydantic import BaseModel, model_validator
```

Change the agents model import line to add `TriggerType`:

```python
from app.models.agents import Agent, AgentRun, AgentVersion, TriggerType
```

- [ ] **Step 4: Replace StartRunRequest in routers/agents.py**

Replace the existing `StartRunRequest` class (lines 38–40):

```python
class StartRunRequest(BaseModel):
    version_id: str | None = None
    user_id: str | None = None
    metadata: dict | None = None
    trigger_type: TriggerType = TriggerType.api
    trigger_id: str | None = None
    parent_run_id: str | None = None

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

- [ ] **Step 5: Update start_run route body in routers/agents.py**

In the `start_run` function, after `_assert_agent_org(db, agent_id, org_id)`, add the parent org check and update the INSERT. Replace from `_assert_agent_org` call to end of function:

```python
    _assert_agent_org(db, agent_id, org_id)
    logger.info("Starting run agent_id=%s version_id=%s trigger_type=%s", agent_id, payload.version_id, payload.trigger_type)

    if payload.parent_run_id is not None:
        parent = db.execute(
            text("SELECT organization_id FROM agent_runs WHERE id = :id"),
            {"id": payload.parent_run_id},
        ).first()
        if parent is None or str(parent.organization_id) != org_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="parent_run_id not found or belongs to a different organization.",
            )

    row = (
        db.execute(
            text("""
            INSERT INTO agent_runs (agent_id, version_id, user_id, status, metadata, organization_id,
                                   trigger_type, trigger_id, parent_run_id)
            VALUES (:agent_id, :version_id, :user_id, 'running', :metadata, :org_id,
                    :trigger_type, :trigger_id, :parent_run_id)
            RETURNING *
        """),
            {
                "agent_id": agent_id,
                "version_id": payload.version_id,
                "user_id": payload.user_id,
                "metadata": payload.metadata,
                "org_id": org_id,
                "trigger_type": payload.trigger_type,
                "trigger_id": payload.trigger_id,
                "parent_run_id": payload.parent_run_id,
            },
        )
        .mappings()
        .first()
    )
    db.commit()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to start run — unexpected response from database.",
        )

    run = AgentRun.model_validate(dict(row))
    logger.info("Run started id=%s agent_id=%s trigger_type=%s", run.id, agent_id, run.trigger_type)
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"success": True, "data": run.model_dump(mode="json"), "error": None},
    )
```

- [ ] **Step 6: Run all platform tests**

```bash
cd ezop-platform
.venv/bin/pytest tests/ -v
```

Expected: all tests PASS. Verify `TestStartRunTrigger` (7 tests) and `TestStartRun` (existing 2 tests) all pass.

- [ ] **Step 7: Run linter**

```bash
cd ezop-platform
.venv/bin/ruff check app/ tests/
```

Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add ezop-platform/app/routers/agents.py ezop-platform/tests/test_agents.py
git commit -m "feat: add trigger fields and parent_run validation to start_run"
```

---

### Task 4: SDK — client + agent trigger support

**Files:**
- Modify: `ezop-sdk/python/ezop/client.py`
- Modify: `ezop-sdk/python/ezop/agent.py`
- Modify: `ezop-sdk/python/tests/test_agent.py`

Context: `EzopClient.start_run` is in `ezop-sdk/python/ezop/client.py` (line 50). `Agent.init` is in `ezop-sdk/python/ezop/agent.py` (line 98). The existing SDK test `test_calls_start_run_with_correct_args` at line 137 of `test_agent.py` will break because the call signature changes.

- [ ] **Step 1: Update test_calls_start_run_with_correct_args**

In `ezop-sdk/python/tests/test_agent.py`, replace `test_calls_start_run_with_correct_args` (lines 137–144):

```python
    def test_calls_start_run_with_correct_args(self):
        with (
            patch("ezop.client.EzopClient.register_agent", return_value=AGENT_RESP),
            patch("ezop.client.EzopClient.create_version", return_value=VERSION_RESP),
            patch("ezop.client.EzopClient.start_run", return_value=RUN_RESP) as mock_run,
        ):
            Agent.init(name="support-bot", owner="growth-team", version="v0.3", runtime="langchain")
            mock_run.assert_called_once_with(
                "agent-uuid-123",
                "version-uuid-456",
                trigger_type=None,
                trigger_id=None,
                parent_run_id=None,
            )
```

- [ ] **Step 2: Add TestAgentInitTrigger class**

Add after `TestAgentInit` class (before `TestAgentClose`):

```python
class TestAgentInitTrigger:
    def test_passes_parent_run_id_to_start_run(self):
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
                trigger_type="agent",
                parent_run_id="parent-run-uuid-000",
            )
            mock_run.assert_called_once_with(
                "agent-uuid-123",
                "version-uuid-456",
                trigger_type="agent",
                trigger_id=None,
                parent_run_id="parent-run-uuid-000",
            )

    def test_passes_trigger_id_to_start_run(self):
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
                trigger_type="user",
                trigger_id="user-abc",
            )
            mock_run.assert_called_once_with(
                "agent-uuid-123",
                "version-uuid-456",
                trigger_type="user",
                trigger_id="user-abc",
                parent_run_id=None,
            )
```

- [ ] **Step 3: Run to verify tests fail**

```bash
cd ezop-sdk/python
.venv/bin/pytest tests/test_agent.py::TestAgentInit::test_calls_start_run_with_correct_args tests/test_agent.py::TestAgentInitTrigger -v
```

Expected: failures — `Agent.init` doesn't accept `trigger_type`/`parent_run_id` yet.

- [ ] **Step 4: Update client.py — add trigger params to start_run**

Replace the `start_run` method in `ezop-sdk/python/ezop/client.py` (lines 50–67):

```python
    def start_run(
        self,
        agent_id: str,
        version_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[dict] = None,
        trigger_type: Optional[str] = None,
        trigger_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
    ) -> dict:
        logger.info("Starting run agent_id=%s version_id=%s", agent_id, version_id)
        body: dict = {}
        if version_id is not None:
            body["version_id"] = version_id
        if user_id is not None:
            body["user_id"] = user_id
        if metadata is not None:
            body["metadata"] = metadata
        if trigger_type is not None:
            body["trigger_type"] = trigger_type
        if trigger_id is not None:
            body["trigger_id"] = trigger_id
        if parent_run_id is not None:
            body["parent_run_id"] = parent_run_id
        result = self._post(f"/agents/{agent_id}/runs", body)
        logger.info("Run started id=%s", result.get("data", {}).get("id"))
        return result
```

- [ ] **Step 5: Update agent.py — add trigger params to Agent.init**

In `Agent.init` (line 98), add three keyword-only parameters after `changelog=None`:

```python
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
```

Replace the `client.start_run` call (line 164) with:

```python
        run_data = client.start_run(
            model.id,
            agent_version.id,
            trigger_type=trigger_type,
            trigger_id=trigger_id,
            parent_run_id=parent_run_id,
        )["data"]
```

- [ ] **Step 6: Run all SDK tests**

```bash
cd ezop-sdk/python
.venv/bin/pytest tests/test_agent.py -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add ezop-sdk/python/ezop/client.py ezop-sdk/python/ezop/agent.py ezop-sdk/python/tests/test_agent.py
git commit -m "feat: expose trigger_type, trigger_id, parent_run_id in SDK Agent.init"
```

---

### Task 5: UI data layer — actions.ts

**Files:**
- Modify: `ezop-light-ui/app/dashboard/agents/actions.ts`

Context: `AgentRun` type is at line 12. `listAgents` function starts at line 80. The `prisma.agentRun.findMany` call is at lines 107–118. The `recentRuns` mapping is at lines 147–159. After the schema migration (Task 1), Prisma generates `spawned_runs` as a relation on `AgentRun` because of the `@relation("RunChain")` self-reference.

- [ ] **Step 1: Replace AgentRun type**

Replace lines 12–17 of `actions.ts`:

```ts
export type AgentRun = {
  id: string;
  status: "success" | "failed" | "partial" | "running" | "cancelled";
  startTime: string;
  durationS: number;
  triggerType: string;
  triggerId: string | null;
  parentRunId: string | null;
  spawnedRunCount: number;
};
```

- [ ] **Step 2: Add SpawnedRun type and listSpawnedRuns after AgentRun type**

```ts
export type SpawnedRun = {
  id: string;
  status: string;
  startTime: string;
  durationS: number;
};

export async function listSpawnedRuns(runId: string): Promise<SpawnedRun[]> {
  const { organizationId } = await getOrgContext();
  const rows = await prisma.agentRun.findMany({
    where: { parent_run_id: runId, organization_id: organizationId },
    orderBy: { start_time: "asc" },
    select: {
      id: true,
      status: true,
      start_time: true,
      end_time: true,
    },
  });
  return rows.map((r: (typeof rows)[0]) => {
    const start = r.start_time.getTime();
    const end = r.end_time ? r.end_time.getTime() : start;
    return {
      id: r.id,
      status: r.status,
      startTime: r.start_time.toISOString(),
      durationS: Math.max(0, Math.round((end - start) / 1000)),
    };
  });
}
```

- [ ] **Step 3: Update agentRun query in listAgents**

Replace the `prisma.agentRun.findMany` call (lines 107–118) with:

```ts
    prisma.agentRun.findMany({
      where: { organization_id: organizationId },
      orderBy: { start_time: "desc" },
      take: 500,
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
      },
    }),
```

- [ ] **Step 4: Update recentRuns mapping**

Replace the `recentRuns` mapping (lines 147–159):

```ts
    const recentRuns: AgentRun[] = agentRuns
      .slice(0, 10)
      .map((r: (typeof runRows)[0]) => {
        const start = r.start_time.getTime();
        const end = r.end_time ? r.end_time.getTime() : start;
        const durationS = Math.max(0, Math.round((end - start) / 1000));
        return {
          id: r.id,
          status: r.status as AgentRun["status"],
          startTime: r.start_time.toISOString(),
          durationS,
          triggerType: r.trigger_type,
          triggerId: r.trigger_id ?? null,
          parentRunId: r.parent_run_id ?? null,
          spawnedRunCount: r._count.spawned_runs,
        };
      });
```

- [ ] **Step 5: Run TypeScript type check**

```bash
cd ezop-light-ui
npx tsc --noEmit
```

Expected: no type errors.

- [ ] **Step 6: Commit**

```bash
git add ezop-light-ui/app/dashboard/agents/actions.ts
git commit -m "feat: add trigger fields and spawned run count to AgentRun query"
```

---

### Task 6: UI component — trigger column, Triggered by, Spawned runs panel

**Files:**
- Modify: `ezop-light-ui/components/AgentInventory/index.tsx`

Context: `RunsTab` is at lines 190–245. The grid template is currently `"1fr 70px 60px 16px"` (4 columns: Run ID, Status, Duration, expand arrow). `AgentRun` and `RunEvent` are imported from `actions.ts` at line 4. The `handleRunClick` async function is at line 195. The expanded row detail currently shows only the `SpanTree` component.

- [ ] **Step 1: Update the import line**

Replace line 4–5 of `ezop-light-ui/components/AgentInventory/index.tsx`:

```ts
import type { Agent, AgentRun, RunEvent, SpawnedRun } from "@/app/dashboard/agents/actions"
import { listRunEvents, listSpawnedRuns } from "@/app/dashboard/agents/actions"
```

- [ ] **Step 2: Add trigger constants and TriggerBadge component**

After `RUN_STATUS_COLOR` (around line 38), add:

```ts
const TRIGGER_COLOR: Record<string, string> = {
  api:     "#6B7280",
  user:    "#3B82F6",
  cron:    "#8B5CF6",
  webhook: "#F97316",
  agent:   "#06B6D4",
}

function TriggerBadge({ run, onParentClick }: { run: AgentRun; onParentClick: (id: string) => void }) {
  const color = TRIGGER_COLOR[run.triggerType] ?? "#6B7280"
  const label = run.triggerType.toUpperCase()
  if (run.triggerType === "agent" && run.parentRunId) {
    return (
      <span
        onClick={e => { e.stopPropagation(); onParentClick(run.parentRunId!) }}
        style={{ display: "inline-flex", alignItems: "center", gap: 3, padding: "2px 6px", borderRadius: 99, fontSize: 10, fontWeight: 500, background: color + "22", color, cursor: "pointer", border: `1px solid ${color}44` }}
      >
        {label} ↑
      </span>
    )
  }
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 3, padding: "2px 6px", borderRadius: 99, fontSize: 10, fontWeight: 500, background: color + "22", color }}>
      {label}{run.triggerId ? ` · ${run.triggerId.slice(0, 10)}` : ""}
    </span>
  )
}
```

- [ ] **Step 3: Replace RunsTab function**

Replace the entire `RunsTab` function (lines 190–245):

```ts
function RunsTab({ agent }: { agent: Agent }) {
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null)
  const [runEvents, setRunEvents] = useState<Record<string, RunEvent[]>>({})
  const [loadingRunId, setLoadingRunId] = useState<string | null>(null)
  const [spawnedRuns, setSpawnedRuns] = useState<Record<string, SpawnedRun[]>>({})
  const [loadingSpawnedRunId, setLoadingSpawnedRunId] = useState<string | null>(null)
  const [expandedSpawnedRunId, setExpandedSpawnedRunId] = useState<string | null>(null)

  async function handleRunClick(runId: string) {
    if (expandedRunId === runId) { setExpandedRunId(null); return }
    setExpandedRunId(runId)
    if (runEvents[runId]) return
    setLoadingRunId(runId)
    try {
      const events = await listRunEvents(runId)
      setRunEvents(prev => ({ ...prev, [runId]: events }))
    } finally {
      setLoadingRunId(null)
    }
  }

  async function handleSpawnedRunsClick(runId: string) {
    if (expandedSpawnedRunId === runId) { setExpandedSpawnedRunId(null); return }
    setExpandedSpawnedRunId(runId)
    if (spawnedRuns[runId]) return
    setLoadingSpawnedRunId(runId)
    try {
      const runs = await listSpawnedRuns(runId)
      setSpawnedRuns(prev => ({ ...prev, [runId]: runs }))
    } finally {
      setLoadingSpawnedRunId(null)
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 80px 70px 60px 16px", gap: "0.5rem", fontSize: 10, color: "var(--text-muted)", paddingBottom: 6, borderBottom: "1px solid var(--card-border)" }}>
        {["Run ID", "Trigger", "Status", "Duration", ""].map(h => <div key={h}>{h}</div>)}
      </div>
      {agent.recentRuns.map(run => {
        const isExpanded = expandedRunId === run.id
        const isLoading  = loadingRunId === run.id
        return (
          <div key={run.id}>
            <div
              onClick={() => handleRunClick(run.id)}
              style={{
                display: "grid", gridTemplateColumns: "1fr 80px 70px 60px 16px",
                gap: "0.5rem", padding: "0.6rem 0", borderBottom: "1px solid var(--card-border)",
                alignItems: "center", fontSize: 12, cursor: "pointer",
                background: isExpanded ? "var(--sidebar-active-bg)" : "transparent",
              }}
            >
              <div style={{ fontFamily: "monospace", color: "var(--text-muted)", fontSize: 11 }}>{run.id.slice(0, 8)}</div>
              <TriggerBadge run={run} onParentClick={handleRunClick} />
              <span style={{ display: "inline-block", padding: "2px 6px", borderRadius: 99, fontSize: 10, fontWeight: 500, background: RUN_STATUS_COLOR[run.status] + "22", color: RUN_STATUS_COLOR[run.status] }}>{run.status}</span>
              <div style={{ color: "var(--text-muted)" }}>{run.durationS}s</div>
              <div style={{ fontSize: 10, color: "var(--text-muted)" }}>{isExpanded ? "▲" : "▼"}</div>
            </div>
            {isExpanded && (
              <div style={{ padding: "0.75rem 0.5rem", borderBottom: "1px solid var(--card-border)", background: "var(--sidebar-active-bg)" }}>
                {/* Triggered by */}
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: "0.5rem", display: "flex", alignItems: "center", gap: 6 }}>
                  <span>Triggered by</span>
                  <TriggerBadge run={run} onParentClick={handleRunClick} />
                  {run.triggerType === "agent" && run.parentRunId && (
                    <span style={{ fontFamily: "monospace", fontSize: 11, color: "var(--text-muted)" }}>
                      Run {run.parentRunId.slice(0, 8)}
                    </span>
                  )}
                </div>

                {/* Spawned runs panel */}
                {run.spawnedRunCount > 0 && (
                  <div style={{ marginBottom: "0.75rem" }}>
                    <button
                      onClick={e => { e.stopPropagation(); handleSpawnedRunsClick(run.id) }}
                      style={{ background: "none", border: "none", cursor: "pointer", padding: "4px 0", display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--text-muted)", width: "100%" }}
                    >
                      <span>{expandedSpawnedRunId === run.id ? "▼" : "▶"}</span>
                      <span>Spawned runs ({run.spawnedRunCount})</span>
                    </button>
                    {expandedSpawnedRunId === run.id && (
                      <div style={{ marginTop: 4, paddingLeft: 12, borderLeft: "2px solid var(--card-border)" }}>
                        {loadingSpawnedRunId === run.id ? (
                          <div style={{ fontSize: 11, color: "var(--text-muted)", padding: "4px 0" }}>Loading…</div>
                        ) : (spawnedRuns[run.id] ?? []).map(sr => (
                          <div
                            key={sr.id}
                            style={{ display: "grid", gridTemplateColumns: "1fr 70px 50px", gap: "0.5rem", padding: "4px 0", fontSize: 11, borderBottom: "1px solid var(--card-border)", alignItems: "center" }}
                          >
                            <span style={{ fontFamily: "monospace", color: "var(--text-muted)" }}>{sr.id.slice(0, 8)}</span>
                            <span style={{ padding: "1px 5px", borderRadius: 99, fontSize: 10, background: RUN_STATUS_COLOR[sr.status as AgentRun["status"]] + "22", color: RUN_STATUS_COLOR[sr.status as AgentRun["status"]] }}>{sr.status}</span>
                            <span style={{ color: "var(--text-muted)" }}>{sr.durationS}s</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Events tree */}
                {isLoading
                  ? <div style={{ textAlign: "center", color: "var(--text-muted)", fontSize: 12, padding: "1rem 0" }}>Loading events…</div>
                  : <SpanTree events={runEvents[run.id] ?? []} />
                }
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 4: Run TypeScript type check**

```bash
cd ezop-light-ui
npx tsc --noEmit
```

Expected: no type errors.

- [ ] **Step 5: Run ESLint**

```bash
cd ezop-light-ui
npm run lint
```

Expected: no errors or warnings on changed files.

- [ ] **Step 6: Commit**

```bash
git add ezop-light-ui/components/AgentInventory/index.tsx
git commit -m "feat: add trigger column, Triggered by line, and Spawned runs panel to AgentInventory"
```
