# the-black-goat-memory

A Postgres-backed key/value memory plugin for `the-black-goat`. One table
(`goat_memory.kv`), three tools:

- `memory.put(namespace, key, value)` — upsert.
- `memory.get(namespace, key)` — read or `(None, None)`.
- `memory.list(namespace, since=, limit=)` — most-recent-first.

Schema lives at `db/memory.sql` (repo root) and is auto-applied to a fresh
Postgres container by the `compose.yml` init mount, or applied to a running
container with `task memory:init`.

Config: `MEMORY_DATABASE_URL` (env), e.g.
`postgresql://absurd:absurd@localhost:5432/absurd`.
