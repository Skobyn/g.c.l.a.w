# Phoenix — gclaw OTLP sink

Arize Phoenix runs as a second Cloud Run service (`phoenix`) in the
same GCP project as the gclaw backend, acting as a rich trace/eval
UI on top of the same OpenInference spans gclaw already ships to
Cloud Trace. Data never leaves the project.

```
gclaw-backend (Cloud Run) ──OTLP/HTTP──> phoenix (Cloud Run) ──> Cloud SQL Postgres
                         └─OTLP──> Cloud Trace  (primary sink, in-project)
```

## Provisioning + deploy

The main [`README.md`](../../README.md#phoenix-observability) has
the three-step quickstart. TL;DR:

```bash
./scripts/bootstrap-phoenix.sh <your-project>          # one-time infra
gcloud builds submit --config infra/phoenix/cloudbuild.yaml ...  # deploy
# then wire the OTEL endpoint secret + redeploy the backend
```

`scripts/bootstrap-phoenix.sh` handles the Cloud SQL instance, VPC
connector, service account, IAM bindings, and Secret Manager entries
(`phoenix-sql-url`, `phoenix-auth-secret`). It's idempotent — re-run
safely.

## Rollback

Phoenix failures never take down gclaw (`init_tracing` is fail-soft
and the OTLP exporter swallows errors). To roll back the Phoenix
service itself:

```bash
# Freeze the current revision, stop serving traffic:
gcloud run services update-traffic phoenix \
  --to-revisions=LATEST=0 --region=us-central1 --project=<your-project>

# OR roll back to a specific previous revision:
gcloud run revisions list --service=phoenix --region=us-central1 --project=<your-project>
gcloud run services update-traffic phoenix \
  --to-revisions=<previous-revision>=100 --region=us-central1 --project=<your-project>
```

To fully disable ingestion without tearing down the Phoenix service
or Cloud SQL instance, flip the backend's `OBSERVABILITY_ENABLED=false`
via a Cloud Run service update. Cloud Trace will keep receiving
spans (in-project, zero cost increase).

## License

Arize Phoenix is distributed under the **Elastic License 2.0**.
Self-host for internal use is fine; redistribution or offering
Phoenix as a managed service to third parties is not. Review
<https://github.com/Arize-ai/phoenix/blob/main/LICENSE> before
changing the deployment model (e.g. exposing Phoenix publicly).
