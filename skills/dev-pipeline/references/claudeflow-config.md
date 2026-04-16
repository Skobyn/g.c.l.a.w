# claudeflow Configuration

## Installation

```bash
npx claude-flow@latest init
```

## Key Agents

### GitHub Integration

```bash
npx claude-flow agent spawn github-integration
```

Features:
- Automated code review on PRs
- Issue triage and labeling
- Release management
- Changelog generation

### Workflow Automation

```bash
npx claude-flow agent spawn workflow-automation
```

Features:
- CI/CD pipeline management
- Testing automation
- Deployment coordination

### Code Review

```bash
npx claude-flow agent spawn code-review
```

Features:
- Multi-agent code analysis
- Security scanning
- Style enforcement
- Suggestions and fixes

## Configuration File

Create `.claude-flow/config.json`:

```json
{
  "agents": {
    "github": {
      "enabled": true,
      "autoReview": true,
      "autoMerge": false
    },
    "codeReview": {
      "enabled": true,
      "strictMode": false
    }
  },
  "github": {
    "owner": "your-username",
    "repo": "your-repo",
    "defaultBranch": "main"
  },
  "checkpointing": {
    "enabled": true,
    "autoRelease": true
  }
}
```

## Auto-Checkpointing

claudeflow creates GitHub releases as checkpoints:
- Automatic on significant changes
- Enables easy rollback
- Preserves task context

## Running Workflows

```bash
# Run a workflow file
npx claude-flow workflow run my-workflow.json

# With Claude Code integration
npx claude-flow workflow run my-workflow.json --claude --non-interactive
```

## Best Practices

1. Start with github-integration for PR automation
2. Enable checkpointing early
3. Use code-review agent for quality gates
4. Configure auto-merge only after trust is established
