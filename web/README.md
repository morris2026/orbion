# Orbion Frontend

React 19 + Vite + TypeScript + TailwindCSS 4 + shadcn/ui SPA，为 Orbion 平台提供 Web 界面。

## 开发

```bash
npm ci               # 安装依赖
npm run dev           # 启动开发服务器（代理到后端 :8000）
npm run build         # 构建（tsc + vite build）
npm run lint          # ESLint 检查
npm test              # Vitest 单元测试
npm test -- --watch   # Vitest 监听模式
```

## E2E 测试

需先启动后端和 E2E 专用数据库：

```bash
# 项目根目录
make docker-up
python scripts/start-e2e-server.py   # 启动 E2E 服务器（端口 8002）
make test-e2e                        # 运行 Playwright 测试
```