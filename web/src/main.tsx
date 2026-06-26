import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { loader } from '@monaco-editor/react'
import * as monaco from 'monaco-editor'
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'
import './index.css'
import App from './App.tsx'

// Monaco 从本地 bundle 加载（不走 CDN），避免 e2e 测试受 CDN 网络波动影响
loader.config({ monaco })

// 兼容 e2e 测试：window.monaco.editor.getEditors() 拿编辑器实例
;(window as unknown as { monaco: typeof monaco }).monaco = monaco

// Monaco Web Worker 注册：vite 通过 ?worker 后缀打包 worker 资源
self.MonacoEnvironment = {
  getWorker() {
    return new editorWorker()
  },
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
