#!/usr/bin/env bash
# 服务器端：构建镜像并推送 campus-registry（在源码树根 Yunxi_Project 下执行）
set -euo pipefail
REG="10.50.2.92:15000"
IMAGE="$REG/yunxi/platform"

echo "[build] 开始构建 $IMAGE:latest（首次构建较久，含前端 npm 与后端 pip）"
sudo docker build -f deploy/docker/Dockerfile -t "$IMAGE:latest" .
echo "[build] 完成，推送到 campus-registry"
sudo docker push "$IMAGE:latest"
echo "[build] $IMAGE:latest 已入库"
