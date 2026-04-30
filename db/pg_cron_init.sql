-- Enable pg_cron in the absurd database (matches cron.database_name in
-- compose.yml). Idempotent.

CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Allow the absurd application user to read/write the cron schema so the
-- scheduling layer can manage cron.job entries from the application side.
GRANT USAGE ON SCHEMA cron TO absurd;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA cron TO absurd;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA cron TO absurd;
