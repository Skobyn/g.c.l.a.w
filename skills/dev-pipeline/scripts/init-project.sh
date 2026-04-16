#!/bin/bash
set -e

# Dev Pipeline - Project Initializer
# Creates a complete dev environment with GitHub, Claude Code, claudeflow, and GCP

print_usage() {
    echo "Usage: $0 --name <project-name> --github-user <username> --gcp-project <project-id> --stack <python|node>"
    echo ""
    echo "Options:"
    echo "  --name          Project name (lowercase, hyphens ok)"
    echo "  --github-user   GitHub username or org"
    echo "  --gcp-project   GCP project ID"
    echo "  --stack         Tech stack: python or node"
    echo "  --private       Make GitHub repo private (default: public)"
    echo "  --skip-gcp      Skip GCP setup"
    echo "  --skip-claude   Skip Claude Code CLI setup"
    echo ""
    echo "Environment variables:"
    echo "  GITHUB_TOKEN    GitHub PAT (required if gh not authenticated)"
    echo "  GCP_SA_KEY      Path to GCP service account JSON"
}

# Defaults
PRIVATE=true
SKIP_GCP=false
SKIP_CLAUDE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --name) PROJECT_NAME="$2"; shift 2 ;;
        --github-user) GITHUB_USER="$2"; shift 2 ;;
        --gcp-project) GCP_PROJECT="$2"; shift 2 ;;
        --stack) STACK="$2"; shift 2 ;;
        --private) PRIVATE=true; shift ;;
        --skip-gcp) SKIP_GCP=true; shift ;;
        --skip-claude) SKIP_CLAUDE=true; shift ;;
        --help) print_usage; exit 0 ;;
        *) echo "Unknown option: $1"; print_usage; exit 1 ;;
    esac
done

# Validate required args
if [[ -z "$PROJECT_NAME" || -z "$GITHUB_USER" || -z "$STACK" ]]; then
    echo "Error: Missing required arguments"
    print_usage
    exit 1
fi

if [[ "$STACK" != "python" && "$STACK" != "node" ]]; then
    echo "Error: Stack must be 'python' or 'node'"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

echo "=========================================="
echo "Dev Pipeline Setup: $PROJECT_NAME"
echo "Stack: $STACK"
echo "GitHub: $GITHUB_USER/$PROJECT_NAME"
echo "GCP: ${GCP_PROJECT:-skipped}"
echo "=========================================="

# Create project directory
mkdir -p "$PROJECT_NAME"
cd "$PROJECT_NAME"

echo ""
echo "[1/7] Initializing Git repository..."
git init
echo "# $PROJECT_NAME" > README.md
git add README.md
git commit -m "Initial commit"

echo ""
echo "[2/7] Creating project structure..."
mkdir -p app .github/workflows .claude

# Create stack-specific files
if [[ "$STACK" == "python" ]]; then
    cp "$SKILL_DIR/assets/docker/Dockerfile.python" Dockerfile
    cat > requirements.txt << 'EOF'
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
pydantic>=2.0.0
python-dotenv>=1.0.0
EOF
    cat > app/main.py << 'EOF'
from fastapi import FastAPI

app = FastAPI(title="API")

@app.get("/")
def root():
    return {"status": "ok"}

@app.get("/health")
def health():
    return {"healthy": True}
EOF
else
    cp "$SKILL_DIR/assets/docker/Dockerfile.node" Dockerfile
    cat > package.json << EOF
{
  "name": "$PROJECT_NAME",
  "version": "1.0.0",
  "main": "app/index.js",
  "scripts": {
    "start": "node app/index.js",
    "dev": "node --watch app/index.js"
  },
  "dependencies": {
    "express": "^4.18.2",
    "dotenv": "^16.3.1"
  }
}
EOF
    cat > app/index.js << 'EOF'
const express = require('express');
const app = express();
const PORT = process.env.PORT || 8080;

app.get('/', (req, res) => res.json({ status: 'ok' }));
app.get('/health', (req, res) => res.json({ healthy: true }));

app.listen(PORT, () => console.log(`Server running on port ${PORT}`));
EOF
fi

echo ""
echo "[3/7] Creating GitHub Actions workflow..."
if [[ "$SKIP_GCP" == "true" ]]; then
    cp "$SKILL_DIR/assets/workflows/ci-only.yml" .github/workflows/ci.yml
else
    sed "s/{{PROJECT_ID}}/$GCP_PROJECT/g; s/{{SERVICE_NAME}}/$PROJECT_NAME/g" \
        "$SKILL_DIR/assets/workflows/deploy-cloudrun.yml" > .github/workflows/deploy.yml
fi

echo ""
echo "[4/7] Creating Claude Code config..."
cat > .claude/settings.json << EOF
{
  "project": "$PROJECT_NAME",
  "model": "claude-sonnet-4-20250514",
  "permissions": {
    "allow_read": true,
    "allow_write": true,
    "allow_execute": true
  }
}
EOF

echo ""
echo "[5/7] Creating .gitignore..."
cat > .gitignore << 'EOF'
# Dependencies
node_modules/
__pycache__/
*.pyc
.venv/
venv/

# Environment
.env
.env.local
*.local

# IDE
.idea/
.vscode/
*.swp

# OS
.DS_Store
Thumbs.db

# Build
dist/
build/
*.egg-info/

# Logs
*.log
logs/
EOF

if [[ "$SKIP_GCP" == "false" && -n "$GCP_PROJECT" ]]; then
    echo ""
    echo "[6/7] Creating Cloud Build config..."
    sed "s/{{PROJECT_ID}}/$GCP_PROJECT/g; s/{{SERVICE_NAME}}/$PROJECT_NAME/g" \
        "$SKILL_DIR/assets/cloudbuild/cloudbuild.yaml" > cloudbuild.yaml
else
    echo ""
    echo "[6/7] Skipping GCP setup..."
fi

echo ""
echo "[7/7] Creating GitHub repository..."
VISIBILITY="--public"
if [[ "$PRIVATE" == "true" ]]; then
    VISIBILITY="--private"
fi

if command -v gh &> /dev/null; then
    gh repo create "$GITHUB_USER/$PROJECT_NAME" $VISIBILITY --source=. --push
elif [[ -n "$GITHUB_TOKEN" ]]; then
    # Create via API
    curl -X POST -H "Authorization: token $GITHUB_TOKEN" \
        -H "Accept: application/vnd.github.v3+json" \
        https://api.github.com/user/repos \
        -d "{\"name\":\"$PROJECT_NAME\",\"private\":$PRIVATE}"
    git remote add origin "https://github.com/$GITHUB_USER/$PROJECT_NAME.git"
    git push -u origin main
else
    echo "Warning: GitHub CLI not available and GITHUB_TOKEN not set"
    echo "Please create repo manually and run:"
    echo "  git remote add origin https://github.com/$GITHUB_USER/$PROJECT_NAME.git"
    echo "  git push -u origin main"
fi

echo ""
echo "=========================================="
echo "✅ Project $PROJECT_NAME created!"
echo ""
echo "Next steps:"
echo "  cd $PROJECT_NAME"
if [[ "$SKIP_CLAUDE" == "false" ]]; then
    echo "  claude  # Start Claude Code"
fi
echo "  npx claude-flow@latest init  # Set up claudeflow"
if [[ "$SKIP_GCP" == "false" ]]; then
    echo ""
    echo "GCP Setup (if not done):"
    echo "  gcloud config set project $GCP_PROJECT"
    echo "  gcloud services enable run.googleapis.com cloudbuild.googleapis.com"
    echo ""
    echo "Add GitHub secrets for CI/CD:"
    echo "  GCP_PROJECT_ID: $GCP_PROJECT"
    echo "  GCP_SA_KEY: <service account JSON>"
fi
echo "=========================================="
