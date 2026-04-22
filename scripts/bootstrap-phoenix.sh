#!/usr/bin/env bash
#
# bootstrap-phoenix.sh — one-time provisioning for the Phoenix OTLP
# observability sink (runs as a second Cloud Run service).
#
# What this does (idempotent):
#   1. Enable sqladmin + vpcaccess + compute APIs.
#   2. Create a phoenix-run-sa service account with the roles it needs
#      (cloudsql.client, logging.logWriter, secretmanager.secretAccessor,
#      monitoring.metricWriter).
#   3. Create a Cloud SQL Postgres instance `phoenix-db` (db_f1_micro,
#      private IP on the default network).
#   4. Create the `phoenix` database and `phoenix` SQL user with a
#      generated random password.
#   5. Store the full connection URL in Secret Manager as
#      `phoenix-sql-url` and grant phoenix-run-sa access.
#   6. Create a PHOENIX_SECRET auth secret placeholder.
#   7. Create a VPC connector `gclaw-connector` (reuse if one exists).
#   8. Grant the Cloud Build SA the roles to deploy Phoenix
#      (run.admin, iam.serviceAccountUser on phoenix-run-sa).
#
# What this does NOT do:
#   - Deploy Phoenix itself. After this script succeeds, run:
#       gcloud builds submit --project <your-project> \
#         --config infra/phoenix/cloudbuild.yaml \
#         --substitutions _PROJECT_ID=<your-project>,\
# _IMAGE=us-central1-docker.pkg.dev/<your-project>/gclaw/phoenix,\
# _SERVICE_ACCOUNT=phoenix-run-sa@<your-project>.iam.gserviceaccount.com,\
# _VPC_CONNECTOR=gclaw-connector
#   - Wire the backend to Phoenix. After the Phoenix deploy succeeds,
#     grab its URL and run:
#       PHOENIX_URL=$(gcloud run services describe phoenix \
#         --region=<your-region> --project=<your-project> \
#         --format='value(status.url)')
#       printf '%s/v1/traces' "$PHOENIX_URL" | \
#         gcloud secrets versions add otel-exporter-otlp-endpoint \
#         --data-file=- --project=<your-project>
#     Then redeploy the backend with OBSERVABILITY_ENABLED=true.
#
# Usage:
#   ./scripts/bootstrap-phoenix.sh <PROJECT_ID> [REGION]
#
# Cost estimate: Cloud SQL db_f1_micro is ~$10/mo. Set a budget alert:
#   https://console.cloud.google.com/billing/budgets

set -euo pipefail

PROJECT_ID="${1:?Usage: $0 <PROJECT_ID> [REGION]}"
REGION="${2:-us-central1}"

SQL_INSTANCE="phoenix-db"
SQL_DB="phoenix"
SQL_USER="phoenix"
SA_NAME="phoenix-run-sa"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SQL_URL_SECRET="phoenix-sql-url"
AUTH_SECRET_NAME="phoenix-auth-secret"
VPC_CONNECTOR="gclaw-connector"

say()  { printf '\n\033[1;36m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$1" >&2; }
die()  { printf '\033[1;31mxx\033[0m %s\n' "$1" >&2; exit 1; }

command -v gcloud >/dev/null || die "gcloud not on PATH"

# 1 — APIs
say "Enabling Phoenix-specific APIs"
gcloud services enable \
  sqladmin.googleapis.com \
  vpcaccess.googleapis.com \
  compute.googleapis.com \
  --project="${PROJECT_ID}"

# 2 — Phoenix runtime SA
say "Creating ${SA_NAME}"
if gcloud iam service-accounts describe "${SA_EMAIL}" \
     --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "  already exists — skipping"
else
  gcloud iam service-accounts create "${SA_NAME}" \
    --display-name="Phoenix Cloud Run runtime" \
    --project="${PROJECT_ID}"
fi

say "Granting roles to ${SA_NAME}"
for role in roles/cloudsql.client roles/logging.logWriter \
            roles/secretmanager.secretAccessor \
            roles/monitoring.metricWriter; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${role}" --condition=None --quiet >/dev/null
  echo "  granted ${role}"
done

# 3 — Cloud SQL Postgres
say "Creating Cloud SQL instance ${SQL_INSTANCE}"
if gcloud sql instances describe "${SQL_INSTANCE}" \
     --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "  already exists — skipping"
else
  gcloud sql instances create "${SQL_INSTANCE}" \
    --database-version=POSTGRES_15 \
    --tier=db-f1-micro \
    --region="${REGION}" \
    --network=default \
    --no-assign-ip \
    --project="${PROJECT_ID}"
fi

say "Creating database '${SQL_DB}'"
if gcloud sql databases describe "${SQL_DB}" \
     --instance="${SQL_INSTANCE}" --project="${PROJECT_ID}" \
     >/dev/null 2>&1; then
  echo "  already exists — skipping"
else
  gcloud sql databases create "${SQL_DB}" \
    --instance="${SQL_INSTANCE}" \
    --project="${PROJECT_ID}"
fi

# 4 — SQL user
say "Ensuring SQL user '${SQL_USER}' + password"
if gcloud sql users list --instance="${SQL_INSTANCE}" \
     --project="${PROJECT_ID}" --format='value(name)' \
     | grep -qx "${SQL_USER}"; then
  # Reset password to a fresh one if the user exists but we don't
  # have the password cached anywhere. (phoenix-sql-url will reflect
  # the latest below.)
  PHOENIX_DB_PASS=$(openssl rand -base64 32 | tr -d '\n=/+' | head -c 32)
  gcloud sql users set-password "${SQL_USER}" \
    --instance="${SQL_INSTANCE}" \
    --password="${PHOENIX_DB_PASS}" \
    --project="${PROJECT_ID}"
  echo "  ✓ password rotated"
else
  PHOENIX_DB_PASS=$(openssl rand -base64 32 | tr -d '\n=/+' | head -c 32)
  gcloud sql users create "${SQL_USER}" \
    --instance="${SQL_INSTANCE}" \
    --password="${PHOENIX_DB_PASS}" \
    --project="${PROJECT_ID}"
  echo "  ✓ user created"
fi

# 5 — Connection URL → Secret Manager
say "Recording connection URL in Secret Manager (${SQL_URL_SECRET})"
PRIVATE_IP=$(gcloud sql instances describe "${SQL_INSTANCE}" \
  --project="${PROJECT_ID}" --format='value(ipAddresses[0].ipAddress)')
[[ -z "$PRIVATE_IP" ]] && die "could not resolve ${SQL_INSTANCE} private IP"

SQL_URL=$(printf 'postgresql+psycopg://%s:%s@%s:5432/%s' \
  "${SQL_USER}" "${PHOENIX_DB_PASS}" "${PRIVATE_IP}" "${SQL_DB}")

if gcloud secrets describe "${SQL_URL_SECRET}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  printf '%s' "${SQL_URL}" | gcloud secrets versions add "${SQL_URL_SECRET}" \
    --data-file=- --project="${PROJECT_ID}"
  echo "  ✓ new version added"
else
  printf '%s' "${SQL_URL}" | gcloud secrets create "${SQL_URL_SECRET}" \
    --replication-policy=automatic \
    --data-file=- --project="${PROJECT_ID}"
  gcloud secrets add-iam-policy-binding "${SQL_URL_SECRET}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role=roles/secretmanager.secretAccessor \
    --project="${PROJECT_ID}" --quiet >/dev/null
  echo "  ✓ created + SA access"
fi

# 6 — PHOENIX_SECRET placeholder (used if you later enable Phoenix auth)
say "Ensuring ${AUTH_SECRET_NAME} exists"
if gcloud secrets describe "${AUTH_SECRET_NAME}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "  already exists — skipping"
else
  openssl rand -base64 48 | gcloud secrets create "${AUTH_SECRET_NAME}" \
    --replication-policy=automatic --data-file=- --project="${PROJECT_ID}"
  gcloud secrets add-iam-policy-binding "${AUTH_SECRET_NAME}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role=roles/secretmanager.secretAccessor \
    --project="${PROJECT_ID}" --quiet >/dev/null
  echo "  ✓ created with random 48-byte secret"
fi

# 7 — VPC connector
say "Ensuring VPC connector ${VPC_CONNECTOR}"
if gcloud compute networks vpc-access connectors describe "${VPC_CONNECTOR}" \
     --region="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "  already exists — skipping"
else
  gcloud compute networks vpc-access connectors create "${VPC_CONNECTOR}" \
    --region="${REGION}" \
    --network=default \
    --range=10.8.0.0/28 \
    --project="${PROJECT_ID}"
  echo "  ✓ created"
fi

# 8 — Cloud Build SA permissions for Phoenix deploy
say "Granting Cloud Build SA permission to deploy Phoenix"
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" \
  --format='value(projectNumber)')
CB_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"
gcloud iam service-accounts add-iam-policy-binding "${SA_EMAIL}" \
  --member="serviceAccount:${CB_SA}" \
  --role="roles/iam.serviceAccountUser" \
  --project="${PROJECT_ID}" --quiet >/dev/null
echo "  ✓ iam.serviceAccountUser (on ${SA_NAME}) granted to ${CB_SA}"

# ── DONE ────────────────────────────────────────────────────────────────────

cat <<EOF

\033[1;32m✓ Phoenix infrastructure bootstrapped.\033[0m

Next steps:

  1. Deploy the Phoenix Cloud Run service:
       gcloud builds submit --project ${PROJECT_ID} \\
         --config infra/phoenix/cloudbuild.yaml \\
         --substitutions \\
           _PROJECT_ID=${PROJECT_ID},\\
_IMAGE=us-central1-docker.pkg.dev/${PROJECT_ID}/gclaw/phoenix,\\
_SERVICE_ACCOUNT=${SA_EMAIL},\\
_VPC_CONNECTOR=${VPC_CONNECTOR}

  2. After the Phoenix deploy completes, grab its URL and wire the
     gclaw backend to it:
       PHOENIX_URL=\$(gcloud run services describe phoenix \\
         --region=${REGION} --project=${PROJECT_ID} --format='value(status.url)')
       printf '%s/v1/traces' "\${PHOENIX_URL}" | \\
         gcloud secrets versions add otel-exporter-otlp-endpoint \\
           --data-file=- --project=${PROJECT_ID}

  3. Redeploy the backend with OBSERVABILITY_ENABLED=true so spans
     start flowing into Phoenix.

Resources created:
  - SA: ${SA_EMAIL}
  - Cloud SQL: ${SQL_INSTANCE} (POSTGRES_15, db_f1_micro, private IP)
  - DB: ${SQL_DB}  User: ${SQL_USER}
  - Secrets: ${SQL_URL_SECRET} (rotated), ${AUTH_SECRET_NAME}
  - VPC connector: ${VPC_CONNECTOR} (10.8.0.0/28)
  - Cloud Build SA: roles/iam.serviceAccountUser on ${SA_NAME}

Cost: Cloud SQL db_f1_micro ≈ \$10/mo. Set a budget alert:
  https://console.cloud.google.com/billing/budgets?project=${PROJECT_ID}
EOF
