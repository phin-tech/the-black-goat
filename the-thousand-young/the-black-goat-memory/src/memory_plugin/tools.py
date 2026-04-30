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
