#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ubuntu/researchlanka-ai}"
REPO_URL="${REPO_URL:-https://github.com/krish-anu/researchlanka-ai.git}"
BRANCH="${BRANCH:-main}"
ENV_FILE="${ENV_FILE:-deploy/aws.ec2.env}"
COMPOSE_FILE="${COMPOSE_FILE:-compose.aws.yml}"
DATA_ARCHIVE="${DATA_ARCHIVE:-${DATA_ZIP:-}}"
LOAD_DATASET="${LOAD_DATASET:-false}"
DATASET_PATH="${DATASET_PATH:-data/processed/common/common_publications_final_2016_2026_ai_review_filtered.csv}"

if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
else
  SUDO="sudo"
fi

install_packages() {
  if command -v apt-get >/dev/null 2>&1; then
    $SUDO apt-get update
    $SUDO apt-get install -y ca-certificates curl git unzip

    if ! command -v docker >/dev/null 2>&1; then
      $SUDO install -m 0755 -d /etc/apt/keyrings
      curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | $SUDO tee /etc/apt/keyrings/docker.asc >/dev/null
      $SUDO chmod a+r /etc/apt/keyrings/docker.asc
      . /etc/os-release
      echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" \
        | $SUDO tee /etc/apt/sources.list.d/docker.list >/dev/null
      $SUDO apt-get update
      $SUDO apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    fi
  elif command -v dnf >/dev/null 2>&1; then
    $SUDO dnf install -y git curl unzip docker docker-compose-plugin
  else
    echo "Unsupported OS: install git, unzip, Docker, and Docker Compose plugin manually." >&2
    exit 1
  fi

  $SUDO systemctl enable docker
  $SUDO systemctl start docker
  $SUDO usermod -aG docker "$USER" || true
}

clone_or_update_repo() {
  mkdir -p "$(dirname "$APP_DIR")"

  if [ -d "$APP_DIR/.git" ]; then
    git -C "$APP_DIR" fetch origin "$BRANCH"
    git -C "$APP_DIR" checkout "$BRANCH"
    git -C "$APP_DIR" pull --ff-only origin "$BRANCH"
  else
    git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
  fi
}

prepare_env() {
  cd "$APP_DIR"
  mkdir -p deploy secrets

  if [ ! -f "$ENV_FILE" ]; then
    cp deploy/aws.ec2.env.example "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    cat <<MSG

Created $APP_DIR/$ENV_FILE from the example file.
Edit it before exposing the app:

  nano $APP_DIR/$ENV_FILE

Set POSTGRES_PASSWORD, AUTH_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD, and
RESEARCHLANKA_ADMIN_API_TOKEN to real values.

MSG
    exit 0
  fi

  if [ ! -f secrets/google_sheets_service_account.json ]; then
    echo "{}" > secrets/google_sheets_service_account.json
    chmod 600 secrets/google_sheets_service_account.json
  fi
}

restore_data_zip() {
  if [ -n "$DATA_ARCHIVE" ]; then
    cd "$APP_DIR"
    unzip -o "$DATA_ARCHIVE"
  fi
}

start_stack() {
  cd "$APP_DIR"
  COMPOSE="docker compose --env-file $ENV_FILE -f $COMPOSE_FILE"

  $COMPOSE config >/tmp/researchlanka-compose.ok
  $COMPOSE up --build -d db
  $COMPOSE run --rm -T --interactive=false api python scripts/database/apply_database_migrations.py </dev/null

  if [ "$LOAD_DATASET" = "true" ]; then
    $COMPOSE run --rm -T --interactive=false api \
      python scripts/database/load_records.py "$DATASET_PATH" --year-min 2016 --year-max 2026 </dev/null
  fi

  $COMPOSE up --build -d --remove-orphans
  $COMPOSE ps
}

install_packages
clone_or_update_repo
prepare_env
restore_data_zip
start_stack

cat <<MSG

ResearchLanka stack started.

Open:
  http://$(curl -fsSL http://169.254.169.254/latest/meta-data/public-ipv4 || hostname -I | awk '{print $1}'):3000

Logs:
  cd $APP_DIR
  docker compose --env-file $ENV_FILE -f $COMPOSE_FILE logs -f frontend
  docker compose --env-file $ENV_FILE -f $COMPOSE_FILE logs -f api

MSG
