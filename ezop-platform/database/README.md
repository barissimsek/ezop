# Database

Schema ownership lives here. Prisma (`ezop-light-ui`) is a consumer — it syncs table structure in development environments only and is never used in production.

## Structure

```
database/
├── base/                                    # Starting point (initial database)
│   ├── 01-enumerated-types.sql
│   ├── 02-base-schemas.sql
│   ├── 03-functions.sql
│   └── 04-minimum-data.sql
├── current/                                 # Current release state
│   ├── 01-enumerated-types.sql
│   ├── 02-base-schemas.sql
│   ├── 03-functions.sql                     # Stored procedures & triggers
│   └── 04-minimum-data.sql                  # Seed data (plans, service costs)
└── migrations/                              # Incremental changes since base
    └── YYYYMMDDHHMMSS-description.sql
```

The current schema = `base/` + all files in `migrations/` applied in timestamp order.  
`current/` always reflects this combined state and is the reference for deployments.

## Development (Docker Compose)

The `migrate` service in `docker-compose.yml` runs automatically on `docker compose up` and handles everything in order:

1. `prisma db push` — creates and syncs all tables (handles circular foreign keys safely)
2. `psql ... current/03-functions.sql` — stored procedures and triggers
3. `psql ... current/04-minimum-data.sql` — seed data

To reset to a clean state:

```bash
docker compose down -v   # removes the postgres volume
docker compose up --build
```

## Production (no Docker Compose)

**Fresh database** — apply `current/` in order:

```bash
psql $DATABASE_URL -f database/current/01-enumerated-types.sql
psql $DATABASE_URL -f database/current/02-base-schemas.sql
psql $DATABASE_URL -f database/current/03-functions.sql
psql $DATABASE_URL -f database/current/04-minimum-data.sql
```

**Release deployment** — apply new incremental migrations, then refresh stored procedures and seed data:

```bash
# 1. Apply schema changes
psql $DATABASE_URL -f database/migrations/20240615120000-add-agent-tags.sql

# 2. Re-apply stored procedures (CREATE OR REPLACE — safe to re-run)
psql $DATABASE_URL -f database/current/03-functions.sql

# 3. Re-apply seed data (INSERT ... ON CONFLICT DO NOTHING — safe to re-run)
psql $DATABASE_URL -f database/current/04-minimum-data.sql
```

## Prisma schema

`ezop-light-ui/prisma/schema.prisma` is a **consumer** of this schema — it does not own it. Developers maintain `schema.prisma` manually and keep it in sync with `current/` after every migration. It is never generated from the database automatically.

`prisma db push` runs only in environments where the database is ephemeral and disposable:

- Docker Compose (`migrate` service) — spins up a fresh database from scratch
- GitHub Actions — CI builds with a temporary database

It is **never** run in production. Production databases are managed exclusively through the SQL migration files in this directory.

To sync `schema.prisma` after applying a migration:

```bash
cd ezop-light-ui
DATABASE_URL=postgresql://... npx prisma db pull
```

## Adding a schema change

1. Create `database/migrations/YYYYMMDDHHMMSS-description.sql` with the diff SQL
2. Update the relevant `database/current/` files to reflect the new state
3. Open a PR — reviewed and merged like any code change
4. Apply during the next release deployment

## Rules

- Migration files are never edited after they are merged. Corrections require a new file.
- GitHub is the source of truth and change management system.
