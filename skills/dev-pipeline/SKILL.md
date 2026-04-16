---
name: dev-pipeline
description: Set up a complete development pipeline for new projects. Creates GitHub repo, configures Claude Code CLI + claudeflow for AI-assisted development, and sets up GCP Cloud Run deployment with GitHub Actions CI/CD. Use when starting a new project, setting up dev infrastructure, or asking about development workflows.
---

# Dev Pipeline Skill

Sets up a production-ready development pipeline for any new project.

## What It Creates

1. **GitHub Repository** - Initialized with proper structure
2. **Claude Code CLI** - For AI-assisted development
3. **claudeflow** - Agent orchestration, code review, auto-checkpointing
4. **GCP Cloud Run** - Containerized deployment
5. **GitHub Actions CI/CD** - Auto-deploy on push to main

## Prerequisites (User Must Provide)

- GitHub Personal Access Token (PAT) with `repo` scope
- GCP Project ID
- GCP Service Account key (JSON) with Cloud Run permissions
- Anthropic API key (for Claude Code)

## Quick Start

```bash
# Run the full setup
./skills/dev-pipeline/scripts/init-project.sh \
  --name "project-name" \
  --github-user "username" \
  --gcp-project "project-id" \
  --stack "python"  # or "node"
```

## Manual Setup Steps

### 1. Install Claude Code CLI

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

Or via npm (deprecated but works):
```bash
npm install -g @anthropic-ai/claude-code
```

### 2. Configure GitHub

```bash
# Install GitHub CLI
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt update && sudo apt install gh -y

# Authenticate
gh auth login

# Or use PAT directly
export GITHUB_TOKEN="your-pat-here"
```

### 3. Install claudeflow

```bash
npx claude-flow@latest init
```

Configure for GitHub integration:
```bash
npx claude-flow agent spawn github-integration
```

### 4. Set Up GCP

```bash
# Install gcloud CLI
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
gcloud init

# Authenticate
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Enable required APIs
gcloud services enable run.googleapis.com cloudbuild.googleapis.com containerregistry.googleapis.com
```

### 5. Create GitHub Actions Workflow

See `references/github-actions.md` for workflow templates.

### 6. Create Dockerfile

See `references/dockerfile-templates.md` for stack-specific templates.

## Project Structure Created

```
project-name/
├── .github/
│   └── workflows/
│       └── deploy.yml      # CI/CD pipeline
├── .claude/
│   └── settings.json       # Claude Code config
├── Dockerfile              # Container definition
├── cloudbuild.yaml         # GCP Cloud Build config
├── requirements.txt        # (Python) or package.json (Node)
└── app/
    └── main.py             # (or index.js)
```

## References

- `references/github-actions.md` - CI/CD workflow templates
- `references/gcp-cloudrun.md` - Cloud Run deployment guide
- `references/dockerfile-templates.md` - Dockerfiles for Python/Node
- `references/claudeflow-config.md` - claudeflow setup and agents

## Assets

- `assets/workflows/` - GitHub Actions YAML templates
- `assets/docker/` - Dockerfile templates
- `assets/cloudbuild/` - GCP Cloud Build configs
