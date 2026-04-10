-- AddColumn
ALTER TABLE "agent_runs" ADD COLUMN "parent_run_id" UUID;
ALTER TABLE "agent_runs" ADD COLUMN "root_run_id" UUID;

-- Backfill: existing runs are root runs
UPDATE "agent_runs" SET "root_run_id" = "id";

-- Make root_run_id NOT NULL after backfill
ALTER TABLE "agent_runs" ALTER COLUMN "root_run_id" SET NOT NULL;

-- Self-referential FK
ALTER TABLE "agent_runs" ADD CONSTRAINT "agent_runs_parent_run_id_fkey"
  FOREIGN KEY ("parent_run_id") REFERENCES "agent_runs"("id")
  ON DELETE SET NULL ON UPDATE NO ACTION;

-- Self-parent prevention
ALTER TABLE "agent_runs" ADD CONSTRAINT "agent_runs_no_self_parent"
  CHECK ("parent_run_id" <> "id");

-- Index for tree queries
CREATE INDEX IF NOT EXISTS "agent_runs_root_run_id_idx" ON "agent_runs" ("root_run_id");
