"""Auth application for the OpenAPI-wrapped HTTP tools.

Given an ``AuthSpec`` variant and a resolved secret value, mutates
the ``httpx`` request kwargs (``headers`` / ``params``) in place so
credentials flow to the upstream service in the shape that variant
describes.

Kept separate from ``tool_builder.py`` so auth behavior is tested
end-to-end as part of the builder tests rather than in isolation here.
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Callable

from gclaw.tools.catalog.models import (
    ApiKeyAuth,
    BasicAuth,
    BearerAuth,
    NoAuth,
    OAuth2BearerAuth,
)

logger = logging.getLogger(__name__)


def apply_auth(
    *,
    auth: Any,
    headers: dict[str, str],
    params: dict[str, Any],
    secret_resolver: Callable[[str], str | None],
) -> None:
    """Mutate headers/params in place per the auth spec."""
    if isinstance(auth, NoAuth) or auth is None:
        return

    if isinstance(auth, ApiKeyAuth):
        value = _safe_resolve(secret_resolver, auth.credential_ref)
        if value is None:
            return
        if auth.location == "header":
            headers[auth.param_name] = value
        else:
            params[auth.param_name] = value
        return

    if isinstance(auth, (BearerAuth, OAuth2BearerAuth)):
        value = _safe_resolve(secret_resolver, auth.credential_ref)
        if value is None:
            return
        headers["Authorization"] = f"Bearer {value}"
        return

    if isinstance(auth, BasicAuth):
        value = _safe_resolve(secret_resolver, auth.credential_ref)
        if value is None:
            return
        encoded = base64.b64encode(value.encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {encoded}"
        return


def _safe_resolve(resolver: Callable[[str], str | None], ref: str) -> str | None:
    try:
        return resolver(ref)
    except Exception:
        logger.warning(
            "openapi_auth: secret resolver failed for %s", ref, exc_info=True
        )
        return None
