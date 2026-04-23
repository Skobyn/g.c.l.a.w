#!/usr/bin/env bash
#
# bootstrap-bq-analytics.sh — provision BigQuery for ADR-0003 export.
#
# What this does (idempotent):
#   1. Enable the BigQuery API on the target project.
#   2. Create the analytics dataset (default: gclaw_analytics).
#   3. Grant `gclaw-run-sa` `roles/bigquery.dataEditor` on the dataset.
#
# What this does NOT do:
#   - Create the destination table. The writer auto-creates it on the
#     first flush so the schema lives in code (bq_schema.py) rather
#     than in two places.
#   - Flip BIGQUERY_ANALYTICS_ENABLED. That's a per-deploy decision —
#     update the cloudbuild substitution / `gcloud run services
#     update --update-env-vars` after this script lands.
#
# Usage:
#   ./scripts/bootstrap-bq-analytics.sh <PROJECT_ID> [LOCATION] [DATASET]
#   ./scripts/bootstrap-bq-analytics.sh my-gclaw-prod US gclaw_analytics

set -euo pipefail

PROJECT_ID="${1:?Usage: $0 <PROJECT_ID> [LOCATION] [DATASET]}"
LOCATION="${2:-US}"
DATASET="${3:-gclaw_analytics}"

SA_NAME="gclaw-run-sa"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

say()  { printf '\n\033[1;36m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$1" >&2; }
die()  { printf '\033[1;31mxx\033[0m %s\n' "$1" >&2; exit 1; }

for cmd in gcloud bq; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    die "'$cmd' not on PATH. Install the Google Cloud SDK and re-run."
  fi
done

say "Project: ${PROJECT_ID}  Location: ${LOCATION}  Dataset: ${DATASET}"

# 1 — Enable the BigQuery API
say "Enabling BigQuery API"
gcloud services enable bigquery.googleapis.com --project="${PROJECT_ID}"

# 2 — Create the dataset (idempotent — bq mk fails if it already exists,
#     so probe first via bq show).
say "Creating dataset ${PROJECT_ID}:${DATASET}"
if bq --project_id="${PROJECT_ID}" show --dataset "${DATASET}" >/dev/null 2>&1; then
  echo "  dataset already exists — skipping"
else
  bq --project_id="${PROJECT_ID}" --location="${LOCATION}" mk \
    --dataset \
    --description "GClaw agent analytics events (ADR-0003)" \
    "${PROJECT_ID}:${DATASET}"
fi

# 3 — Grant the runtime SA dataEditor on the dataset.
#     Project-level bigquery.dataEditor would also work, but
#     dataset-scoped keeps the blast radius small.
say "Granting roles/bigquery.dataEditor to ${SA_EMAIL} on ${DATASET}"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/bigquery.dataEditor" \
  --condition=None --quiet >/dev/null
echo "  granted (project-level binding — restrict to dataset later if desired)"

cat <<EOF

\033[1;32m✓ BigQuery analytics bootstrap complete.\033[0m

Next steps:
  - Flip BIGQUERY_ANALYTICS_ENABLED=true on the next deploy:
      gcloud run services update gclaw \\
        --region <region> \\
        --update-env-vars BIGQUERY_ANALYTICS_ENABLED=true,\\
BIGQUERY_ANALYTICS_DATASET=${DATASET}
  - The destination table is auto-created on the first span flush
    using the schema in src/gclaw/observability/bq_schema.py.
EOF
