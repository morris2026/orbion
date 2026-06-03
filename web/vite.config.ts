import path from 'path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    // 开发代理：前端请求/api/*和/auth/*转发到后端FastAPI
    proxy: {
      '/auth': 'http://localhost:8000',
      '/projects': 'http://localhost:8000',
      '/plans': 'http://localhost:8000',
      '/outputs': 'http://localhost:8000',
      '/threads': 'http://localhost:8000',
      '/events': 'http://localhost:8000',
      '/agents': 'http://localhost:8000',
    },
  },
})