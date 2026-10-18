# Database

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

## Initializing Database

1. `prisma db push` — creates and syncs all tables (handles circular foreign keys safely)
2. `psql ... current/03-functions.sql` — stored procedures and triggers
3. `psql ... current/04-minimum-data.sql` — seed data

In local dev environment:

The `migrate` service in `docker-compose.yml` runs automatically on `docker compose up` and handles all three steps above.

## Schema Migration

Apply only the incremental migration files that haven't been applied yet:

```bash
# Apply a single migration
psql $DATABASE_URL -f database/migrations/2026/20260405152758-add-agent-id-to-events-and-spans.sql

# Apply all pending migrations in order (bash)
for f in database/migrations/2026/*.sql; do
  psql $DATABASE_URL -f "$f"
done
```

**Rules:**
- Migration files are applied in timestamp order and never edited after being merged.
- Each file is idempotent where possible, but re-applying is not guaranteed safe — track which migrations have run.
- If a migration fails partway through, fix the underlying issue before retrying. Do not partially re-apply.
- Corrections to a bad migration require a new migration file, not editing the original.
