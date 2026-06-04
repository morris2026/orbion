import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import Approval from '@/pages/Approval'
import * as authModule from '@/lib/auth'

/** 辅助：创建简单JWT */
function createJWT(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  const signature = btoa('fake-signature')
  return `${header}.${body}.${signature}`
}

/** 辅助：mock apiGet返回 */
function mockApiGet(response: unknown) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(response),
  }))
}

/** 辅助：mock apiPost返回 */
function mockApiPost(response: unknown) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(response),
  }))
}


function renderApproval() {
  return render(
    <MemoryRouter initialEntries={['/approval']}>
      <Approval />
    </MemoryRouter>
  )
}

describe('Approval审批面板', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  describe('TC-19.5: 管理员审批面板 → 待审批用户列表', () => {
    it('列出pending用户，每个有approve/reject按钮', async () => {
      // 设置admin JWT
      authModule.setToken(createJWT({ sub: 'admin-1', username: 'admin', is_admin: true }))

      // mock待审批用户列表
      mockApiGet([
        { user_id: 'user-2', username: 'pending1', display_name: 'Pending One', status: 'pending', created_at: '2026-01-01T00:00:00Z' },
        { user_id: 'user-3', username: 'pending2', display_name: 'Pending Two', status: 'pending', created_at: '2026-01-02T00:00:00Z' },
      ])

      renderApproval()

      // 检查：列出pending用户
      await waitFor(() => {
        expect(screen.getByText('pending1')).toBeInTheDocument()
        expect(screen.getByText('pending2')).toBeInTheDocument()
      })

      // 检查：每个用户有approve和reject按钮
      const approveButtons = screen.getAllByRole('button', { name: /通过/i })
      const rejectButtons = screen.getAllByRole('button', { name: /拒绝/i })
      expect(approveButtons.length).toBe(2)
      expect(rejectButtons.length).toBe(2)
    })
  })

  describe('TC-19.6: 管理员审批操作 → 用户变为active', () => {
    it('点击approve按钮 → API调用 → 用户从列表移除', async () => {
      const user = userEvent.setup()
      authModule.setToken(createJWT({ sub: 'admin-1', username: 'admin', is_admin: true }))

      // 依次mock：GET pending列表 → POST approve → GET 刷新后的空列表
      vi.stubGlobal('fetch', vi.fn()
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve([{ user_id: 'user-2', username: 'pending1', display_name: 'Pending One', status: 'pending', created_at: '2026-01-01T00:00:00Z' }]),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ user_id: 'user-2', username: 'pending1', display_name: 'Pending One', status: 'active' }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve([]),
        })
      )

      renderApproval()

      // 等待列表渲染
      await waitFor(() => {
        expect(screen.getByText('pending1')).toBeInTheDocument()
      })

      // 点击approve按钮
      await user.click(screen.getByRole('button', { name: /通过/i }))

      // 检查：用户从列表移除
      await waitFor(() => {
        expect(screen.queryByText('pending1')).not.toBeInTheDocument()
      })
    })
  })
})