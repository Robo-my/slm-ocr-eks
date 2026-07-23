# EKS Deployment Guide

> This guide grows week by week alongside the build. Sections marked 🚧 are placeholders that get filled when the corresponding course week lands.

## Prerequisites (Week 0)

- AWS account with MRANTI credits applied
- CLI tooling: `aws` (v2), `terraform` (>= 1.7), `kubectl`, `helm`
- `aws sts get-caller-identity` returns your account
- Service Quotas approved:
  - **Running On-Demand P instances** ≥ 96 vCPUs (one `p4d.24xlarge`)
  - **Running On-Demand G and VT instances** ≥ 8 vCPUs (one `g4dn.xlarge`, headroom for 2)
- AWS Budgets alarm configured below the credit ceiling

## Week 1 — Cluster provisioning 🚧

Terraform: VPC, EKS cluster, managed node groups (`system` CPU, `apinp` CPU-optimized, `redisnp` high-mem, `gpunpt4` T4, `gpunpa100` A100 at `desired_size = 0`), NVIDIA device plugin, taints/tolerations.

```bash
cd terraform/envs/dev
terraform init
terraform plan
```

## Week 3 — vLLM server 🚧

Build & push `services/vllm-server` to ECR, deploy `k8s/eks/apps/deployment-vlm.yml`, benchmark on A100, scale back to zero.

## Week 4 — Rust ingest gateway 🚧

## Week 5 — Worker, Redis & KEDA 🚧

## Week 6 — API Gateway, Cognito & MCP 🚧
