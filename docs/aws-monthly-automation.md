# AWS Monthly Automation

This guide covers two monthly automation options:

- EC2-only: EC2 runs collection, processing, embeddings, and model training.
- Kaggle build + EC2 deploy: Kaggle runs the heavy notebook, then EC2 downloads
  and deploys the finished artifacts.

Use the Kaggle option when your EC2 instance is too small for the model and
embedding build.

## Recommended Flow

1. Keep the app running on EC2 with `systemd`, Docker, or your current process manager.
2. Run the heavy monthly pipeline from cron or a `systemd` timer.
3. Save every run under `backend/outputs/monthly_runs/<run-id>/`.
4. Write timestamped model artifacts in `backend/data/models/`.
5. Reload PostgreSQL after a successful pipeline run.
6. Upload processed data, models, and logs to S3.
7. Restart the API service so it picks up the new data/model artifacts.

## Recommended Kaggle Flow

```text
EC2 cron
  -> submit dse-project.ipynb to Kaggle
  -> Kaggle runs the heavy pipeline
  -> Kaggle creates researchlanka-kaggle-outputs.zip
  -> EC2 downloads the zip
  -> EC2 unzips data/processed and data/models into backend/
  -> EC2 reloads PostgreSQL
  -> EC2 restarts the API
```

Kaggle is doing the expensive CPU/RAM work. EC2 is only controlling the run and
deploying the output.

## Kaggle API Setup On EC2

Install the Kaggle CLI:

```bash
cd ~/researchlanka-ai/backend
.venv/bin/pip install kaggle
```

Create a Kaggle API token from your Kaggle account settings. Put it on EC2:

```bash
mkdir -p ~/.kaggle
nano ~/.kaggle/kaggle.json
chmod 600 ~/.kaggle/kaggle.json
```

The file should look like this:

```json
{
  "username": "your-kaggle-username",
  "key": "your-kaggle-api-key"
}
```

You also need the raw data as a Kaggle Dataset, for example:

```text
anusankrishnathas/researchlanka-raw-data
```

The notebook uses that dataset at:

```text
/kaggle/input/datasets/anusankrishnathas/researchlanka-raw-data/backend/data
```

## Trigger Kaggle From EC2

Run once manually:

```bash
cd ~/researchlanka-ai
KAGGLE_KERNEL="your-kaggle-username/researchlanka-monthly-build" \
KAGGLE_DATASET="anusankrishnathas/researchlanka-raw-data" \
DATABASE_URL="postgresql://researchlanka_user:change_me@localhost:5433/researchlanka" \
RESTART_SERVICE="researchlanka-api" \
./scripts/aws_trigger_kaggle_monthly.sh
```

This script creates Kaggle kernel metadata, pushes `dse-project.ipynb`, waits
for the Kaggle run to finish, downloads `researchlanka-kaggle-outputs.zip`, and
deploys `data/processed/` and `data/models/` into `backend/`.

For monthly cron:

```cron
0 2 1 * * cd /home/ubuntu/researchlanka-ai && KAGGLE_KERNEL='your-kaggle-username/researchlanka-monthly-build' KAGGLE_DATASET='anusankrishnathas/researchlanka-raw-data' DATABASE_URL='postgresql://researchlanka_user:change_me@localhost:5433/researchlanka' RESTART_SERVICE='researchlanka-api' ./scripts/aws_trigger_kaggle_monthly.sh
```

If you want EC2 only to download outputs but not replace local files, run with:

```bash
DEPLOY_OUTPUTS=0 ./scripts/aws_trigger_kaggle_monthly.sh
```

## EC2 Setup

Install system packages:

```bash
sudo apt update
sudo apt install -y git python3-venv make postgresql-client awscli
```

Clone the repo and install dependencies:

```bash
git clone <repository-url> ~/researchlanka-ai
cd ~/researchlanka-ai
make install
```

Create `backend/.env` or export this in the service/cron environment:

```bash
DATABASE_URL=postgresql://researchlanka_user:change_me@localhost:5433/researchlanka
OPENALEX_EMAIL=you@example.com
```

Make the runner executable:

```bash
chmod +x scripts/aws_monthly_pipeline.sh
```

## Manual Test Run

Run once manually before enabling cron:

```bash
cd ~/researchlanka-ai
DATABASE_URL="postgresql://researchlanka_user:change_me@localhost:5433/researchlanka" \
OPENALEX_EMAIL="you@example.com" \
S3_BUCKET="your-backup-bucket" \
RESTART_SERVICE="researchlanka-api" \
./scripts/aws_monthly_pipeline.sh
```

For a smaller/cheaper embedding build:

```bash
EMBED_MAX_FEATURES=15000 EMBED_DIM=128 EMBED_NGRAM_MAX=1 EMBED_MIN_DF=5 \
./scripts/aws_monthly_pipeline.sh
```

## Cron Schedule

Open the crontab:

```bash
crontab -e
```

Run at 02:00 UTC on the first day of every month:

```cron
0 2 1 * * cd /home/ubuntu/researchlanka-ai && DATABASE_URL='postgresql://researchlanka_user:change_me@localhost:5433/researchlanka' OPENALEX_EMAIL='you@example.com' S3_BUCKET='your-backup-bucket' RESTART_SERVICE='researchlanka-api' ./scripts/aws_monthly_pipeline.sh
```

## What The Script Runs

The monthly script does this:

```text
install/refresh Python dependencies
check/apply/verify database migrations
collect + process the Sri Lanka pipeline
create model train/validation/test splits
train logistic regression classifier
build TF-IDF/SVD publication embeddings
reload PostgreSQL
upload artifacts/logs to S3
restart the app service
```

## EC2 Sizing

For low cost, start with a burstable instance and only resize if the monthly job
fails from memory pressure:

```text
t3.large/t4g.large: cheap app hosting, may be too small for full monthly build
t3.xlarge/t4g.xlarge: better first choice for monthly CPU/RAM pipeline
r6i.large/r7i.large: better when RAM is the bottleneck
```

If cost matters most, stop the large training EC2 when the job finishes and keep
the deployed app on a smaller EC2 instance.

## Safer Production Pattern

For a stronger setup, use two EC2 instances:

```text
small EC2: always-on API/frontend
larger EC2: starts once per month, builds data/models, uploads to S3, then stops
```

The app instance then downloads the latest S3 artifacts and restarts the API.
