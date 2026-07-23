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

# Week 1: uncomment as modules are implemented.
#
# module "vpc" {
#   source       = "../../modules/vpc"
#   project_name = var.project_name
# }
#
# module "eks" {
#   source       = "../../modules/eks"
#   project_name = var.project_name
#   vpc_id       = module.vpc.vpc_id
#   subnet_ids   = module.vpc.private_subnet_ids
# }
#
# module "nodegroups" {
#   source       = "../../modules/nodegroups"
#   cluster_name = module.eks.cluster_name
#   subnet_ids   = module.vpc.private_subnet_ids
# }
#
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
