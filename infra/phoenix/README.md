# Phoenix — gclaw OTLP sink

Arize Phoenix runs as a second Cloud Run service (`phoenix`) in the
same GCP project as the gclaw backend, acting as a rich trace/eval UI
on top of the same OpenInference spans gclaw already ships to Cloud
Trace. Data never leaves the project.

```
gclaw-backend (Cloud Run) ──OTLP/HTTP──> phoenix (Cloud Run) ──> Cloud SQL Postgres
                         └─OTLP──> Cloud Trace  (primary sink, in-project)
```

## One-time provisioning

These steps are **manual** — the CI loop writes IaC but doesn't create
cloud resources. Run them once per environment before the first
`deploy-phoenix` workflow run.

All commands assume `--project=<your-project>`. Substitute your own
project ID if forking.

### 1. Enable required APIs

```bash
gcloud services enable \
  sqladmin.googleapis.com \
  vpcaccess.googleapis.com \
  secretmanager.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  --project=<your-project>
```

### 2. Create the runtime service account

```bash
gcloud iam service-accounts create phoenix-run-sa \
  --display-name="Phoenix Cloud Run runtime" \
  --project=<your-project>

SA=phoenix-run-sa@<your-project>.iam.gserviceaccount.com

for role in roles/cloudsql.client roles/logging.logWriter \
            roles/secretmanager.secretAccessor roles/monitoring.metricWriter; do
  gcloud projects add-iam-policy-binding <your-project> \
    --member="serviceAccount:${SA}" --role="${role}" --quiet
done
```

### 3. Cloud SQL Postgres

```bash
# db_f1_micro is fine for moderate trace volume; bump to db-custom-1-3840
# once ingestion exceeds ~100k spans/day.
gcloud sql instances create phoenix-db \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=us-central1 \
  --network=default \
  --no-assign-ip \
  --project=<your-project>

gcloud sql databases create phoenix \
  --instance=phoenix-db \
  --project=<your-project>

# Generate a strong password for the phoenix user.
PHOENIX_DB_PASS=$(openssl rand -base64 32)
gcloud sql users create phoenix \
  --instance=phoenix-db \
  --password="${PHOENIX_DB_PASS}" \
  --project=<your-project>

# Record the connection URL in Secret Manager (Phoenix reads this from
# PHOENIX_SQL_DATABASE_URL at startup). The `host=/cloudsql/...` form
# uses the Cloud SQL Auth Proxy socket that Cloud Run mounts when the
# service has the cloudsql.client role + an `--add-cloudsql-instances`
# flag. We use the VPC connector path instead for lower latency.
INSTANCE_CONN=$(gcloud sql instances describe phoenix-db \
  --project=<your-project> --format='value(connectionName)')
PRIVATE_IP=$(gcloud sql instances describe phoenix-db \
  --project=<your-project> --format='value(ipAddresses[0].ipAddress)')

printf 'postgresql+psycopg://phoenix:%s@%s:5432/phoenix' \
  "${PHOENIX_DB_PASS}" "${PRIVATE_IP}" \
  | gcloud secrets create phoenix-sql-url \
      --data-file=- --project=<your-project>

gcloud secrets add-iam-policy-binding phoenix-sql-url \
  --member="serviceAccount:${SA}" \
  --role=roles/secretmanager.secretAccessor \
  --project=<your-project>
```

Set up a budget alert at $20/mo on the Cloud SQL line item (Console →
Billing → Budgets & alerts → New budget → filter to Cloud SQL).

### 4. VPC connector

```bash
gcloud compute networks vpc-access connectors create gclaw-connector \
  --region=us-central1 \
  --network=default \
  --range=10.8.0.0/28 \
  --project=<your-project>
```

(Reuse an existing connector if you already have one — just update
`_VPC_CONNECTOR` in `infra/phoenix/cloudbuild.yaml`.)

### 5. Grant the deployer SA permission to manage Phoenix

The existing GitHub Actions deployer (`gclaw-deployer`) needs to be
able to deploy the new service:

```bash
DEPLOYER=gclaw-deployer@<your-project>.iam.gserviceaccount.com

# Cloud Run deploy + SA impersonation (to assign phoenix-run-sa to the service).
gcloud projects add-iam-policy-binding <your-project> \
  --member="serviceAccount:${DEPLOYER}" \
  --role=roles/run.admin --quiet

gcloud iam service-accounts add-iam-policy-binding phoenix-run-sa@<your-project>.iam.gserviceaccount.com \
  --member="serviceAccount:${DEPLOYER}" \
  --role=roles/iam.serviceAccountUser --quiet
```

### 6. Wire the backend to the Phoenix URL

After the first successful `deploy-phoenix` workflow run, grab the
service URL and set it as a Secret Manager entry the backend reads:

```bash
PHOENIX_URL=$(gcloud run services describe phoenix \
  --region=us-central1 --project=<your-project> --format='value(status.url)')

# Phoenix's OTLP/HTTP ingress is at /v1/traces on the service URL.
printf '%s/v1/traces' "${PHOENIX_URL}" \
  | gcloud secrets create otel-exporter-otlp-endpoint \
      --data-file=- --project=<your-project>
```

Then update `cloudbuild.yaml` (root) to inject it:

```yaml
- --set-secrets=...,OTEL_EXPORTER_OTLP_ENDPOINT=otel-exporter-otlp-endpoint:latest
- --set-env-vars=...,OBSERVABILITY_ENABLED=true
```

## Rollback

Phoenix failures never take down gclaw (`init_tracing` is fail-soft and
the OTLP exporter errors are swallowed). To roll back:

```bash
# Freeze the current revision, stop serving traffic:
gcloud run services update-traffic phoenix \
  --to-revisions=LATEST=0 --region=us-central1 --project=<your-project>

# OR roll back to a specific previous revision:
gcloud run revisions list --service=phoenix --region=us-central1 --project=<your-project>
gcloud run services update-traffic phoenix \
  --to-revisions=<previous-revision>=100 --region=us-central1 --project=<your-project>
```

If you want to fully disable ingestion without a redeploy, flip the
backend's `OBSERVABILITY_ENABLED=false` via a Cloud Run service update —
Cloud Trace will keep receiving spans (in-project, zero cost increase).

## License note

Arize Phoenix is distributed under the **Elastic License 2.0**. Self-host
is allowed for internal use; redistribution and providing Phoenix as a
managed service to third parties is not. Review the license text at
<https://github.com/Arize-ai/phoenix/blob/main/LICENSE> before changing
the deployment model (e.g. exposing Phoenix publicly).
