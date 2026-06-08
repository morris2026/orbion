# Orbion

多人 + 多 Agent 双协作的 AI 开发平台。核心模式：人类讨论达成共识 → AI 总结/分解/执行 → 人类审批产出。事件驱动架构，Agent 通过订阅事件参与协作。

## 技术栈

| 层 | 技术 |
|---|------|
| 前端 | React 19 + Vite（SPA）+ TypeScript + TailwindCSS 4 + shadcn/ui |
| 后端 | Python 3.12+ / FastAPI + Pydantic + asyncpg |
| 事件总线 | EventBus Protocol 抽象接口 + PostgreSQL Event Store |
| 依赖管理 | uv（后端）、npm（前端） |
| 容器化 | Docker + docker-compose（PostgreSQL 16 + 应用） |

## 快速开始

### 前置条件

- Python 3.12+
- Node.js 22+
- Docker & Docker Compose
- uv（Python 包管理器）

### 安装

```bash
# 克隆仓库
git clone <repo-url> && cd orbion

# 后端依赖
uv sync

# 前端依赖
cd web && npm ci && cd ..

# 启动 PostgreSQL
make docker-up

# 初始化数据库（含测试数据库）
make db-init
```

### 配置

非敏感配置在 `orbion.json`，敏感配置通过环境变量注入：

```bash
export ORBION_JWT_SECRET=<your-secret>
export ORBION_ANTHROPIC_API_KEY=<your-key>   # Agent 运行时需要
export ORBION_POSTGRES__PASSWORD=<your-pg-password>
```

### 运行

```bash
# 后端（开发模式）
.venv/bin/python -m uvicorn app.main:app --reload --port 8000

# 前端（开发模式，自动代理到后端 :8000）
cd web && npm run dev
```

或通过 Docker 一键启动：

```bash
make docker-up   # PostgreSQL + 应用，端口 8000
```

## 测试

| 命令 | 说明 |
|------|------|
| `make test` | 单元测试，80% 覆盖率阈值 |
| `make test-front` | 前端 Vitest 测试 |
| `make test-integration` | 集成测试，80% 覆盖率阈值 |
| `make test-all` | 全量 Python 测试 |
| `make test-random` | 10 次随机顺序 pytest 运行 |
| `make test-e2e` | Playwright E2E 测试 |
| `make check` | 完整质量门禁：format + lint + type + test-all + test-front + audit |

## 质量检查

| 命令 | 说明 |
|------|------|
| `make format` | ruff 格式化（app/ tests/） |
| `make lint` | ruff 检查 |
| `make lint-fix` | ruff 自动修复 |
| `make type` | mypy 严格类型检查 |
| `make audit` | pip-audit 安全审计 |

## 部署

```bash
make staging          # 部署 staging 环境（端口 8001，PG 端口 5433）
make staging-logs     # 查看 staging 日志
make staging-down     # 停止 staging 环境
make staging-clean    # 清理并重新部署 staging
```

## 许可证

私有项目，未开源。