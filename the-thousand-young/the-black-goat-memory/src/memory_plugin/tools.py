from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from psycopg import Connection
from pydantic import BaseModel, Field, SecretStr


class MemoryConfig(BaseModel):
    database_url: SecretStr  # env: MEMORY_DATABASE_URL


# ---------- put ----------


class MemoryPutInput(BaseModel):
    namespace: str = Field(min_length=1)
    key: str = Field(min_length=1)
    value: dict[str, Any]


class MemoryPutOutput(BaseModel):
    written_at: datetime


def put(input: MemoryPutInput, *, config: MemoryConfig) -> MemoryPutOutput:
    """Upsert (namespace, key) -> value, returning the server's written_at."""
    with Connection.connect(
        config.database_url.get_secret_value(), autocommit=True
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO goat_memory.kv (namespace, key, value, written_at)
                VALUES (%s, %s, %s::jsonb, now())
                ON CONFLICT (namespace, key) DO UPDATE
                  SET value = EXCLUDED.value,
                      written_at = now()
                RETURNING written_at;
                """,
                (input.namespace, input.key, json.dumps(input.value)),
            )
            row = cur.fetchone()
            assert row is not None  # RETURNING always yields a row on success
            (written_at,) = row
    return MemoryPutOutput(written_at=written_at)


# ---------- get ----------


class MemoryGetInput(BaseModel):
    namespace: str = Field(min_length=1)
    key: str = Field(min_length=1)


class MemoryGetOutput(BaseModel):
    value: dict[str, Any] | None = None
    written_at: datetime | None = None


def get(input: MemoryGetInput, *, config: MemoryConfig) -> MemoryGetOutput:
    """Read a value or return (None, None) if absent."""
    with Connection.connect(config.database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT value, written_at FROM goat_memory.kv "
                "WHERE namespace = %s AND key = %s",
                (input.namespace, input.key),
            )
            row = cur.fetchone()
    if row is None:
        return MemoryGetOutput()
    value, written_at = row
    return MemoryGetOutput(value=value, written_at=written_at)


# ---------- list ----------


class MemoryListInput(BaseModel):
    namespace: str = Field(min_length=1)
    since: datetime | None = None
    limit: int = Field(default=100, ge=1, le=10_000)


class MemoryListItem(BaseModel):
    key: str
    value: dict[str, Any]
    written_at: datetime


class MemoryListOutput(BaseModel):
    items: list[MemoryListItem]


def list_(input: MemoryListInput, *, config: MemoryConfig) -> MemoryListOutput:
    """Most-recent-first listing within a namespace, optionally since a cutoff."""
    with Connection.connect(config.database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            if input.since is None:
                cur.execute(
                    "SELECT key, value, written_at FROM goat_memory.kv "
                    "WHERE namespace = %s "
                    "ORDER BY written_at DESC "
                    "LIMIT %s",
                    (input.namespace, input.limit),
                )
            else:
                cur.execute(
                    "SELECT key, value, written_at FROM goat_memory.kv "
                    "WHERE namespace = %s AND written_at >= %s "
                    "ORDER BY written_at DESC "
                    "LIMIT %s",
                    (input.namespace, input.since, input.limit),
                )
            rows = cur.fetchall()
    items = [
        MemoryListItem(key=k, value=v, written_at=w) for (k, v, w) in rows
    ]
    return MemoryListOutput(items=items)
