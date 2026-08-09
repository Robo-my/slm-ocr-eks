# EKS Deployment Guide

> This guide grows week by week alongside the build. Sections marked 🚧 are placeholders that get filled when the corresponding course week lands.

## Prerequisites (Week 0)

- AWS account with MRANTI credits applied
- CLI tooling: `aws` (v2), `terraform` (>= 1.7), `kubectl`, `helm`
- `aws sts get-caller-identity` returns your account
- **Running On-Demand G and VT instances** quota ≥ 4 vCPUs in the target region (verified by a successful `g6.xlarge` launch)
- AWS Budgets alarm configured below the credit ceiling

> **Region note:** ap-southeast-5 (Malaysia) offers only the g6 (L4) GPU family — no g4dn/g5/P instances. Both GPU tiers therefore run `g6.xlarge`. The tiers stay architecturally separate (own node groups, taints, scalers); instance types are one-line swaps in `terraform/envs/dev/variables.tf` if you build in another region.

## Week 1 — Cluster provisioning

Terraform provisions: VPC (2 AZs, private nodes behind a single NAT gateway), EKS control plane, and five managed node groups:

| Node group | Instance | Count | Taint |
|---|---|---|---|
| `system` | t3.medium | 2 | — |
| `apinp` | t3.medium | 1 | `dedicated=apinp:NoSchedule` |
| `redisnp` | t3.medium | 1 | `dedicated=redisnp:NoSchedule` |
| `gpunp-layout` | g6.xlarge | 0→2 | `nvidia.com/gpu=true:NoSchedule` |
| `gpunp-serving` | g6.xlarge | 0→1 | `nvidia.com/gpu=true:NoSchedule` |

Every node group carries a `role=<name>` label; workloads target a group with the **toleration + nodeSelector** pair (either alone is not enough — the toleration only *permits*, the selector *pins*).

```bash
cd terraform/envs/dev
terraform init
terraform plan    # review: ~20 resources, no GPU capacity (GPU groups desired_size = 0)
terraform apply
aws eks update-kubeconfig --region ap-southeast-5 --name slm-ocr-eks-dev
kubectl get nodes -L role                        # 4 CPU nodes, correct roles
kubectl describe nodes | grep -A2 "Taints:"     # taints per table above
kubectl apply -f ../../k8s/eks/infra/nvidia-device-plugin.yaml
```

### Week 1 lab (EKS port of the Lesson 1 AKS lab)

```bash
kubectl apply -f k8s/eks/apps/lab-api.yaml      # Deployment on tainted apinp + ClusterIP Service
kubectl get svc ocr-inference-service           # internal ClusterIP, no EXTERNAL-IP
kubectl apply -f k8s/eks/apps/lab-job.yaml      # Job on system pool curls across node groups
kubectl logs -f job/document-batch-job
kubectl delete -f k8s/eks/apps/lab-job.yaml -f k8s/eks/apps/lab-api.yaml
```

Unlike the course lab, the cluster is **not** torn down afterwards: control plane + CPU groups stay up (hybrid lifecycle); only GPU groups scale to zero.

## Week 3 — vLLM server 🚧

Build & push `services/vllm-server` to ECR, deploy `k8s/eks/apps/deployment-vlm.yml`, benchmark on A100, scale back to zero.

## Week 4 — Rust ingest gateway 🚧

## Week 5 — Worker, Redis & KEDA 🚧

## Week 6 — API Gateway, Cognito & MCP 🚧
