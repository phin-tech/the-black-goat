from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from the_black_goat import build_registry
from the_black_goat.config import DictConfigSource


class FakeAbsurd:
    """Records spawned tasks so enqueue() works without a real broker/DB."""

    def __init__(self) -> None:
        self.spawns: list[tuple[str, dict]] = []
        self._n = 0

    def register_task(self, name):  # build_registry -> install_runner uses this
        def _decorator(func):
            return func

        return _decorator

    def spawn(self, task_name, params, **kwargs):
        self._n += 1
        self.spawns.append((params["tool"], params["input"]))
        return {"task_id": f"task-{self._n}"}


@pytest.fixture
def ingest():
    import facts_plugin

    from ingest_service import start_ingest_server

    absurd = FakeAbsurd()
    registry = build_registry(
        plugins={"facts": facts_plugin},
        config_source=DictConfigSource(
            {"facts": {"database_url": "postgresql://unused"}}
        ),
        absurd=absurd,
    )
    tokens = {"gann-token": "gann-homework", "other-token": "other-source"}
    server = start_ingest_server(registry, tokens, port=0)
    yield server, absurd
    server.shutdown()


def _post(url, body, token=None):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token is not None:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def _fact(external_id="evt-1", **over):
    base = {
        "domain": "homework",
        "type": "homework.assignment",
        "external_id": external_id,
        "subject": f"gann:{external_id}",
        "title": "Read chapter 3",
        "person": "adam",
        "source_plugin": "SPOOFED",  # must be overridden by the token
    }
    base.update(over)
    return base


def test_healthz(ingest):
    server, _ = ingest
    with urllib.request.urlopen(server.url + "healthz") as resp:
        assert resp.status == 200


def test_missing_token_is_401(ingest):
    server, absurd = ingest
    status, _ = _post(server.url + "ingest/facts", {"facts": [_fact()]})
    assert status == 401
    assert absurd.spawns == []


def test_facts_enqueued_with_forced_source(ingest):
    server, absurd = ingest
    status, body = _post(
        server.url + "ingest/facts",
        {"facts": [_fact("a"), _fact("b")]},
        token="gann-token",
    )
    assert status == 202
    assert body["accepted"] == 2
    assert body["source"] == "gann-homework"
    assert len(absurd.spawns) == 2
    for tool, params in absurd.spawns:
        assert tool == "facts.upsert"
        # token identity wins over whatever the caller sent
        assert params["source_plugin"] == "gann-homework"
        assert params["person"] == "adam"


def test_invalid_fact_rejects_whole_batch(ingest):
    server, absurd = ingest
    bad = _fact("b")
    del bad["domain"]  # domain is required
    status, body = _post(
        server.url + "ingest/facts",
        {"facts": [_fact("a"), bad]},
        token="gann-token",
    )
    assert status == 400
    assert body["error"] == "validation failed"
    assert absurd.spawns == []  # atomic: nothing enqueued


def test_definition_forces_source(ingest):
    server, absurd = ingest
    status, body = _post(
        server.url + "ingest/definitions",
        {
            "type": "homework.assignment",
            "domain": "homework",
            "title": "Gann assignment",
            "source_plugin": "SPOOFED",
        },
        token="gann-token",
    )
    assert status == 202
    tool, params = absurd.spawns[0]
    assert tool == "facts.define"
    assert params["source_plugin"] == "gann-homework"


def test_people_is_not_source_forced(ingest):
    server, absurd = ingest
    status, body = _post(
        server.url + "ingest/people",
        {"handle": "adam", "display_name": "Adam"},
        token="gann-token",
    )
    assert status == 202
    tool, params = absurd.spawns[0]
    assert tool == "facts.people_put"
    assert params["handle"] == "adam"
    assert "source_plugin" not in params  # cross-source, not attributed
