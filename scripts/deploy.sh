#!/usr/bin/env bash
#
# deploy.sh — apply your private overlay (if you have one) and run the
# Cloud Build pipeline.
#
# Usage:
#   ./scripts/deploy.sh <PROJECT_ID> [REGION]
#
# Optional environment variables:
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
#   POSTIZ_CHANNEL_PRIMARY   Primary channel ID (legacy env name:
#                            POSTIZ_CHANNEL_SCOTT — see settings.py).
#   POSTIZ_CHANNEL_SECONDARY Secondary channel ID (legacy:
#                            POSTIZ_CHANNEL_APEX).
#   VPC_CONNECTOR            VPC connector name (only if reaching
#                            internal-only Cloud Run services).
#
# Each env var maps to a Cloud Build substitution; unset = use the
# default in cloudbuild.yaml.

set -euo pipefail

PROJECT_ID="${1:?Usage: $0 <PROJECT_ID> [REGION]}"
REGION="${2:-us-central1}"
OVERLAY="${OVERLAY:-${HOME}/dev/gclaw-overlay}"

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
[[ -n "${POSTIZ_CHANNEL_PRIMARY:-}" ]]   && SUBS+=",_POSTIZ_CHANNEL_SCOTT=${POSTIZ_CHANNEL_PRIMARY}"
[[ -n "${POSTIZ_CHANNEL_SECONDARY:-}" ]] && SUBS+=",_POSTIZ_CHANNEL_APEX=${POSTIZ_CHANNEL_SECONDARY}"

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
  git clean -fd \
    user.md \
    skills/lyons-blog-pipeline 2>/dev/null || true
fi

echo "==> Done. Cloud Run will serve the new revision once build + deploy finish."
