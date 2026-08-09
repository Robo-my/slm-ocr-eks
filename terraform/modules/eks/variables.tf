variable "cluster_name" {
  description = "Name of the EKS cluster."
  type        = string
}

variable "cluster_version" {
  description = "Kubernetes version for the EKS control plane."
  type        = string
  default     = "1.32"
}

variable "subnet_ids" {
  description = "Subnets for the EKS control plane ENIs (private subnets)."
  type        = list(string)
}
