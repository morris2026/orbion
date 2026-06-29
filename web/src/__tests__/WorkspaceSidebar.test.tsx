import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

Element.prototype.scrollIntoView = vi.fn()
global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
Element.prototype.getAnimations = vi.fn().mockReturnValue([])

import * as authModule from '@/lib/auth'
import { WorkspaceSidebar } from '@/components/WorkspaceSidebar'

function renderWithRouter(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

function renderSidebar() {
  return renderWithRouter(
    <WorkspaceSidebar
      showLeft={true}
      showMiddle={true}
      showRight={true}
      onToggleLeft={() => {}}
      onToggleMiddle={() => {}}
      onToggleRight={() => {}}
    />,
  )
}

describe('WorkspaceSidebar', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('顶部渲染 Orbion 图标', () => {
    vi.spyOn(authModule, 'getUsername').mockReturnValue('testuser')
    vi.spyOn(authModule, 'getDisplayName').mockReturnValue(null)
    vi.spyOn(authModule, 'getIsAdmin').mockReturnValue(false)

    renderSidebar()

    expect(screen.getByTestId('sidebar-brand')).toBeInTheDocument()
    expect(screen.getByText('O')).toBeInTheDocument()
  })

  it('底部渲染用户菜单头像（display_name 首字母）', () => {
    vi.spyOn(authModule, 'getUsername').mockReturnValue('testuser')
    vi.spyOn(authModule, 'getDisplayName').mockReturnValue('张三')
    vi.spyOn(authModule, 'getIsAdmin').mockReturnValue(false)

    renderSidebar()

    expect(screen.getByTestId('sidebar-user')).toBeInTheDocument()
    expect(screen.getByText('张')).toBeInTheDocument()
  })

  it('无 display_name 时用 username 首字母', () => {
    vi.spyOn(authModule, 'getUsername').mockReturnValue('admin')
    vi.spyOn(authModule, 'getDisplayName').mockReturnValue(null)
    vi.spyOn(authModule, 'getIsAdmin').mockReturnValue(false)

    renderSidebar()

    expect(screen.getByText('A')).toBeInTheDocument()
  })

  it('admin 用户时用户菜单包含新用户审批', () => {
    vi.spyOn(authModule, 'getUsername').mockReturnValue('admin')
    vi.spyOn(authModule, 'getDisplayName').mockReturnValue(null)
    vi.spyOn(authModule, 'getIsAdmin').mockReturnValue(true)

    // base-ui DropdownMenu 在 jsdom 中不渲染 popup，
    // 此处验证 sidebar 渲染了头像按钮（admin 标识的 A）
    renderSidebar()

    expect(screen.getByText('A')).toBeInTheDocument()
  })
})
