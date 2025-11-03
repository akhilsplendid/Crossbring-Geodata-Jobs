#!/usr/bin/env sh
set -e

if [ "${BOOTSTRAP_AF}" = "true" ] || [ "${BOOTSTRAP_AF}" = "1" ]; then
  echo "[entrypoint] Bootstrapping AF jobs before starting dashboard..."
  python scripts/fetch_af_jobs.py \
    --occupation-field "${AF_OCCUPATION_FIELD:-apaJ_2ja_LuF}" \
    --pages "${AF_PAGES:-5}" \
    --max-records "${AF_MAX_RECORDS:-25}" || echo "[entrypoint] AF bootstrap failed; continuing"
fi

exec "$@"

