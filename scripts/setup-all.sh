#!/usr/bin/env bash
# 一键准备所有本地环境：杀残留→dev→init-test-dbs→e2e→staging
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

# 颜色输出
info()  { echo -e "\033[1;34m==>\033[0m $*"; }
ok()    { echo -e "\033[1;32m ✓\033[0m $*"; }
fail()  { echo -e "\033[1;31m ✗\033[0m $*"; exit 1; }

# ── 1. 清理所有 Orbion 容器 ──────────────────────────────────────
info "停止所有 Orbion 容器..."
for project in orbion-dev orbion-staging; do
  for f in docker-compose.dev.yml docker-compose.staging.yml; do
    docker compose -p "$project" -f "$f" down --remove-orphans 2>/dev/null || true
  done
done
# 杀掉可能残留的 e2e uvicorn 进程（端口 8002）
if command -v lsof &>/dev/null; then
  lsof -ti:8002 2>/dev/null | xargs kill 2>/dev/null || true
fi
ok "容器已清理"

# ── 2. 启动 dev 环境（PG 5432 + API 8000） ──────────────────────
info "启动 dev 环境 (PG:5432 API:8000)..."
docker compose -p orbion-dev -f docker-compose.dev.yml up -d --build

info "等待 dev PostgreSQL 就绪..."
wait_for_pg() {
  local host="$1" port="$2" max_wait="${3:-60}" elapsed=0
  until docker compose -p orbion-dev -f docker-compose.dev.yml exec -T postgres pg_isready -h "$host" -p 5432 -U orbion -d orbion >/dev/null 2>&1; do
    sleep 2
    elapsed=$((elapsed + 2))
    if [[ $elapsed -ge $max_wait ]]; then
      fail "PostgreSQL ($host:$port) 未在 ${max_wait}s 内就绪"
    fi
  done
}
wait_for_pg localhost 5432
ok "dev 环境就绪 (PG:5432 API:8000)"

# ── 3. 初始化测试数据库（orbion_test / orbion_e2e） ──────────────
info "初始化测试数据库 (orbion_test, orbion_e2e)..."
.venv/bin/python scripts/init-test-dbs.py
ok "测试数据库就绪"

# ── 4. 启动 E2E 测试服务器（复用 dev PG，API:8002） ─────────────
info "启动 E2E 测试服务器 (PG:5432 API:8002)..."
.venv/bin/python scripts/start-e2e-server.py &
E2E_PID=$!
# 等待 E2E 服务器就绪
for i in $(seq 1 15); do
  if curl -sf http://localhost:8002/ >/dev/null 2>&1; then
    break
  fi
  sleep 1
  if [[ $i -eq 15 ]]; then
    kill "$E2E_PID" 2>/dev/null || true
    fail "E2E 服务器未在 15s 内就绪"
  fi
done
ok "E2E 服务器就绪 (PG:5432 API:8002, PID=$E2E_PID)"

# ── 5. 启动 staging 环境（PG:5433 + API:8001） ─────────────────
info "启动 staging 环境 (PG:5433 API:8001)..."
bash scripts/deploy-staging.sh
ok "staging 环境就绪"

# ── 汇总 ──────────────────────────────────────────────────────────
echo ""
echo -e "\033[1;36m╔══════════════════════════════════════════════╗"
echo -e "║        Orbion 本地环境全部就绪               ║"
echo -e "╠══════════════════════════════════════════════╣"
echo -e "║  dev       PG:5432  API:http://localhost:8000 ║"
echo -e "║  e2e       PG:5432  API:http://localhost:8002 ║"
echo -e "║  staging   PG:5433  API:http://localhost:8001 ║"
echo -e "╚══════════════════════════════════════════════╝\033[0m"
echo ""
echo "  E2E 服务器 PID: $E2E_PID"
echo "  停止 E2E: kill $E2E_PID"
echo "  停止全部: make docker-down && make staging-down && kill $E2E_PID"
