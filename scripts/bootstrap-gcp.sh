#!/usr/bin/env bash
#
# bootstrap-gcp.sh — one-time provisioning for a fresh gclaw deployment.
#
# What this does (idempotent — safe to re-run):
#
#   A. PREFLIGHT
#      1. Check gcloud / uv / docker are on PATH.
#      2. Check the target project exists + billing is linked.
#
#   B. CORE GCP STATE
#      3. Enable required APIs (Vertex AI, Firestore, Cloud Run,
#         Secret Manager, Artifact Registry, Cloud Build, Cloud
#         Scheduler, IAM Credentials, Storage).
#      4. Create Firestore (Native mode) in your chosen region.
#      5. Create an Artifact Registry Docker repo named "gclaw".
#      6. Create the runtime SA `gclaw-run-sa@…` + grant the
#         least-privilege roles the backend needs at runtime.
#      7. Grant the Cloud Build service agent the roles it needs
#         to deploy (run.admin, iam.serviceAccountUser on
#         gclaw-run-sa, artifactregistry.writer, secretAccessor).
#         Without this, `gcloud builds submit` fails at the deploy step.
#      8. Create the GCS bucket gclaw uses for shared-context blackboard.
#      9. Apply firestore.rules and firestore.indexes.json.
#
#   C. OPTIONAL
#     10. Create a Vertex AI Memory Bank reasoning engine (skip with
#         --no-memory if you're running MEMORY_ENABLED=false).
#
# What this does NOT do:
#   - Provision Firebase / Firebase Auth (do that in the Firebase
#     console at https://console.firebase.google.com if you plan to
#     run with FIREBASE_AUTH_ENABLED=true).
#   - Populate Secret Manager with API keys (run
#     scripts/seed-secrets.sh next).
#   - Deploy the backend (run scripts/deploy.sh).
#   - Create the Cloud Scheduler heartbeat job (run scripts/deploy.sh
#     with HEARTBEAT_SCHEDULER=true).
#   - Provision Phoenix / Cloud SQL (see infra/phoenix/README.md).
#   - Provision Vertex AI model endpoints (see infra/vertex-models/).
#
# Usage:
#   ./scripts/bootstrap-gcp.sh <PROJECT_ID> [REGION] [flags]
#   ./scripts/bootstrap-gcp.sh my-gclaw-prod us-central1
#   ./scripts/bootstrap-gcp.sh my-gclaw-prod us-central1 --no-memory
#
# Prerequisites:
#   - gcloud authenticated as a user with Owner or Project IAM Admin
#     on the target project.
#   - The project must already exist AND have an active billing
#     account linked (this script won't create projects or attach
#     billing — both involve org-policy decisions outside our scope).

set -euo pipefail

PROJECT_ID="${1:?Usage: $0 <PROJECT_ID> [REGION] [--no-memory]}"
REGION="${2:-us-central1}"
ENABLE_MEMORY=true

for arg in "$@"; do
  case "$arg" in
    --no-memory) ENABLE_MEMORY=false ;;
  esac
done

SA_NAME="gclaw-run-sa"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
AR_REPO="gclaw"
SHARED_BUCKET="gclaw-shared-context-${PROJECT_ID}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

say() { printf '\n\033[1;36m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$1" >&2; }
die()  { printf '\033[1;31mxx\033[0m %s\n' "$1" >&2; exit 1; }

# ── A. PREFLIGHT ────────────────────────────────────────────────────────────

say "Preflight"

for cmd in gcloud uv docker; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    die "'$cmd' not on PATH. Install it and re-run."
  fi
  echo "  ✓ ${cmd} found: $(command -v "$cmd")"
done

if ! gcloud projects describe "${PROJECT_ID}" >/dev/null 2>&1; then
  die "project '${PROJECT_ID}' not accessible. Create it in the GCP console or switch accounts with 'gcloud auth login'."
fi
echo "  ✓ project accessible: ${PROJECT_ID}"

# Billing check — the API requires billing to be active before enable.
# `gcloud beta billing` is the canonical check; fall back to alpha if beta
# isn't installed.
BILL_CMD="gcloud beta billing"
if ! gcloud beta billing --help >/dev/null 2>&1; then
  BILL_CMD="gcloud alpha billing"
fi
BILL_STATE=$(${BILL_CMD} projects describe "${PROJECT_ID}" \
  --format='value(billingEnabled)' 2>/dev/null || echo "")
if [[ "${BILL_STATE}" != "True" ]]; then
  die "billing is not enabled on ${PROJECT_ID}. Link a billing account: https://console.cloud.google.com/billing/linkedaccount?project=${PROJECT_ID}"
fi
echo "  ✓ billing linked"

# ── B. CORE GCP STATE ───────────────────────────────────────────────────────

say "Project: ${PROJECT_ID}  Region: ${REGION}  Memory Bank: ${ENABLE_MEMORY}"

# 3 — APIs
say "Enabling required GCP APIs"
gcloud services enable \
  aiplatform.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  cloudscheduler.googleapis.com \
  datastore.googleapis.com \
  firestore.googleapis.com \
  iamcredentials.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  --project="${PROJECT_ID}"

# 4 — Firestore Native
say "Creating Firestore (Native mode) in ${REGION}"
if gcloud firestore databases describe \
     --database='(default)' --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "  Firestore already exists — skipping create"
else
  gcloud firestore databases create \
    --location="${REGION}" --type=firestore-native \
    --project="${PROJECT_ID}"
fi

# 5 — Artifact Registry
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

# 6 — Runtime service account + IAM
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

# 7 — Cloud Build service agent permissions.
# Cloud Build uses a per-project service agent named
# <project-number>@cloudbuild.gserviceaccount.com. It needs to be
# able to deploy Cloud Run services, impersonate gclaw-run-sa,
# push images to Artifact Registry, and read the OTEL endpoint
# secret during the deploy step.
say "Granting Cloud Build roles to deploy Cloud Run"
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" \
  --format='value(projectNumber)')
CB_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"
for role in \
    roles/run.admin \
    roles/artifactregistry.writer \
    roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${CB_SA}" \
    --role="${role}" --condition=None --quiet >/dev/null
  echo "  granted ${role} to ${CB_SA}"
done
# iam.serviceAccountUser must be granted on the runtime SA (not the
# project) — that's what lets Cloud Build assign gclaw-run-sa to the
# Cloud Run service.
gcloud iam service-accounts add-iam-policy-binding "${SA_EMAIL}" \
  --member="serviceAccount:${CB_SA}" \
  --role="roles/iam.serviceAccountUser" \
  --project="${PROJECT_ID}" --quiet >/dev/null
echo "  granted roles/iam.serviceAccountUser (on ${SA_NAME}) to ${CB_SA}"

# 8 — GCS bucket for shared context
say "Creating shared-context bucket gs://${SHARED_BUCKET}"
if gcloud storage buckets describe "gs://${SHARED_BUCKET}" \
     --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "  bucket already exists — skipping"
else
  gcloud storage buckets create "gs://${SHARED_BUCKET}" \
    --location="${REGION}" --uniform-bucket-level-access \
    --project="${PROJECT_ID}"
fi

# 9 — Firestore rules + indexes
#
# We use the raw Firestore APIs (not Firebase CLI) to avoid a hard
# dependency on `firebase-tools`. Rules go via `gcloud firestore`;
# indexes we apply by reading firestore.indexes.json and calling
# gcloud for each composite index.
say "Applying firestore.rules"
if [[ -f "${REPO_ROOT}/firestore.rules" ]]; then
  # The gcloud `security-rules` API is the right tool but it's
  # behind a preview track and tends to change. For now, print the
  # Firebase CLI command as a fallback and skip if firebase-tools
  # isn't installed.
  if command -v firebase >/dev/null 2>&1; then
    (cd "${REPO_ROOT}" && firebase --project "${PROJECT_ID}" \
      deploy --only firestore:rules --non-interactive) || \
      warn "firestore:rules deploy failed — run manually later"
  else
    warn "firebase CLI not installed; skipping rules deploy. Install with 'npm install -g firebase-tools' then run: firebase --project ${PROJECT_ID} deploy --only firestore:rules"
  fi
else
  warn "firestore.rules not found — skipping"
fi

say "Applying firestore.indexes.json"
if [[ -f "${REPO_ROOT}/firestore.indexes.json" ]]; then
  if command -v firebase >/dev/null 2>&1; then
    (cd "${REPO_ROOT}" && firebase --project "${PROJECT_ID}" \
      deploy --only firestore:indexes --non-interactive) || \
      warn "firestore:indexes deploy failed — run manually later"
  else
    warn "firebase CLI not installed; skipping indexes deploy. Install with 'npm install -g firebase-tools' then run: firebase --project ${PROJECT_ID} deploy --only firestore:indexes"
  fi
else
  warn "firestore.indexes.json not found — skipping"
fi

# ── C. OPTIONAL ─────────────────────────────────────────────────────────────

# 10 — Vertex AI Memory Bank reasoning engine
MEMORY_ENGINE_ID=""
if [[ "${ENABLE_MEMORY}" == "true" ]]; then
  say "Creating Vertex AI Memory Bank reasoning engine"
  MEMORY_ENGINE_ID=$(cd "${REPO_ROOT}" && uv run --quiet python - <<PY
import sys
try:
    from vertexai import agent_engines
    import vertexai
    vertexai.init(project="${PROJECT_ID}", location="${REGION}")
    engine = agent_engines.create(display_name="gclaw-memory")
    full = engine.resource_name
    # resource_name is like projects/<num>/locations/<loc>/reasoningEngines/<id>
    print(full.rsplit("/", 1)[-1])
except Exception as exc:
    print(f"ERROR: {exc}", file=sys.stderr)
    sys.exit(2)
PY
) || MEMORY_ENGINE_ID=""
  if [[ -n "${MEMORY_ENGINE_ID}" ]]; then
    echo "  ✓ created engine: ${MEMORY_ENGINE_ID}"
  else
    warn "Memory Bank engine creation failed. Re-run with --no-memory or create manually (see https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/memory-bank/overview)"
  fi
fi

# ── DONE ────────────────────────────────────────────────────────────────────

cat <<EOF

\033[1;32m✓ GCP bootstrap complete.\033[0m

Next steps:
  1. Populate Secret Manager:
     ./scripts/seed-secrets.sh ${PROJECT_ID} --apply --values ./my-secrets.env

  2. (Optional) Set up Firebase Auth in the Firebase console:
     https://console.firebase.google.com/project/${PROJECT_ID}/authentication

  3. Deploy:
$(if [[ -n "${MEMORY_ENGINE_ID}" ]]; then
  printf '     MEMORY_ENGINE_ID=%s \\\\\n     ./scripts/deploy.sh %s %s\n' "${MEMORY_ENGINE_ID}" "${PROJECT_ID}" "${REGION}"
else
  printf '     ./scripts/deploy.sh %s %s\n' "${PROJECT_ID}" "${REGION}"
fi)

Resources created:
  - APIs enabled: aiplatform, artifactregistry, cloudbuild,
    cloudscheduler, datastore, firestore, iamcredentials, run,
    secretmanager, storage
  - Firestore (default) in ${REGION} — Native mode
  - Artifact Registry repo: ${AR_REPO}
  - Runtime SA: ${SA_EMAIL}
    (aiplatform.user, datastore.user, logging.logWriter,
     monitoring.metricWriter, secretmanager.secretAccessor,
     storage.objectAdmin)
  - Cloud Build SA: ${CB_SA}
    (run.admin, artifactregistry.writer, secretmanager.secretAccessor,
     serviceAccountUser on ${SA_NAME})
  - GCS bucket: gs://${SHARED_BUCKET}
$(if [[ -n "${MEMORY_ENGINE_ID}" ]]; then echo "  - Memory Bank engine: ${MEMORY_ENGINE_ID}"; fi)
EOF
