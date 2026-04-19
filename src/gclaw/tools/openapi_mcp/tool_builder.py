"""Build an ADK-ready async callable from one OperationDef.

The returned function accepts the operation's parameters as kwargs:
path params get template-substituted; query / header params get
routed to their respective httpx arguments; a ``body`` kwarg (JSON-
serializable object) becomes the request body for POST/PUT/PATCH.

Failures surface as structured strings so the LLM has something to
reason about. Response bodies are capped at 16 KB with a truncation
marker; the upstream HTTP status line is always included in the
returned text.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

import httpx

from gclaw.tools.openapi_mcp.auth import apply_auth
from gclaw.tools.openapi_mcp.loader import OperationDef

logger = logging.getLogger(__name__)

_RESPONSE_CAP_BYTES = 16 * 1024
_HTTP_TIMEOUT_SECONDS = 30.0


def build_tool(
    op: OperationDef,
    *,
    auth: Any,
    base_url: str,
    secret_resolver: Callable[[str], str | None],
    http_transport: Any | None = None,
) -> Callable[..., Any]:
    """Return an async callable wrapping ``op`` as an ADK tool."""

    async def _call(**kwargs: Any) -> str:
        return await _invoke(
            op=op,
            auth=auth,
            base_url=base_url,
            secret_resolver=secret_resolver,
            http_transport=http_transport,
            kwargs=kwargs,
        )

    # Name + docstring surface through ADK's FunctionTool wrapping so
    # the model sees the operation_id and summary the way catalog
    # authors labeled them.
    _call.__name__ = op.operation_id
    _call.__doc__ = op.summary or f"{op.method} {op.path}"
    return _call


async def _invoke(
    *,
    op: OperationDef,
    auth: Any,
    base_url: str,
    secret_resolver: Callable[[str], str | None],
    http_transport: Any | None,
    kwargs: dict[str, Any],
) -> str:
    # Split incoming kwargs by location.
    params_by_loc: dict[str, dict[str, Any]] = {
        "path": {},
        "query": {},
        "header": {},
    }
    for p in op.parameters:
        if p.name not in kwargs:
            if p.required:
                return (
                    f"openapi-tool error: missing required parameter "
                    f"{p.name!r} (location={p.location})"
                )
            continue
        params_by_loc.setdefault(p.location, {})[p.name] = kwargs.pop(p.name)

    # Path interpolation.
    try:
        url_path = op.path.format(**params_by_loc["path"])
    except KeyError as e:
        return f"openapi-tool error: path template missing value for {{{e.args[0]}}}"

    body = kwargs.pop("body", None)

    headers: dict[str, str] = dict(params_by_loc["header"])
    query: dict[str, Any] = dict(params_by_loc["query"])
    apply_auth(
        auth=auth,
        headers=headers,
        params=query,
        secret_resolver=secret_resolver,
    )

    request_kwargs: dict[str, Any] = {"params": query or None, "headers": headers or None}
    if body is not None:
        request_kwargs["json"] = body

    url = base_url.rstrip("/") + url_path
    client_kwargs: dict[str, Any] = {"timeout": _HTTP_TIMEOUT_SECONDS}
    if http_transport is not None:
        client_kwargs["transport"] = http_transport

    async with httpx.AsyncClient(**client_kwargs) as client:
        try:
            resp = await client.request(op.method, url, **request_kwargs)
        except Exception as e:
            return f"openapi-tool error: HTTP call failed: {e}"

    return _render_response(resp)


def _render_response(resp: httpx.Response) -> str:
    status_line = f"HTTP {resp.status_code}"
    try:
        parsed = resp.json()
        body_text = json.dumps(parsed, indent=2)
    except Exception:
        body_text = resp.text

    if resp.status_code >= 400:
        trimmed = body_text[:_RESPONSE_CAP_BYTES]
        return f"{status_line}: {trimmed}"

    if len(body_text) <= _RESPONSE_CAP_BYTES:
        return f"{status_line}\n{body_text}"

    head = body_text[: _RESPONSE_CAP_BYTES // 2]
    tail = body_text[-(_RESPONSE_CAP_BYTES // 2) :]
    return f"{status_line}\n{head}\n… (truncated from {len(body_text)} chars)\n{tail}"
