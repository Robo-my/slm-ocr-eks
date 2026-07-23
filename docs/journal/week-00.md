# Week 0 — Scaffold & AWS Setup (Jul 23–26, 2026)

## Goal

Get the repo, Terraform skeleton, and AWS account ready before Week 1 (Kubernetes for AI Systems) content arrives, so the build can start immediately.

## What I did

- [x] Created `slm-ocr-eks` repo with full directory scaffold
- [x] Wrote the portfolio README with architecture diagram and 6-week roadmap
- [x] Documented the Azure/GCP → AWS service mapping (`docs/aws_service_mapping.md`)
- [x] Terraform skeleton in `terraform/envs/dev` (validates, applies nothing)
- [ ] Filed Service Quotas request for P-instance vCPUs (96) — **takes days, filed early on purpose**
- [ ] Filed Service Quotas request for G-instance vCPUs (8)
- [ ] Set AWS Budgets alarm on MRANTI credit spend
- [ ] Pushed to GitHub

## Key decisions

- **Faithful GPU replica** (T4 + A100) rather than budget substitutes (g5/L4) — the point is to reproduce the course's hardware asymmetry and its scaling economics. Mitigation: strict scale-to-zero on the A100 group.
- **Terraform over eksctl** — more upfront work, but the infra story is half the portfolio value.
- **EKS-only scope** — the upstream repo already covers AKS/GKE; this repo tells the AWS story cleanly.
- **Apache 2.0 license** — matches the upstream repo's actual LICENSE file (their README says MIT, but the LICENSE file governs).

## Notes / gotchas

- `p4d.24xlarge` ≈ $32/hr and is 8× A100 — AWS has no single-A100 on-demand instance like Azure's `NC24ads_A100_v4`. The single-vs-eight GPU utilization question is deferred to Week 3.
- New AWS accounts default P/G instance quotas to **0 vCPUs**.
