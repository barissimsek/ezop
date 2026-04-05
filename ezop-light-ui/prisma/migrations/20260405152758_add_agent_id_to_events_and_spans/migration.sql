-- Step 1: add nullable so existing rows don't violate NOT NULL
ALTER TABLE "events" ADD COLUMN "agent_id" UUID REFERENCES "agents"("id") ON DELETE CASCADE ON UPDATE NO ACTION;
ALTER TABLE "spans"  ADD COLUMN "agent_id" UUID REFERENCES "agents"("id") ON DELETE CASCADE ON UPDATE NO ACTION;

-- Step 2: backfill from agent_runs (agent_id on a run is immutable)
UPDATE "events" e SET "agent_id" = r."agent_id" FROM "agent_runs" r WHERE e."run_id" = r."id";
UPDATE "spans"  s SET "agent_id" = r."agent_id" FROM "agent_runs" r WHERE s."run_id" = r."id";

-- Step 3: enforce NOT NULL after backfill
ALTER TABLE "events" ALTER COLUMN "agent_id" SET NOT NULL;
ALTER TABLE "spans"  ALTER COLUMN "agent_id" SET NOT NULL;

-- Step 4: indexes
CREATE INDEX "events_agent_time_idx"     ON "events" ("agent_id", "timestamp" DESC);
CREATE INDEX "events_agent_category_idx" ON "events" ("agent_id", "category", "timestamp" DESC);
CREATE INDEX "spans_agent_start_idx"     ON "spans"  ("agent_id", "start_time" DESC);
