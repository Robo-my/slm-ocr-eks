resource "aws_iam_role" "node" {
  name = "${var.cluster_name}-node-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "node" {
  for_each = toset([
    "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
    "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
    "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
  ])

  role       = aws_iam_role.node.name
  policy_arn = each.value
}

resource "aws_eks_node_group" "this" {
  for_each = var.node_groups

  cluster_name    = var.cluster_name
  node_group_name = each.key
  node_role_arn   = aws_iam_role.node.arn
  subnet_ids      = var.subnet_ids

  instance_types = [each.value.instance_type]
  ami_type       = each.value.gpu ? "AL2023_x86_64_NVIDIA" : "AL2023_x86_64_STANDARD"
  capacity_type  = "ON_DEMAND"
  disk_size      = each.value.gpu ? 100 : 20

  scaling_config {
    desired_size = each.value.desired_size
    min_size     = each.value.min_size
    max_size     = each.value.max_size
  }

  labels = {
    role = each.key
  }

  # GPU groups get the standard nvidia.com/gpu taint; dedicated CPU groups
  # (api, redis) get a role taint so general workloads stay off them.
  # The system group has no taint and catches everything else.
  dynamic "taint" {
    for_each = each.value.gpu ? [1] : []
    content {
      key    = "nvidia.com/gpu"
      value  = "true"
      effect = "NO_SCHEDULE"
    }
  }

  dynamic "taint" {
    for_each = each.value.dedicated ? [1] : []
    content {
      key    = "dedicated"
      value  = each.key
      effect = "NO_SCHEDULE"
    }
  }

  # KEDA/cluster-autoscaler drive desired_size at runtime; Terraform must
  # not fight them on subsequent applies.
  lifecycle {
    ignore_changes = [scaling_config[0].desired_size]
  }

  depends_on = [aws_iam_role_policy_attachment.node]
}
