#!/usr/bin/env bash
# Deploy Gemma 4 31B to a Vertex AI endpoint in the apexfoundation project.
#
# Prerequisites:
#   - gcloud CLI authenticated with sufficient permissions
#   - Vertex AI API enabled on the target project
#   - Sufficient GPU quota (L4 or A100 recommended for 31B)
#
# Usage:
#   ./deploy-gemma4.sh [PROJECT_ID] [REGION]

set -euo pipefail

PROJECT_ID="${1:-apexfoundation}"
REGION="${2:-us-central1}"
MODEL_ID="google/gemma-4-31b-it"
ENDPOINT_NAME="gclaw-gemma4-31b"
MACHINE_TYPE="g2-standard-48"
ACCELERATOR_TYPE="NVIDIA_L4"
ACCELERATOR_COUNT=4

echo "==> Deploying Gemma 4 31B to Vertex AI"
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

echo "==> Uploading model from Model Garden: ${MODEL_ID}"
gcloud ai models upload \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --display-name="gemma-4-31b-it" \
    --container-image-uri="us-docker.pkg.dev/vertex-ai/prediction/vllm-serve:latest" \
    --artifact-uri="gs://vertex-model-garden-public-us/${MODEL_ID}" \
    --container-args="--model=${MODEL_ID},--max-model-len=65536,--tensor-parallel-size=4"

MODEL_RESOURCE=$(gcloud ai models list \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --filter="displayName=gemma-4-31b-it" \
    --sort-by="~createTime" \
    --limit=1 \
    --format="value(name)")

echo "==> Deploying model to endpoint"
gcloud ai endpoints deploy-model "${ENDPOINT_ID}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --model="${MODEL_RESOURCE}" \
    --display-name="gemma-4-31b-serving" \
    --machine-type="${MACHINE_TYPE}" \
    --accelerator-type="${ACCELERATOR_TYPE}" \
    --accelerator-count="${ACCELERATOR_COUNT}" \
    --min-replica-count=0 \
    --max-replica-count=1

echo "==> Done. Set this in your .env:"
echo "    GEMMA_ENDPOINT_ID=${ENDPOINT_ID}"
