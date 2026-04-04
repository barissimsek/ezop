# Migrations

Incremental SQL files applied on top of `database/base/` to reach the current schema.

## Naming convention

```
YYYYMMDDHHMMSS-short-description.sql
```

Example: `20240615120000-add-agent-tags.sql`

## Rules

- One file per logical change.
- Files are never edited after they are merged. Corrections require a new file.
- Applied in timestamp order during release deployment.

## Applying

```bash
psql $DATABASE_URL -f database/migrations/20240615120000-add-agent-tags.sql
```
