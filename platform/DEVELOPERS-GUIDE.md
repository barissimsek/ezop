# Developers Guide

## Repository structure

```
ezop/
├── ezop-platform/     # FastAPI REST API — SDK agents send data here
├── ezop-light-ui/     # Next.js dashboard — browse agents, runs, and events
└── ezop-sdk/
    └── python/        # Python SDK (pip install ezop)
```

All three projects share a single PostgreSQL database. `ezop-light-ui` owns the schema via Prisma. `ezop-platform` reads and writes using SQLAlchemy.

---

## Local development setup

### Option A — Docker Compose (recommended)

The fastest way to get everything running.

**Prerequisites**

- Docker + Docker Compose
- Google OAuth 2.0 credentials (create a client ID at [Google Cloud Console](https://console.cloud.google.com/) with redirect URI `http://localhost:13001/api/auth/callback/google`)

**Steps**

1. Create a `.env` file in the repo root:

```bash
AUTH_SECRET=$(openssl rand -base64 32)
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
```

2. Start all services:

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Dashboard (ezop-light-ui) | http://localhost:13001 |
| API server (ezop-platform) | http://localhost:13000 |
| PostgreSQL | localhost:13002 |

The `migrate` service runs automatically on startup — it pushes the Prisma schema, applies stored procedures, and seeds minimum data.

```bash
docker compose up -d          # run in background
docker compose logs -f        # tail all logs
docker compose down -v        # stop and delete the database volume
```

Because you want to see your changes immediately, probably you want to bring only the postgres up with `docker-compose` and run other services manually.

---

### Option B — Manual setup (per service)

Use this when you need to iterate quickly on a specific service without rebuilding containers.

**Prerequisites**

- PostgreSQL 16+ running locally
- Python 3.12+
- Node.js 20+

#### 1. Start PostgreSQL

```bash
createdb ezop
```

Or with Docker (just the database):

```bash
docker compose up postgres -d
```

#### 2. ezop-light-ui (Next.js dashboard)

```bash
cd ezop-light-ui
npm install
```

Create `ezop-light-ui/.env.local`:

```bash
DATABASE_URL=postgresql://ezop:ezop@localhost:13002/ezop   # adjust for your setup
AUTH_SECRET=$(openssl rand -base64 32)
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
EZOP_API_URL=http://localhost:13000
```

Initialize the database:

```bash
npx prisma db push
psql $DATABASE_URL -f ../ezop-platform/database/current/03-functions.sql
psql $DATABASE_URL -f ../ezop-platform/database/current/04-minimum-data.sql
```

Start the dev server:

```bash
PORT=13001 npm run dev
```

Dashboard is at http://localhost:13001.

#### 3. ezop-platform (FastAPI API server)

```bash
cd ezop-platform
make install         # creates .venv and installs dependencies
```

Create `ezop-platform/.env`:

```bash
DATABASE_URL=postgresql://ezop:ezop@localhost:13002/ezop
LOG_LEVEL=INFO
```

Start the server:

```bash
export DATABASE_URL=postgresql://ezop:ezop@localhost:13002/ezop
.venv/bin/uvicorn app.main:app --reload --port 13000
```

API is at http://localhost:13000.

#### 4. ezop-sdk (Python SDK)

```bash
cd ezop-sdk/python
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Set environment variables and test against your local platform:

```bash
export EZOP_API_URL=http://localhost:13000
export EZOP_API_KEY=your-api-key   # create one via the dashboard
```

---

## Running tests

### ezop-platform

```bash
cd ezop-platform
make test            # runs pytest
make lint            # ruff check + format check
make check           # lint + test
```

Tests are unit tests using `unittest.mock` — no database required.

### ezop-light-ui

```bash
cd ezop-light-ui
npm run lint         # ESLint
npm run test:e2e     # Playwright end-to-end tests (requires running services)
```

### ezop-sdk

```bash
cd ezop-sdk/python
pytest
```

---

## Database

See [ezop-platform/database/README.md](../ezop-platform/database/README.md) for schema ownership, migration strategy, and how to apply migrations to existing systems.

**Adding a schema change:**

1. Update `ezop-light-ui/prisma/schema.prisma` (source of truth)
2. Run `npx prisma migrate dev --create-only --name your-description` from `ezop-light-ui/`
3. Replace the generated migration SQL with the correct 3-step form if adding columns to existing tables (nullable → backfill → NOT NULL)
4. Create a matching file in `ezop-platform/database/migrations/YYYYMMDDHHMMSS-your-description.sql`
5. Update `ezop-platform/database/current/` to reflect the new combined state

---

## Branch and PR workflow

- Branch from `develop`, not `main`
- One logical change per PR
- Open PRs against `develop` — never merge directly into `main`
- Big structural changes require a design spec (see [CONTRIBUTING.md](../CONTRIBUTING.md))

---

## Architecture notes

- **Schema ownership**: Prisma (`ezop-light-ui/prisma/schema.prisma`) is the source of truth. `ezop-platform` uses raw SQL via SQLAlchemy and must stay in sync manually.
- **Auth**: `ezop-light-ui` uses NextAuth v5 with Google OAuth. `ezop-platform` uses API key authentication (Bearer token, SHA-256 hashed in the DB).
- **Plan limits**: `ezop-platform/app/gatekeeper.py` enforces per-org limits (agents, events/month) defined in the `plans` table.
- **Event model**: Events are append-only. `agent_id` and `organization_id` are denormalized directly onto `events` and `spans` for fast agent-scoped queries without joins.
