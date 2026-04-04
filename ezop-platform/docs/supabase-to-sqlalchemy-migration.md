# Supabase SDK → SQLAlchemy + PostgreSQL Migration Plan

## Goal

Replace the Supabase Python SDK with SQLAlchemy (Core, not ORM) backed by psycopg2.
The Supabase database itself stays intact — only the Python client layer changes.

---

## Why

- Remove dependency on Supabase's PostgREST HTTP layer (extra network hop on every query)
- Direct PostgreSQL connection via psycopg2 — lower latency, better control
- SQLAlchemy Core gives us composable queries, transactions, and connection pooling
- Easier to write integration tests without Supabase infra

---

## Scope

| Layer | Change |
|---|---|
| `app/clients/supabase.py` | Replace with `app/clients/db.py` — SQLAlchemy engine + session factory |
| `app/config.py` | Replace `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` with `DATABASE_URL` |
| `app/auth.py` | Rewrite queries using SQLAlchemy |
| `app/gatekeeper.py` | Rewrite queries using SQLAlchemy |
| `app/routers/agents.py` | Rewrite queries using SQLAlchemy |
| `app/routers/runs.py` | Rewrite queries using SQLAlchemy |
| `app/routers/spans.py` | Rewrite queries using SQLAlchemy |
| `requirements.txt` | Remove `supabase`, add `sqlalchemy`, `psycopg2-binary` |
| `.env.example` | Replace Supabase vars with `DATABASE_URL` |

---

## Step-by-Step Plan

### Step 1 — Add dependencies

`requirements.txt`:
```
fastapi
hypercorn
python-dotenv
sqlalchemy
psycopg2-binary
```

Remove `supabase`.

---

### Step 2 — Update config

Replace `supabase_url` / `supabase_service_role_key` with a single `database_url`:

```python
self.database_url = os.getenv("DATABASE_URL", "")
if not self.database_url:
    raise RuntimeError("DATABASE_URL must be set.")
```

`.env` format:
```
DATABASE_URL=postgresql://user:password@host:5432/dbname
```

---

### Step 3 — Create `app/clients/db.py`

Replace `app/clients/supabase.py` with a SQLAlchemy engine + session dependency:

```python
from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.config import get_settings

@lru_cache
def _engine():
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )

def get_db():
    Session = sessionmaker(bind=_engine())
    db = Session()
    try:
        yield db
    finally:
        db.close()
```

All routers replace `Depends(get_supabase)` with `Depends(get_db)` and the type annotation changes from `supabase.Client` to `sqlalchemy.orm.Session`.

---

### Step 4 — Query translation reference

Each Supabase SDK pattern maps to a SQLAlchemy Core `text()` query or expression:

#### SELECT single row
```python
# Supabase
db.table("api_keys").select("id, organization_id, expires_at")
  .eq("key_hash", key_hash).is_("revoked_at", "null").execute()

# SQLAlchemy
from sqlalchemy import text
row = db.execute(
    text("SELECT id, organization_id, expires_at FROM api_keys "
         "WHERE key_hash = :key_hash AND revoked_at IS NULL"),
    {"key_hash": key_hash}
).mappings().first()
```

#### SELECT with count
```python
# Supabase
db.table("agents").select("id", count="exact").eq("organization_id", org_id).execute()
# result.count

# SQLAlchemy
count = db.execute(
    text("SELECT COUNT(*) FROM agents WHERE organization_id = :org_id"),
    {"org_id": org_id}
).scalar()
```

#### INSERT
```python
# Supabase
db.table("agent_runs").insert({...}).execute()

# SQLAlchemy
row = db.execute(
    text("INSERT INTO agent_runs (...) VALUES (...) RETURNING *"),
    {...}
).mappings().first()
db.commit()
```

#### UPDATE
```python
# Supabase
db.table("agent_runs").update(update).eq("id", run_id).execute()

# SQLAlchemy
row = db.execute(
    text("UPDATE agent_runs SET status = :status WHERE id = :id RETURNING *"),
    {"status": payload.status, "id": run_id}
).mappings().first()
db.commit()
```

#### UPSERT (INSERT ... ON CONFLICT DO UPDATE)
```python
# Supabase
db.table("agents").upsert({...}, on_conflict="name,owner,organization_id",
                           returning="representation").execute()

# SQLAlchemy
row = db.execute(text("""
    INSERT INTO agents (name, owner, organization_id, runtime, description, default_permissions)
    VALUES (:name, :owner, :organization_id, :runtime, :description, :default_permissions)
    ON CONFLICT (name, owner, organization_id) DO UPDATE SET
        runtime = EXCLUDED.runtime,
        description = EXCLUDED.description,
        default_permissions = EXCLUDED.default_permissions,
        updated_at = now()
    RETURNING *
"""), {...}).mappings().first()
db.commit()
```

#### UPSERT ignore duplicates (ON CONFLICT DO NOTHING)
```python
# Supabase
db.table("agent_versions").upsert({...}, on_conflict="agent_id,version",
                                   ignore_duplicates=True).execute()

# SQLAlchemy
row = db.execute(text("""
    INSERT INTO agent_versions (agent_id, version, permissions, changelog)
    VALUES (:agent_id, :version, :permissions, :changelog)
    ON CONFLICT (agent_id, version) DO NOTHING
    RETURNING *
"""), {...}).mappings().first()
db.commit()
# row is None if duplicate — fetch existing separately
```

---

### Step 5 — File-by-file changes

#### `app/auth.py`
- Replace `Client` type with `Session`
- Replace two Supabase queries with `text()` equivalents (SELECT api_keys, UPDATE last_used_at)

#### `app/gatekeeper.py`
- Replace `Client` type with `Session`
- 5 queries: organizations SELECT, plans SELECT, agents SELECT (exists check), agents COUNT, events COUNT

#### `app/routers/agents.py`
- 6 queries: agent upsert, agent_versions upsert, agent_versions fetch, agent_runs list, agent_runs insert, agent exists check

#### `app/routers/runs.py`
- 6 queries: run org check, run update, span insert, span parent check, span run_id check, events insert

#### `app/routers/spans.py`
- 1 query: span update (close span)

---

### Step 6 — Update tests

- `conftest.py`: replace env vars with a `DATABASE_URL` pointing to a test DB or use a mock
- Consider `pytest-postgresql` or a local Docker Postgres for integration tests

---

### Step 7 — Update CI

`.github/workflows/ci.yaml` test job:
```yaml
services:
  postgres:
    image: postgres:16
    env:
      POSTGRES_DB: ezop_test
      POSTGRES_USER: ezop
      POSTGRES_PASSWORD: test
    ports: ["5432:5432"]
    options: --health-cmd pg_isready --health-interval 5s --health-timeout 5s --health-retries 5

env:
  DATABASE_URL: postgresql://ezop:test@localhost:5432/ezop_test
```

---

## Rollout Order

1. `requirements.txt` + `config.py` + `app/clients/db.py`
2. `app/auth.py` (touches every request — validate first)
3. `app/gatekeeper.py`
4. `app/routers/agents.py`
5. `app/routers/runs.py`
6. `app/routers/spans.py`
7. Remove `app/clients/supabase.py`
8. Update `.env.example`, `conftest.py`, CI

---

## Not in scope

- Schema changes (tables stay as-is in Postgres)
- Supabase Auth, Storage, Realtime (not used)
- SQLAlchemy ORM models (Core `text()` queries are sufficient and keep the diff small)
