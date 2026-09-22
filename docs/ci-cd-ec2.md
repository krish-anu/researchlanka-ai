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

Deployments share one concurrency group. An active deployment finishes before
a newer deployment starts, so another trigger cannot cancel a frontend build
or container restart midway through.

The migration container must run with `-T --interactive=false` and stdin
redirected from `/dev/null`. The remote shell reads its script from stdin;
an interactive Compose command can consume the remaining restart commands,
causing a successful job that only builds images and runs migrations.

If the old UI is still visible, check the latest `Deploy Main To EC2` run, not
just an earlier cancelled run. Confirm its logs include API/frontend container
recreation and the final Compose status table. If an older workflow stopped
after migrations, activate the already-built images from the EC2 app directory:

```bash
docker compose --env-file deploy/aws.ec2.env -f compose.aws.yml up -d --force-recreate api frontend
docker compose --env-file deploy/aws.ec2.env -f compose.aws.yml ps
```

Then reload the page with `Ctrl+Shift+R` to load the current frontend assets.

## First-Time Branch Setup

Create and push `dev`:

```bash
git checkout -b dev
git push -u origin dev
```

After that, merge feature branches into `dev`. When CI passes, GitHub Actions
will promote `dev` to `main`, and `main` will deploy to EC2.
