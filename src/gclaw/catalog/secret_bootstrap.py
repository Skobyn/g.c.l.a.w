"""Bootstrap Secret Manager-backed runtime credentials.

Some of GClaw's dependencies (the ``gh`` CLI, the ``gws`` CLI, plus any
third-party SDK that reads only from env vars or credential files) can't
be taught to call ``CatalogService.resolve_api_key`` directly. For those,
we read the secret at startup and either:

  - set an env var in this process (``bootstrap="env"``), or
  - write the value to a tmp file and point an env var at it (``bootstrap="file"``).

This module is intentionally small, fail-open, and only touches secrets whose
``SecretSpec.bootstrap != "none"``. Anything a service resolves via
CatalogService on demand is left alone.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from gclaw.migrate.seed_secrets import SECRETS, SecretSpec, _prefixed, sm_path

logger = logging.getLogger(__name__)

# /tmp is the only reliably writable location on Cloud Run.
TMP_DIR = Path("/tmp")


def _fetch_secret(project: str, spec: SecretSpec) -> str | None:
    """Return the latest version's value for ``spec``, or None on any failure."""
    full = _prefixed(spec.name)
    try:
        from google.cloud import secretmanager  # type: ignore

        client = secretmanager.SecretManagerServiceClient()
        resp = client.access_secret_version(name=sm_path(project, full))
        return resp.payload.data.decode("utf-8")
    except Exception as exc:
        logger.info(
            "secret-bootstrap: %s not loaded (%s)", full, exc.__class__.__name__
        )
        return None


def bootstrap_secrets(
    *,
    project: str,
    tmp_dir: Path = TMP_DIR,
    specs: tuple[SecretSpec, ...] = SECRETS,
) -> dict:
    """Apply env + file bootstraps for every spec whose ``bootstrap`` != "none".

    Returns a summary dict with counts + per-spec outcomes. Never raises — a
    missing secret just means that integration won't work until the user rotates
    the key, and that's the caller's problem to surface, not ours.
    """
    applied: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []

    for spec in specs:
        if spec.bootstrap == "none":
            continue

        full = _prefixed(spec.name)
        value = _fetch_secret(project, spec)
        if value is None:
            skipped.append(full)
            continue

        try:
            if spec.bootstrap == "env":
                os.environ[spec.env_alias] = value
                applied.append(f"{full}→env:{spec.env_alias}")

            elif spec.bootstrap == "file":
                if not spec.bootstrap_path:
                    raise ValueError(f"{full} bootstrap=file but no bootstrap_path")
                tmp_dir.mkdir(parents=True, exist_ok=True)
                target = tmp_dir / spec.bootstrap_path
                # Write with 0600 so only this process/user can read.
                fd = os.open(
                    str(target),
                    os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                    0o600,
                )
                try:
                    os.write(fd, value.encode("utf-8"))
                finally:
                    os.close(fd)
                os.environ[spec.env_alias] = str(target)
                applied.append(f"{full}→file:{target}")

            else:
                logger.warning(
                    "secret-bootstrap: unknown bootstrap mode %r for %s",
                    spec.bootstrap,
                    full,
                )
                failed.append(full)

        except Exception as exc:
            logger.warning(
                "secret-bootstrap: failed to apply %s (%s)",
                full,
                exc,
            )
            failed.append(full)

    logger.info(
        "secret-bootstrap: applied=%d skipped=%d failed=%d",
        len(applied),
        len(skipped),
        len(failed),
    )
    return {
        "applied": applied,
        "skipped": skipped,
        "failed": failed,
    }
