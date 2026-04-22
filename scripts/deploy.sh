#!/usr/bin/env bash
#
# deploy.sh — apply your private overlay (if you have one) and run the
# Cloud Build pipeline.
#
# Usage:
#   ./scripts/deploy.sh <PROJECT_ID> [REGION]
#
# Optional environment variables (each maps to a Cloud Build
# substitution; unset = leave default in cloudbuild.yaml empty):
#   OVERLAY                  Path to your private overlay repo. If set
#                            and the directory exists, files are rsync'd
#                            on top of the working tree before build.
#                            Default: $HOME/dev/gclaw-overlay
#   GWS_USER                 Workspace user to impersonate (gws CLI).
#                            Required for the workspace-mgr to function.
#   MEMORY_ENGINE_ID         Vertex AI Memory Bank reasoning engine ID
#                            from bootstrap-gcp.sh step 6.
#   POSTIZ_BASE_URL          Base URL of your Postiz instance.
#   POSTIZ_REVIEWER_URL      Reviewer Cloud Run URL (if separate).
#   POSTIZ_CHANNEL_PRIMARY   Primary Postiz channel ID.
#   POSTIZ_CHANNEL_SECONDARY Secondary Postiz channel ID.
#   VPC_CONNECTOR            VPC connector name (only if reaching
#                            internal-only Cloud Run services).
#   SECRET_NAME_PREFIX       SM resource prefix (default "gclaw-").
#                            Set to "watson-" to keep reading legacy
#                            upstream resources.
#   OVERLAY_RESET_PATHS      Space-separated paths git-clean removes
#                            after deploy (defaults to "user.md" — add
#                            any overlay-only directories you don't
#                            want left in the public clone afterward).
#   HEARTBEAT_SCHEDULER      When "true", create/update a Cloud
#                            Scheduler job that POSTs /heartbeat to
#                            the deployed service every 15 minutes.
#                            Required for the proactive agent loop;
#                            opt-in because it costs ~$0 but adds
#                            deploy-time permissions (cloudscheduler.admin).

set -euo pipefail

PROJECT_ID="${1:?Usage: $0 <PROJECT_ID> [REGION]}"
REGION="${2:-us-central1}"
OVERLAY="${OVERLAY:-${HOME}/dev/gclaw-overlay}"
OVERLAY_RESET_PATHS="${OVERLAY_RESET_PATHS:-user.md}"

cd "$(dirname "$0")/.."

# 1 — Apply overlay if present
if [[ -d "${OVERLAY}" ]]; then
  echo "==> Applying overlay from ${OVERLAY}"
  rsync -av \
    --exclude='.git' \
    --exclude='.env' \
    --exclude='*.lock' \
    --exclude='node_modules' \
    --exclude='__pycache__' \
    "${OVERLAY}/" ./
  echo "    overlay applied; framework files now reflect personal config"
else
  echo "==> No overlay at ${OVERLAY} — deploying framework defaults"
  echo "    (set OVERLAY=/path/to/your/overlay to layer personal config in)"
fi

# 2 — Build substitutions from env
SUBS="_PROJECT_ID=${PROJECT_ID}"
SUBS+=",_REGION=${REGION}"
SUBS+=",_IMAGE=us-central1-docker.pkg.dev/${PROJECT_ID}/gclaw/gclaw"
SUBS+=",_SERVICE_ACCOUNT=gclaw-run-sa@${PROJECT_ID}.iam.gserviceaccount.com"

[[ -n "${MEMORY_ENGINE_ID:-}" ]]         && SUBS+=",_MEMORY_ENGINE_ID=${MEMORY_ENGINE_ID}"
[[ -n "${GWS_USER:-}" ]]                  && SUBS+=",_GWS_USER=${GWS_USER}"
[[ -n "${VPC_CONNECTOR:-}" ]]            && SUBS+=",_VPC_CONNECTOR=${VPC_CONNECTOR}"
[[ -n "${POSTIZ_BASE_URL:-}" ]]          && SUBS+=",_POSTIZ_BASE_URL=${POSTIZ_BASE_URL}"
[[ -n "${POSTIZ_REVIEWER_URL:-}" ]]      && SUBS+=",_POSTIZ_REVIEWER_URL=${POSTIZ_REVIEWER_URL}"
[[ -n "${POSTIZ_CHANNEL_PRIMARY:-}" ]]   && SUBS+=",_POSTIZ_CHANNEL_PRIMARY=${POSTIZ_CHANNEL_PRIMARY}"
[[ -n "${POSTIZ_CHANNEL_SECONDARY:-}" ]] && SUBS+=",_POSTIZ_CHANNEL_SECONDARY=${POSTIZ_CHANNEL_SECONDARY}"
[[ -n "${SECRET_NAME_PREFIX:-}" ]]       && SUBS+=",_SECRET_NAME_PREFIX=${SECRET_NAME_PREFIX}"

# 3 — Submit
echo "==> Submitting Cloud Build to project ${PROJECT_ID}"
gcloud builds submit \
  --project "${PROJECT_ID}" \
  --config cloudbuild.yaml \
  --substitutions "${SUBS}"

# 4 — Reset working tree if we applied an overlay (don't accidentally
# commit overlay files to the public repo)
if [[ -d "${OVERLAY}" ]]; then
  echo "==> Resetting working tree to clean framework state"
  git checkout -- .
  # OVERLAY_RESET_PATHS removes any files/dirs the overlay added that
  # don't exist in the public framework. Defaults to user.md; extend
  # via env for skill directories or anything else overlay-only.
  # shellcheck disable=SC2086
  git clean -fd ${OVERLAY_RESET_PATHS} 2>/dev/null || true
fi

echo "==> Done. Cloud Run will serve the new revision once build + deploy finish."

# 5 — Optional: create/update Cloud Scheduler heartbeat job.
if [[ "${HEARTBEAT_SCHEDULER:-}" == "true" ]]; then
  SERVICE_URL=$(gcloud run services describe gclaw \
    --region="${REGION}" --project="${PROJECT_ID}" \
    --format='value(status.url)' 2>/dev/null || echo "")
  if [[ -z "${SERVICE_URL}" ]]; then
    echo "==> WARNING: could not resolve Cloud Run URL; skipping scheduler"
  else
    JOB_NAME="gclaw-heartbeat"
    SCHED_URL="${SERVICE_URL}/heartbeat"
    echo "==> Ensuring Cloud Scheduler job '${JOB_NAME}' → ${SCHED_URL}"
    if gcloud scheduler jobs describe "${JOB_NAME}" \
         --location="${REGION}" --project="${PROJECT_ID}" \
         >/dev/null 2>&1; then
      gcloud scheduler jobs update http "${JOB_NAME}" \
        --location="${REGION}" --project="${PROJECT_ID}" \
        --schedule="*/15 * * * *" \
        --uri="${SCHED_URL}" \
        --http-method=POST \
        --time-zone="UTC" \
        --quiet
      echo "    updated"
    else
      gcloud scheduler jobs create http "${JOB_NAME}" \
        --location="${REGION}" --project="${PROJECT_ID}" \
        --schedule="*/15 * * * *" \
        --uri="${SCHED_URL}" \
        --http-method=POST \
        --time-zone="UTC" \
        --description="POST /heartbeat every 15 min — gclaw agent consciousness loop" \
        --quiet
      echo "    created"
    fi
  fi
fi
