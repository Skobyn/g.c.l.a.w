#!/usr/bin/env bash
#
# seed-secrets.sh — populate Google Secret Manager with the canonical
# gclaw secrets, either interactively or from a values file.
#
# Wraps `gclaw.migrate.seed_secrets` so you don't have to remember the
# CLI flags. The seeder creates one Secret Manager resource per
# canonical secret name (gemini-api-key, anthropic-api-key, openai-api-key,
# openrouter-api-key, github-copilot-token, perplexity-api-key,
# slack-bot-token, slack-app-token, discord-token, postiz-token,
# gh-token, gws-credentials).
#
# Three usage modes:
#
#   1. Dry-run plan (default):
#        ./scripts/seed-secrets.sh <PROJECT_ID>
#
#   2. From a values file (KEY=value lines):
#        ./scripts/seed-secrets.sh <PROJECT_ID> --apply --values ./my-secrets.env
#
#   3. From shell env vars (uses any *_API_KEY / *_TOKEN you've exported):
#        export OPENAI_API_KEY=sk-...
#        export ANTHROPIC_API_KEY=sk-ant-...
#        ./scripts/seed-secrets.sh <PROJECT_ID> --apply
#
# To leave a secret without a value (so reads fail loudly until you
# rotate), pass --no-placeholder.
#
# Note: secret names use the `watson-` prefix by default (the upstream
# maintainer's legacy convention). Override with SECRET_NAME_PREFIX env
# var or see docs/SECRETS_MIGRATION.md to migrate to a different prefix.

set -euo pipefail

PROJECT_ID="${1:?Usage: $0 <PROJECT_ID> [--apply] [--values FILE] [--no-placeholder]}"
shift

cd "$(dirname "$0")/.."

# Pass everything after PROJECT_ID through to the python CLI.
exec uv run python -m gclaw.migrate.seed_secrets \
  --project "${PROJECT_ID}" "$@"
