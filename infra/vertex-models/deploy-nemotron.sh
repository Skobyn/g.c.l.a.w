#!/usr/bin/env bash
# Deploy Nemotron 3 Super via Vertex AI Model Garden.
#
# Prerequisites:
#   - gcloud CLI authenticated
#   - Vertex AI API enabled
#   - Sufficient GPU quota (A100 80GB recommended for 120B MoE)
#
# Usage:
#   ./deploy-nemotron.sh [PROJECT_ID] [REGION]

set -euo pipefail

PROJECT_ID="${1:-${GCP_PROJECT_ID:-}}"
if [[ -z "$PROJECT_ID" ]]; then
  echo "Usage: $0 <PROJECT_ID> [REGION]" >&2
  echo "       (or set \$GCP_PROJECT_ID in the environment)" >&2
  exit 2
fi
REGION="${2:-us-central1}"
ENDPOINT_NAME="gclaw-nemotron3-super"
MACHINE_TYPE="a2-ultragpu-1g"
ACCELERATOR_TYPE="NVIDIA_A100_80GB"
ACCELERATOR_COUNT=1

echo "==> Deploying Nemotron 3 Super to Vertex AI"
echo "    Project: ${PROJECT_ID}"
echo "    Region:  ${REGION}"
echo "    Machine: ${MACHINE_TYPE} (${ACCELERATOR_COUNT}x ${ACCELERATOR_TYPE})"

ENDPOINT_ID=$(gcloud ai endpoints list \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --filter="displayName=${ENDPOINT_NAME}" \
    --format="value(name)" 2>/dev/null || true)

if [ -z "${ENDPOINT_ID}" ]; then
    echo "==> Creating endpoint: ${ENDPOINT_NAME}"
    gcloud ai endpoints create \
        --project="${PROJECT_ID}" \
        --region="${REGION}" \
        --display-name="${ENDPOINT_NAME}"

    ENDPOINT_ID=$(gcloud ai endpoints list \
        --project="${PROJECT_ID}" \
        --region="${REGION}" \
        --filter="displayName=${ENDPOINT_NAME}" \
        --format="value(name)")
fi

echo "==> Endpoint ID: ${ENDPOINT_ID}"

echo "==> Uploading Nemotron 3 Super from Model Garden"
gcloud ai models upload \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --display-name="nemotron-3-super-120b" \
    --container-image-uri="us-docker.pkg.dev/vertex-ai/prediction/vllm-serve:latest" \
    --artifact-uri="gs://vertex-model-garden-public-us/nvidia/nemotron-3-super-120b-instruct" \
    --container-args="--model=nvidia/nemotron-3-super-120b-instruct,--max-model-len=131072,--tensor-parallel-size=1"

MODEL_RESOURCE=$(gcloud ai models list \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --filter="displayName=nemotron-3-super-120b" \
    --sort-by="~createTime" \
    --limit=1 \
    --format="value(name)")

echo "==> Deploying model to endpoint"
gcloud ai endpoints deploy-model "${ENDPOINT_ID}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --model="${MODEL_RESOURCE}" \
    --display-name="nemotron-3-super-serving" \
    --machine-type="${MACHINE_TYPE}" \
    --accelerator-type="${ACCELERATOR_TYPE}" \
    --accelerator-count="${ACCELERATOR_COUNT}" \
    --min-replica-count=0 \
    --max-replica-count=1

echo "==> Done. Set this in your .env:"
echo "    NEMOTRON_ENDPOINT_ID=${ENDPOINT_ID}"
echo "    NEMOTRON_PROVIDER=vertex"
