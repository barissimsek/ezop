# Agent-to-Agent Run Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add parent/child relationships to agent runs so multi-agent workflows can be traced as a tree, with `root_run_id` denormalization for efficient tree queries.

**Architecture:** `agent_runs` gets two new nullable columns (`parent_run_id`, `root_run_id`). The platform validates parent ownership on `start_run` and sets `root_run_id` to the parent's `root_run_id` (or self for root runs). The SDK exposes `Agent.get_context()` returning an `AgentContext(name, run_id)` and `Agent.init()` gains an optional `parent_run_id` parameter.

**Tech Stack:** PostgreSQL (raw SQL via SQLAlchemy), FastAPI + Pydantic (platform), Python dataclasses (SDK), pytest (both test suites).

---

## File Map

| File | Action | What changes |
|---|---|---|
| `ezop-platform/database/migrations/2026/20260409000001-add-parent-child-run-hierarchy.sql` | **Create** | Migration: two new columns, index, backfill, constraint |
| `ezop-platform/database/current/02-base-schemas.sql` | **Modify** | Add same columns to canonical schema |
| `ezop-platform/app/models/agents.py` | **Modify** | Add `parent_run_id` and `root_run_id` to `AgentRun` Pydantic model |
| `ezop-platform/app/routers/agents.py` | **Modify** | `StartRunRequest` + `start_run` logic |
| `ezop-platform/tests/test_agents.py` | **Modify** | Update `RUN_ROW`, fix broken assertion, add new `TestStartRun` cases |
| `ezop-sdk/python/ezop/models.py` | **Modify** | Add `AgentContext` dataclass; add fields to `AgentRun` |
| `ezop-sdk/python/ezop/client.py` | **Modify** | `start_run` accepts and forwards `parent_run_id` |
| `ezop-sdk/python/ezop/agent.py` | **Modify** | `Agent.init()` accepts `parent_run_id`; add `Agent.get_context()` |
| `ezop-sdk/python/tests/test_agent.py` | **Modify** | Fix broken assertion; add `TestGetContext` + `parent_run_id` tests |

---

## Task 1: Database Migration

**Files:**
- Create: `ezop-platform/database/migrations/2026/20260409000001-add-parent-child-run-hierarchy.sql`
- Modify: `ezop-platform/database/current/02-base-schemas.sql`

- [ ] **Step 1: Write the migration file**

Create `ezop-platform/database/migrations/2026/20260409000001-add-parent-child-run-hierarchy.sql`:

```sql
-- Add parent/child run hierarchy with root_run_id denormalization.
-- parent_run_id: direct parent run (NULL for root runs).
-- root_run_id:   top-level ancestor; always set. Denormalized for O(1) tree queries.

ALTER TABLE agent_runs
  ADD COLUMN parent_run_id uuid REFERENCES agent_runs(id) ON DELETE SET NULL,
  ADD COLUMN root_run_id   uuid;

-- Backfill: all existing runs are root runs, so root_run_id = their own id.
UPDATE agent_runs SET root_run_id = id;

ALTER TABLE agent_runs ALTER COLUMN root_run_id SET NOT NULL;

-- Prevent a run from being its own parent.
ALTER TABLE agent_runs
  ADD CONSTRAINT agent_runs_no_self_parent CHECK (parent_run_id != id);

-- Index for "fetch all runs in this tree" queries.
CREATE INDEX agent_runs_root_run_id_idx ON agent_runs (root_run_id);
```

- [ ] **Step 2: Update `database/current/02-base-schemas.sql`**

In the `agent_runs` table block, add these two lines after `message text null,`:

```sql
  parent_run_id uuid null,
  root_run_id uuid not null,
```

Add the constraint inside the table definition (alongside `agent_runs_pkey`):

```sql
  constraint agent_runs_no_self_parent check ((parent_run_id <> id)),
  constraint agent_runs_parent_run_id_fkey foreign KEY (parent_run_id) references agent_runs (id) on delete set null
```

Add the index after the existing `agent_runs` indexes:

```sql
create index IF not exists agent_runs_root_run_id_idx on public.agent_runs using btree (root_run_id) TABLESPACE pg_default;
```

- [ ] **Step 3: Commit**

```bash
git add ezop-platform/database/migrations/2026/20260409000001-add-parent-child-run-hierarchy.sql
git add ezop-platform/database/current/02-base-schemas.sql
git commit -m "feat: add parent_run_id and root_run_id columns to agent_runs"
```

---

## Task 2: Update Platform `AgentRun` Pydantic Model

**Files:**
- Modify: `ezop-platform/app/models/agents.py`
- Modify: `ezop-platform/tests/test_agents.py` (update `RUN_ROW`)

- [ ] **Step 1: Write the failing test**

In `ezop-platform/tests/test_agents.py`, find `RUN_ROW` and add the two new fields. Replace the existing `RUN_ROW` dict with:

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
    "parent_run_id": None,
    "root_run_id": RUN_ID,
    "created_at": "2024-01-01T00:00:00+00:00",
    "updated_at": "2024-01-01T00:00:00+00:00",
}
```

Add a new test class at the bottom of `test_agents.py`:

```python
class TestAgentRunModel:
    def test_root_run_fields_in_response(self, client, db):
        db.execute.side_effect = [
            make_exec(first=True),
            make_exec(mapping=RUN_ROW),
        ]
        resp = client.post(f"/agents/{AGENT_ID}/runs", json={})
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["parent_run_id"] is None
        assert data["root_run_id"] == RUN_ID
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ezop-platform && python -m pytest tests/test_agents.py::TestAgentRunModel -v
```

Expected: FAIL — `AgentRun` Pydantic model validation error on the new fields.

- [ ] **Step 3: Update `AgentRun` in `app/models/agents.py`**

Replace the existing `AgentRun` class:

```python
class AgentRun(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: UUID
    version_id: UUID | None
    user_id: UUID | None
    status: RunStatus
    metadata: dict | None
    message: str | None
    parent_run_id: UUID | None
    root_run_id: UUID
    organization_id: UUID
    start_time: datetime
    end_time: datetime | None
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ezop-platform && python -m pytest tests/test_agents.py -v
```

Expected: all tests pass (existing tests pass because `RUN_ROW` was updated in Step 1; new test passes).

- [ ] **Step 5: Commit**

```bash
git add ezop-platform/app/models/agents.py ezop-platform/tests/test_agents.py
git commit -m "feat: add parent_run_id and root_run_id to AgentRun Pydantic model"
```

---

## Task 3: Update `start_run` Endpoint

**Files:**
- Modify: `ezop-platform/app/routers/agents.py`
- Modify: `ezop-platform/tests/test_agents.py`

- [ ] **Step 1: Write the failing tests**

Add two constants near the top of `test_agents.py` (after `from tests.conftest import ...`):

```python
PARENT_RUN_ID = "bbbbbbbb-0000-0000-0000-000000000001"
ROOT_RUN_ID   = "bbbbbbbb-0000-0000-0000-000000000002"
```

Add two fixture dicts after `RUN_ROW`:

```python
PARENT_RUN_ROW = {
    "id": PARENT_RUN_ID,
    "agent_id": AGENT_ID,
    "version_id": VERSION_ID,
    "user_id": None,
    "status": "running",
    "organization_id": ORG_ID,
    "start_time": "2024-01-01T00:00:00+00:00",
    "end_time": None,
    "message": None,
    "metadata": None,
    "parent_run_id": None,
    "root_run_id": ROOT_RUN_ID,
    "created_at": "2024-01-01T00:00:00+00:00",
    "updated_at": "2024-01-01T00:00:00+00:00",
}

CHILD_RUN_ROW = {
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
    "parent_run_id": PARENT_RUN_ID,
    "root_run_id": ROOT_RUN_ID,
    "created_at": "2024-01-01T00:00:00+00:00",
    "updated_at": "2024-01-01T00:00:00+00:00",
}
```

Add three new test methods inside `TestStartRun`:

```python
def test_start_child_run_returns_201(self, client, db):
    # DB calls: assert_agent_org, fetch_parent, insert
    db.execute.side_effect = [
        make_exec(first=True),
        make_exec(mapping={"root_run_id": ROOT_RUN_ID, "organization_id": ORG_ID}),
        make_exec(mapping=CHILD_RUN_ROW),
    ]
    resp = client.post(
        f"/agents/{AGENT_ID}/runs",
        json={"parent_run_id": PARENT_RUN_ID},
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["parent_run_id"] == PARENT_RUN_ID
    assert data["root_run_id"] == ROOT_RUN_ID

def test_parent_not_found_returns_404(self, client, db):
    db.execute.side_effect = [
        make_exec(first=True),
        make_exec(mapping=None),
    ]
    resp = client.post(
        f"/agents/{AGENT_ID}/runs",
        json={"parent_run_id": PARENT_RUN_ID},
    )
    assert resp.status_code == 404
    assert "Parent run not found" in resp.json()["error"]["message"]

def test_parent_wrong_org_returns_422(self, client, db):
    other_org = "cccccccc-0000-0000-0000-000000000001"
    db.execute.side_effect = [
        make_exec(first=True),
        make_exec(mapping={"root_run_id": ROOT_RUN_ID, "organization_id": other_org}),
    ]
    resp = client.post(
        f"/agents/{AGENT_ID}/runs",
        json={"parent_run_id": PARENT_RUN_ID},
    )
    assert resp.status_code == 422
    assert "different organization" in resp.json()["error"]["message"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ezop-platform && python -m pytest tests/test_agents.py::TestStartRun -v
```

Expected: the three new tests FAIL (endpoint doesn't support `parent_run_id` yet).

- [ ] **Step 3: Update `app/routers/agents.py`**

Add `import uuid as uuid_mod` at the top (with the other stdlib imports).

Update `StartRunRequest`:

```python
class StartRunRequest(BaseModel):
    version_id: str | None = None
    user_id: str | None = None
    metadata: dict | None = None
    parent_run_id: str | None = None
```

Replace the `start_run` function body:

```python
@router.post(
    "/{agent_id}/runs",
    summary="Start an agent run",
    response_model=ApiResponse[AgentRun],
    status_code=201,
)
def start_run(
    agent_id: str,
    payload: StartRunRequest,
    db: Annotated[Session, Depends(get_db)],
    org_id: Annotated[str, Depends(verify_api_key)],
) -> JSONResponse:
    """Create a new run record with status 'running'."""
    _assert_agent_org(db, agent_id, org_id)
    logger.info("Starting run agent_id=%s version_id=%s", agent_id, payload.version_id)

    run_id = str(uuid_mod.uuid4())
    root_run_id = run_id  # default: this run is its own root

    if payload.parent_run_id is not None:
        parent_row = (
            db.execute(
                text("SELECT root_run_id, organization_id FROM agent_runs WHERE id = :id"),
                {"id": payload.parent_run_id},
            )
            .mappings()
            .first()
        )
        if parent_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent run not found.")
        if str(parent_row["organization_id"]) != org_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Parent run belongs to a different organization.",
            )
        root_run_id = str(parent_row["root_run_id"])

    row = (
        db.execute(
            text("""
                INSERT INTO agent_runs
                    (id, agent_id, version_id, user_id, parent_run_id, root_run_id, status, metadata, organization_id)
                VALUES
                    (:id, :agent_id, :version_id, :user_id, :parent_run_id, :root_run_id, 'running', :metadata, :org_id)
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
    logger.info("Run started id=%s agent_id=%s", run.id, agent_id)
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"success": True, "data": run.model_dump(mode="json"), "error": None},
    )
```

- [ ] **Step 4: Run all platform tests**

```bash
cd ezop-platform && python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add ezop-platform/app/routers/agents.py ezop-platform/tests/test_agents.py
git commit -m "feat: start_run validates parent_run_id and sets root_run_id"
```

---

## Task 4: SDK — `AgentContext` and `AgentRun` Model Updates

**Files:**
- Modify: `ezop-sdk/python/ezop/models.py`
- Modify: `ezop-sdk/python/tests/test_agent.py`

- [ ] **Step 1: Write the failing test**

Add to the top of `ezop-sdk/python/tests/test_agent.py` (after existing imports):

```python
from ezop.models import AgentContext
```

Add a new test class:

```python
class TestAgentContext:
    def test_has_name_and_run_id(self):
        ctx = AgentContext(name="orchestrator", run_id="run-uuid-789")
        assert ctx.name == "orchestrator"
        assert ctx.run_id == "run-uuid-789"

    def test_is_immutable(self):
        ctx = AgentContext(name="orchestrator", run_id="run-uuid-789")
        with pytest.raises(Exception):
            ctx.name = "other"  # type: ignore[misc]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/bs/workdir/repos/ezop/ezop-sdk/python && python -m pytest tests/test_agent.py::TestAgentContext -v
```

Expected: FAIL — `AgentContext` not importable yet.

- [ ] **Step 3: Update `ezop-sdk/python/ezop/models.py`**

Add `AgentContext` after the `AgentVersion` dataclass:

```python
@dataclass(frozen=True)
class AgentContext:
    name: str
    run_id: str
```

Update `AgentRun` to add two optional fields after `message`:

```python
@dataclass
class AgentRun:
    id: str
    agent_id: str
    version_id: Optional[str]
    status: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    metadata: Optional[dict] = None
    message: Optional[str] = None
    parent_run_id: Optional[str] = None
    root_run_id: Optional[str] = None
    _current_span_id: Optional[str] = field(default=None, repr=False, compare=False)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/bs/workdir/repos/ezop/ezop-sdk/python && python -m pytest tests/test_agent.py::TestAgentContext -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ezop-sdk/python/ezop/models.py ezop-sdk/python/tests/test_agent.py
git commit -m "feat: add AgentContext dataclass and parent/root fields to AgentRun"
```

---

## Task 5: SDK — Update `EzopClient.start_run()` and `Agent.init()`

**Files:**
- Modify: `ezop-sdk/python/ezop/client.py`
- Modify: `ezop-sdk/python/ezop/agent.py`
- Modify: `ezop-sdk/python/tests/test_agent.py`

- [ ] **Step 1: Write the failing test**

Add to `TestAgentInit` in `test_agent.py`:

```python
def test_calls_start_run_with_parent_run_id(self):
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
            parent_run_id="parent-run-uuid",
        )
        mock_run.assert_called_once_with(
            "agent-uuid-123", "version-uuid-456", parent_run_id="parent-run-uuid"
        )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/bs/workdir/repos/ezop/ezop-sdk/python && python -m pytest "tests/test_agent.py::TestAgentInit::test_calls_start_run_with_parent_run_id" -v
```

Expected: FAIL — `Agent.init` doesn't accept `parent_run_id` yet.

- [ ] **Step 3: Update `EzopClient.start_run()` in `client.py`**

Replace the existing `start_run` method:

```python
def start_run(
    self,
    agent_id: str,
    version_id: Optional[str] = None,
    user_id: Optional[str] = None,
    metadata: Optional[dict] = None,
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
    if parent_run_id is not None:
        body["parent_run_id"] = parent_run_id
    result = self._post(f"/agents/{agent_id}/runs", body)
    logger.info("Run started id=%s", result.get("data", {}).get("id"))
    return result
```

- [ ] **Step 4: Update `Agent.init()` in `agent.py`**

Add `AgentContext` to the import line at the top of `agent.py`:

```python
from .models import AgentModel, AgentRun, AgentVersion, AgentContext, Event
```

Add `parent_run_id` parameter to `init()` (after `changelog`, inside the `*` keyword-only block):

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
) -> "Agent":
```

In the body of `init()`, replace the two lines that call `start_run` and build `current_run`:

```python
run_data = client.start_run(model.id, agent_version.id, parent_run_id=parent_run_id)["data"]
agent.current_run = AgentRun(
    id=run_data["id"],
    agent_id=model.id,
    version_id=agent_version.id,
    status=run_data.get("status", "running"),
    parent_run_id=run_data.get("parent_run_id"),
    root_run_id=run_data.get("root_run_id"),
)
```

- [ ] **Step 5: Fix the existing `test_calls_start_run_with_correct_args` test**

Find this test in `TestAgentInit` and update its assertion (the call now passes `parent_run_id=None`):

```python
def test_calls_start_run_with_correct_args(self):
    with (
        patch("ezop.client.EzopClient.register_agent", return_value=AGENT_RESP),
        patch("ezop.client.EzopClient.create_version", return_value=VERSION_RESP),
        patch("ezop.client.EzopClient.start_run", return_value=RUN_RESP) as mock_run,
    ):
        Agent.init(name="support-bot", owner="growth-team", version="v0.3", runtime="langchain")
        mock_run.assert_called_once_with("agent-uuid-123", "version-uuid-456", parent_run_id=None)
```

- [ ] **Step 6: Run all SDK tests**

```bash
cd /Users/bs/workdir/repos/ezop/ezop-sdk/python && python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add ezop-sdk/python/ezop/client.py ezop-sdk/python/ezop/agent.py ezop-sdk/python/tests/test_agent.py
git commit -m "feat: Agent.init and EzopClient.start_run accept parent_run_id"
```

---

## Task 6: SDK — `Agent.get_context()`

**Files:**
- Modify: `ezop-sdk/python/ezop/agent.py`
- Modify: `ezop-sdk/python/tests/test_agent.py`

- [ ] **Step 1: Write the failing tests**

Add a new test class to `test_agent.py`:

```python
class TestGetContext:
    def test_returns_agent_context(self):
        agent = make_agent()
        ctx = agent.get_context()
        assert isinstance(ctx, AgentContext)

    def test_name_matches_agent_model(self):
        agent = make_agent()
        ctx = agent.get_context()
        assert ctx.name == "support-bot"

    def test_run_id_matches_active_run(self):
        agent = make_agent()
        ctx = agent.get_context()
        assert ctx.run_id == "run-uuid-789"

    def test_raises_when_no_active_run(self):
        agent = make_agent()
        agent.current_run = None
        with pytest.raises(RuntimeError, match="No active run"):
            agent.get_context()

    def test_raises_after_close(self):
        agent = make_agent()
        end_resp = {"success": True, "error": None, "data": {"status": "success", "metadata": None}}
        with patch("ezop.client.EzopClient.end_run", return_value=end_resp):
            agent.close(status="success")
        with pytest.raises(RuntimeError, match="closed"):
            agent.get_context()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/bs/workdir/repos/ezop/ezop-sdk/python && python -m pytest tests/test_agent.py::TestGetContext -v
```

Expected: FAIL — `Agent.get_context` doesn't exist.

- [ ] **Step 3: Add `get_context()` to `Agent` in `agent.py`**

Add the method after `span()`:

```python
def get_context(self) -> AgentContext:
    """Return a snapshot of the current run context for passing to child agents."""
    self._check_active()
    if self.current_run is None:
        raise RuntimeError("No active run.")
    return AgentContext(name=self.model.name, run_id=self.current_run.id)
```

- [ ] **Step 4: Run all SDK tests**

```bash
cd /Users/bs/workdir/repos/ezop/ezop-sdk/python && python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add ezop-sdk/python/ezop/agent.py ezop-sdk/python/tests/test_agent.py
git commit -m "feat: add Agent.get_context() returning AgentContext(name, run_id)"
```

---

## Task 7: Final Verification

- [ ] **Step 1: Run full platform test suite**

```bash
cd ezop-platform && python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 2: Run full SDK test suite**

```bash
cd /Users/bs/workdir/repos/ezop/ezop-sdk/python && python -m pytest tests/ -v
```

Expected: all tests pass.
