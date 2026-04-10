-- Add parent/child run hierarchy with root_run_id denormalization.
-- parent_run_id: direct parent run (NULL for root runs).
-- root_run_id:   top-level ancestor; always set. Denormalized for O(1) tree queries.

ALTER TABLE agent_runs
  ADD COLUMN parent_run_id uuid REFERENCES agent_runs(id) ON DELETE SET NULL,
  ADD COLUMN root_run_id   uuid;

-- Backfill: all existing runs are root runs, so root_run_id = their own id.
UPDATE agent_runs SET root_run_id = id;

ALTER TABLE agent_runs ALTER COLUMN root_run_id SET NOT NULL;

-- Prevent a run from being its own parent.
ALTER TABLE agent_runs
  ADD CONSTRAINT agent_runs_no_self_parent CHECK (parent_run_id != id);

-- Index for "fetch all runs in this tree" queries.
CREATE INDEX agent_runs_root_run_id_idx ON agent_runs (root_run_id);
