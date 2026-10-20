# AWS Service Choices

The AWS services this pipeline is built on, why each was chosen, and the AWS-specific details that matter.

## Core services

| Concern | AWS choice | Why |
| :--- | :--- | :--- |
| Managed Kubernetes | **EKS** | KEDA, vLLM and the workers are Kubernetes-native; EKS keeps the control plane managed |
| Container registry | **ECR** | Same-region pulls into private subnets, IAM-scoped access |
| Layout tier | **`g6.xlarge` (L4)** node group `gpunp-layout` | ap-southeast-5 offers only the g6 family; one GPU per worker pod |
| Serving tier | **`g6.xlarge` (L4)** node group `gpunp-serving` | Same family, separate group so each tier taints and scales on its own signal |
| GPU drivers | **NVIDIA device plugin** | The EKS GPU AMI ships the driver; the plugin alone exposes `nvidia.com/gpu` (decided Week 1) |
| API gateway | **AWS API Gateway (HTTP API)** | Managed throttling and JWT auth at the edge, pay-per-request |
| Private backend link | **VPC Link → internal NLB** | The cluster stays private; only API Gateway reaches it |
| JWT auth | **Cognito user pool JWT authorizer** | Native HTTP API authorizer, no custom auth code |
| Internal LB | **AWS Load Balancer Controller**, `service.beta.kubernetes.io/aws-load-balancer-scheme: internal` | Provisions the NLB from a Kubernetes Service |
| IaC | **Terraform** (`terraform/`) | Declarative, reviewable, and `destroy` gives a clean $0 idle state |
| Cost guardrail | AWS Budgets alarm + scale-to-zero GPU groups | GPU spend only while work is queued |
| Batch variant trigger | **S3 event notification → SQS → KEDA `aws-sqs-queue` scaler** | Swaps the ingest adapter only; the orchestration core is untouched |

## Cloud-agnostic components

- Redis (in-cluster deployment on a dedicated node group)
- KEDA (Helm install; Redis list scaler + Prometheus scaler)
- vLLM server image
- GLM-OCR SDK / PP-DocLayoutV3 worker
- Rust Axum producer, Python consumer

## Design notes

1. **GPU availability is region-shaped**: ap-southeast-5 has no g4dn/g5/P instances at all — only g6 (L4). Both tiers therefore run `g6.xlarge`; the architecture (separate tainted groups, separate scalers) is unchanged and instance types are one-line swaps. A100 (`p4d` = 8× A100, Singapore only) is a deferred benchmark option.
2. **Quotas**: G-instance vCPU quota confirmed ≥ 4 in ap-southeast-5 (probe launch succeeded, Week 0).
3. **Node autoscaler**: KEDA scales pods, not nodes. A pending GPU pod on an empty node group needs **Karpenter** or **Cluster Autoscaler** to create the node; Karpenter is favored for scale-from-zero GPU pools and lands before the first GPU workload (Week 3).
4. **EKS add-ons**: VPC CNI, CoreDNS, kube-proxy, EBS CSI driver are explicit managed add-ons in Terraform.
