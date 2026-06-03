# Orbion 多环境部署方案

## 目标

三套环境：开发（当前）、Staging（用户测试）、Production（正式使用）。

当前优先级：Staging 部署就绪，Production 结构预留。

## 架构

Docker Compose 单机部署，FastAPI 同时提供 API 和前端静态文件服务。

```
┌─ Docker Compose ──────────────────────┐
│                                        │
│  PostgreSQL ←── FastAPI                │
│  (容器)         (容器)                  │
│                  ├── /auth/*  API路由   │
│                  ├── /projects/* API    │
│                  ├── /events/stream SSE │
│                  └── /      前端静态     │
│                      (web/dist/)        │
│                                        │
└─ 宿主机端口: 8000 ────────────────────┘
```

MVP阶段不需要单独的 Nginx 容器——`static.py` 已挂载 `web/dist/` 做 SPA 服务。性能瓶颈时再加 Nginx 反代。

## 需要新增的文件

| 文件 | 作用 |
|------|------|
| `Dockerfile` | 多阶段构建：先 `npm build` 前端，再 Python 后端，最终镜像包含 `web/dist/` |
| `docker-compose.staging.yml` | Staging 部署：PostgreSQL + FastAPI，staging 环境变量 |
| `docker-compose.prod.yml` | Production 部署模板（当前不用，但结构就位） |
| `.env.staging` | Staging 环境变量（JWT secret、DB 密码等密钥） |
| `.env.staging.example` | 密钥模板（commit 到 git，不含实际值） |

## 环境配置隔离策略

```
开发环境:  orbion.json 默认值 + 本地 ORBION_* env
Staging:   .env.staging 文件（密钥）+ docker-compose.staging.yml
Production: .env.prod（密钥，不入git）+ docker-compose.prod.yml
```

密钥（jwt_secret、DB password）只从 `.env.staging/.env.prod` 读取，不入 git。`orbion.json` 的 `extra="forbid"` 已阻止密钥出现在配置文件中。

## Staging 部署流程

```bash
# 1. 在目标机器上
git clone ...
cp .env.staging.example .env.staging  # 编辑填入实际密钥

# 2. 构建并启动
docker compose -f docker-compose.staging.yml up -d --build

# 3. 初始化数据库
docker compose -f docker-compose.staging.yml exec backend python -m app.migrations

# 4. 访问
http://<host>:8000
```

## 待决策

- Staging 部署目标：VPS / 云服务器 / 本地另一台机器？
- 数据库迁移工具：当前无 migration runner，需补充
- HTTPS：Staging 是否需要 TLS？（开发环境不需要，Production 必须）
- 前端 CDN：Production 阶段是否将静态文件从 FastAPI 分离到 CDN？