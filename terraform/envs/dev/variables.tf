variable "aws_region" {
  description = "AWS region for all resources. ap-southeast-5 (Malaysia) has no p4d capacity; use a region with A100 availability."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Prefix for all resource names."
  type        = string
  default     = "slm-ocr-eks"
}
