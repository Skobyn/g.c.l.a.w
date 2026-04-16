# GCP Cloud Run Deployment

## Overview

Cloud Run is a fully managed serverless platform for containerized applications.

## Initial Setup

```bash
# Set project
gcloud config set project YOUR_PROJECT_ID

# Enable APIs
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  containerregistry.googleapis.com \
  artifactregistry.googleapis.com

# Set default region
gcloud config set run/region us-central1
```

## Manual Deployment

```bash
# Build and deploy in one command
gcloud run deploy SERVICE_NAME \
  --source . \
  --region us-central1 \
  --allow-unauthenticated
```

## Environment Variables

Set via console or CLI:

```bash
gcloud run services update SERVICE_NAME \
  --set-env-vars "KEY1=value1,KEY2=value2"
```

For secrets, use Secret Manager:

```bash
# Create secret
echo -n "secret-value" | gcloud secrets create my-secret --data-file=-

# Grant access to Cloud Run service account
gcloud secrets add-iam-policy-binding my-secret \
  --member="serviceAccount:SERVICE_ACCOUNT" \
  --role="roles/secretmanager.secretAccessor"

# Mount in Cloud Run
gcloud run services update SERVICE_NAME \
  --set-secrets "ENV_VAR=my-secret:latest"
```

## Custom Domain

```bash
# Map domain
gcloud run domain-mappings create \
  --service SERVICE_NAME \
  --domain your-domain.com \
  --region us-central1
```

Then add the DNS records shown.

## Scaling

```bash
# Set min/max instances
gcloud run services update SERVICE_NAME \
  --min-instances 1 \
  --max-instances 10

# Set concurrency
gcloud run services update SERVICE_NAME \
  --concurrency 80
```

## Costs

- Pay per request + compute time
- Free tier: 2 million requests/month
- Min instances incur cost even with no traffic
