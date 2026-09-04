#!/bin/sh
# 云锡三服务统一入口：SVC=portal|compute|data
set -e
export PYTHONUTF8=1

case "$SVC" in
  portal)
    export PYTHONPATH="/app"
    cd /app/portal
    exec python -m uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8003}"
    ;;
  compute)
    export PYTHONPATH="/app/platforms/compute:/app"
    cd /app/platforms/compute
    exec python -m uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8001}"
    ;;
  data)
    export PYTHONPATH="/app/platforms/data/backend:/app"
    cd /app/platforms/data/backend
    exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
    ;;
  *)
    echo "SVC must be portal|compute|data" >&2; exit 1 ;;
esac
