# Stage 1: 前端构建
FROM node:22-alpine AS frontend-builder
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# Stage 2: Python后端
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS backend
# Why: gitpython依赖系统git可执行文件，slim镜像不含git
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
# Why: 先复制依赖文件再sync，利用Docker层缓存——依赖不变时跳过安装步骤
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY app/ ./app/
COPY orbion.json ./
COPY migrations/ ./migrations/
# 前端构建产物
COPY --from=frontend-builder /app/web/dist ./web/dist/
RUN mkdir -p data/memory repo
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]