data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_key_pair" "this" {
  count = var.create_key_pair ? 1 : 0

  key_name   = var.key_pair_name
  public_key = file(pathexpand(var.ssh_public_key_path))

  tags = local.tags
}

resource "aws_security_group" "app" {
  name        = "${var.name_prefix}-app"
  description = "ResearchLanka EC2 Docker Compose access"
  vpc_id      = var.vpc_id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  ingress {
    description = "Next.js frontend"
    from_port   = var.frontend_port
    to_port     = var.frontend_port
    protocol    = "tcp"
    cidr_blocks = var.allowed_frontend_cidrs
  }

  egress {
    description = "Outbound internet"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-app-sg"
  })
}

resource "aws_instance" "app" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.instance_type
  subnet_id                   = var.subnet_id
  vpc_security_group_ids      = [aws_security_group.app.id]
  associate_public_ip_address = var.associate_public_ip
  key_name                    = var.create_key_pair ? aws_key_pair.this[0].key_name : var.key_pair_name
  user_data_replace_on_change = true

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    app_dir         = var.app_dir
    github_repo_url = var.github_repo_url
  })

  root_block_device {
    volume_size           = var.root_volume_size_gb
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-app"
  })
}
