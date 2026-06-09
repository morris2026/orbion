import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, renderHook, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import ThreadList from '@/components/ThreadList'
import MessageItem from '@/components/MessageItem'
import DiscussionPanel from '@/components/DiscussionPanel'
import PlanCard from '@/components/PlanCard'
import OutputDiff from '@/components/OutputDiff'
import Workspace from '@/pages/Workspace'
import * as sseModule from '@/lib/sse'
import * as authModule from '@/lib/auth'
import type { UseWorkspaceOptions } from '@/hooks/useWorkspace'
import { useWorkspace } from '@/hooks/useWorkspace'

/** mock线程数据 */
const mockThreads = [
  { id: 't1', title: '线程1', status: 'active', type: 'discussion', has_summary: true, pending_plan_count: 2, message_count: 5, created_at: '2024-01-01T00:00:00Z' },
  { id: 't2', title: '线程2', status: 'active', type: 'discussion', has_summary: false, pending_plan_count: 0, message_count: 3, created_at: '2024-01-02T00:00:00Z' },
]

/** mock消息数据 */
const mockMessages = [
  { id: 'm1', thread_id: 't1', participant_id: 'u1', participant_type: 'human', display_name: '用户A', content: '你好', event_type: 'DiscussionMessageCreated', created_at: '2024-01-01T10:00:00Z' },
  { id: 'm2', thread_id: 't1', participant_id: 'a1', participant_type: 'agent', display_name: '总结Agent', content: '讨论要点如下', event_type: 'DiscussionSummaryGenerated', created_at: '2024-01-01T11:00:00Z' },
]

/** mock计划数据 */
const mockPlan = {
  id: 'p1', thread_id: 't1', status: 'proposed', proposed_by: 'a1',
  tasks: [
    { task_id: 'task-1', type: 'code', description: '实现登录功能', dependencies: [], priority: 'high', status: 'pending' },
  ],
  created_at: '2024-01-01T12:00:00Z',
}

/** mock产出diff */
const mockDiff = '--- a/file.py\n+++ b/file.py\n@@ -1,3 +1,4 @@\n-old line\n+new line\n+added line'

describe('前端三栏工作区完整交互', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  describe('MVP-20.1: 线程列表展示聚合字段', () => {
    it('has_summary标记：有摘要时显示标记', () => {
      const onSelect = vi.fn()
      render(<ThreadList threads={mockThreads} onSelect={onSelect} />)

      expect(screen.getByText('线程1')).toBeInTheDocument()
      expect(screen.getByTestId('t1-summary')).toBeInTheDocument()

      expect(screen.getByText('线程2')).toBeInTheDocument()
      expect(screen.queryByTestId('t2-summary')).not.toBeInTheDocument()
    })

    it('pending_plan_count和message_count正确显示', () => {
      const onSelect = vi.fn()
      render(<ThreadList threads={mockThreads} onSelect={onSelect} />)

      expect(screen.getByText(/2.*待审/)).toBeInTheDocument()
      expect(screen.getByText(/0.*待审/)).toBeInTheDocument()

      expect(screen.getByText(/5.*消息/)).toBeInTheDocument()
      expect(screen.getByText(/3.*消息/)).toBeInTheDocument()
    })

    it('选择线程触发onSelect回调', async () => {
      const user = userEvent.setup()
      const onSelect = vi.fn()
      render(<ThreadList threads={mockThreads} onSelect={onSelect} />)

      await user.click(screen.getByText('线程1'))
      expect(onSelect).toHaveBeenCalledWith('t1')
    })
  })

  describe('MVP-20.2: 人类/Agent消息样式区分', () => {
    it('participant_type="human"时普通样式', () => {
      render(<MessageItem message={mockMessages[0]} />)
      const container = screen.getByTestId('message-m1')
      expect(container).toHaveAttribute('data-participant-type', 'human')
    })

    it('participant_type="agent"时特殊卡片样式', () => {
      render(<MessageItem message={mockMessages[1]} />)
      const container = screen.getByTestId('message-m2')
      expect(container).toHaveAttribute('data-participant-type', 'agent')
    })
  })

  describe('MVP-20.3: request_summary按钮', () => {
    it('点击请求总结按钮触发onSendMessage回调，包含content和request_summary=true', async () => {
      const user = userEvent.setup()
      const onSendMessage = vi.fn()
      render(<DiscussionPanel messages={mockMessages} onSendMessage={onSendMessage} />)

      // 输入消息内容
      const input = screen.getByPlaceholderText(/输入消息/)
      await user.type(input, '这是我的观点')

      await user.click(screen.getByRole('button', { name: /请求总结/i }))
      expect(onSendMessage).toHaveBeenCalledWith({ content: '这是我的观点', request_summary: true })
    })

    it('未输入内容时点击请求总结使用默认content', async () => {
      const user = userEvent.setup()
      const onSendMessage = vi.fn()
      render(<DiscussionPanel messages={mockMessages} onSendMessage={onSendMessage} />)

      await user.click(screen.getByRole('button', { name: /请求总结/i }))
      expect(onSendMessage).toHaveBeenCalledWith({ content: '请总结当前讨论要点', request_summary: true })
    })
  })

  describe('MVP-20.4: 计划卡片审批操作', () => {
    it('approve按钮触发onApprove回调', async () => {
      const user = userEvent.setup()
      const onApprove = vi.fn()
      const onReject = vi.fn()
      render(<PlanCard plan={mockPlan} onApprove={onApprove} onReject={onReject} />)

      await user.click(screen.getByRole('button', { name: /批准/i }))
      expect(onApprove).toHaveBeenCalledWith('p1')
    })

    it('reject按钮需输入拒绝原因后触发onReject回调', async () => {
      const user = userEvent.setup()
      const onApprove = vi.fn()
      const onReject = vi.fn()
      render(<PlanCard plan={mockPlan} onApprove={onApprove} onReject={onReject} />)

      // 点击拒绝按钮展开输入框
      await user.click(screen.getByRole('button', { name: /拒绝/i }))

      // 输入拒绝原因
      const reasonInput = screen.getByPlaceholderText(/拒绝原因/)
      await user.type(reasonInput, '方案不合理')

      // 确认拒绝
      await user.click(screen.getByRole('button', { name: /确认拒绝/i }))
      expect(onReject).toHaveBeenCalledWith('p1', '方案不合理')
    })
  })

  describe('MVP-20.5: 产出diff预览', () => {
    it('diff内容正确渲染，包含增删行', () => {
      render(<OutputDiff diff={mockDiff} />)
      expect(screen.getByText(/old line/)).toBeInTheDocument()
      expect(screen.getByText(/new line/)).toBeInTheDocument()
      expect(screen.getByText(/added line/)).toBeInTheDocument()
    })
  })

  describe('MVP-20.6: SSE实时更新面板', () => {
    /** 构建注入初始状态的Workspace配置 */
    const baseInitialState: UseWorkspaceOptions = {
      initialState: {
        projects: [{ id: 'proj-1', name: '项目1', description: null, role: 'owner', created_at: '' }],
        selectedProjectId: 'proj-1',
        threads: mockThreads,
        selectedThreadId: 't1',
        messages: mockMessages,
        plans: [],
        outputs: [],
      },
    }

    it('message_created事件更新中栏消息列表（使用后端SSE字段名）', async () => {
      vi.spyOn(authModule, 'isAuthenticated').mockReturnValue(true)
      vi.spyOn(authModule, 'isTokenExpired').mockReturnValue(false)
      vi.spyOn(authModule, 'getIsAdmin').mockReturnValue(false)

      // mock SSE连接，捕获事件回调
      let sseOnEvent: ((event: Record<string, unknown>) => void) | null = null
      vi.spyOn(sseModule, 'createSSEConnection').mockImplementation((_projectId: string, onEvent: (event: Record<string, unknown>) => void) => {
        sseOnEvent = onEvent
        return { close: vi.fn() } as unknown as EventSource
      })
      vi.spyOn(sseModule, 'disconnectSSE').mockImplementation(() => {})

      render(
        <MemoryRouter initialEntries={['/workspace']}>
          <Workspace workspaceOptions={baseInitialState} />
        </MemoryRouter>
      )

      // 初始数据已注入
      expect(screen.getByText('线程1')).toBeInTheDocument()
      expect(screen.getByText('你好')).toBeInTheDocument()

      // 模拟message_created SSE事件——使用后端真实字段名
      sseOnEvent!({
        event_type: 'message_created',
        message_id: 'm-new',
        thread_id: 't1',
        participant_id: 'u2',
        participant_type: 'human',
        participant_display_name: '用户B',
        content: 'SSE新消息',
        created_at: '2024-01-03T10:00:00Z',
      })

      await waitFor(() => {
        expect(screen.getByText('SSE新消息')).toBeInTheDocument()
      })
    })

    it('plan_proposed事件更新右栏计划卡片（使用后端SSE字段名）', async () => {
      vi.spyOn(authModule, 'isAuthenticated').mockReturnValue(true)
      vi.spyOn(authModule, 'isTokenExpired').mockReturnValue(false)
      vi.spyOn(authModule, 'getIsAdmin').mockReturnValue(false)

      let sseOnEvent: ((event: Record<string, unknown>) => void) | null = null
      vi.spyOn(sseModule, 'createSSEConnection').mockImplementation((_projectId: string, onEvent: (event: Record<string, unknown>) => void) => {
        sseOnEvent = onEvent
        return { close: vi.fn() } as unknown as EventSource
      })
      vi.spyOn(sseModule, 'disconnectSSE').mockImplementation(() => {})

      render(
        <MemoryRouter initialEntries={['/workspace']}>
          <Workspace workspaceOptions={baseInitialState} />
        </MemoryRouter>
      )

      expect(screen.getByText('线程1')).toBeInTheDocument()

      // 模拟plan_proposed SSE事件——使用后端真实字段名
      sseOnEvent!({
        event_type: 'plan_proposed',
        plan_id: 'p-new',
        thread_id: 't1',
        participant_id: 'a2',
        participant_type: 'agent',
        participant_display_name: '分解Agent',
        tasks: [{ task_id: 'task-new', type: 'code', description: '新计划任务', dependencies: [], priority: 'medium', status: 'pending' }],
        created_at: '2024-01-04T00:00:00Z',
      })

      await waitFor(() => {
        expect(screen.getByText(/新计划任务/)).toBeInTheDocument()
      })
    })
  })
})

describe('MVP-UI-3.10: 新回调不影响initialState', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('注入initialState后新回调存在且不修改初始值', async () => {
    vi.spyOn(authModule, 'isAuthenticated').mockReturnValue(true)
    vi.spyOn(authModule, 'isTokenExpired').mockReturnValue(false)
    vi.spyOn(authModule, 'getIsAdmin').mockReturnValue(false)

    vi.spyOn(sseModule, 'createSSEConnection').mockImplementation(() => ({ close: vi.fn() } as unknown as EventSource))
    vi.spyOn(sseModule, 'disconnectSSE').mockImplementation(() => {})

    // mock apiPost——handleCreateProject会调用
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ id: 'proj-new', name: '新项目', description: null, role: 'owner', created_at: '' }),
    }))

    const opts: UseWorkspaceOptions = {
      initialState: {
        projects: [{ id: 'proj-1', name: '项目1', description: null, role: 'owner', created_at: '' }],
        selectedProjectId: 'proj-1',
        threads: mockThreads,
        selectedThreadId: 't1',
        messages: mockMessages,
        plans: [],
        outputs: [],
      },
    }

    const { result } = renderHook(() => useWorkspace(opts))

    // 验证initialState正确注入
    expect(result.current.projects).toEqual(opts.initialState!.projects)
    expect(result.current.threads).toEqual(mockThreads)
    expect(result.current.messages).toEqual(mockMessages)

    // 验证6个新回调存在
    expect(result.current.handleCreateProject).toBeDefined()
    expect(result.current.handleCreateThread).toBeDefined()
    expect(result.current.handleRegisterAgent).toBeDefined()
    expect(result.current.handleAddMember).toBeDefined()
    expect(result.current.handleApproveOutput).toBeDefined()
    expect(result.current.handleRequestRevision).toBeDefined()

    // 调用handleCreateProject后初始状态值不变
    await act(async () => {
      result.current.handleCreateProject({ name: '新项目', description: null })
    })

    expect(result.current.threads).toEqual(mockThreads)
    expect(result.current.messages).toEqual(mockMessages)

    vi.unstubAllGlobals()
  })
})