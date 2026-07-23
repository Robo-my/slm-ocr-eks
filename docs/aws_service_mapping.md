# Azure/GCP → AWS Service Mapping

The upstream course targets AKS (Azure) and GKE (GCP). This document is the canonical mapping used for the EKS port, plus the discrepancies that matter.

## Core mapping

| Concern | Azure (course) | GCP (course) | AWS (this repo) |
| :--- | :--- | :--- | :--- |
| Managed Kubernetes | AKS | GKE | **EKS** |
| Container registry | ACR | Artifact Registry | **ECR** |
| T4 layout pool | `Standard_NC4as_T4_v3` pool | `n1-standard-4` + T4 | **`g4dn.xlarge`** managed node group |
| A100 inference pool | `Standard_NC24ads_A100_v4` | `a2-highgpu-1g` | **`p4d.24xlarge`** node group (8× A100 40GB) |
| GPU drivers | NVIDIA GPU Operator (Helm) | GKE built-in drivers | NVIDIA device plugin or GPU Operator (decided Week 1) |
| API gateway | Azure APIM | GCP API Gateway / Apigee | **AWS API Gateway (HTTP API)** |
| Private backend link | APIM internal VNet mode | Private service connect | **VPC Link → internal NLB** |
| JWT auth | Entra ID | GCP IAM | **Cognito user pool JWT authorizer** |
| Internal LB | `azure-load-balancer-internal` annotation | `networking.gke.io/load-balancer-type: Internal` | **AWS Load Balancer Controller**, `service.beta.kubernetes.io/aws-load-balancer-scheme: internal` |
| IaC | `az` CLI scripts | `gcloud` CLI scripts | **Terraform** (`terraform/`) |
| Cost guardrail | — | — | AWS Budgets alarm + scale-to-zero A100 group |

## Cloud-agnostic components (port unchanged)

- Redis (in-cluster deployment on a high-memory node group)
- KEDA (Helm install; Redis list scaler + Prometheus scaler)
- vLLM server image + Qwen 3.5 4B
- GLM-OCR SDK / PP-DocLayoutV3 worker
- Rust Axum producer, Python consumer

## Known discrepancies to handle

1. **A100 granularity**: Azure/GCP offer single-A100 VMs; AWS's `p4d.24xlarge` is 8× A100. Either run one vLLM pod claiming 1 GPU (wasteful) or tune `nvidia.com/gpu` requests / MIG. Decision deferred to Week 3 (documented trade-off is itself portfolio material).
2. **Quotas**: P- and G-instance vCPU quotas default to 0 on new accounts — Service Quotas increase must be requested in advance (Week 0).
3. **Cluster autoscaler**: AKS/GKE have built-in node autoscaling; on EKS choose **Karpenter** vs **Cluster Autoscaler** (decided Week 1; Karpenter favored for scale-from-zero GPU pools).
4. **EKS add-ons**: VPC CNI, CoreDNS, kube-proxy, EBS CSI driver are explicit managed add-ons in Terraform, unlike AKS/GKE defaults.
