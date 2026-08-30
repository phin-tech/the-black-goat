from __future__ import annotations

import uuid
from datetime import UTC, date as Date, datetime as DateTime
from typing import Any, Literal

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, SecretStr


class FactsConfig(BaseModel):
    database_url: SecretStr  # env: FACTS_DATABASE_URL


class FactRecord(BaseModel):
    id: str
    domain: str
    type: str
    source_plugin: str
    source_account: str
    external_id: str
    subject: str
    person: str | None = None
    title: str | None = None
    body: str | None = None
    status: str | None = None
    date: Date | None = None
    starts_at: DateTime | None = None
    ends_at: DateTime | None = None
    due_at: DateTime | None = None
    observed_at: DateTime
    valid_from: DateTime | None = None
    valid_until: DateTime | None = None
    payload: dict[str, Any]
    schema_version: int
    inserted_at: DateTime
    updated_at: DateTime
    deleted_at: DateTime | None = None


def _connect(config: FactsConfig):
    return Connection.connect(config.database_url.get_secret_value())


def _record_from_row(row: dict[str, Any]) -> FactRecord:
    data = dict(row)
    data["id"] = str(data["id"])
    return FactRecord.model_validate(data)


class FactUpsertInput(BaseModel):
    id: uuid.UUID | None = None
    domain: str = Field(min_length=1)
    type: str = Field(min_length=1)
    source_plugin: str = Field(min_length=1)
    source_account: str = ""
    external_id: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    person: str | None = None
    title: str | None = None
    body: str | None = None
    status: str | None = None
    date: Date | None = None
    starts_at: DateTime | None = None
    ends_at: DateTime | None = None
    due_at: DateTime | None = None
    observed_at: DateTime = Field(
        default_factory=lambda: DateTime.now(UTC)
    )
    valid_from: DateTime | None = None
    valid_until: DateTime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    schema_version: int = Field(default=1, ge=1)
    deleted_at: DateTime | None = None


class FactUpsertOutput(BaseModel):
    id: str
    inserted_at: DateTime
    updated_at: DateTime


def upsert(input: FactUpsertInput, *, config: FactsConfig) -> FactUpsertOutput:
    fact_id = input.id or uuid.uuid4()
    with _connect(config) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO goat_memory.facts (
                  id, domain, type, source_plugin, source_account,
                  external_id, subject, person, title, body, status, date,
                  starts_at, ends_at, due_at, observed_at, valid_from,
                  valid_until, payload, schema_version, deleted_at
                )
                VALUES (
                  %s, %s, %s, %s, %s,
                  %s, %s, %s, %s, %s, %s, %s,
                  %s, %s, %s, %s, %s,
                  %s, %s, %s, %s
                )
                ON CONFLICT (
                  source_plugin, source_account, external_id, type
                )
                DO UPDATE SET
                  domain = EXCLUDED.domain,
                  subject = EXCLUDED.subject,
                  person = EXCLUDED.person,
                  title = EXCLUDED.title,
                  body = EXCLUDED.body,
                  status = EXCLUDED.status,
                  date = EXCLUDED.date,
                  starts_at = EXCLUDED.starts_at,
                  ends_at = EXCLUDED.ends_at,
                  due_at = EXCLUDED.due_at,
                  observed_at = EXCLUDED.observed_at,
                  valid_from = EXCLUDED.valid_from,
                  valid_until = EXCLUDED.valid_until,
                  payload = EXCLUDED.payload,
                  schema_version = EXCLUDED.schema_version,
                  deleted_at = EXCLUDED.deleted_at,
                  updated_at = now()
                RETURNING id, inserted_at, updated_at;
                """,
                (
                    fact_id,
                    input.domain,
                    input.type,
                    input.source_plugin,
                    input.source_account,
                    input.external_id,
                    input.subject,
                    input.person,
                    input.title,
                    input.body,
                    input.status,
                    input.date,
                    input.starts_at,
                    input.ends_at,
                    input.due_at,
                    input.observed_at,
                    input.valid_from,
                    input.valid_until,
                    Jsonb(input.payload),
                    input.schema_version,
                    input.deleted_at,
                ),
            )
            row = cur.fetchone()
            assert row is not None
    return FactUpsertOutput(
        id=str(row["id"]),
        inserted_at=row["inserted_at"],
        updated_at=row["updated_at"],
    )


class FactGetInput(BaseModel):
    id: uuid.UUID


class FactGetOutput(BaseModel):
    fact: FactRecord | None = None


def get(input: FactGetInput, *, config: FactsConfig) -> FactGetOutput:
    with _connect(config) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM goat_memory.facts WHERE id = %s",
                (input.id,),
            )
            row = cur.fetchone()
    return FactGetOutput(fact=_record_from_row(row) if row else None)


class FactQueryInput(BaseModel):
    domain: str | None = None
    type: str | None = None
    source_plugin: str | None = None
    source_account: str | None = None
    person: str | None = None
    date: Date | None = None
    starts_from: DateTime | None = None
    starts_until: DateTime | None = None
    due_from: DateTime | None = None
    due_until: DateTime | None = None
    observed_since: DateTime | None = None
    valid_at: DateTime | None = None
    status: str | None = None
    include_deleted: bool = False
    limit: int = Field(default=100, ge=1, le=10_000)


class FactQueryOutput(BaseModel):
    facts: list[FactRecord]


def query(input: FactQueryInput, *, config: FactsConfig) -> FactQueryOutput:
    clauses: list[str] = []
    params: list[Any] = []
    if not input.include_deleted:
        clauses.append("deleted_at IS NULL")
    for field in (
        "domain",
        "type",
        "source_plugin",
        "source_account",
        "person",
        "date",
        "status",
    ):
        value = getattr(input, field)
        if value is not None:
            clauses.append(f"{field} = %s")
            params.append(value)
    if input.starts_from is not None:
        clauses.append("starts_at >= %s")
        params.append(input.starts_from)
    if input.starts_until is not None:
        clauses.append("starts_at < %s")
        params.append(input.starts_until)
    if input.due_from is not None:
        clauses.append("due_at >= %s")
        params.append(input.due_from)
    if input.due_until is not None:
        clauses.append("due_at < %s")
        params.append(input.due_until)
    if input.observed_since is not None:
        clauses.append("observed_at >= %s")
        params.append(input.observed_since)
    if input.valid_at is not None:
        clauses.append("(valid_from IS NULL OR valid_from <= %s)")
        params.append(input.valid_at)
        clauses.append("(valid_until IS NULL OR valid_until > %s)")
        params.append(input.valid_at)

    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(input.limit)
    with _connect(config) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT * FROM goat_memory.facts
                {where}
                ORDER BY COALESCE(starts_at, due_at, observed_at),
                         inserted_at
                LIMIT %s
                """,
                params,
            )
            rows = cur.fetchall()
    return FactQueryOutput(facts=[_record_from_row(row) for row in rows])


class StateGetInput(BaseModel):
    plugin: str = Field(min_length=1)
    account: str = ""
    key: str = Field(min_length=1)


class StateGetOutput(BaseModel):
    value: dict[str, Any] | None = None
    updated_at: DateTime | None = None


def state_get(input: StateGetInput, *, config: FactsConfig) -> StateGetOutput:
    with _connect(config) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT value, updated_at
                FROM goat_memory.source_state
                WHERE plugin = %s AND account = %s AND key = %s
                """,
                (input.plugin, input.account, input.key),
            )
            row = cur.fetchone()
    if row is None:
        return StateGetOutput()
    return StateGetOutput(value=row["value"], updated_at=row["updated_at"])


class StatePutInput(StateGetInput):
    value: dict[str, Any]


class StatePutOutput(BaseModel):
    updated_at: DateTime


def state_put(input: StatePutInput, *, config: FactsConfig) -> StatePutOutput:
    with _connect(config) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO goat_memory.source_state (
                  plugin, account, key, value, updated_at
                )
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (plugin, account, key)
                DO UPDATE SET value = EXCLUDED.value, updated_at = now()
                RETURNING updated_at
                """,
                (
                    input.plugin,
                    input.account,
                    input.key,
                    Jsonb(input.value),
                ),
            )
            row = cur.fetchone()
            assert row is not None
    return StatePutOutput(updated_at=row["updated_at"])


class ArtifactPutInput(BaseModel):
    id: uuid.UUID | None = None
    type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    date: Date | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    generated_by: str = Field(min_length=1)
    fact_ids: list[uuid.UUID] = Field(default_factory=list)
    signal_ids: list[uuid.UUID] = Field(default_factory=list)


class ArtifactPutOutput(BaseModel):
    id: str
    created_at: DateTime


class ArtifactRecord(BaseModel):
    id: str
    type: str
    title: str
    body: str
    date: Date | None = None
    payload: dict[str, Any]
    generated_by: str
    created_at: DateTime


def _artifact_from_row(row: dict[str, Any]) -> ArtifactRecord:
    data = dict(row)
    data["id"] = str(data["id"])
    return ArtifactRecord.model_validate(data)


def artifact_put(
    input: ArtifactPutInput, *, config: FactsConfig
) -> ArtifactPutOutput:
    artifact_id = input.id or uuid.uuid4()
    with _connect(config) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO goat_memory.artifacts (
                  id, type, title, body, date, payload, generated_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, created_at
                """,
                (
                    artifact_id,
                    input.type,
                    input.title,
                    input.body,
                    input.date,
                    Jsonb(input.payload),
                    input.generated_by,
                ),
            )
            row = cur.fetchone()
            assert row is not None
            _insert_artifact_inputs(
                cur,
                artifact_id,
                "fact",
                input.fact_ids,
            )
            _insert_artifact_inputs(
                cur,
                artifact_id,
                "signal",
                input.signal_ids,
            )
    return ArtifactPutOutput(id=str(row["id"]), created_at=row["created_at"])


class ArtifactGetInput(BaseModel):
    id: uuid.UUID


class ArtifactGetOutput(BaseModel):
    artifact: ArtifactRecord | None = None


def artifact_get(
    input: ArtifactGetInput, *, config: FactsConfig
) -> ArtifactGetOutput:
    with _connect(config) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM goat_memory.artifacts WHERE id = %s",
                (input.id,),
            )
            row = cur.fetchone()
    return ArtifactGetOutput(
        artifact=_artifact_from_row(row) if row else None
    )


class ArtifactsQueryInput(BaseModel):
    type: str | None = None
    date: Date | None = None
    generated_by: str | None = None
    limit: int = Field(default=100, ge=1, le=10_000)


class ArtifactsQueryOutput(BaseModel):
    artifacts: list[ArtifactRecord]


def artifacts_query(
    input: ArtifactsQueryInput, *, config: FactsConfig
) -> ArtifactsQueryOutput:
    clauses: list[str] = []
    params: list[Any] = []
    for field in ("type", "date", "generated_by"):
        value = getattr(input, field)
        if value is not None:
            clauses.append(f"{field} = %s")
            params.append(value)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(input.limit)
    with _connect(config) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT * FROM goat_memory.artifacts
                {where}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                params,
            )
            rows = cur.fetchall()
    return ArtifactsQueryOutput(
        artifacts=[_artifact_from_row(row) for row in rows]
    )


def _insert_artifact_inputs(cur, artifact_id, input_type: str, ids):
    for input_id in ids:
        cur.execute(
            """
            INSERT INTO goat_memory.artifact_inputs (
              artifact_id, input_type, input_id
            )
            VALUES (%s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (artifact_id, input_type, input_id),
        )


class ReceiptPutInput(BaseModel):
    id: uuid.UUID | None = None
    kind: str = Field(min_length=1)
    plugin: str = Field(min_length=1)
    target: str | None = None
    external_id: str | None = None
    status: str = Field(min_length=1)
    artifact_id: uuid.UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ReceiptPutOutput(BaseModel):
    id: str
    artifact_id: str | None = None
    created_at: DateTime


class ReceiptRecord(BaseModel):
    id: str
    kind: str
    plugin: str
    target: str | None = None
    external_id: str | None = None
    status: str
    artifact_id: str | None = None
    payload: dict[str, Any]
    created_at: DateTime


def _receipt_from_row(row: dict[str, Any]) -> ReceiptRecord:
    data = dict(row)
    data["id"] = str(data["id"])
    if data["artifact_id"] is not None:
        data["artifact_id"] = str(data["artifact_id"])
    return ReceiptRecord.model_validate(data)


def receipt_put(
    input: ReceiptPutInput, *, config: FactsConfig
) -> ReceiptPutOutput:
    receipt_id = input.id or uuid.uuid4()
    with _connect(config) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO goat_memory.receipts (
                  id, kind, plugin, target, external_id, status,
                  artifact_id, payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, artifact_id, created_at
                """,
                (
                    receipt_id,
                    input.kind,
                    input.plugin,
                    input.target,
                    input.external_id,
                    input.status,
                    input.artifact_id,
                    Jsonb(input.payload),
                ),
            )
            row = cur.fetchone()
            assert row is not None
    artifact_id = row["artifact_id"]
    return ReceiptPutOutput(
        id=str(row["id"]),
        artifact_id=str(artifact_id) if artifact_id is not None else None,
        created_at=row["created_at"],
    )


class ReceiptsQueryInput(BaseModel):
    kind: str | None = None
    plugin: str | None = None
    status: str | None = None
    artifact_id: uuid.UUID | None = None
    limit: int = Field(default=100, ge=1, le=10_000)


class ReceiptsQueryOutput(BaseModel):
    receipts: list[ReceiptRecord]


def receipts_query(
    input: ReceiptsQueryInput, *, config: FactsConfig
) -> ReceiptsQueryOutput:
    clauses: list[str] = []
    params: list[Any] = []
    for field in ("kind", "plugin", "status", "artifact_id"):
        value = getattr(input, field)
        if value is not None:
            clauses.append(f"{field} = %s")
            params.append(value)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(input.limit)
    with _connect(config) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT * FROM goat_memory.receipts
                {where}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                params,
            )
            rows = cur.fetchall()
    return ReceiptsQueryOutput(
        receipts=[_receipt_from_row(row) for row in rows]
    )


Severity = Literal["info", "important", "urgent"]
SignalStatus = Literal["active", "dismissed", "snoozed", "done", "expired"]


class SignalRecord(BaseModel):
    id: str
    definition_name: str
    dedupe_key: str
    domain: str
    kind: str
    title: str
    summary: str
    severity: Severity
    status: SignalStatus
    relevant_at: DateTime | None = None
    expires_at: DateTime | None = None
    confidence: float
    generated_by: str
    payload: dict[str, Any]
    schema_version: int
    created_at: DateTime
    updated_at: DateTime


def _signal_from_row(row: dict[str, Any]) -> SignalRecord:
    data = dict(row)
    data["id"] = str(data["id"])
    data["confidence"] = float(data["confidence"])
    return SignalRecord.model_validate(data)


class SignalPutInput(BaseModel):
    id: uuid.UUID | None = None
    definition_name: str = ""
    dedupe_key: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    severity: Severity = "info"
    status: SignalStatus = "active"
    relevant_at: DateTime | None = None
    expires_at: DateTime | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    generated_by: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    schema_version: int = Field(default=1, ge=1)
    fact_ids: list[uuid.UUID] = Field(default_factory=list)


class SignalPutOutput(BaseModel):
    id: str
    created_at: DateTime
    updated_at: DateTime


def signal_put(
    input: SignalPutInput, *, config: FactsConfig
) -> SignalPutOutput:
    signal_id = input.id or uuid.uuid4()
    with _connect(config) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO goat_memory.signals (
                  id, definition_name, dedupe_key, domain, kind, title,
                  summary, severity, status, relevant_at, expires_at,
                  confidence, generated_by, payload, schema_version
                )
                VALUES (
                  %s, %s, %s, %s, %s, %s,
                  %s, %s, %s, %s, %s,
                  %s, %s, %s, %s
                )
                ON CONFLICT (definition_name, dedupe_key)
                DO UPDATE SET
                  domain = EXCLUDED.domain,
                  kind = EXCLUDED.kind,
                  title = EXCLUDED.title,
                  summary = EXCLUDED.summary,
                  severity = EXCLUDED.severity,
                  status = EXCLUDED.status,
                  relevant_at = EXCLUDED.relevant_at,
                  expires_at = EXCLUDED.expires_at,
                  confidence = EXCLUDED.confidence,
                  generated_by = EXCLUDED.generated_by,
                  payload = EXCLUDED.payload,
                  schema_version = EXCLUDED.schema_version,
                  updated_at = now()
                RETURNING id, created_at, updated_at
                """,
                (
                    signal_id,
                    input.definition_name,
                    input.dedupe_key,
                    input.domain,
                    input.kind,
                    input.title,
                    input.summary,
                    input.severity,
                    input.status,
                    input.relevant_at,
                    input.expires_at,
                    input.confidence,
                    input.generated_by,
                    Jsonb(input.payload),
                    input.schema_version,
                ),
            )
            row = cur.fetchone()
            assert row is not None
            cur.execute(
                "DELETE FROM goat_memory.signal_facts WHERE signal_id = %s",
                (row["id"],),
            )
            for fact_id in input.fact_ids:
                cur.execute(
                    """
                    INSERT INTO goat_memory.signal_facts (signal_id, fact_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (row["id"], fact_id),
                )
    return SignalPutOutput(
        id=str(row["id"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SignalsQueryInput(BaseModel):
    domain: str | None = None
    kind: str | None = None
    status: SignalStatus | None = None
    relevant_from: DateTime | None = None
    relevant_until: DateTime | None = None
    limit: int = Field(default=100, ge=1, le=10_000)


class SignalsQueryOutput(BaseModel):
    signals: list[SignalRecord]


def signals_query(
    input: SignalsQueryInput, *, config: FactsConfig
) -> SignalsQueryOutput:
    clauses: list[str] = []
    params: list[Any] = []
    for field in ("domain", "kind", "status"):
        value = getattr(input, field)
        if value is not None:
            clauses.append(f"{field} = %s")
            params.append(value)
    if input.relevant_from is not None:
        clauses.append("(relevant_at IS NULL OR relevant_at >= %s)")
        params.append(input.relevant_from)
    if input.relevant_until is not None:
        clauses.append("(relevant_at IS NULL OR relevant_at < %s)")
        params.append(input.relevant_until)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(input.limit)
    with _connect(config) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT * FROM goat_memory.signals
                {where}
                ORDER BY COALESCE(relevant_at, created_at), created_at
                LIMIT %s
                """,
                params,
            )
            rows = cur.fetchall()
    return SignalsQueryOutput(
        signals=[_signal_from_row(row) for row in rows]
    )


class SignalDismissInput(BaseModel):
    id: uuid.UUID


class SignalDismissOutput(BaseModel):
    id: str
    status: SignalStatus
    updated_at: DateTime


def signal_dismiss(
    input: SignalDismissInput, *, config: FactsConfig
) -> SignalDismissOutput:
    with _connect(config) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE goat_memory.signals
                SET status = 'dismissed', updated_at = now()
                WHERE id = %s
                RETURNING id, status, updated_at
                """,
                (input.id,),
            )
            row = cur.fetchone()
            if row is None:
                raise KeyError(str(input.id))
    return SignalDismissOutput(
        id=str(row["id"]),
        status=row["status"],
        updated_at=row["updated_at"],
    )


class FactDefinitionRecord(BaseModel):
    id: str
    source_plugin: str
    type: str
    domain: str
    title: str
    description: str
    payload_schema: dict[str, Any]
    tags: list[str]
    enabled: bool
    inserted_at: DateTime
    updated_at: DateTime


def _definition_from_row(row: dict[str, Any]) -> FactDefinitionRecord:
    data = dict(row)
    data["id"] = str(data["id"])
    return FactDefinitionRecord.model_validate(data)


class FactDefinitionPutInput(BaseModel):
    id: uuid.UUID | None = None
    source_plugin: str = Field(min_length=1)
    type: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    title: str = ""
    description: str = ""
    payload_schema: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True


class FactDefinitionPutOutput(BaseModel):
    id: str
    inserted_at: DateTime
    updated_at: DateTime


def define(
    input: FactDefinitionPutInput, *, config: FactsConfig
) -> FactDefinitionPutOutput:
    definition_id = input.id or uuid.uuid4()
    with _connect(config) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO goat_memory.fact_definitions (
                  id, source_plugin, type, domain, title, description,
                  payload_schema, tags, enabled
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_plugin, type)
                DO UPDATE SET
                  domain = EXCLUDED.domain,
                  title = EXCLUDED.title,
                  description = EXCLUDED.description,
                  payload_schema = EXCLUDED.payload_schema,
                  tags = EXCLUDED.tags,
                  enabled = EXCLUDED.enabled,
                  updated_at = now()
                RETURNING id, inserted_at, updated_at
                """,
                (
                    definition_id,
                    input.source_plugin,
                    input.type,
                    input.domain,
                    input.title,
                    input.description,
                    Jsonb(input.payload_schema),
                    input.tags,
                    input.enabled,
                ),
            )
            row = cur.fetchone()
            assert row is not None
    return FactDefinitionPutOutput(
        id=str(row["id"]),
        inserted_at=row["inserted_at"],
        updated_at=row["updated_at"],
    )


class FactDefinitionsQueryInput(BaseModel):
    source_plugin: str | None = None
    domain: str | None = None
    type: str | None = None
    enabled: bool | None = None
    limit: int = Field(default=100, ge=1, le=10_000)


class FactDefinitionsQueryOutput(BaseModel):
    definitions: list[FactDefinitionRecord]


def definitions_query(
    input: FactDefinitionsQueryInput, *, config: FactsConfig
) -> FactDefinitionsQueryOutput:
    clauses: list[str] = []
    params: list[Any] = []
    for field in ("source_plugin", "domain", "type", "enabled"):
        value = getattr(input, field)
        if value is not None:
            clauses.append(f"{field} = %s")
            params.append(value)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(input.limit)
    with _connect(config) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT * FROM goat_memory.fact_definitions
                {where}
                ORDER BY source_plugin, type
                LIMIT %s
                """,
                params,
            )
            rows = cur.fetchall()
    return FactDefinitionsQueryOutput(
        definitions=[_definition_from_row(row) for row in rows]
    )


class PersonRecord(BaseModel):
    handle: str
    display_name: str
    tags: list[str]
    payload: dict[str, Any]
    inserted_at: DateTime
    updated_at: DateTime


class PersonPutInput(BaseModel):
    handle: str = Field(min_length=1)
    display_name: str = ""
    tags: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)


class PersonPutOutput(BaseModel):
    handle: str
    inserted_at: DateTime
    updated_at: DateTime


def people_put(
    input: PersonPutInput, *, config: FactsConfig
) -> PersonPutOutput:
    with _connect(config) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO goat_memory.people (
                  handle, display_name, tags, payload
                )
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (handle)
                DO UPDATE SET
                  display_name = EXCLUDED.display_name,
                  tags = EXCLUDED.tags,
                  payload = EXCLUDED.payload,
                  updated_at = now()
                RETURNING handle, inserted_at, updated_at
                """,
                (
                    input.handle,
                    input.display_name,
                    input.tags,
                    Jsonb(input.payload),
                ),
            )
            row = cur.fetchone()
            assert row is not None
    return PersonPutOutput(
        handle=row["handle"],
        inserted_at=row["inserted_at"],
        updated_at=row["updated_at"],
    )


class PeopleQueryInput(BaseModel):
    handle: str | None = None
    limit: int = Field(default=100, ge=1, le=10_000)


class PeopleQueryOutput(BaseModel):
    people: list[PersonRecord]


def people_query(
    input: PeopleQueryInput, *, config: FactsConfig
) -> PeopleQueryOutput:
    clauses: list[str] = []
    params: list[Any] = []
    if input.handle is not None:
        clauses.append("handle = %s")
        params.append(input.handle)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(input.limit)
    with _connect(config) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT * FROM goat_memory.people
                {where}
                ORDER BY handle
                LIMIT %s
                """,
                params,
            )
            rows = cur.fetchall()
    return PeopleQueryOutput(people=[PersonRecord.model_validate(r) for r in rows])
