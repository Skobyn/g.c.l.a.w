"""OpenAPI spec loader.

Walks paths/operations and returns a flat list of ``OperationDef``
records. Deprecated operations are skipped by default; an explicit
``allowed_operations`` list on ``HttpApiConfig`` whitelists which
operations materialize.

No external validation library — OpenAPI 3.x conformance checking
is the user's responsibility. The loader enforces only what the
builder needs: method, path, parameters (name/location/required),
and an opaque request_body blob passed through for POST shapes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_HTTP_METHODS = {"get", "put", "post", "delete", "patch", "options", "head"}
_SPEC_FETCH_TIMEOUT_SECONDS = 10.0


@dataclass
class Parameter:
    name: str
    location: str  # path | query | header | cookie
    required: bool = False
    schema: dict | None = None


@dataclass
class OperationDef:
    method: str  # uppercase HTTP verb
    path: str
    operation_id: str
    summary: str = ""
    parameters: list[Parameter] = field(default_factory=list)
    request_body: dict | None = None


def load_spec(config: Any, *, http_transport: Any | None = None) -> list[OperationDef]:
    """Load + flatten the OpenAPI spec referenced by ``config``.

    Returns every non-deprecated operation (or the subset whitelisted
    by ``config.allowed_operations``) as an OperationDef. Missing
    operationId is synthesized from method + path so downstream
    identifiers stay stable.
    """
    raw = _resolve_spec(config, http_transport=http_transport)
    paths = raw.get("paths") or {}
    allowed = set(getattr(config, "allowed_operations", None) or [])
    out: list[OperationDef] = []
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        path_level_params = _parse_parameters(path_item.get("parameters") or [])
        for method, op in path_item.items():
            if method.lower() not in _HTTP_METHODS or not isinstance(op, dict):
                continue
            if op.get("deprecated"):
                continue
            op_id = op.get("operationId") or _synth_id(method, path)
            if allowed and op_id not in allowed:
                continue
            parameters = list(path_level_params) + _parse_parameters(
                op.get("parameters") or []
            )
            out.append(
                OperationDef(
                    method=method.upper(),
                    path=path,
                    operation_id=op_id,
                    summary=(op.get("summary") or op.get("description") or "").strip(),
                    parameters=parameters,
                    request_body=op.get("requestBody"),
                )
            )
    return out


def _resolve_spec(config: Any, *, http_transport: Any | None = None) -> dict:
    inline = getattr(config, "spec_inline", None)
    if inline is not None:
        return inline
    url = getattr(config, "spec_url", None)
    if not url:
        raise ValueError("HttpApiConfig has neither spec_inline nor spec_url")
    kwargs = {"timeout": _SPEC_FETCH_TIMEOUT_SECONDS}
    if http_transport is not None:
        kwargs["transport"] = http_transport
    with httpx.Client(**kwargs) as client:
        resp = client.get(url)
        resp.raise_for_status()
    body = resp.text
    if url.endswith(".yaml") or url.endswith(".yml"):
        import yaml

        return yaml.safe_load(body)
    try:
        import json

        return json.loads(body)
    except json.JSONDecodeError:
        import yaml

        return yaml.safe_load(body)


def _parse_parameters(raw_params: list[Any]) -> list[Parameter]:
    out: list[Parameter] = []
    for p in raw_params:
        if not isinstance(p, dict):
            continue
        name = p.get("name")
        loc = p.get("in")
        if not name or not loc:
            continue
        out.append(
            Parameter(
                name=name,
                location=loc,
                required=bool(p.get("required", False)),
                schema=p.get("schema"),
            )
        )
    return out


def _synth_id(method: str, path: str) -> str:
    safe = path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
    return f"{method.lower()}_{safe or 'root'}"
