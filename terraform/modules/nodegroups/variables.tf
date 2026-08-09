variable "cluster_name" {
  description = "Name of the EKS cluster to attach node groups to."
  type        = string
}

variable "subnet_ids" {
  description = "Private subnets the nodes launch into."
  type        = list(string)
}

variable "node_groups" {
  description = "Node groups keyed by role name. gpu = NVIDIA AMI + nvidia.com/gpu taint; dedicated = role taint keeping general workloads off."
  type = map(object({
    instance_type = string
    desired_size  = number
    min_size      = number
    max_size      = number
    gpu           = optional(bool, false)
    dedicated     = optional(bool, false)
  }))
}
