# Branch protection for `main`

The PR-first deployment workflow assumes `main` is server-side protected.
Run these once — they require repo-admin or owner auth (`gh auth status`).

## 1. Protect `main`: require PR + approval + Test status check

The `Test (Python)` check comes from `.github/workflows/deploy.yml` on
`pull_request: branches: [main]`. `Claude Code Review` comes from
`.github/workflows/claude-code-review.yml`.

```bash
gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  /repos/<owner>/<repo>/branches/main/protection \
  -f required_status_checks[strict]=true \
  -f 'required_status_checks[contexts][]=Test (Python)' \
  -f 'required_status_checks[contexts][]=Claude Code Review / claude-review' \
  -F enforce_admins=true \
  -F 'required_pull_request_reviews[required_approving_review_count]=1' \
  -F required_pull_request_reviews[dismiss_stale_reviews]=false \
  -F required_pull_request_reviews[require_code_owner_reviews]=false \
  -F restrictions= \
  -F allow_force_pushes=false \
  -F allow_deletions=false \
  -F required_linear_history=true \
  -F required_conversation_resolution=true
```

If the API rejects either context name (typo / job renamed / first-run not yet
registered), open a throwaway PR first so GitHub has seen those check names at
least once, then re-run.

## 2. Enable repo-level auto-merge

`.github/workflows/auto-merge.yml` calls `gh pr merge --auto`. That requires
auto-merge to be enabled at the repo level.

```bash
gh api \
  --method PATCH \
  -H "Accept: application/vnd.github+json" \
  /repos/<owner>/<repo> \
  -F allow_auto_merge=true \
  -F allow_squash_merge=true \
  -F allow_merge_commit=false \
  -F allow_rebase_merge=false \
  -F delete_branch_on_merge=true \
  -F squash_merge_commit_title=PR_TITLE \
  -F squash_merge_commit_message=PR_BODY
```

## 3. Verify

```bash
gh api /repos/<owner>/<repo>/branches/main/protection --jq '{
  required_status_checks: .required_status_checks.contexts,
  required_reviews: .required_pull_request_reviews.required_approving_review_count,
  enforce_admins: .enforce_admins.enabled,
  allow_force_pushes: .allow_force_pushes.enabled
}'

gh api /repos/<owner>/<repo> --jq '{
  auto_merge: .allow_auto_merge,
  squash: .allow_squash_merge,
  merge_commit: .allow_merge_commit,
  rebase: .allow_rebase_merge,
  delete_branch_on_merge: .delete_branch_on_merge
}'
```

## 4. To undo (emergency)

```bash
gh api --method DELETE /repos/<owner>/<repo>/branches/main/protection
```
