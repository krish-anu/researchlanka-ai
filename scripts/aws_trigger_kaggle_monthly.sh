#!/usr/bin/env bash
set -euo pipefail

# Lightweight EC2 controller for a monthly Kaggle build.
# Kaggle does the heavy data/model work; EC2 downloads and deploys the outputs.

ROOT_DIR="${RESEARCHLANKA_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BACKEND_DIR="${ROOT_DIR}/backend"
NOTEBOOK="${KAGGLE_NOTEBOOK:-${ROOT_DIR}/dse-project.ipynb}"
KERNEL="${KAGGLE_KERNEL:?Set KAGGLE_KERNEL as owner/kernel-slug, for example anusankrishnathas/researchlanka-monthly-build}"
KAGGLE_DATASET="${KAGGLE_DATASET:-anusankrishnathas/researchlanka-raw-data}"
KERNEL_TITLE="${KERNEL_TITLE:-ResearchLanka Monthly Build}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
WORK_DIR="${WORK_DIR:-${BACKEND_DIR}/outputs/kaggle_monthly/${RUN_ID}}"
KERNEL_DIR="${WORK_DIR}/kernel"
OUTPUT_DIR="${WORK_DIR}/kaggle_output"
OUTPUT_ZIP="${OUTPUT_DIR}/researchlanka-kaggle-outputs.zip"
DEPLOY_OUTPUTS="${DEPLOY_OUTPUTS:-1}"
S3_BUCKET="${S3_BUCKET:-}"
S3_PREFIX="${S3_PREFIX:-researchlanka/monthly-runs}"
RESTART_SERVICE="${RESTART_SERVICE:-}"
DB_INPUT="${DB_INPUT:-data/processed/common/common_publications_final_2016_2026.csv}"
PYTHON="${PYTHON:-${BACKEND_DIR}/.venv/bin/python}"
POLL_SECONDS="${POLL_SECONDS:-120}"
MAX_WAIT_SECONDS="${MAX_WAIT_SECONDS:-43200}"

mkdir -p "${KERNEL_DIR}" "${OUTPUT_DIR}"
exec > >(tee -a "${WORK_DIR}/kaggle_monthly.log") 2>&1

echo "Starting Kaggle monthly controller: ${RUN_ID}"
echo "Kernel: ${KERNEL}"
echo "Dataset source: ${KAGGLE_DATASET}"

if [[ ! -f "${HOME}/.kaggle/kaggle.json" ]]; then
  echo "Missing ${HOME}/.kaggle/kaggle.json. Create a Kaggle API token and place it there."
  exit 1
fi

if [[ ! -f "${NOTEBOOK}" ]]; then
  echo "Notebook not found: ${NOTEBOOK}"
  exit 1
fi

cp "${NOTEBOOK}" "${KERNEL_DIR}/dse-project.ipynb"

cat > "${KERNEL_DIR}/kernel-metadata.json" <<JSON
{
  "id": "${KERNEL}",
  "title": "${KERNEL_TITLE}",
  "code_file": "dse-project.ipynb",
  "language": "python",
  "kernel_type": "notebook",
  "is_private": true,
  "enable_gpu": false,
  "enable_internet": true,
  "dataset_sources": ["${KAGGLE_DATASET}"],
  "competition_sources": [],
  "kernel_sources": []
}
JSON

echo "Submitting notebook to Kaggle..."
kaggle kernels push -p "${KERNEL_DIR}"

echo "Polling Kaggle status..."
elapsed=0
while true; do
  status_output="$(kaggle kernels status "${KERNEL}" || true)"
  echo "${status_output}"

  if echo "${status_output}" | grep -Eiq "complete|succeeded|success"; then
    break
  fi

  if echo "${status_output}" | grep -Eiq "error|failed|cancel"; then
    echo "Kaggle run failed."
    exit 1
  fi

  if (( elapsed >= MAX_WAIT_SECONDS )); then
    echo "Timed out waiting for Kaggle after ${MAX_WAIT_SECONDS} seconds."
    exit 1
  fi

  sleep "${POLL_SECONDS}"
  elapsed=$((elapsed + POLL_SECONDS))
done

echo "Downloading Kaggle outputs..."
kaggle kernels output "${KERNEL}" -p "${OUTPUT_DIR}" -o

if [[ ! -f "${OUTPUT_ZIP}" ]]; then
  echo "Expected output zip not found: ${OUTPUT_ZIP}"
  echo "Downloaded files:"
  find "${OUTPUT_DIR}" -maxdepth 2 -type f -print
  exit 1
fi

if [[ "${DEPLOY_OUTPUTS}" == "1" ]]; then
  echo "Deploying Kaggle output zip into backend..."
  unzip -o "${OUTPUT_ZIP}" -d "${BACKEND_DIR}"

  if [[ -n "${DATABASE_URL:-}" ]]; then
    cd "${BACKEND_DIR}"
    "${PYTHON}" scripts/database/check_database_connection.py
    "${PYTHON}" scripts/database/apply_database_migrations.py
    "${PYTHON}" scripts/database/verify_database_schema.py
    make reset-db-2016-now PYTHON="${PYTHON}" DB_LOAD_INPUT="${DB_INPUT}"
  fi
fi

if [[ -n "${S3_BUCKET}" ]]; then
  aws s3 sync "${OUTPUT_DIR}" "s3://${S3_BUCKET}/${S3_PREFIX}/${RUN_ID}/kaggle_output"
  aws s3 cp "${WORK_DIR}/kaggle_monthly.log" "s3://${S3_BUCKET}/${S3_PREFIX}/${RUN_ID}/logs/kaggle_monthly.log"
fi

if [[ -n "${RESTART_SERVICE}" ]]; then
  sudo systemctl restart "${RESTART_SERVICE}"
fi

echo "Kaggle monthly controller finished: ${RUN_ID}"
