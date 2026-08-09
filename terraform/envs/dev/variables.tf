variable "aws_region" {
  description = "AWS region. ap-southeast-5 (Malaysia) offers only the g6 (L4) GPU family; both GPU tiers therefore run g6.xlarge — swap instance types here if building elsewhere."
  type        = string
  default     = "ap-southeast-5"
}

variable "project_name" {
  description = "Prefix for all resource names."
  type        = string
  default     = "slm-ocr-eks"
}

variable "cluster_version" {
  description = "Kubernetes version for the EKS control plane."
  type        = string
  default     = "1.32"
}

# The node lineup. GPU groups start (and idle) at zero — KEDA + autoscaler
# bring them up on queue depth. Instance types are one-line swaps by design.
variable "node_groups" {
  description = "Node groups keyed by role."
  type = map(object({
    instance_type = string
    desired_size  = number
    min_size      = number
    max_size      = number
    gpu           = optional(bool, false)
    dedicated     = optional(bool, false)
  }))
  default = {
    system = {
      instance_type = "t3.medium"
      desired_size  = 2
      min_size      = 2
      max_size      = 2
    }
    apinp = {
      instance_type = "t3.medium"
      desired_size  = 1
      min_size      = 1
      max_size      = 1
      dedicated     = true
    }
    redisnp = {
      instance_type = "t3.medium"
      desired_size  = 1
      min_size      = 1
      max_size      = 1
      dedicated     = true
    }
    gpunp-layout = {
      instance_type = "g6.xlarge"
      desired_size  = 0
      min_size      = 0
      max_size      = 2
      gpu           = true
    }
    gpunp-serving = {
      instance_type = "g6.xlarge"
      desired_size  = 0
      min_size      = 0
      max_size      = 1
      gpu           = true
    }
  }
}
