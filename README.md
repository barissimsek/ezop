# Ezop

Ezop is an open-source observability platform for AI agents. It tracks agent registrations, versions, runs, spans, and events so you have full visibility into every agent deployment.

## Monorepo Structure

```
ezop/
├── ezop-platform/     # REST API server (FastAPI + PostgreSQL)
├── ezop-light-ui/     # Dashboard web app (Next.js)
└── ezop-sdk/
    └── python/        # Python SDK (pip install ezop)
```

## Architecture

```
┌─────────────────┐        ┌──────────────────┐
│   ezop-sdk      │──────▶ │  ezop-platform   │
│  (Python SDK)   │  REST  │  (FastAPI server) │
└─────────────────┘        └────────┬─────────┘
                                    │ PostgreSQL
                           ┌────────▼─────────┐
                           │  ezop-light-ui   │
                           │  (Next.js UI)    │
                           └──────────────────┘
```

**ezop-platform** is the API server. Agents authenticate with an API key and send data (runs, spans, events) via REST. It enforces plan limits and stores everything in PostgreSQL.

**ezop-sdk** is the Python client library. Call `Agent.init()` once at startup and the SDK handles registration, versioning, and run tracking. Install from PyPI: `pip install ezop`.

**ezop-light-ui** is the dashboard. It connects directly to the same PostgreSQL database and lets you browse agents, inspect runs, view spans and events, manage API keys, and invite team members.

## Running with Docker Compose

The quickest way to run the full stack is with Docker Compose. It starts PostgreSQL, the API server, and the dashboard together.

**1. Set up Google OAuth credentials:**

The dashboard uses Google as its authentication provider. You need a Google OAuth 2.0 client:

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth 2.0 Client ID**
3. Set application type to **Web application**
4. Add `http://localhost:13001/api/auth/callback/google` to **Authorised redirect URIs**
5. Copy the **Client ID** and **Client Secret**

**2. Create a `.env` file in the repo root:**

```bash
AUTH_SECRET=your-secret-at-least-32-characters-long
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
```

Generate a strong `AUTH_SECRET` with:

```bash
openssl rand -base64 32
```

**3. Start all services:**

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Dashboard (ezop-light-ui) | http://localhost:13001 |
| API server (ezop-platform) | http://localhost:13000 |
| PostgreSQL | localhost:13002 |

The `migrate` service runs automatically on startup and applies the Prisma schema before the UI and platform start. No manual migration step is needed.

**Useful commands:**

```bash
docker compose up -d          # run in background
docker compose logs -f        # tail logs
docker compose down           # stop
docker compose down -v        # stop and delete database volume
```

## Projects

### ezop-platform

FastAPI REST API server. Requires Python 3.12+ and PostgreSQL.

```bash
cd ezop-platform
python -m venv .venv
.venv/bin/pip install -r requirements.txt
DATABASE_URL=postgresql://... .venv/bin/hypercorn app.main:app --reload
```

Or with Docker:

```bash
docker build -t ezop-platform .
docker run -p 13000:13000 -e DATABASE_URL=postgresql://... ezop-platform
```

### ezop-light-ui

Next.js dashboard. Requires Node 20+ and the same PostgreSQL database.

```bash
cd ezop-light-ui
npm install
npx prisma generate
npx prisma db push     # apply schema to DB
npm run dev
```

Open the dashboard at **http://localhost:13001**. Sign in with your Google account, then go to **Settings → API Keys** to create an API key for the SDK.

### ezop-sdk (Python)

Install the SDK and set your credentials:

```bash
pip install ezop

export EZOP_API_URL=http://localhost:13000
export EZOP_API_KEY=your-api-key-from-the-dashboard
```

```python
from ezop import Agent

agent = Agent.init(
    name="my-agent",
    owner="my-team",
    version="v1.0",
    runtime="python",
)

with agent.span("llm.call"):
    response = llm.generate(prompt)

agent.close(status="success")
```

See [ezop-sdk/python/README.md](ezop-sdk/python/README.md) for the full API reference.

## Environment Variables

### ezop-platform

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string (required) |
| `EZOP_PORT` | Port to listen on (default: `13000`) |
| `LOG_LEVEL` | Log level (default: `INFO`) |

### ezop-light-ui

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string (required) |
| `AUTH_SECRET` | NextAuth secret, min 32 chars — generate with `openssl rand -base64 32` (required) |
| `GOOGLE_CLIENT_ID` | Google OAuth 2.0 client ID (required) |
| `GOOGLE_CLIENT_SECRET` | Google OAuth 2.0 client secret (required) |
| `EZOP_API_URL` | URL of ezop-platform (required) |

### ezop-sdk

| Variable | Description |
|---|---|
| `EZOP_API_KEY` | API key from the dashboard (required) |
| `EZOP_API_URL` | Platform URL (default: `https://api.ezop.ai`) |

## Database Migration Strategy

Schema ownership lives in `ezop-platform`. Prisma (`ezop-light-ui`) is a consumer — it reads the schema from the live database and is used only in development environments to push the initial schema quickly.

### Structure

```
ezop-platform/database/
├── base/
│   ├── 01-enumerated-types.sql   # PostgreSQL enums and extensions
│   ├── 02-base-schemas.sql       # Initial table definitions
│   ├── 03-functions.sql          # Stored procedures and triggers
│   └── 04-minimum-data.sql       # Seed data (plans, service costs)
└── migrations/
    └── YYYYMMDDHHMMSS-description.sql  # Incremental change files
```

`base/` is the initial database. The current production schema is `base/` plus all migrations applied in timestamp order — the same way binlogs work on top of a base snapshot.

### Prisma schema

`ezop-light-ui/prisma/schema.prisma` is maintained in sync with the current database schema. It is used as a reference and for development tooling — not for production migrations.

To regenerate the Prisma schema from a live database (e.g. after applying migrations):

```bash
cd ezop-light-ui
DATABASE_URL=postgresql://... npx prisma db pull
```

### Environments

**Development (Docker Compose, GitHub Actions):** Prisma pushes the table schema on startup via `prisma db push`. The `current/` SQL files (enums, functions, seed data) are loaded automatically by the PostgreSQL container from `/docker-entrypoint-initdb.d/` on first start. No manual steps needed.

**Production:** Prisma is never used. The base SQL is applied once on a fresh database, then incremental migration files are applied in timestamp order on each release.

### Fresh database setup (development)

Start Docker Compose — PostgreSQL will auto-apply `database/current/` on first init, then the `migrate` service runs `prisma db push`:

```bash
docker compose up --build
```

To reset to a clean state:

```bash
docker compose down -v   # removes the postgres volume
docker compose up --build
```

### Fresh database setup (production)

```bash
psql $DATABASE_URL -f database/base/01-enumerated-types.sql
psql $DATABASE_URL -f database/base/02-base-schemas.sql
psql $DATABASE_URL -f database/base/03-functions.sql
psql $DATABASE_URL -f database/base/04-minimum-data.sql
```

### Release deployment

Apply new incremental files in order:

```bash
psql $DATABASE_URL -f database/migrations/20240615120000-add-agent-tags.sql
```

### Adding a schema change

1. Create `database/migrations/YYYYMMDDHHMMSS-description.sql` with the diff SQL
2. Open a PR — reviewed and merged like any code change
3. Apply during the next release deployment

### Rules

- Migration files are never edited after they are merged. Corrections require a new file.
- GitHub is the source of truth and change management system.

## CI

Each project has its own GitHub Actions workflow that runs on changes to its directory:

| Workflow | Triggers on |
|---|---|
| `.github/workflows/sdk.yml` | `ezop-sdk/**` |
| `.github/workflows/platform.yml` | `ezop-platform/**` |
| `.github/workflows/ui.yml` | `ezop-light-ui/**` |

## License

MIT
