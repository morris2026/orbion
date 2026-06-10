#!/usr/bin/env bash
# Orbion 测试环境一键部署脚本
set -euo pipefail

COMPOSE_FILE="docker-compose.staging.yml"
COMPOSE_PROJECT="orbion-staging"
CLEAN=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --clean) CLEAN=true; shift ;;
    -h|--help)
      echo "用法: $0 [--clean]"
      echo ""
      echo "选项:"
      echo "  --clean   删除数据卷，完全重置测试环境"
      echo ""
      echo "部署完成后:"
      echo "  PostgreSQL: localhost:5433 (orbion/orbion_dev)"
      echo "  Orbion API: http://localhost:8001"
      exit 0
      ;;
    *) echo "未知选项: $1"; exit 1 ;;
  esac
done

# --clean: 停止服务并删除所有卷
if $CLEAN; then
  echo "==> 重置测试环境（停止服务并删除数据卷）..."
  docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" down -v 2>/dev/null || true
  echo "==> 数据已清除"
fi

echo "==> 构建并启动测试环境..."
docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" up -d --build

echo "==> 等待 PostgreSQL 就绪..."
MAX_WAIT=60
elapsed=0
until docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" exec -T postgres pg_isready -U orbion -d orbion >/dev/null 2>&1; do
  sleep 2
  elapsed=$((elapsed + 2))
  if [[ $elapsed -ge $MAX_WAIT ]]; then
    echo "==> PostgreSQL 未在 ${MAX_WAIT}秒内就绪，请检查日志:"
    docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" logs --tail=20 postgres
    exit 1
  fi
done
echo "==> PostgreSQL 已就绪"

echo "==> 测试环境已就绪！"
echo "    PostgreSQL: localhost:5433 (orbion/orbion_dev)"
echo "    Orbion API: http://localhost:8001"