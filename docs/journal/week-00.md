# Week 0 — Scaffold & AWS Setup (Jul 23–26, 2026)

## Goal

Get the repo, Terraform skeleton, and AWS account ready so Week 1 (Kubernetes for AI Systems) can start immediately.

## What I did

- [x] Created `slm-ocr-eks` repo with full directory scaffold
- [x] Wrote the portfolio README with architecture diagram and 6-week roadmap
- [x] Documented the AWS service choices (`docs/aws_services.md`)
- [x] Terraform skeleton in `terraform/envs/dev` (validates, applies nothing)
- [ ] Filed Service Quotas request for P-instance vCPUs (96) — **takes days, filed early on purpose**
- [ ] Filed Service Quotas request for G-instance vCPUs (8)
- [ ] Set AWS Budgets alarm on MRANTI credit spend
- [ ] Pushed to GitHub

## Key decisions

- **GPU tiers**: first planned as T4 (layout) + A100 (serving) to model the hardware asymmetry between a light layout model and a heavy transcriber. **Amended Jul 25:** ap-southeast-5 offers only the g6 (L4) family, so both tiers run `g6.xlarge`. The tiers stay architecturally separate; instance types are one-line swaps.
- **Terraform over eksctl** — more upfront work, but the infra story is half the portfolio value.
- **EKS-only scope** — depth on one cloud rather than a thin multi-cloud abstraction.
- **Apache 2.0 license.**

## Notes / gotchas

- `p4d.24xlarge` ≈ $32/hr and is 8× A100 — AWS has no single-A100 on-demand instance. Moot in ap-southeast-5, which has no P instances at all.
- New AWS accounts default P/G instance quotas to **0 vCPUs**.
