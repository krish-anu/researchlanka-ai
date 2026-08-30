#!/usr/bin/env bash
set -euo pipefail

# Monthly ResearchLanka pipeline runner for an AWS EC2 instance.
# Configure with environment variables in cron/systemd rather than editing this file.

ROOT_DIR="${RESEARCHLANKA_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BACKEND_DIR="${ROOT_DIR}/backend"
PYTHON="${PYTHON:-${BACKEND_DIR}/.venv/bin/python}"
PIP="${PIP:-${BACKEND_DIR}/.venv/bin/pip}"
CONFIG="${RESEARCHLANKA_CONFIG:-configurations/sri_lanka/config.json}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
LOG_DIR="${LOG_DIR:-${BACKEND_DIR}/outputs/monthly_runs/${RUN_ID}}"
LOCK_DIR="${LOCK_DIR:-${BACKEND_DIR}/outputs/monthly_pipeline.lock}"

MODEL_INPUT="${MODEL_INPUT:-data/processed/common/common_publications_final_2016_2026_analysis_ready.csv}"
DB_INPUT="${DB_INPUT:-data/processed/common/common_publications_final_2016_2026.csv}"

EMBED_MAX_FEATURES="${EMBED_MAX_FEATURES:-30000}"
EMBED_DIM="${EMBED_DIM:-256}"
EMBED_NGRAM_MAX="${EMBED_NGRAM_MAX:-1}"
EMBED_MIN_DF="${EMBED_MIN_DF:-3}"

S3_BUCKET="${S3_BUCKET:-}"
S3_PREFIX="${S3_PREFIX:-researchlanka/monthly-runs}"
RESTART_SERVICE="${RESTART_SERVICE:-}"

mkdir -p "${LOG_DIR}"
exec > >(tee -a "${LOG_DIR}/monthly_pipeline.log") 2>&1

if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  echo "Another monthly pipeline run is already active: ${LOCK_DIR}"
  exit 1
fi
trap 'rm -rf "${LOCK_DIR}"' EXIT

echo "Starting ResearchLanka monthly pipeline: ${RUN_ID}"
echo "Repository: ${ROOT_DIR}"
echo "Backend: ${BACKEND_DIR}"

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

"${PYTHON}" run_pipeline.py --config "${CONFIG}" --stage all --log-level INFO

make model-splits \
  PYTHON="${PYTHON}" \
  MODEL_SPLIT_INPUT="${MODEL_INPUT}"

make train-logreg \
  PYTHON="${PYTHON}" \
  LOGREG_INPUT="${MODEL_INPUT}" \
  LOGREG_MODEL_OUTPUT="data/models/logistic_regression_primary_domain_${RUN_ID}.joblib" \
  LOGREG_METRICS_OUTPUT="data/models/logistic_regression_primary_domain_${RUN_ID}_metrics.txt" \
  LOGREG_LABEL_COUNTS_OUTPUT="data/models/logistic_regression_primary_domain_${RUN_ID}_labels.csv" \
  LOGREG_PREDICTIONS_OUTPUT="data/models/logistic_regression_primary_domain_${RUN_ID}_predictions.csv" \
  LOGREG_MANIFEST_OUTPUT="data/models/logistic_regression_primary_domain_${RUN_ID}_manifest.json"

make model-embeddings \
  PYTHON="${PYTHON}" \
  EMBED_INPUT="${MODEL_INPUT}" \
  EMBED_OUTPUT="data/models/publication_text_embeddings_${RUN_ID}.parquet" \
  EMBED_MODEL_OUTPUT="data/models/publication_text_embedding_model_${RUN_ID}.joblib" \
  EMBED_MANIFEST_OUTPUT="data/models/publication_text_embeddings_${RUN_ID}_manifest.json" \
  EMBED_SUMMARY_OUTPUT="data/models/publication_text_embeddings_${RUN_ID}_summary.txt" \
  EMBED_MAX_FEATURES="${EMBED_MAX_FEATURES}" \
  EMBED_DIM="${EMBED_DIM}" \
  EMBED_NGRAM_MAX="${EMBED_NGRAM_MAX}" \
  EMBED_MIN_DF="${EMBED_MIN_DF}"

if [[ -n "${DATABASE_URL:-}" ]]; then
  make reset-db-2016-now \
    PYTHON="${PYTHON}" \
    DB_LOAD_INPUT="${DB_INPUT}"
fi

if [[ -n "${S3_BUCKET}" ]]; then
  aws s3 sync data/processed "s3://${S3_BUCKET}/${S3_PREFIX}/${RUN_ID}/data/processed"
  aws s3 sync data/models "s3://${S3_BUCKET}/${S3_PREFIX}/${RUN_ID}/data/models"
  aws s3 sync "${LOG_DIR}" "s3://${S3_BUCKET}/${S3_PREFIX}/${RUN_ID}/logs"
fi

if [[ -n "${RESTART_SERVICE}" ]]; then
  sudo systemctl restart "${RESTART_SERVICE}"
fi

echo "ResearchLanka monthly pipeline finished: ${RUN_ID}"
