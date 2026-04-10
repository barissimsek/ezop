-- Add agent_id to events and spans for direct agent-scoped queries
-- without requiring a JOIN through agent_runs.

ALTER TABLE "events" ADD COLUMN "agent_id" UUID REFERENCES "agents"("id") ON DELETE CASCADE ON UPDATE NO ACTION;
ALTER TABLE "spans"  ADD COLUMN "agent_id" UUID REFERENCES "agents"("id") ON DELETE CASCADE ON UPDATE NO ACTION;

UPDATE "events" e SET "agent_id" = r."agent_id" FROM "agent_runs" r WHERE e."run_id" = r."id";
UPDATE "spans"  s SET "agent_id" = r."agent_id" FROM "agent_runs" r WHERE s."run_id" = r."id";

ALTER TABLE "events" ALTER COLUMN "agent_id" SET NOT NULL;
ALTER TABLE "spans"  ALTER COLUMN "agent_id" SET NOT NULL;

CREATE INDEX "events_agent_time_idx"     ON "events" ("agent_id", "timestamp" DESC);
CREATE INDEX "events_agent_category_idx" ON "events" ("agent_id", "category", "timestamp" DESC);
CREATE INDEX "spans_agent_start_idx"     ON "spans"  ("agent_id", "start_time" DESC);
