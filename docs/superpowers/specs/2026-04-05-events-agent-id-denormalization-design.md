# Design: Denormalize `agent_id` onto `events` and `spans`

**Date:** 2026-04-05  
**Status:** Approved

## Problem

Events and spans have no direct `agent_id` column. Querying "events for agent X" or aggregating event costs per agent requires a JOIN through `agent_runs`. This is too indirect for hot dashboard and analytics paths.

## Decision

Denormalize `agent_id` onto both `events` and `spans`, mirroring how `organization_id` is already denormalized on both tables.

## Primary read patterns addressed

- Dashboard: all events for a given agent (cross-run, agent-scoped)
- Analytics: event counts and cost aggregations grouped by agent

## Schema changes

### `events` table

```sql
-- 1. Add nullable first (existing rows would violate NOT NULL otherwise)
ALTER TABLE events ADD COLUMN agent_id UUID REFERENCES agents(id) ON DELETE CASCADE;

-- 2. Backfill
UPDATE events e SET agent_id = r.agent_id FROM agent_runs r WHERE e.run_id = r.id;

-- 3. Enforce NOT NULL after backfill
ALTER TABLE events ALTER COLUMN agent_id SET NOT NULL;

CREATE INDEX events_agent_time_idx     ON events (agent_id, timestamp DESC);
CREATE INDEX events_agent_category_idx ON events (agent_id, category, timestamp DESC);
```

### `spans` table

```sql
ALTER TABLE spans ADD COLUMN agent_id UUID REFERENCES agents(id) ON DELETE CASCADE;
UPDATE spans  s SET agent_id = r.agent_id FROM agent_runs r WHERE s.run_id = r.id;
ALTER TABLE spans ALTER COLUMN agent_id SET NOT NULL;

CREATE INDEX spans_agent_start_idx ON spans (agent_id, start_time DESC);
```

### Prisma schema (`ezop-light-ui/prisma/schema.prisma`)

Add to `Event` model:
```prisma
agent_id  String  @db.Uuid
agent     Agent   @relation(fields: [agent_id], references: [id], onDelete: Cascade)

@@index([agent_id, timestamp(sort: Desc)], map: "events_agent_time_idx")
@@index([agent_id, category, timestamp(sort: Desc)], map: "events_agent_category_idx")
```

Add to `Span` model:
```prisma
agent_id  String  @db.Uuid
agent     Agent   @relation(fields: [agent_id], references: [id], onDelete: Cascade)

@@index([agent_id, start_time(sort: Desc)], map: "spans_agent_start_idx")
```

Add back-relations to `Agent` model:
```prisma
events  Event[]
spans   Span[]
```

## Write path (`ezop-platform`)

### `_assert_run_org` → `_get_run_agent`

Replace the void validation helper with one that returns `agent_id` (same query, one more column):

```python
def _get_run_agent(db: Session, run_id: str, org_id: str) -> str:
    row = db.execute(
        text("SELECT agent_id FROM agent_runs WHERE id = :id AND organization_id = :org_id"),
        {"id": run_id, "org_id": org_id},
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return str(row.agent_id)
```

### `emit_event`

Call `_get_run_agent` instead of `_assert_run_org`. Add `agent_id` to INSERT cols/vals/params.

### `create_span`

Same as above.

### Pydantic models (`app/models/runs.py`)

Add `agent_id: UUID` to both `Event` and `Span`.

## Read path (`ezop-light-ui`)

Before (JOIN through agent_runs):
```ts
prisma.event.findMany({ where: { run: { agent_id: agentId } } })
```

After (direct filter):
```ts
prisma.event.findMany({ where: { agent_id: agentId } })
```

Aggregations use `groupBy: ['agent_id']` directly on `events`.

## Consistency

`agent_id` on a run is immutable (set at run creation, no update path). Denormalized values cannot go stale.

## What's not changing

- No new API routes
- No change to event ingestion payload (SDK does not send `agent_id`; platform derives it from the run)
- No change to auth or plan-limit logic
