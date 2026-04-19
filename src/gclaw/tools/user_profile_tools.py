"""Read/write tools for the shared user profile (`user.md`).

The profile-mgr uses these to run onboarding and accept explicit
"update my profile" requests. The orchestrator binds the read tool so
it can answer "what do you know about me?" directly from the file
(redundant with the injected `About the User` section, but gives the
model a way to double-check when the user asks).

Tools return strings and never raise into the ADK invocation path —
same convention as ``context_tools`` / ``comms_tools``.
"""

from __future__ import annotations

import logging
import os

from gclaw.config.loader import ConfigLoader

logger = logging.getLogger(__name__)

# Module-level holder; main.py calls set_config_loader(loader) once
# during startup. Mirrors the pattern used by context_tools.
_loader: ConfigLoader | None = None


def set_config_loader(loader: ConfigLoader | None) -> None:
    global _loader
    _loader = loader


def _require() -> ConfigLoader:
    if _loader is None:
        raise RuntimeError("user-profile tools: config loader not configured")
    return _loader


def _err(verb: str, exc: Exception) -> str:
    logger.warning("user_profile_%s failed: %s", verb, exc)
    return f"user_profile_{verb} failed: {exc}"


async def read_user_profile() -> str:
    """Return the current `user.md` content.

    Use this before ``update_user_profile`` so you don't clobber
    sections the user didn't ask to change.

    Returns:
        The markdown body, or a short note if the profile is blank.
    """
    try:
        content = _require().load_user_profile()
    except Exception as e:
        return _err("read", e)
    if not content:
        return (
            "(user.md is blank — no profile yet. Start an onboarding "
            "conversation to populate it, then call update_user_profile "
            "with the full markdown body.)"
        )
    return content


async def update_user_profile(content: str) -> str:
    """Overwrite `user.md` with new markdown.

    This replaces the file wholesale — pass the *complete* profile
    body, not a diff. Always call ``read_user_profile`` first so you
    can preserve existing sections the user did not ask to change.

    Only call this after the user has explicitly confirmed the change.

    Args:
        content: The full markdown body to persist as the user profile.

    Returns:
        A short confirmation with the byte count written.
    """
    try:
        loader = _require()
        path = loader.user_profile_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        body = content if content is not None else ""
        with open(path, "w") as f:
            f.write(body)
    except Exception as e:
        return _err("update", e)
    return f"user.md updated ({len(body)} bytes)."
