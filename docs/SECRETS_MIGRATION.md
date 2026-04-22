# Secret Manager naming and migration

GClaw stores third-party API keys (Gemini, Anthropic, OpenAI,
OpenRouter, GitHub, Postiz, Slack, etc.) in Google Cloud Secret
Manager. Each secret has a name like `<prefix>-<purpose>` — for
example `watson-openai-api-key`. This doc covers:

1. Why the prefix exists.
2. How to change it for your fork.
3. How to migrate live secrets when you change it.

## Why the prefix

Secret Manager is per-project. Many secrets in your project belong
to other apps (Cloud Build, Cloud SQL, your own scripts). The
prefix lets GClaw:

- Filter the admin UI's secret list to only its own secrets.
- Bootstrap only its own secrets at startup (won't clobber unrelated
  env vars).
- Auto-name new secrets created from the admin UI.

The default prefix is `watson-` for historical reasons (the
maintainer's original orchestrator alias). For a public fork you'll
want to choose a prefix matching your own project — the recommended
default for a clean install is `gclaw-`.

## Changing the prefix in code

The prefix is read once at module load from the `SECRET_NAME_PREFIX`
env var, falling back to `watson-`:

```python
# src/gclaw/catalog/secret_manager.py
_NAME_PREFIX = os.environ.get("SECRET_NAME_PREFIX", "watson-")
```

Set the env var in your deployment to override:

```yaml
# cloudbuild.yaml --set-env-vars
SECRET_NAME_PREFIX=gclaw-
```

Or in your local `.env`:

```bash
SECRET_NAME_PREFIX=gclaw-
```

This affects:

- `SecretManagerService.normalize_name` — auto-prepends the prefix
  to user-supplied names in the admin UI.
- `SecretManagerService.list_gclaw_secrets` — filters listings.

Two places **don't yet read the env var** (deferred to keep this
change small):

1. **`src/gclaw/migrate/seed_secrets.py`** — the canonical SECRETS
   list still hardcodes `watson-*` names. Forks running the seeder
   today will create `watson-*` resources regardless of
   `SECRET_NAME_PREFIX`. Fix in a follow-up: build names dynamically
   from the prefix + base.
2. **`web/src/components/admin/models/provider-form.tsx`** — the
   regex `^watson-[a-z0-9-]+$` and the auto-naming helper hardcode
   `watson-`. Forks would need to either patch the regex or accept
   that admin UI validation rejects non-`watson-*` names.

These are tracked as the next iteration of this work. Until then,
forks have two practical paths:

- **Stay on `watson-`** — accept the default; nothing to do.
- **Patch in your overlay** — fork `seed_secrets.py` and the
  provider form to use your prefix; keep the patch in your private
  overlay (see `docs/OVERLAY.md`).

## Migrating live secrets between prefixes

Changing the prefix without touching live Secret Manager would
break production: bootstrap would fail to read `gclaw-gemini-api-key`
when only `watson-gemini-api-key` exists. The migration is a
coordinated three-step:

### Step 1 — Create the new secrets alongside the old

```bash
# Pull each existing secret value, write it under the new name.
OLD=watson; NEW=gclaw
for short in \
    gemini-api-key anthropic-api-key openai-api-key openrouter-api-key \
    github-copilot-token perplexity-api-key slack-bot-token \
    slack-app-token discord-token postiz-token gh-token gws-credentials; do
  value=$(gcloud secrets versions access latest \
    --secret="${OLD}-${short}" --project=<your-project>)
  printf '%s' "$value" | gcloud secrets create "${NEW}-${short}" \
    --replication-policy=automatic --data-file=- --project=<your-project>
done
```

(`gws-credentials` is a JSON file, not a string — check carefully.)

Don't delete the old secrets yet.

### Step 2 — Switch the runtime to the new prefix

Update `cloudbuild.yaml` (or your equivalent) to set
`SECRET_NAME_PREFIX=gclaw-` and redeploy. The `secret_manager.py`
listing + admin UI now use the new prefix. Bootstrap (which goes
through `seed_secrets.py`) still references `watson-*` names until
you complete the seeder follow-up.

For a complete cutover, also patch `seed_secrets.py` in your
overlay so the SECRETS tuple reads `f"{prefix}{base}"` instead of
hardcoded `watson-` literals.

Verify:

```bash
gcloud run services logs read gclaw --region=<region> --project=<your-project> | \
  grep -E '(secret-bootstrap|missing key)'
# Expect: applied=N skipped=0 failed=0
```

### Step 3 — Delete the old secrets

After you've verified the deployment works on the new prefix for at
least one full session (chat + content pipeline + dev pipeline),
delete the old resources:

```bash
for short in \
    gemini-api-key anthropic-api-key openai-api-key openrouter-api-key \
    github-copilot-token perplexity-api-key slack-bot-token \
    slack-app-token discord-token postiz-token gh-token gws-credentials; do
  gcloud secrets delete "${OLD}-${short}" --project=<your-project> --quiet
done
```

If anything still references the old names (forgot a hardcoded
literal somewhere) you'll find out here — the deploy will silently
lose access to that secret. Roll back by recreating from the new
secret's latest version.

## Why this is deferred from the public-release scrub

The full rename touches live Secret Manager resources in the
upstream maintainer's `apex-internal-apps` deployment. Running it
without coordination would silently break the production agents.

This PR therefore:

- Makes `secret_manager.py` respect `SECRET_NAME_PREFIX`.
- Documents the migration recipe (this file).
- Leaves `seed_secrets.py` and the admin-UI form unchanged so the
  upstream deployment continues to work without an env var update.

A later PR can complete the rename once the maintainer has done
Step 1 in their own project.
