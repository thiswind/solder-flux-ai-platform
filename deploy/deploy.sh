#!/usr/bin/env bash
# 云锡平台服务器端部署/更新脚本（在服务器 /home/thiswind/workspace/yunxi-platform 上执行）
# 用法：./deploy.sh up|update|down|status|logs
set -euo pipefail
cd "$(dirname "$0")"

ACTION="${1:-}"
[ -n "$ACTION" ] || { echo "用法: $0 up|update|down|status|logs"; exit 1; }

ensure_env() {
  if [ ! -f .env ]; then
    echo "[deploy] 缺 .env，从 .env.example 复制后请先填好再重跑" >&2
    cp .env.example .env 2>/dev/null || true
    exit 1
  fi
}

case "$ACTION" in
  up)
    ensure_env
    mkdir -p state/portal
    sudo docker compose up -d
    sudo docker compose ps
    ;;
  update)
    ensure_env
    mkdir -p state/portal
    sudo docker compose pull 2>/dev/null || true
    sudo docker compose up -d
    sudo docker compose ps
    ;;
  down)
    sudo docker compose down
    ;;
  status)
    sudo docker compose ps
    ;;
  logs)
    sudo docker compose logs --tail=80 "${2:-}"
    ;;
  *)
    echo "未知动作: $ACTION" >&2; exit 1 ;;
esac
