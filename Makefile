TF_DIR := terraform/envs/dev

.PHONY: tf-init tf-plan tf-apply tf-destroy build deploy help

help:
	@grep -E '^[a-z-]+:' Makefile | sed 's/:.*//' | sort

tf-init:
	terraform -chdir=$(TF_DIR) init

tf-validate:
	terraform -chdir=$(TF_DIR) validate

tf-plan:
	terraform -chdir=$(TF_DIR) plan

tf-apply:
	terraform -chdir=$(TF_DIR) apply

tf-destroy:
	terraform -chdir=$(TF_DIR) destroy

# Week 3+: docker build & push targets per service
build:
	@echo "stub: implemented from Week 3 (vllm-server), Week 4 (gateway-rs), Week 5 (worker-py)"

# Week 1+: kubectl apply -k k8s/eks
deploy:
	@echo "stub: implemented from Week 1"
