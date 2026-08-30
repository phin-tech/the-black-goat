# the-black-goat-ingest

Token-authenticated HTTP edge that lets external **source apps push into the
fact store**. The Goat no longer reaches out and pulls; sources (e.g.
gann-homework) POST their observations here, and a worker upserts them.

## Model

- A **source** is authenticated by a bearer token. `INGEST_TOKENS` maps
  `token -> source_plugin`. The server **forces** that `source_plugin` onto
  every fact/receipt/definition, so a caller can never write as another source.
- Writes are **enqueued as absurd tasks** (`facts.upsert`, `facts.receipt_put`,
  `facts.define`, `facts.people_put`); a `goat_run_tool` worker performs the
  actual DB upsert. The endpoint returns `202` with task ids.
- **People are cross-source** — `POST /ingest/people` is authenticated but not
  attributed to one source, because "adam" is the same person whether the fact
  came from homework or calendar.

## Endpoints

```
GET  /healthz
POST /ingest/facts        { "facts": [ {domain, type, external_id, subject, person?, ...}, ... ] }
POST /ingest/receipt      { "kind": "sync", "status": "ok", "payload": {...} }
POST /ingest/definitions  { "type": "homework.assignment", "domain": "homework", "title": ..., "payload_schema": {...} }
POST /ingest/people       { "handle": "adam", "display_name": "Adam", "tags": [...] }
```

All POSTs require `Authorization: Bearer <token>`. `/ingest/facts` validates the
whole batch first: any invalid fact rejects the batch with `400` and none are
enqueued. Fact definitions are **metadata only** — they are stored for
discovery/labels, and do not gate `/ingest/facts`.

## Run

```sh
ABSURD_DATABASE_URL=postgresql://absurd:absurd@localhost:5432/absurd \
FACTS_DATABASE_URL=postgresql://absurd:absurd@localhost:5432/absurd \
INGEST_TOKENS='{"gann-secret-token": "gann-homework"}' \
the-black-goat-ingest --host 0.0.0.0 --port 8788
```

A separate absurd worker process drains the enqueued `goat_run_tool` tasks.
