#!/usr/bin/env bash
#
# bootstrap-gcp.sh — one-time provisioning for a fresh gclaw deployment.
#
# What this does (idempotent — safe to re-run):
#   1. Enables the GCP APIs gclaw needs (Vertex AI, Firestore, Cloud Run,
#      Secret Manager, Artifact Registry, Cloud Build).
#   2. Creates Firestore (Native mode) in your chosen region.
#   3. Creates an Artifact Registry repo named "gclaw".
#   4. Creates the runtime service account `gclaw-run-sa@…` and grants
#      the least-privilege IAM roles the backend needs.
#   5. Creates the GCS bucket gclaw uses for shared-context blackboard.
#   6. Optionally creates a Vertex AI Memory Bank reasoning engine
#      (skip with --no-memory if you don't want long-term memory yet).
#
# What this does NOT do:
#   - Provision Firebase / Firebase Auth (do that in the Firebase console
#     once you've decided whether to enable user auth at all).
#   - Populate Secret Manager with API keys (run scripts/seed-secrets.sh
#     after this).
#   - Deploy the backend (run scripts/deploy.sh).
#
# Usage:
#   ./scripts/bootstrap-gcp.sh <PROJECT_ID> [REGION]
#   ./scripts/bootstrap-gcp.sh my-gclaw-prod us-central1
#   ./scripts/bootstrap-gcp.sh my-gclaw-prod us-central1 --no-memory
#
# Prerequisites:
#   - gcloud authenticated as a user with Owner or Project IAM Admin on
#     the target project (or the ability to assume those roles).
#   - The project must already exist (this script does not create projects
#     because billing setup + org policies are out of scope).

set -euo pipefail

PROJECT_ID="${1:?Usage: $0 <PROJECT_ID> [REGION] [--no-memory]}"
REGION="${2:-us-central1}"
ENABLE_MEMORY=true

# Allow --no-memory anywhere after the first two args.
for arg in "$@"; do
  case "$arg" in
    --no-memory) ENABLE_MEMORY=false ;;
  esac
done

SA_NAME="gclaw-run-sa"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
AR_REPO="gclaw"
SHARED_BUCKET="gclaw-shared-context-${PROJECT_ID}"

say() { printf '\n\033[1;36m==>\033[0m %s\n' "$1"; }

say "Project: ${PROJECT_ID}  Region: ${REGION}  Memory Bank: ${ENABLE_MEMORY}"

# 1 — APIs
say "Enabling required GCP APIs"
gcloud services enable \
  aiplatform.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  datastore.googleapis.com \
  firestore.googleapis.com \
  iamcredentials.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  --project="${PROJECT_ID}"

# 2 — Firestore Native
say "Creating Firestore (Native mode) in ${REGION}"
if gcloud firestore databases describe \
     --database='(default)' --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "  Firestore already exists — skipping"
else
  gcloud firestore databases create \
    --location="${REGION}" --type=firestore-native \
    --project="${PROJECT_ID}"
fi

# 3 — Artifact Registry
say "Creating Artifact Registry repo '${AR_REPO}'"
if gcloud artifacts repositories describe "${AR_REPO}" \
     --location="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "  AR repo '${AR_REPO}' already exists — skipping"
else
  gcloud artifacts repositories create "${AR_REPO}" \
    --repository-format=docker --location="${REGION}" \
    --description="GClaw container images" \
    --project="${PROJECT_ID}"
fi

# 4 — Runtime service account + IAM
say "Creating runtime service account '${SA_NAME}'"
if gcloud iam service-accounts describe "${SA_EMAIL}" \
     --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "  ${SA_NAME} already exists — skipping create"
else
  gcloud iam service-accounts create "${SA_NAME}" \
    --display-name="GClaw Cloud Run runtime" \
    --project="${PROJECT_ID}"
fi

say "Granting least-privilege roles to ${SA_NAME}"
for role in \
    roles/aiplatform.user \
    roles/datastore.user \
    roles/logging.logWriter \
    roles/monitoring.metricWriter \
    roles/secretmanager.secretAccessor \
    roles/storage.objectAdmin; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${role}" --condition=None --quiet >/dev/null
  echo "  granted ${role}"
done

# 5 — GCS bucket for shared context
say "Creating shared-context bucket gs://${SHARED_BUCKET}"
if gcloud storage buckets describe "gs://${SHARED_BUCKET}" \
     --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "  bucket already exists — skipping"
else
  gcloud storage buckets create "gs://${SHARED_BUCKET}" \
    --location="${REGION}" --uniform-bucket-level-access \
    --project="${PROJECT_ID}"
fi

# 6 — Vertex AI Memory Bank reasoning engine (optional)
if [[ "${ENABLE_MEMORY}" == "true" ]]; then
  say "Creating Vertex AI Memory Bank reasoning engine"
  cat <<EOF

  Memory Bank engines are created via the python SDK, not gcloud.
  Run this in a Python REPL (or as a one-off script):

    from vertexai import agent_engines
    import vertexai
    vertexai.init(project="${PROJECT_ID}", location="${REGION}")
    engine = agent_engines.create(display_name="gclaw-memory")
    print("MEMORY_BANK_REASONING_ENGINE_ID:", engine.resource_name.rsplit("/", 1)[-1])

  Save the printed numeric ID — pass it as the
  _MEMORY_ENGINE_ID substitution to cloudbuild.yaml on first deploy.

EOF
fi

cat <<EOF

\033[1;32m✓ GCP bootstrap complete.\033[0m

Next steps:
  1. Populate Secret Manager:    ./scripts/seed-secrets.sh ${PROJECT_ID}
  2. (Optional) Set up Firebase Auth in the Firebase console.
  3. Deploy:                     ./scripts/deploy.sh ${PROJECT_ID} ${REGION}

Resources created:
  - Project APIs enabled
  - Firestore (default) in ${REGION}
  - Artifact Registry repo: ${AR_REPO}
  - Service account: ${SA_EMAIL}
  - GCS bucket: gs://${SHARED_BUCKET}
EOF
