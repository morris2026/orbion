import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { AppRoutes } from '@/App'
import * as authModule from '@/lib/auth'

/** 辅助：创建简单JWT */
function createJWT(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  const signature = btoa('fake-signature')
  return `${header}.${body}.${signature}`
}

/** 辅助：渲染AppRoutes组件（用MemoryRouter代替BrowserRouter） */
function renderApp(initialPath = '/workspace') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AppRoutes />
    </MemoryRouter>
  )
}

describe('App路由守卫', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  describe('TC-19.7: JWT过期 → 重定向登录页', () => {
    it('存储过期JWT时访问工作区重定向到登录页', () => {
      // 存储一个已过期JWT
      const exp = Math.floor(Date.now() / 1000) - 3600
      const token = createJWT({ sub: 'user-1', exp })
      authModule.setToken(token)

      renderApp('/workspace')

      // 被重定向到登录页，显示登录表单
      expect(screen.getByText(/登录 Orbion/i)).toBeInTheDocument()
    })
  })

  describe('TC-19.8: 未登录访问工作区 → 重定向登录页', () => {
    it('无JWT时访问工作区重定向到登录页', () => {
      // 不存储JWT
      renderApp('/workspace')

      // 被重定向到登录页
      expect(screen.getByText(/登录 Orbion/i)).toBeInTheDocument()
    })
  })

  describe('TC-19.9: 登出流程', () => {
    it('登出清除JWT并重定向登录页', async () => {
      const user = userEvent.setup()
      // 存储有效JWT
      const exp = Math.floor(Date.now() / 1000) + 3600
      const token = createJWT({ sub: 'user-1', username: 'admin', is_admin: true, exp })
      authModule.setToken(token)

      renderApp('/workspace')

      // 等待工作区渲染
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /登出/i })).toBeInTheDocument()
      })

      // 点击登出按钮
      await user.click(screen.getByRole('button', { name: /登出/i }))

      // 检查：JWT被清除
      expect(authModule.getToken()).toBeNull()
      // 检查：重定向到登录页
      await waitFor(() => {
        expect(screen.getByText(/登录 Orbion/i)).toBeInTheDocument()
      })
    })
  })
})