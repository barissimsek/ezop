-- CreateEnum
CREATE TYPE "trigger_type_t" AS ENUM ('unknown', 'api', 'agent', 'user', 'cron', 'webhook');

-- AlterTable
ALTER TABLE "agent_runs" ADD COLUMN "trigger_id" TEXT,
ADD COLUMN "trigger_type" "trigger_type_t" NOT NULL DEFAULT 'unknown';

-- CreateIndex
CREATE INDEX "AgentRun_trigger_type_idx" ON "agent_runs"("trigger_type");
