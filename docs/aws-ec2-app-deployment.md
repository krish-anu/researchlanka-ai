# AWS EC2 App Deployment

This is the simplest production-style deployment for ResearchLanka on AWS:

- EC2 runs Docker Compose.
- PostgreSQL runs in a Docker volume on the same instance.
- The Python API runs on the private Compose network.
- The Next.js frontend is the only public service.

For a stronger production setup later, move PostgreSQL to RDS and put the
frontend behind an Application Load Balancer or Nginx with HTTPS.

## 1. Create The EC2 Instance

You can provision the EC2 host with Terraform:

```bash
cp infra/terraform/aws-ec2/terraform.tfvars.example infra/terraform/aws-ec2/terraform.tfvars
terraform -chdir=infra/terraform/aws-ec2 init
terraform -chdir=infra/terraform/aws-ec2 apply
```

See [`../infra/terraform/aws-ec2/README.md`](../infra/terraform/aws-ec2/README.md)
for variables, SSH key setup, and GitHub Actions handoff.

If creating the instance manually, use:

Recommended first instance:

```text
Ubuntu 24.04 LTS
t3.large or t3.xlarge
30-80 GB gp3 EBS
Security group: allow SSH 22 from your IP, allow frontend port 3000 from your IP or the web
```

If you will run the monthly data/model build on the same instance, start with
`t3.xlarge`. If EC2 only serves the already-built app, `t3.large` is usually a
reasonable first try.

## 2. Install Server Packages

SSH into EC2, then install Docker:

```bash
sudo apt update
sudo apt install -y git ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
```

Log out and back in so the Docker group applies.

## 3. Clone And Configure

```bash
git clone https://github.com/krish-anu/researchlanka-ai.git ~/researchlanka-ai
cd ~/researchlanka-ai
cp deploy/aws.ec2.env.example deploy/aws.ec2.env
nano deploy/aws.ec2.env
```

Generate a real session secret:

```bash
openssl rand -base64 48
```

Put one generated value in `AUTH_SECRET` and another in
`RESEARCHLANKA_ADMIN_API_TOKEN`. Also replace `POSTGRES_PASSWORD`,
`ADMIN_EMAIL`, and `ADMIN_PASSWORD`. Do not keep the example passwords.

## 4. Restore Data Artifacts

The app expects approved, versioned data/model artifacts under `backend/data/`.
They are not downloaded automatically and there is currently no approved public
artifact URL. Obtain the handover bundle through the approved transfer channel,
verify its supplied checksums, and extract it from the repository root:

```bash
unzip <approved-artifact-bundle>.zip
```

At minimum, confirm this file exists:

```bash
ls backend/data/processed/common/researchlanka_ai_publications_final.csv
```

If semantic search is enabled, also confirm the model files named in
`deploy/aws.ec2.env` exist under `backend/data/models/`.

## 5. Start The Stack

```bash
docker compose --env-file deploy/aws.ec2.env -f compose.aws.yml up --build -d
docker compose --env-file deploy/aws.ec2.env -f compose.aws.yml ps
```

Apply migrations and load the prepared AI-reviewed 2016-2026 dataset:

```bash
docker compose --env-file deploy/aws.ec2.env -f compose.aws.yml run --rm api python scripts/database/apply_database_migrations.py
docker compose --env-file deploy/aws.ec2.env -f compose.aws.yml run --rm api python scripts/database/load_records.py data/processed/common/researchlanka_ai_publications_final.csv --year-min 2016 --year-max 2026
docker compose --env-file deploy/aws.ec2.env -f compose.aws.yml restart api frontend
```

## 6. Test

From the EC2 instance:

```bash
curl http://127.0.0.1:3000
docker compose --env-file deploy/aws.ec2.env -f compose.aws.yml exec api python -c "import json, urllib.request; print(json.load(urllib.request.urlopen('http://127.0.0.1:8080/health')))"
```

From your browser:

```text
http://<ec2-public-ip>:3000
```

## Operations

View logs:

```bash
docker compose --env-file deploy/aws.ec2.env -f compose.aws.yml logs -f frontend
docker compose --env-file deploy/aws.ec2.env -f compose.aws.yml logs -f api
```

Deploy new code:

```bash
git pull
docker compose --env-file deploy/aws.ec2.env -f compose.aws.yml up --build -d
```

Back up PostgreSQL:

```bash
docker compose --env-file deploy/aws.ec2.env -f compose.aws.yml exec db pg_dump -U researchlanka_user researchlanka > researchlanka-db-backup.sql
```

Run monthly pipeline automation:

```bash
less docs/aws-monthly-automation.md
```
