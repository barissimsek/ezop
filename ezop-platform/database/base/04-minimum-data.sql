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

INSERT INTO "public"."service_costs"
("id", "service_type", "service_name", "unit_cost", "unit_type", "description", "pricing_details")
VALUES
('340ccf64-b727-49a6-b89f-30679ffdc7c5', 'api', 'stripe_payment', '0.025000', 'per_call', 'Stripe payment processing fee per request', null),
('51559b34-3cef-4a3d-90bf-0f173753e0e3', 'llm', 'gpt-5.2', '0.014000', '1k_output_tokens', 'GPT-5.2 output token pricing', null),
('5a321d0d-ef30-48b2-8ddf-9f1f9cb86d94', 'llm', 'gpt-4.1', '0.002000', '1k_input_tokens', 'GPT-4.1 input token pricing', null),
('68263169-9923-4714-a055-a0bad705c095', 'api', 'stripe_charge', '0.300000', 'per_call', 'Stripe charge API flat fee per request', null),
('d9c3ddd1-1a71-4523-8de8-049c633d365b', 'llm', 'gpt-4.1', '0.008000', '1k_output_tokens', 'GPT-4.1 output token pricing', null),
('f5f6ba81-3e69-4632-8009-19ce36d49839', 'compute', 'vector_search', '0.010000', 'per_1k_vectors', 'Vector DB search cost per 1000 vectors', '{"gpu":"a100","memory_gb":16}'),
('fe3b8928-30d7-4e48-a290-f46220262a90', 'llm', 'claude', '0.001750', '1k_input_tokens', 'GPT-5.2 input token pricing', null);
