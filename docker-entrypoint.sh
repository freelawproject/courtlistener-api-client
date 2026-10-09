#!/bin/sh
set -e

# Must be set before prometheus_client is imported
export PROMETHEUS_MULTIPROC_DIR="${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus}"
mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
find "$PROMETHEUS_MULTIPROC_DIR" -maxdepth 1 -type f -name '*.db' -delete

if [ -n "${PGHOST:-}" ]; then
    python -m courtlistener.mcp.storage init \
        || echo "OAuth store init failed; starting anyway so /health can report it" >&2
fi

if [ "$TARGET_ENV" = "prod" ]; then
    # Production command
    exec gunicorn \
        --config=/app/gunicorn.conf.py \
        --workers=${MCP_WORKERS:-4} \
        --worker-class=uvicorn.workers.UvicornWorker \
        --bind=0.0.0.0:8080 \
        --timeout=300 \
        --access-logfile=- \
        --error-logfile=- \
        courtlistener.mcp.app:app
else
    # Development command
    exec uvicorn courtlistener.mcp.app:app \
        --host 0.0.0.0 \
        --port 8080 \
        --log-level debug \
        --reload
fi
