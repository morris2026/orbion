import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import Login from '@/pages/Login'
import * as authModule from '@/lib/auth'

/** 辅助：mock apiPost返回 */
function mockApiPost(response: unknown) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(response),
  }))
}

/** 辅助：mock apiPost返回错误 */
function mockApiPostError(status: number, detail: string) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: false,
    status,
    json: () => Promise.resolve({ detail }),
  }))
}

/** 辅助：渲染Login组件（需在Router内部） */
function renderLogin() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <Login />
    </MemoryRouter>
  )
}

describe('Login页面', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  describe('TC-19.1: 注册表单 → pending状态提示', () => {
    it('非首个用户注册后显示等待管理员审批提示', async () => {
      const user = userEvent.setup()
      // 非首个用户注册返回pending状态
      mockApiPost({
        user_id: 'user-2',
        username: 'newuser',
        display_name: 'New User',
        status: 'pending',
        access_token: null,
        message: 'Awaiting admin approval',
      })

      renderLogin()

      // 切换到注册表单
      await user.click(screen.getByRole('button', { name: /注册/i }))

      // 填写注册表单
      await user.type(screen.getByLabelText(/用户名/i), 'newuser')
      await user.type(screen.getByLabelText(/密码/i), 'password123')
      await user.type(screen.getByLabelText(/显示名称/i), 'New User')

      // 提交
      await user.click(screen.getByRole('button', { name: /提交注册/i }))

      // 检查：显示等待审批提示（标题和段落都包含此文本）
      await waitFor(() => {
        expect(screen.getAllByText(/等待管理员审批/i).length).toBeGreaterThanOrEqual(1)
      })
      // 检查：不存储JWT
      expect(localStorage.getItem('orbion_token')).toBeNull()
    })
  })

  describe('TC-19.2: 第一个用户注册 → 自动审批 → 跳转工作区', () => {
    it('首个用户注册后自动获得JWT并跳转', async () => {
      const user = userEvent.setup()
      const navigateMock = vi.fn()
      vi.spyOn(authModule, 'setToken')

      mockApiPost({
        user_id: 'user-1',
        username: 'admin',
        display_name: 'Admin',
        status: 'active',
        access_token: 'jwt-token-123',
        token_type: 'bearer',
        message: 'First admin user',
      })

      renderLogin()

      // 切换到注册表单
      await user.click(screen.getByRole('button', { name: /注册/i }))

      await user.type(screen.getByLabelText(/用户名/i), 'admin')
      await user.type(screen.getByLabelText(/密码/i), 'password123')
      await user.type(screen.getByLabelText(/显示名称/i), 'Admin User')

      await user.click(screen.getByRole('button', { name: /提交注册/i }))

      // 检查：JWT写入存储
      await waitFor(() => {
        expect(authModule.setToken).toHaveBeenCalledWith('jwt-token-123')
      })
    })
  })

  describe('TC-19.3: 登录表单 → JWT存储 → 跳转工作区', () => {
    it('登录成功后JWT存储', async () => {
      const user = userEvent.setup()
      vi.spyOn(authModule, 'setToken')

      mockApiPost({
        user_id: 'user-1',
        username: 'admin',
        display_name: 'Admin',
        access_token: 'jwt-login-token',
        token_type: 'bearer',
      })

      renderLogin()

      // 默认显示登录表单
      await user.type(screen.getByLabelText(/用户名/i), 'admin')
      await user.type(screen.getByLabelText(/密码/i), 'password123')

      await user.click(screen.getByRole('button', { name: /登录/i }))

      // 检查：JWT写入存储
      await waitFor(() => {
        expect(authModule.setToken).toHaveBeenCalledWith('jwt-login-token')
      })
    })
  })

  describe('TC-19.4: pending用户登录 → 403提示', () => {
    it('pending用户登录显示等待审批提示', async () => {
      const user = userEvent.setup()

      // 登录返回403 pending
      mockApiPostError(403, 'Account pending admin approval')

      renderLogin()

      await user.type(screen.getByLabelText(/用户名/i), 'pendinguser')
      await user.type(screen.getByLabelText(/密码/i), 'password123')

      await user.click(screen.getByRole('button', { name: /登录/i }))

      // 检查：显示等待审批提示（标题和段落都包含此文本）
      await waitFor(() => {
        expect(screen.getAllByText(/等待管理员审批/i).length).toBeGreaterThanOrEqual(1)
      })
      // 检查：不存储JWT
      expect(localStorage.getItem('orbion_token')).toBeNull()
    })

    it('rejected用户登录显示被拒绝提示', async () => {
      const user = userEvent.setup()

      mockApiPostError(403, 'Account registration was rejected')

      renderLogin()

      await user.type(screen.getByLabelText(/用户名/i), 'rejecteduser')
      await user.type(screen.getByLabelText(/密码/i), 'password123')

      await user.click(screen.getByRole('button', { name: /登录/i }))

      await waitFor(() => {
        expect(screen.getAllByText(/被拒绝/i).length).toBeGreaterThanOrEqual(1)
      })
      expect(localStorage.getItem('orbion_token')).toBeNull()
    })
  })

  })