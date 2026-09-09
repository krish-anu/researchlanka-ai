#!/usr/bin/env bash
set -euo pipefail

# Manual/monthly incremental ResearchLanka refresh for AWS EC2.
# Cron example:
#   0 2 1 * * RESEARCHLANKA_ROOT=/srv/researchlanka-ai DATABASE_URL=... /srv/researchlanka-ai/scripts/aws_incremental_pipeline.sh

ROOT_DIR="${RESEARCHLANKA_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BACKEND_DIR="${ROOT_DIR}/backend"
PYTHON="${PYTHON:-${BACKEND_DIR}/.venv/bin/python}"
PIP="${PIP:-${BACKEND_DIR}/.venv/bin/pip}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
LOG_DIR="${LOG_DIR:-${BACKEND_DIR}/outputs/incremental/logs/${RUN_ID}}"
LOCK_DIR="${LOCK_DIR:-${BACKEND_DIR}/outputs/incremental.lock}"
RESTART_SERVICE="${RESTART_SERVICE:-}"
S3_BUCKET="${S3_BUCKET:-}"
S3_PREFIX="${S3_PREFIX:-researchlanka/incremental-runs}"

mkdir -p "${LOG_DIR}"
exec > >(tee -a "${LOG_DIR}/incremental_pipeline.log") 2>&1

if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  echo "Another incremental pipeline run is already active: ${LOCK_DIR}"
  exit 1
fi
trap 'rm -rf "${LOCK_DIR}"' EXIT

echo "Starting ResearchLanka incremental pipeline: ${RUN_ID}"
cd "${BACKEND_DIR}"

if [[ ! -x "${PYTHON}" ]]; then
  python3 -m venv .venv
fi

"${PIP}" install -r requirements.txt

if [[ -n "${DATABASE_URL:-}" ]]; then
  "${PYTHON}" scripts/database/check_database_connection.py
  "${PYTHON}" scripts/database/apply_database_migrations.py
  "${PYTHON}" scripts/database/verify_database_schema.py
fi

make incremental-update PYTHON="${PYTHON}"

if [[ -n "${S3_BUCKET}" ]]; then
  aws s3 sync outputs/incremental "s3://${S3_BUCKET}/${S3_PREFIX}/outputs/incremental"
  aws s3 sync "${LOG_DIR}" "s3://${S3_BUCKET}/${S3_PREFIX}/logs/${RUN_ID}"
fi

if [[ -n "${RESTART_SERVICE}" ]]; then
  sudo systemctl restart "${RESTART_SERVICE}"
fi

echo "ResearchLanka incremental pipeline finished: ${RUN_ID}"
