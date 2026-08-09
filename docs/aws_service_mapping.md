# Azure/GCP → AWS Service Mapping

The upstream course targets AKS (Azure) and GKE (GCP). This document is the canonical mapping used for the EKS port, plus the discrepancies that matter.

## Core mapping

| Concern | Azure (course) | GCP (course) | AWS (this repo) |
| :--- | :--- | :--- | :--- |
| Managed Kubernetes | AKS | GKE | **EKS** |
| Container registry | ACR | Artifact Registry | **ECR** |
| T4 layout pool | `Standard_NC4as_T4_v3` pool | `n1-standard-4` + T4 | **`g6.xlarge` (L4)** node group `gpunp-layout` — ap-southeast-5 offers only the g6 family |
| A100 inference pool | `Standard_NC24ads_A100_v4` | `a2-highgpu-1g` | **`g6.xlarge` (L4)** node group `gpunp-serving`; A100 (`p4d`, Singapore) is a deferred benchmark option |
| GPU drivers | NVIDIA GPU Operator (Helm) | GKE built-in drivers | **NVIDIA device plugin** (decided Week 1: single plugin suffices, EKS GPU AMI ships the driver) |
| API gateway | Azure APIM | GCP API Gateway / Apigee | **AWS API Gateway (HTTP API)** |
| Private backend link | APIM internal VNet mode | Private service connect | **VPC Link → internal NLB** |
| JWT auth | Entra ID | GCP IAM | **Cognito user pool JWT authorizer** |
| Internal LB | `azure-load-balancer-internal` annotation | `networking.gke.io/load-balancer-type: Internal` | **AWS Load Balancer Controller**, `service.beta.kubernetes.io/aws-load-balancer-scheme: internal` |
| IaC | `az` CLI scripts | `gcloud` CLI scripts | **Terraform** (`terraform/`) |
| Cost guardrail | — | — | AWS Budgets alarm + scale-to-zero GPU groups |
| Batch variant trigger (Lecture Note II §7) | Blob event → Storage Queue → KEDA | GCS event → Pub/Sub → KEDA | **S3 event notification → SQS → KEDA `aws-sqs-queue` scaler** |

## Cloud-agnostic components (port unchanged)

- Redis (in-cluster deployment on a high-memory node group)
- KEDA (Helm install; Redis list scaler + Prometheus scaler)
- vLLM server image + Qwen 3.5 4B
- GLM-OCR SDK / PP-DocLayoutV3 worker
- Rust Axum producer, Python consumer

## Known discrepancies to handle

1. **GPU availability is region-shaped**: ap-southeast-5 has no g4dn/g5/P instances at all — only g6 (L4). Both tiers therefore run `g6.xlarge`; the architecture (separate tainted groups, separate scalers) is unchanged and instance types are one-line swaps. The old A100-granularity question (`p4d` = 8× A100) only returns if a Singapore benchmark ever happens.
2. **Quotas**: G-instance vCPU quota confirmed ≥ 4 in ap-southeast-5 (probe launch succeeded, Week 0).
3. **Cluster autoscaler**: AKS/GKE have built-in node autoscaling; on EKS choose **Karpenter** vs **Cluster Autoscaler** (decided Week 1; Karpenter favored for scale-from-zero GPU pools).
4. **EKS add-ons**: VPC CNI, CoreDNS, kube-proxy, EBS CSI driver are explicit managed add-ons in Terraform, unlike AKS/GKE defaults.
