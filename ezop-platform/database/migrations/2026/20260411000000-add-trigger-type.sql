-- Migration: 20260411000000-add-trigger-type
-- Adds trigger_type_t enum and trigger columns to agent_runs

CREATE TYPE public.trigger_type_t AS ENUM (
    'unknown',
    'api',
    'agent',
    'user',
    'cron',
    'webhook'
);

ALTER TABLE public.agent_runs
    ADD COLUMN trigger_type public.trigger_type_t NOT NULL DEFAULT 'unknown',
    ADD COLUMN trigger_id   TEXT NULL;

CREATE INDEX idx_agent_runs_trigger_type ON public.agent_runs (trigger_type);
