from __future__ import annotations

from the_black_goat import ToolDef, hookimpl, tool

from facts_plugin import tools as _tools


def _tool(name, func, input_schema, output_schema, *, side_effect, tags):
    return tool(
        name=name,
        func=func,
        input=input_schema,
        output=output_schema,
        config=_tools.FactsConfig,
        is_idempotent=side_effect == "reads_external",
        side_effect=side_effect,
        tags=tags,
    )


_UPSERT = _tool(
    "upsert",
    _tools.upsert,
    _tools.FactUpsertInput,
    _tools.FactUpsertOutput,
    side_effect="writes_external",
    tags=("facts", "memory"),
)

_GET = _tool(
    "get",
    _tools.get,
    _tools.FactGetInput,
    _tools.FactGetOutput,
    side_effect="reads_external",
    tags=("facts", "memory"),
)

_QUERY = _tool(
    "query",
    _tools.query,
    _tools.FactQueryInput,
    _tools.FactQueryOutput,
    side_effect="reads_external",
    tags=("facts", "memory"),
)

_STATE_GET = _tool(
    "state_get",
    _tools.state_get,
    _tools.StateGetInput,
    _tools.StateGetOutput,
    side_effect="reads_external",
    tags=("state", "memory"),
)

_STATE_PUT = _tool(
    "state_put",
    _tools.state_put,
    _tools.StatePutInput,
    _tools.StatePutOutput,
    side_effect="writes_external",
    tags=("state", "memory"),
)

_ARTIFACT_PUT = _tool(
    "artifact_put",
    _tools.artifact_put,
    _tools.ArtifactPutInput,
    _tools.ArtifactPutOutput,
    side_effect="writes_external",
    tags=("artifacts", "memory"),
)

_ARTIFACT_GET = _tool(
    "artifact_get",
    _tools.artifact_get,
    _tools.ArtifactGetInput,
    _tools.ArtifactGetOutput,
    side_effect="reads_external",
    tags=("artifacts", "memory"),
)

_ARTIFACTS_QUERY = _tool(
    "artifacts_query",
    _tools.artifacts_query,
    _tools.ArtifactsQueryInput,
    _tools.ArtifactsQueryOutput,
    side_effect="reads_external",
    tags=("artifacts", "memory"),
)

_RECEIPT_PUT = _tool(
    "receipt_put",
    _tools.receipt_put,
    _tools.ReceiptPutInput,
    _tools.ReceiptPutOutput,
    side_effect="writes_external",
    tags=("receipts", "memory"),
)

_RECEIPTS_QUERY = _tool(
    "receipts_query",
    _tools.receipts_query,
    _tools.ReceiptsQueryInput,
    _tools.ReceiptsQueryOutput,
    side_effect="reads_external",
    tags=("receipts", "memory"),
)

_SIGNAL_PUT = _tool(
    "signal_put",
    _tools.signal_put,
    _tools.SignalPutInput,
    _tools.SignalPutOutput,
    side_effect="writes_external",
    tags=("signals", "memory"),
)

_SIGNALS_QUERY = _tool(
    "signals_query",
    _tools.signals_query,
    _tools.SignalsQueryInput,
    _tools.SignalsQueryOutput,
    side_effect="reads_external",
    tags=("signals", "memory"),
)

_SIGNAL_DISMISS = _tool(
    "signal_dismiss",
    _tools.signal_dismiss,
    _tools.SignalDismissInput,
    _tools.SignalDismissOutput,
    side_effect="writes_external",
    tags=("signals", "memory"),
)


@hookimpl
def goat_register_tools() -> list[ToolDef]:
    return [
        _UPSERT,
        _GET,
        _QUERY,
        _STATE_GET,
        _STATE_PUT,
        _ARTIFACT_PUT,
        _ARTIFACT_GET,
        _ARTIFACTS_QUERY,
        _RECEIPT_PUT,
        _RECEIPTS_QUERY,
        _SIGNAL_PUT,
        _SIGNALS_QUERY,
        _SIGNAL_DISMISS,
    ]
