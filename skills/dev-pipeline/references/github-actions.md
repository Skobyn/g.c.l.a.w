# GitHub Actions Workflows

## CI/CD with GCP Cloud Run

The `deploy-cloudrun.yml` workflow:

1. Triggers on push to `main`
2. Builds Docker image
3. Pushes to Google Container Registry
4. Deploys to Cloud Run

### Required GitHub Secrets

| Secret | Description |
|--------|-------------|
| `GCP_PROJECT_ID` | Your GCP project ID |
| `GCP_SA_KEY` | Service account JSON with Cloud Run Admin + Storage Admin |

### Creating a Service Account

```bash
# Create service account
gcloud iam service-accounts create github-actions \
  --display-name="GitHub Actions"

# Grant permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"

# Create key
gcloud iam service-accounts keys create key.json \
  --iam-account=github-actions@$PROJECT_ID.iam.gserviceaccount.com

# Add to GitHub secrets (base64 encode the JSON)
cat key.json | base64
```

## CI Only (No Deployment)

Use `ci-only.yml` for projects not deploying to GCP. Runs tests and linting only.

## Branch Protection

Recommended settings for `main`:
- Require pull request reviews
- Require status checks to pass
- Require branches to be up to date
