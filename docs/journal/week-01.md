# Week 1 — Kubernetes for AI Systems (Jul 27 – Aug 2)

**Course input:** Lesson 1/6 article ("From Docker Containers to AI Infrastructure", Jul 29) + Sunday walkthrough (Lecture Note II: architecture rationale & K8s foundations).

## What I built

- Terraform modules `vpc`, `eks`, `nodegroups` composed in `envs/dev`: VPC (2 AZs, single NAT), EKS control plane, five managed node groups per the node lineup — GPU groups defined, tainted, and idling at `desired_size = 0`.
- The `nodegroups` module is parameterized by role: a map keyed by node-group name, so instance types are one-line swaps (matters because ap-southeast-5 only offers the g6/L4 family).
- NVIDIA device plugin DaemonSet (vendored, affinity-scoped to GPU roles) — a no-op until a GPU node exists.
- EKS port of the lesson's AKS hands-on lab: `http-echo` Deployment pinned to the tainted `apinp` group + ClusterIP Service + a curl Job from the untainted `system` group, proving cross-node-group internal DNS networking.

## Key lessons worth remembering

1. **Never probe a model server like a web server.** A naive readiness probe (30s budget) kills a vLLM pod mid-VRAM-load → CrashLoopBackOff. The pattern: `startupProbe` with ~300s budget, fast-failing `readinessProbe` for service registration, `livenessProbe` for CUDA deadlocks. Lands in Week 3's vLLM Deployment.
2. **Taint + toleration + nodeSelector is a three-part formula.** The taint repels, the toleration permits, the nodeSelector pins. A toleration alone doesn't place the pod on the GPU node — misconception the article calls out.
3. **The orchestrator (consumer) is CPU-bound, not GPU-bound.** The layout model runs fine on a small GPU; the fan-out (~8–10 regions/page → hundreds of concurrent vLLM calls) is what saturates cores. Size that node by vCPU count.
4. **Two-stage OCR wins on token cost, GPU utilization (many short requests beat few long ones), hallucination scope, and auditability** (every value traces to a bounding box). Single-stage is only right for fixed single-page use cases.
5. **No KV-cache reuse in OCR** (documents rarely repeat) → don't reserve cache memory; spend it on batching. This drives Week 3's vLLM tuning.
6. **The 64MB `/dev/shm` trap:** default shared memory breaks CUDA IPC / zero-copy handoff; fix with `emptyDir: {medium: Memory, sizeLimit: 4Gi}`.
7. **Batch variant = adapter swap.** Storage event → queue → KEDA replaces producer+Redis; on AWS that's S3 → SQS → KEDA SQS scaler, orchestration core untouched.

## AWS deltas vs the course

- Course lab: `az aks create` + `az aks nodepool add --node-taints`. Here: Terraform `aws_eks_node_group` with `taint` blocks — same semantics, declarative.
- Course tears the cluster down at lab end; this repo keeps control plane + CPU groups up (hybrid lifecycle), GPU groups at zero.
- `ignore_changes` on `desired_size` so KEDA/autoscaler and Terraform don't fight over GPU node counts.

## Verification

- `terraform validate` ✅
- `terraform apply` + `kubectl get nodes -L role` + lab Job logs: _pending credential refresh — see PR_.
- GPU `nvidia.com/gpu` allocatable check deferred to Week 3 (first real GPU need; avoids ~$0.80/hr just for a smoke test).
