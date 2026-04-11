-- Extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Enum types ────────────────────────────────────────────────────────────────

CREATE TYPE public.run_status AS ENUM ('running', 'success', 'failed');

CREATE TYPE public.plan_t AS ENUM ('free', 'pro', 'enterprise');

CREATE TYPE public.billing_status_t AS ENUM ('active', 'inactive', 'past_due', 'canceled');

CREATE TYPE public.audit_action_t AS ENUM (
  'created', 'updated', 'deleted',
  'invited', 'joined', 'removed',
  'api_key_created', 'api_key_revoked',
  'agent_registered', 'run_started', 'run_completed'
);

CREATE TYPE public.event_category AS ENUM (
  'agent', 'llm', 'tool', 'reasoning', 'system', 'user', 'memory', 'cost', 'error'
);

CREATE TYPE public.event_type AS ENUM (
  'agent_run_started', 'agent_run_completed', 'agent_run_failed',
  'llm_request', 'llm_response',
  'reasoning_step', 'reasoning_plan', 'reasoning_reflection', 'reasoning_decision', 'reasoning_final',
  'tool_call_started', 'tool_call_completed', 'tool_call_failed', 'tool_retry',
  'memory_query', 'memory_retrieval', 'memory_write',
  'span_started', 'span_completed',
  'user_input', 'user_feedback',
  'cost_calculated',
  'error_raised'
);

CREATE TYPE public.event_subtype AS ENUM (
  'chain_of_thought', 'react', 'reflection', 'self_consistency',
  'http', 'database', 'filesystem', 'api',
  'timeout', 'rate_limit', 'validation', 'tool_error', 'llm_error'
);

CREATE TYPE public.trigger_type_t AS ENUM (
    'unknown',
    'api',
    'agent',
    'user',
    'cron',
    'webhook'
);
