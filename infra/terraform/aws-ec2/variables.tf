variable "aws_region" {
  description = "AWS region where the EC2 instance will be created."
  type        = string
  default     = "us-east-1"
}

variable "name_prefix" {
  description = "Name prefix for AWS resources."
  type        = string
  default     = "researchlanka"
}

variable "instance_type" {
  description = "EC2 instance type."
  type        = string
  default     = "t3.large"
}

variable "vpc_id" {
  description = "VPC ID for the security group. Leave null to use the provider default VPC."
  type        = string
  default     = null
}

variable "subnet_id" {
  description = "Subnet ID for the EC2 instance. Leave null to let AWS choose a default subnet."
  type        = string
  default     = null
}

variable "associate_public_ip" {
  description = "Whether to associate a public IPv4 address with the instance."
  type        = bool
  default     = true
}

variable "allowed_ssh_cidr" {
  description = "CIDR allowed to SSH into the instance. Prefer your-ip/32."
  type        = string
}

variable "allowed_frontend_cidrs" {
  description = "CIDR blocks allowed to reach the frontend port."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "frontend_port" {
  description = "Public frontend port exposed by compose.aws.yml."
  type        = number
  default     = 3000
}

variable "root_volume_size_gb" {
  description = "Root EBS volume size in GiB."
  type        = number
  default     = 30
}

variable "create_key_pair" {
  description = "Create an AWS key pair from ssh_public_key_path."
  type        = bool
  default     = true
}

variable "key_pair_name" {
  description = "AWS EC2 key pair name to create or reuse."
  type        = string
  default     = "researchlanka-ec2"
}

variable "ssh_public_key_path" {
  description = "Local path to the SSH public key when create_key_pair is true."
  type        = string
  default     = "~/.ssh/researchlanka_ec2.pub"
}

variable "app_dir" {
  description = "Application directory on the EC2 instance."
  type        = string
  default     = "/home/ubuntu/researchlanka-ai"
}

variable "github_repo_url" {
  description = "Optional repository URL to clone during first boot. Leave empty to clone manually or through CI."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Additional resource tags."
  type        = map(string)
  default     = {}
}
