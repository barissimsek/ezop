# Trigger Type Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `trigger_type` and `trigger_id` columns to `agent_runs` so every run records what triggered it (API, agent, user, cron, webhook, or unknown).

**Architecture:** A new PostgreSQL enum `trigger_type_t` and two columns on `agent_runs` are added via a migration. The platform exposes these as optional fields on `StartRunRequest` with a cross-field validator enforcing that `trigger_type='agent'` requires `parent_run_id`. The SDK forwards both optional parameters through `Agent.init()` → `EzopClient.start_run()` and populates them on `AgentRun`.

**Tech Stack:** PostgreSQL enum, FastAPI/Pydantic v2, Python StrEnum, Python dataclasses, pytest, Prisma

---

### Task 1: DB Migration — Add `trigger_type_t` enum and columns

**Files:**
- Create: `ezop-platform/database/migrations/0009_add_trigger_type.sql`
- Modify: `ezop-platform/database/current/01-enumerated-types.sql`
- Modify: `ezop-platform/database/current/02-base-schemas.sql`
- Modify: `ezop-light-ui/prisma/schema.prisma`
- Create: `ezop-light-ui/prisma/migrations/20260411000000_add_trigger_type/migration.sql`

- [ ] **Step 1: Write the migration file**

Create `ezop-platform/database/migrations/0009_add_trigger_type.sql`:

```sql
-- Migration: 0009_add_trigger_type
-- Adds trigger_type_t enum and trigger columns to agent_runs

CREATE TYPE public.trigger_type_t AS ENUM (
    'unknown',
    'api',
    'agent',
    'user',
    'cron',
    'webhook'
);

ALTER TABLE public.agent_runs
    ADD COLUMN trigger_type public.trigger_type_t NOT NULL DEFAULT 'unknown',
    ADD COLUMN trigger_id   TEXT NULL;

CREATE INDEX idx_agent_runs_trigger_type ON public.agent_runs (trigger_type);
```

- [ ] **Step 2: Update canonical enum types file**

In `ezop-platform/database/current/01-enumerated-types.sql`, add after the last existing enum:

```sql
CREATE TYPE public.trigger_type_t AS ENUM (
    'unknown',
    'api',
    'agent',
    'user',
    'cron',
    'webhook'
);
```

- [ ] **Step 3: Update canonical base schema**

In `ezop-platform/database/current/02-base-schemas.sql`, inside the `agent_runs` table definition add the two new columns and index. After the existing `root_run_id` line add:

```sql
    trigger_type            public.trigger_type_t       not null    default 'unknown',
    trigger_id              text                        null,
```

And after the existing `idx_agent_runs_root_run_id` index line add:

```sql
create index idx_agent_runs_trigger_type on public.agent_runs (trigger_type);
```

- [ ] **Step 4: Update Prisma schema**

In `ezop-light-ui/prisma/schema.prisma`, add the enum and update the `AgentRun` model.

Add the enum (after the existing `RunStatus` enum or near other enums):

```prisma
enum trigger_type_t {
  unknown
  api
  agent
  user
  cron
  webhook
}
```

In the `AgentRun` model, add after `root_run_id`:

```prisma
  trigger_type  trigger_type_t  @default(unknown)
  trigger_id    String?
```

And add to `@@index` list:

```prisma
  @@index([trigger_type])
```

- [ ] **Step 5: Create Prisma migration file**

Create `ezop-light-ui/prisma/migrations/20260411000000_add_trigger_type/migration.sql`:

```sql
-- CreateEnum
CREATE TYPE "trigger_type_t" AS ENUM ('unknown', 'api', 'agent', 'user', 'cron', 'webhook');

-- AlterTable
ALTER TABLE "AgentRun" ADD COLUMN "trigger_id" TEXT,
ADD COLUMN "trigger_type" "trigger_type_t" NOT NULL DEFAULT 'unknown';

-- CreateIndex
CREATE INDEX "AgentRun_trigger_type_idx" ON "AgentRun"("trigger_type");
```

- [ ] **Step 6: Commit**

```bash
git add ezop-platform/database/migrations/0009_add_trigger_type.sql \
        ezop-platform/database/current/01-enumerated-types.sql \
        ezop-platform/database/current/02-base-schemas.sql \
        ezop-light-ui/prisma/schema.prisma \
        ezop-light-ui/prisma/migrations/20260411000000_add_trigger_type/migration.sql
git commit -m "feat: add trigger_type_t enum and columns to agent_runs"
```

---

### Task 2: Platform — TriggerType enum, StartRunRequest validator, INSERT update

**Files:**
- Modify: `ezop-platform/app/models/agents.py`
- Modify: `ezop-platform/app/routers/agents.py`
- Modify: `ezop-platform/tests/test_agents.py`

- [ ] **Step 1: Write failing tests**

In `ezop-platform/tests/test_agents.py`:

1. Add `trigger_type` and `trigger_id` to the `RUN_ROW` fixture used in existing tests. Find `RUN_ROW` and add:

```python
RUN_ROW = {
    # ... existing fields ...
    "trigger_type": "unknown",
    "trigger_id": None,
}
```

2. Add a new test class after `TestStartRun`:

```python
class TestStartRunTrigger:
    def test_start_run_with_cron_trigger(self, client, mock_db):
        mock_db.execute.return_value.mappings.return_value.first.side_effect = [
            {"organization_id": ORG_ID},  # _assert_agent_org
            {**RUN_ROW, "trigger_type": "cron", "trigger_id": "daily-cleanup"},
        ]
        resp = client.post(
            f"/agents/{AGENT_ID}/runs",
            json={"trigger_type": "cron", "trigger_id": "daily-cleanup"},
            headers={"x-api-key": "test-key"},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["trigger_type"] == "cron"
        assert data["trigger_id"] == "daily-cleanup"

    def test_start_run_default_trigger_unknown(self, client, mock_db):
        mock_db.execute.return_value.mappings.return_value.first.side_effect = [
            {"organization_id": ORG_ID},
            {**RUN_ROW},
        ]
        resp = client.post(
            f"/agents/{AGENT_ID}/runs",
            json={},
            headers={"x-api-key": "test-key"},
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["trigger_type"] == "unknown"

    def test_agent_trigger_requires_parent_run_id(self, client, mock_db):
        mock_db.execute.return_value.mappings.return_value.first.return_value = {
            "organization_id": ORG_ID
        }
        resp = client.post(
            f"/agents/{AGENT_ID}/runs",
            json={"trigger_type": "agent"},
            headers={"x-api-key": "test-key"},
        )
        assert resp.status_code == 422
        assert "parent_run_id required" in resp.json()["detail"][0]["msg"]

    def test_non_agent_trigger_rejects_parent_run_id(self, client, mock_db):
        mock_db.execute.return_value.mappings.return_value.first.return_value = {
            "organization_id": ORG_ID
        }
        resp = client.post(
            f"/agents/{AGENT_ID}/runs",
            json={"trigger_type": "user", "parent_run_id": PARENT_RUN_ID},
            headers={"x-api-key": "test-key"},
        )
        assert resp.status_code == 422
        assert "parent_run_id only valid" in resp.json()["detail"][0]["msg"]
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd ezop-platform && .venv/bin/pytest tests/test_agents.py::TestStartRunTrigger -v
```

Expected: FAIL (fields don't exist yet)

- [ ] **Step 3: Add TriggerType enum to models**

In `ezop-platform/app/models/agents.py`, add after the `RunStatus` class:

```python
class TriggerType(StrEnum):
    unknown = "unknown"
    api     = "api"
    agent   = "agent"
    user    = "user"
    cron    = "cron"
    webhook = "webhook"
```

Add `trigger_type` and `trigger_id` to the `AgentRun` Pydantic model:

```python
trigger_type: TriggerType
trigger_id: str | None
```

- [ ] **Step 4: Update StartRunRequest and start_run endpoint**

In `ezop-platform/app/routers/agents.py`:

1. Import `TriggerType` and add `model_validator`:

```python
from pydantic import BaseModel, model_validator
from app.models.agents import Agent, AgentRun, AgentVersion, TriggerType
```

2. Update `StartRunRequest`:

```python
class StartRunRequest(BaseModel):
    version_id: str | None = None
    user_id: str | None = None
    metadata: dict | None = None
    parent_run_id: str | None = None
    trigger_type: TriggerType = TriggerType.unknown
    trigger_id: str | None = None

    @model_validator(mode="after")
    def validate_trigger(self) -> "StartRunRequest":
        if self.trigger_type == TriggerType.agent and self.parent_run_id is None:
            raise ValueError("parent_run_id required when trigger_type is 'agent'")
        if self.trigger_type != TriggerType.agent and self.parent_run_id is not None:
            raise ValueError("parent_run_id only valid when trigger_type is 'agent'")
        return self
```

3. Update the INSERT in `start_run` to include the new columns:

```python
row = (
    db.execute(
        text("""
            INSERT INTO agent_runs
                (id, agent_id, version_id, user_id, parent_run_id, root_run_id, status, metadata, organization_id, trigger_type, trigger_id)
            VALUES
                (:id, :agent_id, :version_id, :user_id, :parent_run_id, :root_run_id, 'running', :metadata, :org_id, :trigger_type, :trigger_id)
            RETURNING *
        """),
        {
            "id": run_id,
            "agent_id": agent_id,
            "version_id": payload.version_id,
            "user_id": payload.user_id,
            "parent_run_id": payload.parent_run_id,
            "root_run_id": root_run_id,
            "metadata": payload.metadata,
            "org_id": org_id,
            "trigger_type": payload.trigger_type.value,
            "trigger_id": payload.trigger_id,
        },
    )
    .mappings()
    .first()
)
```

- [ ] **Step 5: Run tests**

```bash
cd ezop-platform && .venv/bin/pytest tests/test_agents.py -v
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add ezop-platform/app/models/agents.py \
        ezop-platform/app/routers/agents.py \
        ezop-platform/tests/test_agents.py
git commit -m "feat: add TriggerType enum and trigger fields to platform start_run"
```

---

### Task 3: SDK — AgentRun dataclass, client, agent, tests

**Files:**
- Modify: `ezop-sdk/python/ezop/models.py`
- Modify: `ezop-sdk/python/ezop/client.py`
- Modify: `ezop-sdk/python/ezop/agent.py`
- Modify: `ezop-sdk/python/tests/test_agent.py`

- [ ] **Step 1: Write failing tests**

In `ezop-sdk/python/tests/test_agent.py`:

1. Update `RUN_RESP` to include new fields:

```python
RUN_RESP = {
    "id": "run-uuid-789",
    "status": "running",
    "parent_run_id": None,
    "root_run_id": "run-uuid-789",
    "trigger_type": "unknown",
    "trigger_id": None,
}
```

2. Update `test_calls_start_run_with_correct_args` to include new params:

```python
mock_client.start_run.assert_called_once_with(
    "agent-uuid-123",
    "version-uuid-456",
    parent_run_id=None,
    trigger_type=None,
    trigger_id=None,
)
```

3. Add new tests:

```python
def test_calls_start_run_with_trigger_type_and_id(mock_client):
    mock_client.register_agent.return_value = {"data": AGENT_RESP}
    mock_client.create_version.return_value = {"data": VERSION_RESP}
    mock_client.start_run.return_value = {
        "data": {**RUN_RESP, "trigger_type": "cron", "trigger_id": "daily-cleanup"}
    }

    with patch("ezop.agent.EzopClient", return_value=mock_client):
        agent = Agent.init(
            name="test-agent",
            owner="test-owner",
            version="1.0.0",
            runtime="python",
            trigger_type="cron",
            trigger_id="daily-cleanup",
        )

    mock_client.start_run.assert_called_once_with(
        "agent-uuid-123",
        "version-uuid-456",
        parent_run_id=None,
        trigger_type="cron",
        trigger_id="daily-cleanup",
    )
    assert agent.current_run.trigger_type == "cron"
    assert agent.current_run.trigger_id == "daily-cleanup"


def test_run_has_trigger_type_and_id(mock_client):
    mock_client.register_agent.return_value = {"data": AGENT_RESP}
    mock_client.create_version.return_value = {"data": VERSION_RESP}
    mock_client.start_run.return_value = {"data": RUN_RESP}

    with patch("ezop.agent.EzopClient", return_value=mock_client):
        agent = Agent.init(
            name="test-agent",
            owner="test-owner",
            version="1.0.0",
            runtime="python",
        )

    assert agent.current_run.trigger_type == "unknown"
    assert agent.current_run.trigger_id is None
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd ezop-sdk/python && .venv/bin/pytest tests/test_agent.py -v
```

Expected: FAIL

- [ ] **Step 3: Update AgentRun dataclass in models.py**

In `ezop-sdk/python/ezop/models.py`, in the `AgentRun` dataclass add before `_current_span_id`:

```python
trigger_type: Optional[str] = None
trigger_id: Optional[str] = None
```

- [ ] **Step 4: Update EzopClient.start_run()**

In `ezop-sdk/python/ezop/client.py`, update `start_run()`:

```python
def start_run(
    self,
    agent_id: str,
    version_id: Optional[str] = None,
    user_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    parent_run_id: Optional[str] = None,
    trigger_type: Optional[str] = None,
    trigger_id: Optional[str] = None,
) -> dict:
    body: dict = {}
    if version_id is not None:
        body["version_id"] = version_id
    if user_id is not None:
        body["user_id"] = user_id
    if metadata is not None:
        body["metadata"] = metadata
    if parent_run_id is not None:
        body["parent_run_id"] = parent_run_id
    if trigger_type is not None:
        body["trigger_type"] = trigger_type
    if trigger_id is not None:
        body["trigger_id"] = trigger_id
    return self._post(f"/agents/{agent_id}/runs", body)
```

- [ ] **Step 5: Update Agent.init()**

In `ezop-sdk/python/ezop/agent.py`, add `trigger_type` and `trigger_id` to `Agent.init()` keyword-only params:

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
    parent_run_id: Optional[str] = None,
    trigger_type: Optional[str] = None,
    trigger_id: Optional[str] = None,
) -> "Agent":
```

Update the `client.start_run(...)` call:

```python
run_data = client.start_run(
    model.id,
    agent_version.id,
    parent_run_id=parent_run_id,
    trigger_type=trigger_type,
    trigger_id=trigger_id,
)["data"]
```

Update the `AgentRun` construction:

```python
agent.current_run = AgentRun(
    id=run_data["id"],
    agent_id=model.id,
    version_id=agent_version.id,
    status=run_data.get("status", "running"),
    parent_run_id=run_data.get("parent_run_id"),
    root_run_id=run_data.get("root_run_id"),
    trigger_type=run_data.get("trigger_type"),
    trigger_id=run_data.get("trigger_id"),
)
```

- [ ] **Step 6: Run tests**

```bash
cd ezop-sdk/python && .venv/bin/pytest tests/test_agent.py -v
```

Expected: all pass

- [ ] **Step 7: Format**

```bash
cd ezop-sdk/python && .venv/bin/ruff format ezop/ tests/
```

- [ ] **Step 8: Commit**

```bash
git add ezop-sdk/python/ezop/models.py \
        ezop-sdk/python/ezop/client.py \
        ezop-sdk/python/ezop/agent.py \
        ezop-sdk/python/tests/test_agent.py
git commit -m "feat: add trigger_type and trigger_id to SDK AgentRun, client, and agent"
```

---

### Task 4: Final Verification

**Files:** none — run existing test suites

- [ ] **Step 1: Run full platform test suite**

```bash
cd ezop-platform && .venv/bin/pytest tests/ -v
```

Expected: all pass

- [ ] **Step 2: Run full SDK test suite**

```bash
cd ezop-sdk/python && .venv/bin/pytest tests/ -v
```

Expected: all pass

- [ ] **Step 3: Run platform linter**

```bash
cd ezop-platform && .venv/bin/ruff check app/ tests/
```

Expected: no issues

- [ ] **Step 4: Run SDK linter**

```bash
cd ezop-sdk/python && .venv/bin/ruff check ezop/ tests/
```

Expected: no issues
