"""GClaw migration utilities.

Houses one-off setup scripts that aren't part of the request-serving
runtime — currently the Secret Manager seeder invoked out-of-band by
``uv run python -m gclaw.migrate.seed_secrets``.
"""
