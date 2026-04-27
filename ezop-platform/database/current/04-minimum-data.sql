-- Free Plan
INSERT INTO public.plans (name, version, limits)
VALUES (
  'free',
  1,
  '{
    "events_per_month": -1,
    "agents": -1,
    "retention_days": 1
  }'::jsonb
);

