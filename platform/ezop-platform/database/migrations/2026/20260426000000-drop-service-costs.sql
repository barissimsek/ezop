-- Migration: 20260426000000-drop-service-costs
-- Removes service_costs table. Token/API usage is tracked via events;
-- USD cost conversion is no longer computed by the platform.

DROP TABLE IF EXISTS public.service_costs;
