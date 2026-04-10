-- Step 1: Add columns as nullable (no violation on existing rows)
ALTER TABLE "agent_runs" ADD COLUMN IF NOT EXISTS "trigger_type" TEXT;
ALTER TABLE "agent_runs" ADD COLUMN IF NOT EXISTS "trigger_id" TEXT;
ALTER TABLE "agent_runs" ADD COLUMN IF NOT EXISTS "parent_run_id" UUID;

-- Step 2: Backfill trigger_type on existing rows
UPDATE "agent_runs" SET "trigger_type" = 'api' WHERE "trigger_type" IS NULL;

-- Step 3: Make trigger_type NOT NULL and set default
ALTER TABLE "agent_runs" ALTER COLUMN "trigger_type" SET NOT NULL;
ALTER TABLE "agent_runs" ALTER COLUMN "trigger_type" SET DEFAULT 'api';

-- Foreign key for parent_run_id (self-referential)
ALTER TABLE "agent_runs" ADD CONSTRAINT "agent_runs_parent_run_id_fkey"
  FOREIGN KEY ("parent_run_id") REFERENCES "agent_runs"("id")
  ON DELETE SET NULL ON UPDATE NO ACTION;

-- CHECK constraints (DB-level enforcement)
ALTER TABLE "agent_runs" ADD CONSTRAINT "agent_requires_parent"
  CHECK (trigger_type != 'agent' OR parent_run_id IS NOT NULL);
ALTER TABLE "agent_runs" ADD CONSTRAINT "non_agent_forbids_parent"
  CHECK (trigger_type = 'agent' OR parent_run_id IS NULL);
ALTER TABLE "agent_runs" ADD CONSTRAINT "agent_forbids_trigger_id"
  CHECK (trigger_type != 'agent' OR trigger_id IS NULL);

-- Indexes
CREATE INDEX IF NOT EXISTS "agent_runs_parent_run_idx"
  ON "agent_runs" ("parent_run_id") WHERE "parent_run_id" IS NOT NULL;
CREATE INDEX IF NOT EXISTS "agent_runs_trigger_idx"
  ON "agent_runs" ("trigger_type", "trigger_id") WHERE "trigger_id" IS NOT NULL;
