# Vertex AI Model Deployments

Deployment scripts and configuration for running large language models on Google Cloud Vertex AI.

## Supported Models

| Model | Provider | Parameters | Architecture | GPUs | Machine Type | Max Context |
|-------|----------|-----------|--------------|------|--------------|-------------|
| Gemma 4 31B | Google | 31B | Dense | 4x L4 | g2-standard-48 | 65K tokens |
| Nemotron 3 Super | NVIDIA | 120B | MoE | 1x A100 80GB | a2-ultragpu-1g | 131K tokens |

## Prerequisites

- **gcloud CLI** — authenticated with appropriate IAM permissions
- **Vertex AI API** — enabled on target GCP project
- **GPU Quota** — sufficient quota for target machine type and region
- **Project Setup** — compute project and Firestore project configured

### Required IAM Permissions

- `aiplatform.endpoints.create`
- `aiplatform.endpoints.deployModel`
- `aiplatform.models.upload`
- `aiplatform.models.get`
- `aiplatform.models.list`
- `compute.instances.create` (for underlying compute)

## Deployment

All scripts accept optional `PROJECT_ID` and `REGION` arguments:

```bash
./deploy-gemma4.sh [PROJECT_ID] [REGION]
./deploy-nemotron.sh [PROJECT_ID] [REGION]
```

### Deploy Gemma 4 31B

```bash
# Default: apexfoundation project, us-central1 region
./deploy-gemma4.sh

# Custom project and region
./deploy-gemma4.sh my-project us-west1
```

Deployment time: **15-25 minutes** (model upload + endpoint configuration)

### Deploy Nemotron 3 Super

```bash
# Default: apexfoundation project, us-central1 region
./deploy-nemotron.sh

# Custom project and region
./deploy-nemotron.sh my-project europe-west1
```

Deployment time: **20-30 minutes** (larger model, more inference optimization)

## Environment Variables

After successful deployment, set these variables in your `.env`:

```bash
# Gemma 4 Endpoint
GEMMA_ENDPOINT_ID=projects/123456/locations/us-central1/endpoints/1234567890
GEMMA_PROJECT_ID=apexfoundation
GEMMA_REGION=us-central1
GEMMA_PROVIDER=vertex

# Nemotron 3 Super Endpoint
NEMOTRON_ENDPOINT_ID=projects/123456/locations/us-central1/endpoints/9876543210
NEMOTRON_PROJECT_ID=apexfoundation
NEMOTRON_REGION=us-central1
NEMOTRON_PROVIDER=vertex
```

Endpoint IDs are printed at the end of each deployment script.

## Cost Estimates (Monthly, us-central1)

**Gemma 4 31B** on g2-standard-48 (4x L4):
- Compute: ~$4,000/month
- Storage: ~$50/month
- **Total: ~$4,050/month**

**Nemotron 3 Super** on a2-ultragpu-1g (1x A100 80GB):
- Compute: ~$8,000/month
- Storage: ~$100/month
- **Total: ~$8,100/month**

_Costs assume 24/7 availability with 0-1 replica scaling. Production workloads may require larger replica counts._

## Monitoring

### View Endpoint Status

```bash
gcloud ai endpoints list --project=apexfoundation --region=us-central1
gcloud ai endpoints describe ENDPOINT_ID --project=apexfoundation --region=us-central1
```

### View Model Deployments

```bash
gcloud ai endpoints describe ENDPOINT_ID \
    --project=apexfoundation \
    --region=us-central1 \
    --format="value(deployedModels[].displayName)"
```

### Check Quotas

```bash
gcloud compute project-info describe --project=apexfoundation \
    --format="table(quotas[name,usage,limit].select(name,usage,limit))"
```

## Troubleshooting

### GPU Quota Exceeded

Check available quota and request increase if needed:

```bash
gcloud compute project-info describe --project=apexfoundation \
    --format="table(quotas[name,usage,limit])"
```

Quota requests through GCP Console typically take 1-3 business days.

### Model Upload Fails

Verify Model Garden bucket access:

```bash
gsutil ls gs://vertex-model-garden-public-us/
```

### Deployment Timeout

Check endpoint creation status:

```bash
gcloud ai endpoints describe ENDPOINT_ID \
    --project=apexfoundation \
    --region=us-central1
```

Deployments can take 20-30 minutes. Monitor via Cloud Console.

## References

- [Vertex AI Model Garden](https://cloud.google.com/vertex-ai/docs/model-garden/overview)
- [vLLM Serving Container](https://github.com/lm-sys/vllm)
- [Gemma Model Card](https://huggingface.co/google/gemma-4-31b-it)
- [Nemotron Model Card](https://huggingface.co/nvidia/Nemotron-3-Super-120B-Instruct)
