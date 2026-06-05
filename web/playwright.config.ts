import { defineConfig } from '@playwright/test'
import path from 'path'

const projectRoot = path.resolve(import.meta.dirname, '..')

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  retries: 0,
  timeout: 30000,
  expect: { timeout: 10000 },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
  use: {
    baseURL: 'http://localhost:8002',
    headless: true,
    screenshot: 'only-on-failure',
  },
  webServer: {
    // 使用独立E2E启动脚本注入TestModelAdapter，不修改生产代码
    command: `cd ${projectRoot} && ORBION_POSTGRES__DB=orbion_e2e .venv/bin/python scripts/start-e2e-server.py`,
    port: 8002,
    reuseExistingServer: true,
    timeout: 30000,
  },
})