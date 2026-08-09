terraform {
  required_version = ">= 1.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "slm-ocr-eks"
      ManagedBy = "terraform"
      Env       = "dev"
    }
  }
}

module "vpc" {
  source       = "../../modules/vpc"
  project_name = var.project_name
}

module "eks" {
  source          = "../../modules/eks"
  cluster_name    = local.cluster_name
  cluster_version = var.cluster_version
  subnet_ids      = module.vpc.private_subnet_ids
}

module "nodegroups" {
  source       = "../../modules/nodegroups"
  cluster_name = module.eks.cluster_name
  subnet_ids   = module.vpc.private_subnet_ids
  node_groups  = var.node_groups
}

locals {
  cluster_name = "${var.project_name}-dev"
}

# Week 3:
# module "ecr" {
#   source       = "../../modules/ecr"
#   project_name = var.project_name
# }
#
# Week 6:
# module "apigw" {
#   source       = "../../modules/apigw"
#   project_name = var.project_name
# }

output "cluster_name" {
  value = module.eks.cluster_name
}

output "update_kubeconfig" {
  value = "aws eks update-kubeconfig --region ${var.aws_region} --name ${module.eks.cluster_name}"
}
