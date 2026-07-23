# Local state for Week 0. Migrate to S3 + DynamoDB locking in Week 1
# once the account bootstrap (state bucket) exists:
#
# terraform {
#   backend "s3" {
#     bucket         = "slm-ocr-eks-tfstate-<account-id>"
#     key            = "envs/dev/terraform.tfstate"
#     region         = "us-east-1"
#     dynamodb_table = "slm-ocr-eks-tflock"
#     encrypt        = true
#   }
# }
