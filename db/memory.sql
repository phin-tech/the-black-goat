CREATE SCHEMA IF NOT EXISTS goat_memory;

CREATE TABLE IF NOT EXISTS goat_memory.kv (
  namespace   text         NOT NULL,
  key         text         NOT NULL,
  value       jsonb        NOT NULL,
  written_at  timestamptz  NOT NULL DEFAULT now(),
  PRIMARY KEY (namespace, key)
);

CREATE INDEX IF NOT EXISTS kv_namespace_written_at_idx
  ON goat_memory.kv (namespace, written_at DESC);
