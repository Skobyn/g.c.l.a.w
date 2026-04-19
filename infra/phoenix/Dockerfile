# syntax=docker/dockerfile:1.7
#
# Arize Phoenix — OTLP trace sink for gclaw observability.
#
# Phoenix is published as arizephoenix/phoenix on Docker Hub. The base
# image already bundles the Phoenix server, its web UI, and the HTTP +
# gRPC OTLP receivers. This Dockerfile just wraps it with the Cloud Run
# runtime envs we want.
#
# Port contract (Cloud Run supports ONE port): Phoenix serves the UI AND
# the HTTP OTLP endpoint (POST /v1/traces) on PHOENIX_PORT. gRPC OTLP is
# disabled because Cloud Run wouldn't route it alongside HTTP.
#
# Pin a specific digest before the first production rollout:
#   docker pull arizephoenix/phoenix:version-8.0.0
#   docker inspect --format='{{index .RepoDigests 0}}' arizephoenix/phoenix:version-8.0.0
#   -> arizephoenix/phoenix@sha256:<digest>
# Then replace the FROM line below with the digest form.
#
# The Elastic License 2.0 governs self-host redistribution — see
# infra/phoenix/README.md for the compliance note.

FROM arizephoenix/phoenix:version-8.0.0@sha256:c047635fd0d8e96a702359eb85d1197237e3cf82116d8643666fb759142b180e
# Digest pinned 2026-04-18 from docker.io/arizephoenix/phoenix:version-8.0.0.
# Refresh on bump: curl the manifest for a new tag and paste the
# `docker-content-digest` header value.

# Phoenix reads these at startup. PHOENIX_SQL_DATABASE_URL is injected
# at deploy time by Cloud Run via Secret Manager (see cloudbuild.yaml
# --set-secrets flag). When absent, Phoenix falls back to SQLite in
# PHOENIX_WORKING_DIR — useful for a quick sanity check but lost on
# every Cloud Run cold start.
ENV PHOENIX_WORKING_DIR=/tmp/phoenix \
    PHOENIX_PORT=6006 \
    PHOENIX_HOST=0.0.0.0 \
    PHOENIX_ENABLE_AUTH=true \
    PHOENIX_TRACE_RETENTION_DAYS=14 \
    PHOENIX_GRPC_PORT=0

EXPOSE 6006
