from __future__ import annotations

import argparse
import json
import os
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping

from pydantic import ValidationError

from the_black_goat import Registry

FACTS_TOOL = "facts.upsert"
RECEIPT_TOOL = "facts.receipt_put"
DEFINE_TOOL = "facts.define"
PEOPLE_TOOL = "facts.people_put"


@dataclass(frozen=True)
class IngestServer:
    httpd: ThreadingHTTPServer
    thread: threading.Thread
    url: str

    def shutdown(self) -> None:
        self.httpd.shutdown()
        self.thread.join(timeout=2)
        self.httpd.server_close()


def _resolve_source(tokens: Mapping[str, str], header: str | None) -> str | None:
    """Map an ``Authorization: Bearer <token>`` header to a source_plugin."""
    if not header:
        return None
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return tokens.get(parts[1])


def start_ingest_server(
    registry: Registry,
    tokens: Mapping[str, str],
    *,
    host: str = "127.0.0.1",
    port: int = 8788,
) -> IngestServer:
    """Start the ingest HTTP edge.

    ``tokens`` maps bearer token -> source_plugin. Every write forces that
    source_plugin onto the payload, so a caller can never write as another
    source. Facts/receipts/definitions are enqueued as absurd tasks (the
    registry must be built with ``absurd=``); a worker performs the upserts.
    """
    tokens = dict(tokens)
    facts_input = registry.get(FACTS_TOOL).input_schema
    receipt_input = registry.get(RECEIPT_TOOL).input_schema
    define_input = registry.get(DEFINE_TOOL).input_schema
    people_input = registry.get(PEOPLE_TOOL).input_schema

    class _Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, obj: dict) -> None:
            body = json.dumps(obj, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/healthz":
                self._send(200, {"status": "ok"})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:
            source = _resolve_source(tokens, self.headers.get("Authorization"))
            if source is None:
                self._send(401, {"error": "invalid or missing token"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length).decode() if length else ""
                payload = json.loads(raw or "{}")
            except (ValueError, json.JSONDecodeError) as exc:
                self._send(400, {"error": f"bad json: {exc}"})
                return
            if not isinstance(payload, dict):
                self._send(400, {"error": "body must be a JSON object"})
                return

            if self.path == "/ingest/facts":
                self._ingest_facts(source, payload)
            elif self.path == "/ingest/receipt":
                self._ingest_one(source, payload, receipt_input, RECEIPT_TOOL, "plugin")
            elif self.path == "/ingest/definitions":
                self._ingest_one(source, payload, define_input, DEFINE_TOOL, "source_plugin")
            elif self.path == "/ingest/people":
                # People are a shared, cross-source namespace: authenticated by a
                # valid token, but not attributed/forced to one source.
                self._ingest_one(source, payload, people_input, PEOPLE_TOOL, None)
            else:
                self._send(404, {"error": "not found"})

        def _ingest_facts(self, source: str, payload: dict) -> None:
            items = payload.get("facts")
            if not isinstance(items, list) or not items:
                self._send(400, {"error": "body must contain a non-empty 'facts' list"})
                return
            # Validate the whole batch first so acceptance is all-or-nothing.
            validated: list[dict] = []
            errors: list[dict] = []
            for i, item in enumerate(items):
                if not isinstance(item, dict):
                    errors.append({"index": i, "error": "fact must be an object"})
                    continue
                forced = {**item, "source_plugin": source}
                try:
                    facts_input.model_validate(forced)
                except ValidationError as exc:
                    errors.append({"index": i, "error": exc.errors(include_url=False)})
                    continue
                validated.append(forced)
            if errors:
                self._send(400, {"error": "validation failed", "details": errors})
                return
            task_ids = [registry.enqueue(FACTS_TOOL, f) for f in validated]
            self._send(
                202,
                {"accepted": len(task_ids), "task_ids": task_ids, "source": source},
            )

        def _ingest_one(
            self,
            source: str,
            payload: dict,
            schema,
            tool: str,
            source_field: str | None,
        ) -> None:
            # source_field=None => shared namespace (e.g. people): authenticated
            # but not attributed to one source.
            forced = payload if source_field is None else {**payload, source_field: source}
            try:
                schema.model_validate(forced)
            except ValidationError as exc:
                self._send(
                    400,
                    {"error": "validation failed", "details": exc.errors(include_url=False)},
                )
                return
            task_id = registry.enqueue(tool, forced)
            self._send(202, {"accepted": 1, "task_id": task_id, "source": source})

        def log_message(self, format: str, *args) -> None:
            return

    httpd = ThreadingHTTPServer((host, port), _Handler)
    assigned_port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return IngestServer(
        httpd=httpd,
        thread=thread,
        url=f"http://{host}:{assigned_port}/",
    )


def _load_tokens(raw: str | None) -> dict[str, str]:
    """Parse INGEST_TOKENS (JSON object: token -> source_plugin)."""
    if not raw:
        raise SystemExit("INGEST_TOKENS is required (JSON object: token -> source)")
    tokens = json.loads(raw)
    if not isinstance(tokens, dict) or not tokens:
        raise SystemExit("INGEST_TOKENS must be a non-empty JSON object")
    return {str(k): str(v) for k, v in tokens.items()}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run The Black Goat ingest edge.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8788)
    args = parser.parse_args(argv)

    from absurd_sdk import Absurd

    import facts_plugin
    from the_black_goat import build_registry
    from the_black_goat.config import EnvConfigSource

    db_url = os.environ.get("ABSURD_DATABASE_URL")
    if not db_url:
        raise SystemExit("ABSURD_DATABASE_URL is required")
    absurd = Absurd(db_url, queue_name=os.environ.get("GOAT_QUEUE", "default"))
    registry = build_registry(
        plugins={"facts": facts_plugin},
        config_source=EnvConfigSource(),
        absurd=absurd,
    )
    tokens = _load_tokens(os.environ.get("INGEST_TOKENS"))

    server = start_ingest_server(
        registry, tokens, host=args.host, port=args.port
    )
    print(f"the-black-goat-ingest listening at {server.url}")
    try:
        server.thread.join()
    except KeyboardInterrupt:
        server.shutdown()
