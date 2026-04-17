#!/bin/sh
set -e

if [ "$TARGET_ENV" = "prod" ]; then
    # Production command
    exec gunicorn \
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