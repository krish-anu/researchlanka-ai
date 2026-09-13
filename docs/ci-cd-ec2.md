# CI/CD To AWS EC2

This repository uses three GitHub Actions workflows:

1. `Dev CI` runs tests and checks when code is pushed to `dev`, and on pull
   requests targeting `dev` or `main`.
2. `Promote Dev To Main` pushes the tested `dev` commit to `main` after
   `Dev CI` passes.
3. `Deploy Main To EC2` deploys every `main` push to the EC2 Docker Compose
   server.

## Branch Flow

```text
feature branch -> pull request/merge to dev -> CI -> main -> EC2 deploy
```

The promotion workflow uses a direct push from `dev` to `main`. If `main` has
branch protection rules that block GitHub Actions from pushing, replace this
with a manual pull request from `dev` to `main`.

## Required GitHub Secrets

Add these in GitHub:

```text
Settings -> Secrets and variables -> Actions -> New repository secret
```

Required:

```text
EC2_HOST=98.81.141.112
EC2_SSH_KEY=<private key contents from dse_project.pem>
```

Optional:

```text
EC2_USER=ubuntu
EC2_APP_DIR=/home/ubuntu/researchlanka-ai
```

## EC2 Requirements

The EC2 app directory must already have:

```text
.env
backend/data/
```

The deploy workflow does not delete Docker volumes or local data files. It
rebuilds images, recreates containers, applies database migrations, restarts the
API/frontend, and prunes unused Docker images.

## First-Time Branch Setup

Create and push `dev`:

```bash
git checkout -b dev
git push -u origin dev
```

After that, merge feature branches into `dev`. When CI passes, GitHub Actions
will promote `dev` to `main`, and `main` will deploy to EC2.
