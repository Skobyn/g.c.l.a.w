"""Idempotent Secret Manager seeder for GClaw credentials.

Usage:
    # Dry run (prints what would be created):
    uv run python -m gclaw.migrate.seed_secrets

    # Create secrets with a placeholder value:
    uv run python -m gclaw.migrate.seed_secrets --apply

    # Create + replace values from a local env-style file:
    uv run python -m gclaw.migrate.seed_secrets --apply --values ./my-secrets.env

The values file is simple KEY=value lines matching the canonical names below.
Lines starting with ``#`` and empty lines are ignored. Values ARE sent to
Secret Manager — the file should not be committed to git.

After running, each secret lives at
    projects/{project}/secrets/{name}/versions/latest
and can be referenced from a catalog provider with
    ApiKeySpec(kind=SECRET_MANAGER, value="<full path>")

Rotation flow: edit the secret in the GCP console or push a new value via
this CLI; the catalog's resolve_api_key() fetches the latest version on
each call (no process restart required).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SecretSpec:
    """One canonical secret we manage.

    ``bootstrap`` controls how the runtime loads this secret:
      - "env": set env_alias in the process env (for CLIs that read env vars)
      - "file": write value to /tmp/<bootstrap_path> and set env_alias to that path
                (for CLIs/libs that expect a credentials file)
      - "none": not auto-loaded; consumed directly by CatalogService or similar
    """

    name: str
    description: str
    env_alias: str
    bootstrap: str = "none"             # "env" | "file" | "none"
    bootstrap_path: str = ""            # filename (without /tmp/) when bootstrap="file"


# Canonical list. Add to this as new integrations land — the CLI uses it as
# the source of truth for what should exist.
SECRETS: tuple[SecretSpec, ...] = (
    SecretSpec(
        "gclaw-google-api-key",
        "Gemini API direct (generativelanguage.googleapis.com).",
        "GOOGLE_API_KEY",
    ),
    SecretSpec(
        "gclaw-anthropic-api-key",
        "Anthropic API (Claude Opus/Sonnet/Haiku).",
        "ANTHROPIC_API_KEY",
    ),
    SecretSpec(
        "gclaw-openai-api-key",
        "OpenAI API (GPT-4o, o1, etc).",
        "OPENAI_API_KEY",
    ),
    SecretSpec(
        "gclaw-openrouter-api-key",
        "OpenRouter — gateway to many OSS + commercial models.",
        "OPENROUTER_API_KEY",
    ),
    SecretSpec(
        "gclaw-github-copilot-token",
        "GitHub Copilot subscription token for copilot-api models.",
        "GITHUB_COPILOT_TOKEN",
    ),
    SecretSpec(
        "gclaw-perplexity-api-key",
        "Perplexity — web search + sourced research.",
        "PERPLEXITY_API_KEY",
    ),
    SecretSpec(
        "gclaw-slack-bot-token",
        "Slack bot token (xoxb-…) for comms delivery.",
        "SLACK_BOT_TOKEN",
    ),
    SecretSpec(
        "gclaw-slack-app-token",
        "Slack app-level token (xapp-…) for socket-mode events.",
        "SLACK_APP_TOKEN",
    ),
    SecretSpec(
        "gclaw-discord-bot-token",
        "Discord bot token for comms delivery.",
        "DISCORD_BOT_TOKEN",
    ),
    SecretSpec(
        "gclaw-gh-token",
        "GitHub Personal Access Token used by the gh CLI (dev-mgr agent).",
        "GH_TOKEN",
        bootstrap="env",
    ),
    SecretSpec(
        "gclaw-gws-credentials",
        "Google Workspace credentials JSON for the gws CLI (comms + workspace-mgr).",
        "GOOGLE_WORKSPACE_CREDENTIALS_FILE",
        bootstrap="file",
        bootstrap_path="gws-credentials.json",
    ),
)


DEFAULT_PROJECT = "apex-internal-apps"
PLACEHOLDER_VALUE = "REPLACE_ME"


def sm_path(project: str, name: str, *, version: str = "latest") -> str:
    """Full Secret Manager resource path for a given secret."""
    return f"projects/{project}/secrets/{name}/versions/{version}"


def parse_values_file(path: str) -> dict[str, str]:
    """Parse KEY=value pairs from a simple env-style file."""
    values: dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                logger.warning("values file: line %d has no '=', skipping", lineno)
                continue
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def _resolve_value(
    spec: SecretSpec,
    values: dict[str, str],
    *,
    use_env_fallback: bool,
) -> str | None:
    """Return the value to store for this spec, or None if not provided.

    Lookup order:
      1. values[spec.name]           — canonical name wins
      2. values[spec.env_alias]      — convenience: people write OPENAI_API_KEY=…
      3. env[spec.env_alias]         — only if use_env_fallback is True
    """
    if spec.name in values:
        return values[spec.name]
    if spec.env_alias in values:
        return values[spec.env_alias]
    if use_env_fallback:
        env_val = os.environ.get(spec.env_alias)
        if env_val:
            return env_val
    return None


def _client_and_parent(project: str):
    """Lazy import so tests can stub without installing google-cloud-secret-manager."""
    from google.cloud import secretmanager  # type: ignore

    client = secretmanager.SecretManagerServiceClient()
    parent = f"projects/{project}"
    return client, parent


def _secret_exists(client, project: str, name: str) -> bool:
    try:
        client.get_secret(name=f"projects/{project}/secrets/{name}")
        return True
    except Exception:
        return False


def ensure_secret(client, project: str, spec: SecretSpec) -> bool:
    """Create the secret resource if missing. Returns True when created."""
    if _secret_exists(client, project, spec.name):
        return False
    parent = f"projects/{project}"
    client.create_secret(
        request={
            "parent": parent,
            "secret_id": spec.name,
            "secret": {
                "replication": {"automatic": {}},
                "labels": {"app": "gclaw"},
            },
        }
    )
    return True


def add_version(client, project: str, spec: SecretSpec, value: str) -> str:
    """Add a new version with the given value. Returns the version resource name."""
    parent = f"projects/{project}/secrets/{spec.name}"
    resp = client.add_secret_version(
        request={"parent": parent, "payload": {"data": value.encode("utf-8")}}
    )
    return resp.name


def seed_all(
    *,
    project: str,
    values: dict[str, str],
    apply: bool,
    use_env_fallback: bool,
    placeholder_for_missing: bool,
) -> list[dict]:
    """Ensure every SPEC in SECRETS has a resource + (optionally) a version.

    Returns a plan/result list describing what was done per secret.
    """
    results: list[dict] = []

    if not apply:
        client = None
    else:
        client, _ = _client_and_parent(project)

    for spec in SECRETS:
        entry: dict = {
            "name": spec.name,
            "description": spec.description,
            "path": sm_path(project, spec.name),
            "created": False,
            "version_added": None,
            "value_source": None,
        }
        value = _resolve_value(spec, values, use_env_fallback=use_env_fallback)
        if value is None and placeholder_for_missing:
            value = PLACEHOLDER_VALUE
            entry["value_source"] = "placeholder"
        elif value is not None:
            entry["value_source"] = (
                "values-file" if (spec.name in values or spec.env_alias in values)
                else "env"
            )

        if not apply:
            entry["will_create"] = True
            entry["will_add_version"] = value is not None
            results.append(entry)
            continue

        entry["created"] = ensure_secret(client, project, spec)
        if value is not None:
            entry["version_added"] = add_version(client, project, spec, value)

        results.append(entry)

    return results


def print_plan(results: list[dict], *, apply: bool) -> None:
    print()
    print("Secret Manager plan" if not apply else "Secret Manager result")
    print("─" * 60)
    for r in results:
        verb = (
            ("created" if r["created"] else "exists")
            if apply else ("would create" if r.get("will_create") else "would update")
        )
        v_note = (
            f"+version ({r['value_source']})"
            if (r.get("version_added") or r.get("will_add_version")) else "no-version"
        )
        print(f"  {r['name']:<30}  [{verb}]  {v_note}")
        print(f"    {r['description']}")
        print(f"    path: {r['path']}")
    print()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually create/update secrets in Secret Manager.",
    )
    parser.add_argument(
        "--values",
        help="Path to env-style KEY=value file of secret values.",
    )
    parser.add_argument(
        "--no-env-fallback",
        action="store_true",
        help="Do not read values from env vars when absent from --values.",
    )
    parser.add_argument(
        "--no-placeholder",
        action="store_true",
        help=(
            "Skip adding a REPLACE_ME placeholder version for secrets that "
            "have no real value — leave them version-less so read attempts fail loudly."
        ),
    )
    args = parser.parse_args(argv)

    values = parse_values_file(args.values) if args.values else {}

    results = seed_all(
        project=args.project,
        values=values,
        apply=args.apply,
        use_env_fallback=not args.no_env_fallback,
        placeholder_for_missing=not args.no_placeholder,
    )
    print_plan(results, apply=args.apply)

    if not args.apply:
        print("Dry-run. Re-run with --apply to write.")
        return 0
    print("Done. Reference paths above in your catalog providers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
