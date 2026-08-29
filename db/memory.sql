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

CREATE TABLE IF NOT EXISTS goat_memory.facts (
  id              uuid         PRIMARY KEY,
  domain          text         NOT NULL,
  type            text         NOT NULL,
  source_plugin   text         NOT NULL,
  source_account  text         NOT NULL DEFAULT '',
  external_id     text         NOT NULL,
  subject         text         NOT NULL,
  title           text,
  body            text,
  status          text,
  date            date,
  starts_at       timestamptz,
  ends_at         timestamptz,
  due_at          timestamptz,
  observed_at     timestamptz  NOT NULL DEFAULT now(),
  valid_from      timestamptz,
  valid_until     timestamptz,
  payload         jsonb        NOT NULL DEFAULT '{}'::jsonb,
  schema_version  integer      NOT NULL DEFAULT 1,
  inserted_at     timestamptz  NOT NULL DEFAULT now(),
  updated_at      timestamptz  NOT NULL DEFAULT now(),
  deleted_at      timestamptz,
  UNIQUE (source_plugin, source_account, external_id, type)
);

CREATE INDEX IF NOT EXISTS facts_domain_type_idx
  ON goat_memory.facts (domain, type);
CREATE INDEX IF NOT EXISTS facts_date_idx
  ON goat_memory.facts (date);
CREATE INDEX IF NOT EXISTS facts_starts_at_idx
  ON goat_memory.facts (starts_at);
CREATE INDEX IF NOT EXISTS facts_due_at_idx
  ON goat_memory.facts (due_at);
CREATE INDEX IF NOT EXISTS facts_observed_at_idx
  ON goat_memory.facts (observed_at);
CREATE INDEX IF NOT EXISTS facts_source_idx
  ON goat_memory.facts (source_plugin, source_account);
CREATE INDEX IF NOT EXISTS facts_payload_gin_idx
  ON goat_memory.facts USING gin (payload);

CREATE TABLE IF NOT EXISTS goat_memory.signal_definitions (
  id                uuid         PRIMARY KEY,
  qualified_name    text         NOT NULL UNIQUE,
  plugin            text         NOT NULL,
  domain            text         NOT NULL,
  kind              text         NOT NULL,
  title             text         NOT NULL,
  description       text         NOT NULL DEFAULT '',
  strategy          text         NOT NULL
    CHECK (strategy IN ('deterministic', 'llm', 'hybrid')),
  input_query       jsonb        NOT NULL DEFAULT '{}'::jsonb,
  generator_tool    text,
  output_schema     jsonb,
  min_confidence    numeric      NOT NULL DEFAULT 0.7,
  default_severity  text         NOT NULL DEFAULT 'info',
  tags              text[]       NOT NULL DEFAULT '{}',
  enabled           boolean      NOT NULL DEFAULT true,
  inserted_at       timestamptz  NOT NULL DEFAULT now(),
  updated_at        timestamptz  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS goat_memory.signals (
  id               uuid         PRIMARY KEY,
  definition_name  text         NOT NULL DEFAULT '',
  dedupe_key       text         NOT NULL,
  domain           text         NOT NULL,
  kind             text         NOT NULL,
  title            text         NOT NULL,
  summary          text         NOT NULL,
  severity         text         NOT NULL
    CHECK (severity IN ('info', 'important', 'urgent')),
  status           text         NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'dismissed', 'snoozed', 'done', 'expired')),
  relevant_at      timestamptz,
  expires_at       timestamptz,
  confidence       numeric      NOT NULL
    CHECK (confidence >= 0 AND confidence <= 1),
  generated_by     text         NOT NULL,
  payload          jsonb        NOT NULL DEFAULT '{}'::jsonb,
  schema_version   integer      NOT NULL DEFAULT 1,
  created_at       timestamptz  NOT NULL DEFAULT now(),
  updated_at       timestamptz  NOT NULL DEFAULT now(),
  UNIQUE (definition_name, dedupe_key)
);

CREATE INDEX IF NOT EXISTS signals_domain_kind_idx
  ON goat_memory.signals (domain, kind);
CREATE INDEX IF NOT EXISTS signals_status_idx
  ON goat_memory.signals (status);
CREATE INDEX IF NOT EXISTS signals_relevant_at_idx
  ON goat_memory.signals (relevant_at);
CREATE INDEX IF NOT EXISTS signals_expires_at_idx
  ON goat_memory.signals (expires_at);
CREATE INDEX IF NOT EXISTS signals_definition_idx
  ON goat_memory.signals (definition_name);

CREATE TABLE IF NOT EXISTS goat_memory.signal_facts (
  signal_id  uuid  NOT NULL
    REFERENCES goat_memory.signals(id) ON DELETE CASCADE,
  fact_id    uuid  NOT NULL
    REFERENCES goat_memory.facts(id) ON DELETE CASCADE,
  role       text  NOT NULL DEFAULT 'supporting',
  PRIMARY KEY (signal_id, fact_id)
);

CREATE TABLE IF NOT EXISTS goat_memory.artifacts (
  id            uuid         PRIMARY KEY,
  type          text         NOT NULL,
  title         text         NOT NULL,
  body          text         NOT NULL,
  date          date,
  payload       jsonb        NOT NULL DEFAULT '{}'::jsonb,
  generated_by  text         NOT NULL,
  created_at    timestamptz  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS goat_memory.artifact_inputs (
  artifact_id  uuid  NOT NULL
    REFERENCES goat_memory.artifacts(id) ON DELETE CASCADE,
  input_type   text  NOT NULL CHECK (input_type IN ('fact', 'signal')),
  input_id     uuid  NOT NULL,
  role         text  NOT NULL DEFAULT 'included',
  PRIMARY KEY (artifact_id, input_type, input_id)
);

CREATE TABLE IF NOT EXISTS goat_memory.source_state (
  plugin      text         NOT NULL,
  account     text         NOT NULL DEFAULT '',
  key         text         NOT NULL,
  value       jsonb        NOT NULL,
  updated_at  timestamptz  NOT NULL DEFAULT now(),
  PRIMARY KEY (plugin, account, key)
);

CREATE TABLE IF NOT EXISTS goat_memory.receipts (
  id           uuid         PRIMARY KEY,
  kind         text         NOT NULL,
  plugin       text         NOT NULL,
  target       text,
  external_id  text,
  status       text         NOT NULL,
  artifact_id  uuid
    REFERENCES goat_memory.artifacts(id) ON DELETE SET NULL,
  payload      jsonb        NOT NULL DEFAULT '{}'::jsonb,
  created_at   timestamptz  NOT NULL DEFAULT now()
);
