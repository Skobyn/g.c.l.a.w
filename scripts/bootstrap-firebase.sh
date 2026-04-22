#!/usr/bin/env bash
#
# bootstrap-firebase.sh — add Firebase to an existing GCP project and
# enable the auth bits gclaw needs, without touching the Firebase console.
#
# What this does:
#   1. Enable firebase.googleapis.com + identitytoolkit.googleapis.com.
#   2. Add Firebase to the GCP project (idempotent — skips if already on).
#   3. Create a Firebase Web App named "gclaw-web" (if absent).
#   4. Fetch the web config (apiKey, authDomain, appId, etc.).
#   5. Enable email/password + anonymous sign-in via Identity Toolkit.
#   6. Write the NEXT_PUBLIC_FIREBASE_* env lines to web/.env.firebase.
#
# What this does NOT do:
#   - Configure Google sign-in. Google provider setup requires OAuth
#     consent screen + brand review which is partly console-only. See
#     the "Google sign-in" note at the bottom of this file's output.
#   - Turn FIREBASE_AUTH_ENABLED=true in the backend — that's a
#     cloudbuild substitution you flip on your next deploy.
#
# Usage:
#   ./scripts/bootstrap-firebase.sh <PROJECT_ID>
#
# Prerequisites:
#   - bootstrap-gcp.sh already run (for billing + core IAM).
#   - The caller has roles/firebase.admin on the project.

set -euo pipefail

PROJECT_ID="${1:?Usage: $0 <PROJECT_ID>}"
APP_DISPLAY_NAME="gclaw-web"
OUT_FILE="${2:-web/.env.firebase}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

say() { printf '\n\033[1;36m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$1" >&2; }
die()  { printf '\033[1;31mxx\033[0m %s\n' "$1" >&2; exit 1; }

command -v gcloud >/dev/null || die "gcloud not on PATH"
command -v jq >/dev/null || die "jq not on PATH (brew install jq / apt-get install jq)"
command -v curl >/dev/null || die "curl not on PATH"

ACCESS_TOKEN=$(gcloud auth print-access-token)
[[ -z "$ACCESS_TOKEN" ]] && die "no access token — run 'gcloud auth login'"

auth_header=(-H "Authorization: Bearer ${ACCESS_TOKEN}")
ct_header=(-H "Content-Type: application/json")

# 1 — Enable APIs
say "Enabling Firebase APIs"
gcloud services enable \
  firebase.googleapis.com \
  identitytoolkit.googleapis.com \
  --project="${PROJECT_ID}"

# 2 — Add Firebase to GCP project (idempotent)
say "Adding Firebase to project ${PROJECT_ID}"
ADD_RESP=$(curl -sS -X POST \
  "${auth_header[@]}" "${ct_header[@]}" \
  "https://firebase.googleapis.com/v1beta1/projects/${PROJECT_ID}:addFirebase" \
  -d '{}' || true)
if echo "$ADD_RESP" | jq -e '.error.status == "ALREADY_EXISTS"' >/dev/null 2>&1; then
  echo "  Firebase already enabled on ${PROJECT_ID} — skipping"
elif echo "$ADD_RESP" | jq -e '.name' >/dev/null 2>&1; then
  echo "  ✓ Firebase added (long-running op; completes in ~10s)"
  sleep 10
elif echo "$ADD_RESP" | jq -e '.error' >/dev/null 2>&1; then
  ERR_MSG=$(echo "$ADD_RESP" | jq -r '.error.message')
  # Some errors are fine — "FAILED_PRECONDITION" when the project is
  # already Firebase-enabled under a different pathway.
  if [[ "$ERR_MSG" == *"already"* ]]; then
    echo "  Firebase already present (per API response) — skipping"
  else
    die "Firebase add failed: ${ERR_MSG}"
  fi
fi

# 3 — Create or find the Firebase Web App
say "Ensuring Firebase Web App '${APP_DISPLAY_NAME}' exists"
LIST_RESP=$(curl -sS "${auth_header[@]}" \
  "https://firebase.googleapis.com/v1beta1/projects/${PROJECT_ID}/webApps")
APP_ID=$(echo "$LIST_RESP" | \
  jq -r --arg name "$APP_DISPLAY_NAME" \
    '.apps[]? | select(.displayName == $name) | .appId' | head -n 1)

if [[ -z "$APP_ID" || "$APP_ID" == "null" ]]; then
  CREATE_RESP=$(curl -sS -X POST "${auth_header[@]}" "${ct_header[@]}" \
    "https://firebase.googleapis.com/v1beta1/projects/${PROJECT_ID}/webApps" \
    -d "$(jq -n --arg name "$APP_DISPLAY_NAME" '{displayName: $name}')")
  # The response is a long-running op; poll for ~10s until it resolves.
  sleep 8
  LIST_RESP=$(curl -sS "${auth_header[@]}" \
    "https://firebase.googleapis.com/v1beta1/projects/${PROJECT_ID}/webApps")
  APP_ID=$(echo "$LIST_RESP" | \
    jq -r --arg name "$APP_DISPLAY_NAME" \
      '.apps[]? | select(.displayName == $name) | .appId' | head -n 1)
  if [[ -z "$APP_ID" || "$APP_ID" == "null" ]]; then
    warn "Web app create may still be in progress. Re-run this script in a minute if config fetch below fails."
    die "Could not locate web app ID after create. Response was: $CREATE_RESP"
  fi
  echo "  ✓ created web app: ${APP_ID}"
else
  echo "  web app already exists: ${APP_ID}"
fi

# 4 — Fetch web app config
say "Fetching Firebase web config"
CFG=$(curl -sS "${auth_header[@]}" \
  "https://firebase.googleapis.com/v1beta1/projects/${PROJECT_ID}/webApps/${APP_ID}/config")
if ! echo "$CFG" | jq -e '.apiKey' >/dev/null; then
  die "Could not fetch web config; response: $CFG"
fi

API_KEY=$(echo "$CFG" | jq -r '.apiKey')
AUTH_DOMAIN=$(echo "$CFG" | jq -r '.authDomain')
PROJECT_ID_CFG=$(echo "$CFG" | jq -r '.projectId')
STORAGE_BUCKET=$(echo "$CFG" | jq -r '.storageBucket // empty')
MESSAGING_SENDER_ID=$(echo "$CFG" | jq -r '.messagingSenderId')
APP_ID_CFG=$(echo "$CFG" | jq -r '.appId')

# 5 — Enable email/password + anonymous sign-in
say "Enabling email/password + anonymous sign-in providers"
IT_BODY=$(jq -n '{
  signIn: {
    email: { enabled: true, passwordRequired: true },
    anonymous: { enabled: true }
  }
}')
IT_RESP=$(curl -sS -X PATCH \
  "${auth_header[@]}" "${ct_header[@]}" \
  "https://identitytoolkit.googleapis.com/admin/v2/projects/${PROJECT_ID}/config?updateMask=signIn.email,signIn.anonymous" \
  -d "$IT_BODY" || true)
if echo "$IT_RESP" | jq -e '.error' >/dev/null 2>&1; then
  ERR=$(echo "$IT_RESP" | jq -r '.error.message')
  warn "Identity Toolkit config update failed: ${ERR}"
  warn "You can enable providers manually at: https://console.firebase.google.com/project/${PROJECT_ID}/authentication/providers"
else
  echo "  ✓ providers enabled: email/password, anonymous"
fi

# 6 — Write NEXT_PUBLIC_FIREBASE_* to the config file
say "Writing ${OUT_FILE}"
OUT_PATH="${REPO_ROOT}/${OUT_FILE}"
mkdir -p "$(dirname "$OUT_PATH")"
cat > "$OUT_PATH" <<EOF
# Generated by scripts/bootstrap-firebase.sh — safe to commit only if
# you're OK publishing the Firebase apiKey (it IS a public client
# identifier; restrict usage via Firebase Security Rules + Auth).
NEXT_PUBLIC_FIREBASE_API_KEY=${API_KEY}
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=${AUTH_DOMAIN}
NEXT_PUBLIC_FIREBASE_PROJECT_ID=${PROJECT_ID_CFG}
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=${STORAGE_BUCKET}
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=${MESSAGING_SENDER_ID}
NEXT_PUBLIC_FIREBASE_APP_ID=${APP_ID_CFG}
EOF
echo "  ✓ ${OUT_FILE} written"

cat <<EOF

\033[1;32m✓ Firebase bootstrap complete.\033[0m

Next steps:

  1. Source or cat ${OUT_FILE} into web/.env.local for local dev:
       cat ${OUT_FILE} >> web/.env.local
     Or pass as build-args via web/cloudbuild.yaml for Cloud Run builds.

  2. (Optional) Enable Google sign-in.
     Google provider requires OAuth consent screen + brand review which
     is partly console-only. Two-click path:
       https://console.firebase.google.com/project/${PROJECT_ID}/authentication/providers
     → enable "Google" → set the support email → save.

  3. Flip FIREBASE_AUTH_ENABLED=true in your backend cloudbuild
     substitutions on your next deploy.

EOF
