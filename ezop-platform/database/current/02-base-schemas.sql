create table public.organizations (
  id uuid not null default gen_random_uuid (),
  name text not null,
  created_at timestamp with time zone not null default now(),
  plan public.plan_t null default 'free'::plan_t,
  updated_at timestamp with time zone not null default now(),
  constraint organizations_pkey primary key (id)
) TABLESPACE pg_default;

create table public.users (
  id uuid not null,
  email text not null,
  created_at timestamp with time zone not null default now(),
  firstname text null,
  lastname text null,
  constraint users_pkey primary key (id),
  constraint users_email_key unique (email)
) TABLESPACE pg_default;

create table public.organization_members (
  user_id uuid not null,
  organization_id uuid not null,
  role text not null default 'member'::text,
  constraint organization_members_pkey primary key (user_id, organization_id),
  constraint organization_members_organization_id_fkey foreign KEY (organization_id) references organizations (id) on delete CASCADE,
  constraint organization_members_user_id_fkey foreign KEY (user_id) references users (id) on delete CASCADE
) TABLESPACE pg_default;

create table public.plans (
  id uuid not null default gen_random_uuid (),
  name public.plan_t not null,
  version integer not null default 1,
  limits jsonb not null default '{}'::jsonb,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint plans_pkey primary key (id)
) TABLESPACE pg_default;

create table public.service_costs (
  id uuid not null default gen_random_uuid (),
  service_type text not null,
  service_name text not null,
  unit_cost numeric(18, 6) not null default 0,
  unit_type text not null,
  description text null,
  pricing_details jsonb null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint service_costs_pkey primary key (id),
  constraint service_costs_service_type_check check (
    (
      service_type = any (
        array[
          'llm'::text,
          'api'::text,
          'tool'::text,
          'compute'::text
        ]
      )
    )
  )
) TABLESPACE pg_default;

create table public.agents (
  id uuid not null default gen_random_uuid (),
  name text not null,
  owner text not null,
  default_permissions text[] null,
  description text null,
  runtime text null,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  organization_id uuid not null,
  constraint agents_pkey primary key (id),
  constraint agents_name_owner_unique unique (name, owner, organization_id),
  constraint agents_org_fkey foreign KEY (organization_id) references organizations (id) on delete CASCADE
) TABLESPACE pg_default;

create index IF not exists agents_owner_idx on public.agents using btree (owner) TABLESPACE pg_default;

create index IF not exists agents_name_idx on public.agents using btree (name) TABLESPACE pg_default;

create index IF not exists agents_org_idx on public.agents using btree (organization_id) TABLESPACE pg_default;

create table public.agent_versions (
  id uuid not null default gen_random_uuid (),
  agent_id uuid not null,
  version text not null,
  permissions text[] null,
  changelog text null,
  created_at timestamp with time zone not null default now(),
  organization_id uuid not null,
  constraint agent_versions_pkey primary key (id),
  constraint agent_versions_agent_id_version_key unique (agent_id, version),
  constraint agent_versions_agent_id_fkey foreign KEY (agent_id) references agents (id) on delete CASCADE,
  constraint agent_versions_org_fkey foreign KEY (organization_id) references organizations (id) on delete CASCADE
) TABLESPACE pg_default;

create index IF not exists agent_versions_agent_id_idx on public.agent_versions using btree (agent_id) TABLESPACE pg_default;

create index IF not exists agent_versions_version_idx on public.agent_versions using btree (version) TABLESPACE pg_default;

create index IF not exists agent_versions_org_idx on public.agent_versions using btree (organization_id) TABLESPACE pg_default;

create table public.agent_runs (
  id uuid not null default gen_random_uuid (),
  agent_id uuid not null,
  version_id uuid null,
  user_id uuid null,
  start_time timestamp with time zone not null default now(),
  end_time timestamp with time zone null default now(),
  status public.run_status not null,
  metadata jsonb null,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  message text null,
  parent_run_id uuid null,
  root_run_id uuid not null,
  organization_id uuid not null,
  constraint agent_runs_pkey primary key (id),
  constraint agent_runs_agent_id_fkey foreign KEY (agent_id) references agents (id) on delete CASCADE,
  constraint agent_runs_organization_id_fkey foreign KEY (organization_id) references organizations (id) on delete CASCADE,
  constraint agent_runs_version_id_fkey foreign KEY (version_id) references agent_versions (id) on delete set null,
  constraint agent_runs_no_self_parent check ((parent_run_id <> id)),
  constraint agent_runs_parent_run_id_fkey foreign KEY (parent_run_id) references agent_runs (id) on delete set null
) TABLESPACE pg_default;

create index IF not exists agent_runs_agent_id_idx on public.agent_runs using btree (agent_id) TABLESPACE pg_default;

create index IF not exists agent_runs_version_id_idx on public.agent_runs using btree (version_id) TABLESPACE pg_default;

create index IF not exists agent_runs_start_time_idx on public.agent_runs using btree (start_time) TABLESPACE pg_default;

create index IF not exists agent_runs_status_idx on public.agent_runs using btree (status) TABLESPACE pg_default;

create index IF not exists agent_runs_root_run_id_idx on public.agent_runs using btree (root_run_id) TABLESPACE pg_default;

create table public.spans (
  run_id uuid not null,
  name text null,
  start_time timestamp with time zone not null default now(),
  end_time timestamp with time zone null,
  metadata jsonb null,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  id uuid not null default gen_random_uuid (),
  parent_id uuid null,
  organization_id uuid not null,
  agent_id uuid not null,
  constraint spans_pkey primary key (id),
  constraint spans_organization_id_fkey foreign KEY (organization_id) references organizations (id) on delete CASCADE,
  constraint spans_parent_id_fkey foreign KEY (parent_id) references spans (id) on delete CASCADE,
  constraint spans_run_id_fkey foreign KEY (run_id) references agent_runs (id) on delete CASCADE,
  constraint spans_agent_fkey foreign KEY (agent_id) references agents (id) on delete CASCADE,
  constraint spans_no_self_parent check ((id <> parent_id))
) TABLESPACE pg_default;

create index IF not exists spans_run_id_idx on public.spans using btree (run_id) TABLESPACE pg_default;

create index IF not exists spans_start_time_idx on public.spans using btree (start_time) TABLESPACE pg_default;

create index IF not exists spans_run_start_idx on public.spans using btree (run_id, start_time) TABLESPACE pg_default;

create index IF not exists spans_parent_id_idx on public.spans using btree (parent_id) TABLESPACE pg_default;

create index IF not exists spans_agent_start_idx on public.spans using btree (agent_id, start_time desc) TABLESPACE pg_default;

create trigger update_spans_updated_at BEFORE
update on spans for EACH row
execute FUNCTION update_updated_at_column ();

create table public.events (
  id uuid not null default gen_random_uuid (),
  run_id uuid not null,
  span_id uuid null,
  name text not null,
  timestamp timestamp with time zone not null default now(),
  input jsonb null,
  output jsonb null,
  metadata jsonb null,
  error jsonb null,
  created_at timestamp with time zone not null default now(),
  organization_id uuid not null,
  sequence bigint generated always as identity not null,
  category public.event_category not null,
  type public.event_type null,
  subtype public.event_subtype null,
  iteration_id integer null,
  agent_id uuid not null,
  constraint events_pkey primary key (id),
  constraint events_organization_id_fkey foreign KEY (organization_id) references organizations (id) on delete CASCADE,
  constraint events_run_id_fkey foreign KEY (run_id) references agent_runs (id) on delete CASCADE,
  constraint events_span_id_fkey foreign KEY (span_id) references spans (id) on delete CASCADE,
  constraint events_agent_fkey foreign KEY (agent_id) references agents (id) on delete CASCADE,
  constraint events_type_requires_category check (
    (
      (
        (category = 'llm'::event_category)
        and (
          type = any (
            array[
              'llm_request'::event_type,
              'llm_response'::event_type
            ]
          )
        )
      )
      or (
        (category = 'tool'::event_category)
        and (
          type = any (
            array[
              'tool_call_started'::event_type,
              'tool_call_completed'::event_type,
              'tool_call_failed'::event_type,
              'tool_retry'::event_type
            ]
          )
        )
      )
      or (
        (category = 'reasoning'::event_category)
        and (
          type = any (
            array[
              'reasoning_step'::event_type,
              'reasoning_plan'::event_type,
              'reasoning_reflection'::event_type,
              'reasoning_decision'::event_type,
              'reasoning_final'::event_type
            ]
          )
        )
      )
      or (
        (category = 'agent'::event_category)
        and (
          type = any (
            array[
              'agent_run_started'::event_type,
              'agent_run_completed'::event_type,
              'agent_run_failed'::event_type
            ]
          )
        )
      )
      or (
        (category = 'memory'::event_category)
        and (
          type = any (
            array[
              'memory_query'::event_type,
              'memory_retrieval'::event_type,
              'memory_write'::event_type
            ]
          )
        )
      )
      or (
        (category = 'system'::event_category)
        and (
          type = any (
            array[
              'span_started'::event_type,
              'span_completed'::event_type
            ]
          )
        )
      )
      or (
        (category = 'user'::event_category)
        and (
          type = any (
            array[
              'user_input'::event_type,
              'user_feedback'::event_type
            ]
          )
        )
      )
      or (
        (category = 'cost'::event_category)
        and (type = 'cost_calculated'::event_type)
      )
      or (
        (category = 'error'::event_category)
        and (type = 'error_raised'::event_type)
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists events_run_id_idx on public.events using btree (run_id) TABLESPACE pg_default;

create index IF not exists events_name_idx on public.events using btree (name) TABLESPACE pg_default;

create index IF not exists events_timestamp_idx on public.events using btree ("timestamp") TABLESPACE pg_default;

create index IF not exists events_span_id_idx on public.events using btree (span_id) TABLESPACE pg_default;

create index IF not exists events_span_time_idx on public.events using btree (span_id, "timestamp") TABLESPACE pg_default;

create index IF not exists events_run_time_idx on public.events using btree (run_id, "timestamp") TABLESPACE pg_default;

create index IF not exists events_org_idx on public.events using btree (organization_id) TABLESPACE pg_default;

create index IF not exists events_reasoning_idx on public.events using btree (run_id, category, type) TABLESPACE pg_default;

create index IF not exists events_iteration_idx on public.events using btree (run_id, iteration_id) TABLESPACE pg_default;

create index IF not exists events_category_time_idx on public.events using btree (category, "timestamp" desc) TABLESPACE pg_default;

create index IF not exists events_agent_time_idx on public.events using btree (agent_id, "timestamp" desc) TABLESPACE pg_default;

create index IF not exists events_agent_category_idx on public.events using btree (agent_id, category, "timestamp" desc) TABLESPACE pg_default;

create table public.api_keys (
  id uuid not null default gen_random_uuid (),
  name text not null,
  description text null,
  key_prefix text not null,
  key_hash text not null,
  scopes text[] not null default '{}'::text[],
  last_used_at timestamp with time zone null,
  expires_at timestamp with time zone null,
  revoked_at timestamp with time zone null,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  organization_id uuid not null,
  created_by uuid null,
  plan text null,
  constraint api_keys_pkey primary key (id),
  constraint api_keys_prefix_unique unique (key_prefix),
  constraint api_keys_created_by_fkey foreign KEY (created_by) references users (id) on delete set null,
  constraint api_keys_organization_id_fkey foreign KEY (organization_id) references organizations (id) on delete CASCADE
) TABLESPACE pg_default;

create index IF not exists api_keys_key_prefix_idx on public.api_keys using btree (key_prefix) TABLESPACE pg_default;

create index IF not exists api_keys_created_at_idx on public.api_keys using btree (created_at desc) TABLESPACE pg_default;

create trigger api_keys_updated_at BEFORE
update on api_keys for EACH row
execute FUNCTION update_updated_at ();

create table public.audit_logs (
  id uuid not null default gen_random_uuid (),
  organization_id uuid not null,
  actor_type text not null,
  actor_id uuid null,
  action public.audit_action_t not null,
  resource_type text not null,
  resource_id uuid null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamp with time zone not null default now(),
  constraint audit_logs_pkey primary key (id),
  constraint fk_audit_logs_org foreign KEY (organization_id) references organizations (id) on delete CASCADE
) TABLESPACE pg_default;

create index IF not exists idx_audit_logs_org on public.audit_logs using btree (organization_id) TABLESPACE pg_default;

create index IF not exists idx_audit_logs_created_at on public.audit_logs using btree (created_at desc) TABLESPACE pg_default;

create index IF not exists idx_audit_logs_action on public.audit_logs using btree (action) TABLESPACE pg_default;

