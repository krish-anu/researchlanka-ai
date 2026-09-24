# ResearchLanka AWS EC2 Terraform

This Terraform stack provisions the EC2 host used by the existing
`compose.aws.yml` deployment and GitHub Actions workflow.

It creates:

- An Ubuntu 24.04 EC2 instance.
- A security group for SSH and the public frontend port.
- An optional SSH key pair from your public key.
- Docker and Docker Compose plugin installation through cloud-init.
- A persistent EBS root volume sized for the app, data artifacts, and Docker
  images.

PostgreSQL still runs in Docker on the instance, matching the current
deployment docs. Secrets and app data are intentionally not managed by
Terraform; keep them in GitHub Actions secrets and on the EC2 filesystem.

The defaults use a Free Tier eligible instance type so new AWS accounts can
apply the stack. For the full dataset and model-serving workload, use
`t3.large` or `t3.xlarge` after your AWS account allows non-Free-Tier EC2
instances.

## Prerequisites

Install Terraform and configure AWS credentials locally:

```bash
aws configure
terraform -chdir=infra/terraform/aws-ec2 init
```

Create a key if you do not already have one:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/researchlanka_ec2 -C researchlanka-ec2
```

## Configure

Copy the sample file:

```bash
cp infra/terraform/aws-ec2/terraform.tfvars.example infra/terraform/aws-ec2/terraform.tfvars
```

Edit `terraform.tfvars` and set:

- `allowed_ssh_cidr` to your public IP with `/32`.
- `ssh_public_key_path` to your public key.
- `github_repo_url` if you want cloud-init to clone the repo on first boot.
- `instance_type` to `t3.large` or `t3.xlarge` when you are ready for the
  production-sized app host.

## Deploy

```bash
terraform -chdir=infra/terraform/aws-ec2 plan
terraform -chdir=infra/terraform/aws-ec2 apply
```

After apply, Terraform prints the public IP and SSH command.

## Connect GitHub Actions

Add or update these repository secrets:

```text
EC2_HOST=<terraform output public_ip>
EC2_USER=ubuntu
EC2_APP_DIR=/home/ubuntu/researchlanka-ai
EC2_SSH_KEY=<contents of ~/.ssh/researchlanka_ec2>
```

Then add the app secrets already documented in `docs/ci-cd-ec2.md`.

## First App Setup

SSH into the instance:

```bash
ssh -i ~/.ssh/researchlanka_ec2 ubuntu@<public-ip>
```

If the repo was not cloned by cloud-init:

```bash
git clone <repository-url> ~/researchlanka-ai
```

Create the app environment and restore data artifacts as documented in
`docs/aws-ec2-app-deployment.md`.

## Destroy

Destroying this stack deletes the EC2 instance and its root EBS volume,
including Docker volumes stored there.

```bash
terraform -chdir=infra/terraform/aws-ec2 destroy
```
