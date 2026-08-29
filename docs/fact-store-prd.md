# Fact Store PRD

Status: draft

## Summary

The Black Goat needs a SQL-backed memory layer whose primary primitive is the
Fact: a sourced assertion observed from an external Source. Plugins contribute
capabilities; ingestor tools use those capabilities to sync source data into
facts. The store indexes those facts for deterministic programs. Agent modules
may then propose Signals, which are user-facing interpretations backed by facts.

For the first proof of concept, this store supports:

- Google Calendar sync every few hours.
- A fact-backed daily brief at 7:30 AM America/New_York.
- Slack delivery.
- Future domains such as todos, weather, reminders, and personal notes.

The system should remain program-first. Agents may summarize or propose
signals, but deterministic code owns ingestion, validation, persistence,
dedupe, scheduling, and delivery.

## System Flow

Plugins are the extension and packaging mechanism. They may contribute source
connectors, ingestor tools, signal definitions, routines, delivery tools, and
schedules. They are not themselves the data primitive.

```text
Plugin contributes capabilities
        |
        v
Source -> Ingestor -> Facts -> Signal Definitions -> Signals
                              \                         |
                               \                        v
                                +------------------> Routine
                                                       |
                                                       v
                                                   Artifact
                                                       |
                                                       v
                                                Delivery Tool
                                                       |
                                                       v
                                                    Receipt
```

In words:

- Sources provide observed data.
- Ingestors turn source data into facts.
- Signal definitions infer user-facing signals from facts and state.
- Routines compose facts and signals into artifacts.
- Delivery tools consume artifacts and create receipts.
- Plugins contribute the tools and definitions that make those steps possible.

## Problem

The current memory plugin is a simple namespace/key/value store. That is useful
for early experiments, but it does not give the daily brief a good way to ask:

- What facts are relevant today?
- What is upcoming?
- Which facts came from which source?
- Which generated insights were backed by which facts?
- Which briefs were sent, when, and where?
- Which sync state belongs to which plugin/account?

As calendar, todo, weather, and notification plugins appear, the system needs a
shared data model that is queryable without making the core framework
calendar-specific or todo-specific.

## Goals

- Store observed plugin data as typed, sourced, queryable facts.
- Support common time queries across domains: date, starts_at, ends_at, due_at,
  observed_at, valid_from, and valid_until.
- Store user-facing signals separately from raw facts.
- Track which facts support each signal.
- Allow plugins to register predefined signal definitions.
- Store generated artifacts such as daily briefs.
- Store delivery receipts such as Slack message timestamps.
- Store plugin sync state such as cursors, tokens, and last successful syncs.
- Use PostgreSQL as the backing store, with JSONB for domain-specific payloads.
- Keep the model generic enough for calendar, todo, weather, and later domains.

## Non-Goals

- Do not build a full personal knowledge graph in the POC.
- Do not make per-domain SQL tables such as `calendar_events` or `todo_items`
  until a domain proves it needs one.
- Do not let LLMs write directly to the database.
- Do not require a UI for the first version.
- Do not make signals trusted facts. Signals are derived interpretations.

## Core Concepts

### Source

A Source is an external system, account, or data feed that can be observed.

Examples:

- A Google Calendar account.
- A Todoist workspace.
- A weather API location.
- A Slack workspace.

Sources are represented in configuration and state. They are not plugins.
Plugins provide tools for syncing or delivering through sources.

### Ingestor

An Ingestor is a tool that reads from a source and writes facts.

Examples:

- `google_calendar.sync`
- `todoist.sync`
- `weather.sync_forecast`

Ingestors may update source state and write receipts for sync runs, but their
primary output is facts.

### Fact

A Fact is an observed, sourced assertion.

Examples:

- A calendar event exists from 10:00 to 10:30.
- A todo item is due today.
- The weather forecast says rain begins after 4:00 PM.

Facts are the primary persistence primitive. They should be idempotent by source
identity: `(source_plugin, source_account, external_id, type)`.

### Signal

A Signal is a user-facing interpretation backed by one or more facts.

Examples:

- "Prep for the 10:00 customer call. No notes are attached."
- "Two meetings overlap from 2:00 to 2:30."
- "Leave earlier for the dentist because rain starts before travel time."
- "Calendar has not synced since yesterday evening."

Signals may be produced by deterministic detectors, by an LLM, or by a hybrid
flow. In all cases, stored signals must reference supporting fact ids or another
auditable source such as sync state.

### Signal Definition

A Signal Definition is a plugin-declared recipe for producing signals. This is
how plugins can "predefine" useful signals without immediately producing them.

Examples:

- The calendar plugin defines `calendar.schedule_conflict`.
- The calendar plugin defines `calendar.prep_needed`.
- The todo plugin defines `todo.deadline_risk`.
- The weather plugin defines `weather.travel_weather_risk`.
- The core system defines `system.stale_sync`.

A definition may be deterministic, LLM-assisted, or hybrid. The definition is
registered by the plugin; the signal instances are generated later by a scheduled
or explicit signal generation tool.

### Domain

A Domain is a semantic family of facts, signals, and signal definitions.

Examples:

- `calendar`
- `todo`
- `weather`
- `contacts`
- `system`

Domains are not separate database schemas in the POC. They are query and
ownership boundaries. A plugin may own one domain or contribute facts and signal
definitions to several domains.

### Collection

A Collection is a saved query or curated bundle of facts and signals.

Examples:

- Today.
- This week.
- Needs prep.
- Upcoming travel.
- Waiting on me.

For the POC, collections can be computed at query time. Stored collections can
come later if users need custom saved views.

### Artifact

An Artifact is generated output, not observed source data. Artifacts are the
things routines produce and delivery tools consume.

Examples:

- A daily brief.
- A rendered Slack message.
- A weekly planning report.

Artifacts should reference the facts and signals used to produce them.

### Routine

A Routine is a scheduled or manually triggered workflow that gathers facts and
signals, produces artifacts, and may call delivery tools.

Examples:

- Daily brief.
- Weekly planning brief.
- End-of-day follow-up review.

The daily brief is a routine. It is not a fact or a signal.

### State

State is machine bookkeeping.

Examples:

- Google Calendar `nextSyncToken`.
- Last successful sync time.
- Last failed run and failure message.

State is not user-facing memory, but signals may be generated from it.

### Receipt

A Receipt proves that an effect happened.

Examples:

- Slack `chat.postMessage` returned channel `C123` and timestamp `123.456`.
- A calendar sync imported 47 facts.
- A scheduled run failed.

Receipts support auditability and retry safety.

## Plugin Contract

Plugins may contribute capabilities used by the data flow:

1. Source configuration schemas.
2. Ingestor tools.
3. Signal definitions.
4. Routine definitions.
5. Delivery tools.
6. Schedules.

Plugins should not be treated as sources, facts, signals, or routines. They are
the mechanism for adding those capabilities to the registry. A calendar plugin
may contribute a Google Calendar source config, an ingestor tool, and calendar
signal definitions. A routines plugin may contribute the daily brief routine. A
Slack plugin may contribute delivery tools.

Proposed hook shape:

```python
class GoatHooks:
    def goat_register_tools(self) -> list[ToolDef]: ...
    def goat_register_schedules(self) -> list[Schedule]: ...
    def goat_register_signal_definitions(self) -> list[SignalDefinition]: ...
    def goat_register_routines(self) -> list[RoutineDefinition]: ...
```

Proposed signal definition model:

```python
class SignalDefinition(BaseModel):
    plugin: str = ""
    name: str
    domain: str
    kind: str
    title: str
    desc: str = ""
    strategy: Literal["deterministic", "llm", "hybrid"]
    input_query: dict
    generator_tool: str | None = None
    output_schema: type[BaseModel] | None = None
    min_confidence: float = 0.7
    default_severity: Literal["info", "important", "urgent"] = "info"
    tags: tuple[str, ...] = ()

    @computed_field
    @property
    def qualified_name(self) -> str:
        return f"{self.plugin}.{self.name}" if self.plugin else self.name
```

For deterministic definitions, the plugin should provide a tool that generates
candidate signals and reference it with `generator_tool`. For LLM definitions,
the plugin should provide the query shape and output constraints, while the core
signal runner handles prompt assembly, validation, dedupe, and storage.

Predefined signal definitions are not user-facing messages by themselves. They
are reusable recipes. The user-facing records are the generated Signal rows.

## SQL Data Model

The first implementation should be a generic PostgreSQL schema with relational
columns for common query axes and JSONB payloads for domain-specific detail.

### `goat_memory.facts`

Stores observed assertions.

```sql
CREATE TABLE goat_memory.facts (
  id uuid PRIMARY KEY,
  domain text NOT NULL,
  type text NOT NULL,

  source_plugin text NOT NULL,
  source_account text NOT NULL DEFAULT '',
  external_id text NOT NULL,

  subject text NOT NULL,
  title text,
  body text,
  status text,

  date date,
  starts_at timestamptz,
  ends_at timestamptz,
  due_at timestamptz,
  observed_at timestamptz NOT NULL DEFAULT now(),
  valid_from timestamptz,
  valid_until timestamptz,

  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  schema_version integer NOT NULL DEFAULT 1,

  inserted_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz,

  UNIQUE (source_plugin, source_account, external_id, type)
);
```

Recommended indexes:

```sql
CREATE INDEX facts_domain_type_idx ON goat_memory.facts (domain, type);
CREATE INDEX facts_date_idx ON goat_memory.facts (date);
CREATE INDEX facts_starts_at_idx ON goat_memory.facts (starts_at);
CREATE INDEX facts_due_at_idx ON goat_memory.facts (due_at);
CREATE INDEX facts_observed_at_idx ON goat_memory.facts (observed_at);
CREATE INDEX facts_source_idx
  ON goat_memory.facts (source_plugin, source_account);
CREATE INDEX facts_payload_gin_idx ON goat_memory.facts USING gin (payload);
```

Notes:

- `domain` is a broad family such as `calendar`, `todo`, or `weather`.
- `type` is the precise fact type such as `calendar.event`.
- `subject` is the thing the fact is about. For POC calendar events this can be
  a stable source urn such as `google_calendar:primary:event_123`.
- `source_account` is an empty string when no account applies. It is not
  nullable because PostgreSQL unique constraints treat nulls as distinct.
- `external_id` must be stable. For local or derived facts, the writer should
  generate a deterministic id.
- `payload` stores raw and normalized domain-specific fields.
- `deleted_at` supports tombstones for source records that disappear.

### `goat_memory.signal_definitions`

Stores plugin-declared signal recipes.

```sql
CREATE TABLE goat_memory.signal_definitions (
  id uuid PRIMARY KEY,
  qualified_name text NOT NULL UNIQUE,
  plugin text NOT NULL,
  domain text NOT NULL,
  kind text NOT NULL,
  title text NOT NULL,
  description text NOT NULL DEFAULT '',
  strategy text NOT NULL CHECK (strategy IN ('deterministic', 'llm', 'hybrid')),
  input_query jsonb NOT NULL DEFAULT '{}'::jsonb,
  generator_tool text,
  output_schema jsonb,
  min_confidence numeric NOT NULL DEFAULT 0.7,
  default_severity text NOT NULL DEFAULT 'info',
  tags text[] NOT NULL DEFAULT '{}',
  enabled boolean NOT NULL DEFAULT true,
  inserted_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
```

The registry can also keep signal definitions in memory, like tools and
schedules. Persisting them is useful for audit, admin views, and disabling a
definition without uninstalling a plugin.

### `goat_memory.signals`

Stores generated user-facing interpretations.

```sql
CREATE TABLE goat_memory.signals (
  id uuid PRIMARY KEY,
  definition_name text NOT NULL DEFAULT '',
  dedupe_key text NOT NULL,
  domain text NOT NULL,
  kind text NOT NULL,

  title text NOT NULL,
  summary text NOT NULL,
  severity text NOT NULL CHECK (severity IN ('info', 'important', 'urgent')),
  status text NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'dismissed', 'snoozed', 'done', 'expired')),

  relevant_at timestamptz,
  expires_at timestamptz,
  confidence numeric NOT NULL CHECK (confidence >= 0 AND confidence <= 1),

  generated_by text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  schema_version integer NOT NULL DEFAULT 1,

  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),

  UNIQUE (definition_name, dedupe_key)
);
```

Recommended indexes:

```sql
CREATE INDEX signals_domain_kind_idx ON goat_memory.signals (domain, kind);
CREATE INDEX signals_status_idx ON goat_memory.signals (status);
CREATE INDEX signals_relevant_at_idx ON goat_memory.signals (relevant_at);
CREATE INDEX signals_expires_at_idx ON goat_memory.signals (expires_at);
CREATE INDEX signals_definition_idx ON goat_memory.signals (definition_name);
```

The signal runner constructs `dedupe_key` deterministically, usually from the
definition name, sorted supporting fact ids, kind, and relevant time window.

### `goat_memory.signal_facts`

Joins signals to supporting facts.

```sql
CREATE TABLE goat_memory.signal_facts (
  signal_id uuid NOT NULL REFERENCES goat_memory.signals(id) ON DELETE CASCADE,
  fact_id uuid NOT NULL REFERENCES goat_memory.facts(id) ON DELETE CASCADE,
  role text NOT NULL DEFAULT 'supporting',
  PRIMARY KEY (signal_id, fact_id)
);
```

### `goat_memory.artifacts`

Stores generated outputs such as daily briefs.

```sql
CREATE TABLE goat_memory.artifacts (
  id uuid PRIMARY KEY,
  type text NOT NULL,
  title text NOT NULL,
  body text NOT NULL,
  date date,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  generated_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
```

### `goat_memory.artifact_inputs`

Tracks which facts and signals were used to produce an artifact.

```sql
CREATE TABLE goat_memory.artifact_inputs (
  artifact_id uuid NOT NULL
    REFERENCES goat_memory.artifacts(id) ON DELETE CASCADE,
  input_type text NOT NULL CHECK (input_type IN ('fact', 'signal')),
  input_id uuid NOT NULL,
  role text NOT NULL DEFAULT 'included',
  PRIMARY KEY (artifact_id, input_type, input_id)
);
```

### `goat_memory.source_state`

Stores plugin/account state.

```sql
CREATE TABLE goat_memory.source_state (
  plugin text NOT NULL,
  account text NOT NULL DEFAULT '',
  key text NOT NULL,
  value jsonb NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (plugin, account, key)
);
```

### `goat_memory.receipts`

Stores side-effect receipts and run records.

```sql
CREATE TABLE goat_memory.receipts (
  id uuid PRIMARY KEY,
  kind text NOT NULL,
  plugin text NOT NULL,
  target text,
  external_id text,
  status text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
```

## Fact Store API

The SQL schema should be wrapped by typed tools rather than exposed directly to
agents.

Minimum POC tools:

```text
facts.upsert
facts.get
facts.query
facts.link_signal

signals.generate
signals.query
signals.dismiss

artifacts.put
artifacts.query

state.get
state.put

receipts.put
```

Delivery tools should accept either an `artifact_id` or a fully rendered
artifact payload. For auditable routines, prefer `artifact_id`: the delivery
tool reads the artifact, sends it, and writes a receipt that references the
artifact.

`facts.query` should support:

- `domain`
- `type`
- `source_plugin`
- `source_account`
- `date`
- `starts_between`
- `due_between`
- `observed_since`
- `valid_at`
- `status`
- `limit`

The daily brief should call typed query tools, not raw SQL.

## Daily Brief POC Flow

### Calendar Sync

Schedule:

```text
every 2 or 3 hours
```

Flow:

```text
google_calendar.sync
  -> read source_state nextSyncToken
  -> fetch changed events
  -> upsert calendar.event facts
  -> update source_state
  -> write receipt
```

### Signal Generation

Schedule:

```text
before daily brief, for example 7:20 AM America/New_York
```

Flow:

```text
signals.generate
  -> load enabled signal definitions
  -> query candidate facts/state
  -> run deterministic detectors and bounded LLM proposers
  -> validate fact references
  -> dedupe active signals
  -> store accepted signals
```

### Daily Brief

Schedule:

```text
7:30 AM America/New_York
```

Flow:

```text
daily_brief.generate
  -> query today's facts
  -> query upcoming facts
  -> query active signals
  -> write daily_brief artifact
  -> slack.send_message artifact_id
  -> write Slack receipt referencing artifact_id
```

## Validation Rules

All LLM-proposed signals must pass deterministic validation before storage:

- Every referenced fact id exists.
- The signal does not invent times, people, or event names absent from facts.
- `confidence` is within the configured threshold.
- `expires_at` is present for time-sensitive signals.
- The same active signal does not already exist for the same definition and
  supporting facts.
- The summary is short enough for Slack.
- The signal is actionable or decision-relevant.

Signals that merely restate a fact should be rejected.

## Open Questions

- Should `source_account` be user-visible, or should accounts be modeled as
  first-class entities?
- Should collections be stored in SQL for the POC, or computed from queries?
- Should signal definitions be disabled through config, database state, or both?
- Should facts support soft deletion and tombstones for removed source events?
- Should daily brief generation create signals inline if a prior signal run did
  not happen?

## Milestones

### Milestone 1: Fact Store Schema

- Add SQL migrations for facts, state, artifacts, receipts, signals, and signal
  fact links.
- Add Pydantic models and typed store tools.
- Keep the existing KV memory plugin available during transition.

### Milestone 2: Calendar Facts

- Add Google Calendar sync plugin.
- Store calendar events as `calendar.event` facts.
- Store sync token and last sync status in `source_state`.

### Milestone 3: Predefined Signals

- Add signal definition hookspec and registry support.
- Let the calendar plugin define schedule conflict and prep-needed signals.
- Add `signals.generate` with deterministic validation and dedupe.

### Milestone 4: Daily Slack Brief

- Generate a daily brief artifact from facts and active signals.
- Send it to Slack at 7:30 AM America/New_York.
- Store Slack delivery receipts.
