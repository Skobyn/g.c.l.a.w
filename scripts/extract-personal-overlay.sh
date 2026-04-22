#!/usr/bin/env bash
#
# extract-personal-overlay.sh — one-time extraction of personal content
# from a previous git commit into a fresh private overlay repo.
#
# Use this when you've scrubbed the public repo of personal content
# (agent prompts, soul files, brand-specific skills) and want to
# reconstitute that content in a separate private overlay.
#
# What gets extracted (configurable below):
#   - agents/content-mgr.md          (your branded version)
#   - soul/content.md                (your real content voice)
#   - user.md                        (your filled-in identity, if any)
#   - skills/lyons-blog-pipeline/    (deleted-from-public skill)
#   - crons/                         (your schedule config)
#
# Usage:
#   ./scripts/extract-personal-overlay.sh [OVERLAY_DIR] [SOURCE_REF]
#
# Defaults:
#   OVERLAY_DIR  $HOME/dev/gclaw-overlay
#   SOURCE_REF   f1b5310  (commit before the open-source cleanup)
#
# After extraction, cd into OVERLAY_DIR and:
#   git init -b main
#   git add .
#   git commit -m "feat: initial overlay extracted from gclaw"
#   gh repo create <you>/gclaw-overlay --private --source=. --push

set -euo pipefail

OVERLAY_DIR="${1:-${HOME}/dev/gclaw-overlay}"
SOURCE_REF="${2:-f1b5310}"

cd "$(dirname "$0")/.."

# Verify the source ref exists
if ! git rev-parse --verify "${SOURCE_REF}^{commit}" >/dev/null 2>&1; then
  echo "Error: source ref '${SOURCE_REF}' does not exist in this repo" >&2
  exit 1
fi

# Files to lift from the source commit. Add to this list if you've
# personalized other paths.
FILES_TO_EXTRACT=(
  "agents/content-mgr.md"
  "soul/content.md"
  "user.md"
)

# Whole directories to lift verbatim.
DIRS_TO_EXTRACT=(
  "skills/lyons-blog-pipeline"
  "crons"
)

mkdir -p "${OVERLAY_DIR}"

echo "==> Extracting from ${SOURCE_REF} into ${OVERLAY_DIR}"

# Single files
for f in "${FILES_TO_EXTRACT[@]}"; do
  if git cat-file -e "${SOURCE_REF}:${f}" 2>/dev/null; then
    mkdir -p "${OVERLAY_DIR}/$(dirname "${f}")"
    git show "${SOURCE_REF}:${f}" > "${OVERLAY_DIR}/${f}"
    echo "  + ${f}"
  else
    echo "  - ${f} (not present at ${SOURCE_REF}, skipping)"
  fi
done

# Directories
for d in "${DIRS_TO_EXTRACT[@]}"; do
  mapfile -t paths < <(
    git ls-tree -r --name-only "${SOURCE_REF}" -- "${d}" 2>/dev/null
  )
  if [[ ${#paths[@]} -eq 0 ]]; then
    echo "  - ${d}/ (not present at ${SOURCE_REF}, skipping)"
    continue
  fi
  for f in "${paths[@]}"; do
    mkdir -p "${OVERLAY_DIR}/$(dirname "${f}")"
    git show "${SOURCE_REF}:${f}" > "${OVERLAY_DIR}/${f}"
  done
  echo "  + ${d}/ (${#paths[@]} files)"
done

# Drop a starter README + .gitignore so the overlay is push-ready
if [[ ! -f "${OVERLAY_DIR}/README.md" ]]; then
  cat > "${OVERLAY_DIR}/README.md" <<EOF
# gclaw-overlay (private)

Personal overlay for [gclaw](https://github.com/Skobyn/gclaw). Files
here are rsync'd onto the public framework at deploy time via
\`scripts/deploy.sh\` (with OVERLAY pointed at this directory).

Never push to a public remote.
EOF
  echo "  + README.md"
fi

if [[ ! -f "${OVERLAY_DIR}/.gitignore" ]]; then
  cat > "${OVERLAY_DIR}/.gitignore" <<EOF
.env
.env.local
*.key
*.pem
*.p12
*credentials*.json
*service-account*.json
*-sa.json
__pycache__/
*.pyc
.DS_Store
EOF
  echo "  + .gitignore"
fi

cat <<EOF

\033[1;32m✓ Extraction complete.\033[0m

Next steps:
  cd ${OVERLAY_DIR}
  git init -b main
  git add .
  git commit -m "feat: initial overlay extracted from gclaw ${SOURCE_REF}"
  gh repo create <you>/gclaw-overlay --private --source=. --push

Then deploy with the overlay applied:
  cd $(pwd)
  OVERLAY=${OVERLAY_DIR} ./scripts/deploy.sh <PROJECT_ID>
EOF
