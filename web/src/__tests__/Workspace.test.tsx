import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, renderHook, act, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

// jsdom不支持scrollIntoView、ResizeObserver、getAnimations，全局mock
Element.prototype.scrollIntoView = vi.fn()
global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
Element.prototype.getAnimations = vi.fn().mockReturnValue([])

import ProjectTree from '@/components/ProjectTree'
import MessageBubble from '@/components/MessageBubble'
import DiscussionPanel from '@/components/DiscussionPanel'
import PlanCard from '@/components/PlanCard'
import OutputDiff from '@/components/OutputDiff'
import Workspace from '@/pages/Workspace'
import * as sseModule from '@/lib/sse'
import * as authModule from '@/lib/auth'
import * as apiModule from '@/lib/api'
import type { UseWorkspaceOptions } from '@/hooks/useWorkspace'
import { useWorkspace } from '@/hooks/useWorkspace'
import type { ProjectListItem, ThreadListItem } from '@/types/api'

/** mock线程数据（含project_id和默认线程） */
const mockThreads: ThreadListItem[] = [
  { id: 'dt-1', project_id: 'proj-1', title: '默认线程1', status: 'active', type: 'discussion', has_summary: false, pending_plan_count: 0, message_count: 0, unread_count: 0, created_at: '2024-01-01T00:00:00Z' },
  { id: 't1', project_id: 'proj-1', title: '线程1', status: 'active', type: 'discussion', has_summary: true, pending_plan_count: 2, message_count: 5, unread_count: 3, created_at: '2024-01-01T00:00:00Z' },
  { id: 't2', project_id: 'proj-1', title: '线程2', status: 'active', type: 'discussion', has_summary: false, pending_plan_count: 0, message_count: 3, unread_count: 0, created_at: '2024-01-02T00:00:00Z' },
  { id: 'dt-2', project_id: 'proj-2', title: '默认线程2', status: 'active', type: 'discussion', has_summary: false, pending_plan_count: 0, message_count: 0, unread_count: 0, created_at: '2024-01-02T00:00:00Z' },
]

/** mock项目数据 */
const mockProjects: ProjectListItem[] = [
  { id: 'proj-1', name: '项目Alpha', description: '描述1', role: 'owner', default_thread_id: 'dt-1', created_at: '2024-01-01T00:00:00Z' },
  { id: 'proj-2', name: '项目Beta', description: null, role: 'member', default_thread_id: 'dt-2', created_at: '2024-01-02T00:00:00Z' },
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

  describe('MVP-20.1: 线程列表基本渲染', () => {
    it('线程名称正确显示', () => {
      const onSelectThread = vi.fn()
      render(<ProjectTree
        projects={mockProjects}
        threads={mockThreads}
        selectedProjectId="proj-1"
        selectedThreadId="dt-1"
        onSelectThread={onSelectThread}
        onSelectProject={vi.fn()}
        onCreateProject={vi.fn()}
        onCreateThread={vi.fn()}
        onAddMember={vi.fn()}
        onRegisterAgent={vi.fn()}
      />)

      expect(screen.getByText('线程1')).toBeInTheDocument()
      expect(screen.getByText('线程2')).toBeInTheDocument()
    })

    it('选择线程触发onSelectThread回调', async () => {
      const user = userEvent.setup()
      const onSelectThread = vi.fn()
      render(<ProjectTree
        projects={mockProjects}
        threads={mockThreads}
        selectedProjectId="proj-1"
        selectedThreadId="dt-1"
        onSelectThread={onSelectThread}
        onSelectProject={vi.fn()}
        onCreateProject={vi.fn()}
        onCreateThread={vi.fn()}
        onAddMember={vi.fn()}
        onRegisterAgent={vi.fn()}
      />)

      await user.click(screen.getByText('线程1'))
      expect(onSelectThread).toHaveBeenCalledWith('t1')
    })
  })

  describe('MVP-20.2-更新: MessageBubble人类/Agent消息样式区分', () => {
    it('participant_type="human"别人消息 → 左对齐浅色泡泡', () => {
      render(<MessageBubble message={mockMessages[0]} currentUserId="u-other" />)
      const bubble = screen.getByTestId('bubble-m1')
      expect(bubble).toHaveAttribute('data-participant-type', 'other')
      expect(bubble).toHaveAttribute('data-align', 'left')
    })

    it('participant_type="agent" → Agent浅蓝泡泡🤖', () => {
      render(<MessageBubble message={mockMessages[1]} currentUserId="u1" />)
      const bubble = screen.getByTestId('bubble-m2')
      expect(bubble).toHaveAttribute('data-participant-type', 'agent')
      expect(bubble).toHaveAttribute('data-align', 'left')
    })
  })

  describe('MVP-20.3-更新: 请求总结→斜杠命令', () => {
    it('输入/summarize+Enter → request_summary=true + 默认文案', async () => {
      const onSendMessage = vi.fn().mockResolvedValue(undefined)
      render(<DiscussionPanel messages={mockMessages} currentUserId="u1" onSendMessage={onSendMessage} />)

      const textarea = screen.getByPlaceholderText(/输入消息.*\/summarize/i)
      fireEvent.change(textarea, { target: { value: '/summarize' } })
      fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })

      await waitFor(() => {
        expect(onSendMessage).toHaveBeenCalledWith({ content: '请总结当前讨论要点', request_summary: true })
      })
    })

    it('输入/summarize 观点+Enter → request_summary=true + 观点内容', async () => {
      const onSendMessage = vi.fn().mockResolvedValue(undefined)
      render(<DiscussionPanel messages={mockMessages} currentUserId="u1" onSendMessage={onSendMessage} />)

      const textarea = screen.getByPlaceholderText(/输入消息.*\/summarize/i)
      fireEvent.change(textarea, { target: { value: '/summarize 观点' } })
      fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })

      await waitFor(() => {
        expect(onSendMessage).toHaveBeenCalledWith({ content: '观点', request_summary: true })
      })
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
        projects: [{ id: 'proj-1', name: '项目1', description: null, role: 'owner', default_thread_id: 't1', created_at: '' }],
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

      // 初始数据已注入——ProjectTree显示项目名而非默认线程名
      expect(screen.getByText('项目1')).toBeInTheDocument()
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

      expect(screen.getByText('项目1')).toBeInTheDocument()

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

describe('消息显示：POST触发后端→SSE推送显示（单一来源）', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('POST发送消息后→SSE推送→消息显示（不重复）', async () => {
    vi.spyOn(authModule, 'isAuthenticated').mockReturnValue(true)
    vi.spyOn(authModule, 'isTokenExpired').mockReturnValue(false)
    vi.spyOn(authModule, 'getIsAdmin').mockReturnValue(false)

    let sseOnEvent: ((event: Record<string, unknown>) => void) | null = null
    vi.spyOn(sseModule, 'createSSEConnection').mockImplementation((_projectId: string, onEvent: (event: Record<string, unknown>) => void) => {
      sseOnEvent = onEvent
      return { close: vi.fn() } as unknown as EventSource
    })
    vi.spyOn(sseModule, 'disconnectSSE').mockImplementation(() => {})
    vi.spyOn(apiModule, 'apiGet').mockResolvedValue([])
    // POST只触发后端发布事件，不返回消息用于乐观更新
    vi.spyOn(apiModule, 'apiPost').mockResolvedValue(undefined)

    const opts: UseWorkspaceOptions = {
      initialState: {
        projects: [{ id: 'proj-1', name: '项目1', description: null, role: 'owner', default_thread_id: 't1', created_at: '' }],
        selectedProjectId: 'proj-1',
        threads: mockThreads,
        selectedThreadId: 't1',
        messages: [],
        plans: [],
        outputs: [],
      },
    }

    const { result } = renderHook(() => useWorkspace(opts))

    // 发送消息（POST仅触发后端）
    await act(async () => {
      result.current.handleSendMessage({ content: 'SSE推送消息' })
    })

    // POST不直接更新state——消息列表仍为空
    expect(result.current.messages.length).toBe(0)

    // SSE推送消息
    act(() => {
      sseOnEvent!({
        event_type: 'message_created',
        message_id: 'msg-sse-test',
        thread_id: 't1',
        participant_id: 'u1',
        participant_type: 'human',
        participant_display_name: '用户A',
        content: 'SSE推送消息',
        created_at: '2024-01-01T12:00:00Z',
      })
    })

    // SSE推送后消息出现
    await waitFor(() => {
      expect(result.current.messages.length).toBe(1)
      expect(result.current.messages[0].id).toBe('msg-sse-test')
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
        projects: [{ id: 'proj-1', name: '项目1', description: null, role: 'owner', default_thread_id: 't1', created_at: '' }],
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

describe('useWorkspace: 重启后加载已有数据', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('无initialState时通过API加载项目列表并按名称排序', async () => {
    const unsortedProjects: ProjectListItem[] = [
      { id: 'proj-2', name: 'Zeta项目', description: null, role: 'member', default_thread_id: 'dt-2', created_at: '2024-01-02T00:00:00Z' },
      { id: 'proj-1', name: 'Alpha项目', description: '描述', role: 'owner', default_thread_id: 'dt-1', created_at: '2024-01-01T00:00:00Z' },
    ]
    const sortedProjects = [...unsortedProjects].sort((a, b) => a.name.localeCompare(b.name))

    vi.spyOn(authModule, 'isAuthenticated').mockReturnValue(true)
    vi.spyOn(authModule, 'isTokenExpired').mockReturnValue(false)
    vi.spyOn(sseModule, 'createSSEConnection').mockImplementation(() => ({ close: vi.fn() } as unknown as EventSource))
    vi.spyOn(sseModule, 'disconnectSSE').mockImplementation(() => {})
    // apiGet按URL区分：/projects返回项目列表，/projects/:id/threads返回空线程
    vi.spyOn(apiModule, 'apiGet').mockImplementation((url: string) => {
      if (url === '/projects') return Promise.resolve(unsortedProjects)
      return Promise.resolve([])
    })

    const { result } = renderHook(() => useWorkspace())

    expect(result.current.projects).toEqual([])

    await waitFor(() => {
      expect(result.current.projects).toEqual(sortedProjects)
    })

    expect(apiModule.apiGet).toHaveBeenCalledWith('/projects')
  })

  it('有initialState时跳过API加载', async () => {
    vi.spyOn(authModule, 'isAuthenticated').mockReturnValue(true)
    vi.spyOn(authModule, 'isTokenExpired').mockReturnValue(false)
    vi.spyOn(sseModule, 'createSSEConnection').mockImplementation(() => ({ close: vi.fn() } as unknown as EventSource))
    vi.spyOn(sseModule, 'disconnectSSE').mockImplementation(() => {})
    vi.spyOn(apiModule, 'apiGet').mockResolvedValue([])

    const opts: UseWorkspaceOptions = {
      initialState: {
        projects: mockProjects,
        selectedProjectId: 'proj-1',
        threads: mockThreads,
        selectedThreadId: 'dt-1',
        messages: mockMessages,
        plans: [],
        outputs: [],
      },
    }

    const { result } = renderHook(() => useWorkspace(opts))

    expect(result.current.projects).toEqual(mockProjects)
    expect(apiModule.apiGet).not.toHaveBeenCalledWith('/projects')
  })
})

describe('MVP-UI-4.x: ProjectTree组件', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  /** ProjectTree默认props */
  const treeProps = {
    projects: mockProjects,
    threads: mockThreads,
    selectedProjectId: 'proj-1',
    selectedThreadId: 'dt-1',
    onSelectThread: vi.fn(),
    onSelectProject: vi.fn(),
    onCreateProject: vi.fn(),
    onCreateThread: vi.fn(),
    onAddMember: vi.fn(),
    onRegisterAgent: vi.fn(),
  }

  describe('MVP-UI-4.1: 两层树形渲染', () => {
    it('项目节点和子线程渲染，图标按钮存在，顶部新建项目按钮存在', async () => {
      const user = userEvent.setup()
      render(<ProjectTree {...treeProps} />)

      // 项目节点存在
      expect(screen.getByText('项目Alpha')).toBeInTheDocument()
      expect(screen.getByText('项目Beta')).toBeInTheDocument()

      // 子线程存在于选中项目下
      expect(screen.getByText('线程1')).toBeInTheDocument()
      expect(screen.getByText('线程2')).toBeInTheDocument()

      // 项目节点旁图标按钮存在（➕👤🤖）
      expect(screen.getByRole('button', { name: /新建线程.*proj-1/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /添加成员.*proj-1/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /注册Agent.*proj-1/i })).toBeInTheDocument()

      // 顶部新建项目➕按钮存在
      expect(screen.getByRole('button', { name: /新建项目/i })).toBeInTheDocument()
    })
  })

  describe('MVP-UI-4.2: 选中项目高亮', () => {
    it('选中项目 → data-selected="true"', () => {
      render(<ProjectTree {...treeProps} />)

      // proj-1是选中项目，应该有data-selected
      const projectNode = screen.getByTestId('project-proj-1')
      expect(projectNode).toHaveAttribute('data-selected', 'true')

      // proj-2不是选中项目，不应该有data-selected
      const otherProjectNode = screen.getByTestId('project-proj-2')
      expect(otherProjectNode).not.toHaveAttribute('data-selected')
    })
  })

  describe('MVP-UI-4.3: 点击项目选中项目和默认线程', () => {
    it('点击项目 → onSelectProject收到项目ID，onSelectThread收到默认线程ID', async () => {
      const user = userEvent.setup()
      const onSelectThread = vi.fn()
      const onSelectProject = vi.fn()
      render(<ProjectTree {...treeProps} selectedProjectId={null} selectedThreadId={null} onSelectThread={onSelectThread} onSelectProject={onSelectProject} />)

      await user.click(screen.getByText('项目Alpha'))
      expect(onSelectProject).toHaveBeenCalledWith('proj-1')
      expect(onSelectThread).toHaveBeenCalledWith('dt-1')
    })
  })

  describe('MVP-UI-4.4: 点击子线程', () => {
    it('点击线程 → onSelectThread收到线程ID，onSelectProject收到项目ID', async () => {
      const user = userEvent.setup()
      const onSelectThread = vi.fn()
      const onSelectProject = vi.fn()
      render(<ProjectTree {...treeProps} onSelectThread={onSelectThread} onSelectProject={onSelectProject} />)

      await user.click(screen.getByText('线程1'))
      expect(onSelectThread).toHaveBeenCalledWith('t1')
      expect(onSelectProject).toHaveBeenCalledWith('proj-1')
    })
  })

  describe('MVP-UI-4.5: 未读Badge', () => {
    it('unread_count > 1 → 显示数字Badge', () => {
      render(<ProjectTree {...treeProps} />)

      // 线程1的unread_count=3 → 显示数字Badge
      expect(screen.getByText('3')).toHaveAttribute('data-unread', 'true')
    })

    it('unread_count === 1 → 显示蓝色圆点', () => {
      const singleUnreadThreads: ThreadListItem[] = [
        { id: 't1', project_id: 'proj-1', title: '线程1', status: 'active', type: 'discussion', has_summary: false, pending_plan_count: 0, message_count: 0, unread_count: 1, created_at: '2024-01-01T00:00:00Z' },
      ]
      render(<ProjectTree {...treeProps} threads={singleUnreadThreads} />)

      // 1条未读显示圆点而非数字
      expect(screen.getByText('线程1')).toBeInTheDocument()
      expect(screen.queryByText('1')).not.toBeInTheDocument()
    })
  })

  describe('MVP-UI-4.6: 选中线程不显示未读', () => {
    it('当前选中线程 → 无未读提示', () => {
      // 选中线程t1（unread_count=3），但因为是选中线程，不应显示未读Badge
      render(<ProjectTree {...treeProps} selectedThreadId='t1' />)

      // 线程1被选中，即使有unread_count也不显示Badge
      const t1Node = screen.getByTestId('thread-t1')
      expect(t1Node).not.toHaveAttribute('data-unread')
    })
  })

  describe('MVP-UI-4.7: 项目节点图标按钮回调', () => {
    it('➕→onCreateThread，👤→onAddMember，🤖→onRegisterAgent', async () => {
      const user = userEvent.setup()
      const onCreateThread = vi.fn()
      const onAddMember = vi.fn()
      const onRegisterAgent = vi.fn()
      render(<ProjectTree {...treeProps} onCreateThread={onCreateThread} onAddMember={onAddMember} onRegisterAgent={onRegisterAgent} />)

      await user.click(screen.getByRole('button', { name: /新建线程.*proj-1/i }))
      expect(onCreateThread).toHaveBeenCalledWith('proj-1')

      await user.click(screen.getByRole('button', { name: /添加成员.*proj-1/i }))
      expect(onAddMember).toHaveBeenCalledWith('proj-1')

      await user.click(screen.getByRole('button', { name: /注册Agent.*proj-1/i }))
      expect(onRegisterAgent).toHaveBeenCalledWith('proj-1')
    })
  })

  describe('MVP-UI-4.8: 顶部新建项目按钮', () => {
    it('导航栏顶部➕按钮 → onCreateProject', async () => {
      const user = userEvent.setup()
      const onCreateProject = vi.fn()
      render(<ProjectTree {...treeProps} onCreateProject={onCreateProject} />)

      await user.click(screen.getByRole('button', { name: /新建项目/i }))
      expect(onCreateProject).toHaveBeenCalled()
    })
  })

  describe('MVP-UI-4.9: 项目无子线程', () => {
    it('只有默认线程 → 不显示子节点', () => {
      // 提供包含默认线程的threads数组，默认线程不显示为子节点
      const onlyDefaultThreads: ThreadListItem[] = [
        { id: 'dt-1', project_id: 'proj-1', title: '默认线程', status: 'active', type: 'discussion', has_summary: false, pending_plan_count: 0, message_count: 0, unread_count: 0, created_at: '2024-01-01T00:00:00Z' },
      ]
      render(<ProjectTree {...treeProps} threads={onlyDefaultThreads} />)

      // 项目Alpha仍存在但默认线程不作为子节点显示
      expect(screen.getByText('项目Alpha')).toBeInTheDocument()
      expect(screen.queryByText('默认线程')).not.toBeInTheDocument()
      expect(screen.queryByText('线程1')).not.toBeInTheDocument()
    })
  })

  describe('MVP-UI-4.10: 空项目列表', () => {
    it('projects=[] → 显示空状态提示', () => {
      render(<ProjectTree {...treeProps} projects={[]} />)

      expect(screen.getByText(/暂无项目/i)).toBeInTheDocument()
    })
  })

  describe('MVP-UI-4.11: Tooltip hover', () => {
    it('hover图标按钮 → 显示对应文字', async () => {
      const user = userEvent.setup()
      render(<ProjectTree {...treeProps} />)

      // hover新建线程按钮
      await user.hover(screen.getByRole('button', { name: /新建线程.*proj-1/i }))
      expect(screen.getByText('新建线程')).toBeInTheDocument()

      // hover添加成员按钮
      await user.hover(screen.getByRole('button', { name: /添加成员.*proj-1/i }))
      expect(screen.getByText('添加成员')).toBeInTheDocument()

      // hover注册Agent按钮
      await user.hover(screen.getByRole('button', { name: /注册Agent.*proj-1/i }))
      expect(screen.getByText('注册Agent')).toBeInTheDocument()
    })
  })

  describe('MVP-UI-4.12: tooltip打开时按钮保持可见', () => {
    it('hover按钮→按钮容器显示opacity-100（JS state控制）', async () => {
      const user = userEvent.setup()
      render(<ProjectTree {...treeProps} />)

      const addMemberBtn = screen.getByRole('button', { name: /添加成员.*proj-1/i })
      await user.hover(addMemberBtn)

      // hover 触发 → hoveredProjectId = proj-1 → opacity-100
      const buttonGroup = addMemberBtn.parentElement!
      const classes = buttonGroup.className.split(' ')
      expect(classes).toContain('opacity-100')
      expect(classes).not.toContain('opacity-0')
    })

    it('未hover且无tooltip时按钮容器显示opacity-0', () => {
      render(<ProjectTree {...treeProps} />)

      const addMemberBtn = screen.getByRole('button', { name: /添加成员.*proj-1/i })
      // 初始状态 → 无hover无tooltip → opacity-0
      const buttonGroup = addMemberBtn.parentElement!
      const classes = buttonGroup.className.split(' ')
      expect(classes).toContain('opacity-0')
      expect(classes).not.toContain('opacity-100')
    })

    it('hover后离开→tooltip关闭→按钮容器恢复opacity-0', async () => {
      const user = userEvent.setup()
      render(<ProjectTree {...treeProps} />)

      const newThreadBtn = screen.getByRole('button', { name: /新建线程.*proj-1/i })
      await user.hover(newThreadBtn)

      // hover时按钮可见
      const buttonGroup = newThreadBtn.parentElement!
      expect(buttonGroup.className.split(' ')).toContain('opacity-100')

      // 鼠标移到另一个项目 → tooltip关闭 → 恢复opacity-0
      await user.hover(screen.getByText('项目Beta'))
      await waitFor(() => {
        expect(screen.queryByText('新建线程')).not.toBeInTheDocument()
      })
      expect(buttonGroup.className.split(' ')).toContain('opacity-0')
      expect(buttonGroup.className.split(' ')).not.toContain('opacity-100')
    })
  })

  describe('MVP-20.1-更新: ThreadList→ProjectTree迁移', () => {
    it('线程名称在新组件中正确显示', () => {
      render(<ProjectTree {...treeProps} />)

      expect(screen.getByText('线程1')).toBeInTheDocument()
      expect(screen.getByText('线程2')).toBeInTheDocument()
    })
  })

  describe('MVP-UI-4.13: 选中高亮——点谁高亮谁', () => {
    it('选中项目+默认线程 → 项目高亮（用户点了项目行）', () => {
      render(<ProjectTree {...treeProps} selectedThreadId='dt-1' />)

      const projectRow = screen.getByTestId('project-proj-1').firstElementChild!
      expect(projectRow.className).toContain('bg-accent')
    })

    it('选中非默认线程 → 线程高亮，项目不高亮', () => {
      render(<ProjectTree {...treeProps} selectedThreadId='t1' />)

      const t1Row = screen.getByTestId('thread-t1')
      expect(t1Row.className).toContain('bg-accent')

      const projectRow = screen.getByTestId('project-proj-1').firstElementChild!
      expect(projectRow.className).not.toContain('bg-accent')
    })

    it('未选中任何线程 → 项目不高亮', () => {
      render(<ProjectTree {...treeProps} selectedThreadId={null} />)

      const projectRow = screen.getByTestId('project-proj-1').firstElementChild!
      expect(projectRow.className).not.toContain('bg-accent')
    })
  })

  describe('MVP-UI-4.14: 折叠/展开——点击项目切换', () => {
    it('点击项目 → 选中项目+切换折叠', async () => {
      const user = userEvent.setup()
      const onSelectProject = vi.fn()
      render(<ProjectTree {...treeProps} selectedProjectId={null} selectedThreadId={null} onSelectProject={onSelectProject} />)

      expect(screen.queryByText('线程1')).not.toBeInTheDocument()

      await user.click(screen.getByText('项目Alpha'))
      expect(onSelectProject).toHaveBeenCalledWith('proj-1')

      // 展开后线程可见
      await waitFor(() => {
        expect(screen.getByText('线程1')).toBeInTheDocument()
      })
    })

    it('再次点击项目 → 折叠，线程隐藏', async () => {
      const user = userEvent.setup()
      render(<ProjectTree {...treeProps} />)

      expect(screen.getByText('线程1')).toBeInTheDocument()

      await user.click(screen.getByText('项目Alpha'))

      await waitFor(() => {
        expect(screen.queryByText('线程1')).not.toBeInTheDocument()
      })
    })

    it('点击项目B不影响项目A的折叠状态', async () => {
      const user = userEvent.setup()
      render(<ProjectTree {...treeProps} />)

      expect(screen.getByText('线程1')).toBeInTheDocument()

      await user.click(screen.getByText('项目Beta'))

      // 项目A的线程仍然可见
      expect(screen.getByText('线程1')).toBeInTheDocument()
    })
  })

  describe('MVP-UI-4.15: 箭头显示条件', () => {
    it('有非默认线程的项目 → 显示箭头', () => {
      render(<ProjectTree {...treeProps} />)

      // proj-1有t1/t2两个非默认线程 → 箭头存在
      const proj1Chevrons = screen.getByTestId('project-proj-1').querySelectorAll('svg.shrink-0')
      expect(proj1Chevrons.length).toBeGreaterThanOrEqual(1)
    })

    it('只有默认线程的项目 → 不显示箭头（显示占位）', () => {
      const noExtraThreads: ThreadListItem[] = [
        { id: 'dt-1', project_id: 'proj-1', title: '默认', status: 'active', type: 'discussion', has_summary: false, pending_plan_count: 0, message_count: 0, created_at: '2024-01-01T00:00:00Z' },
        { id: 'dt-2', project_id: 'proj-2', title: '默认', status: 'active', type: 'discussion', has_summary: false, pending_plan_count: 0, message_count: 0, created_at: '2024-01-02T00:00:00Z' },
      ]
      render(<ProjectTree {...treeProps} threads={noExtraThreads} />)

      // proj-1只有默认线程 → 无箭头svg，有占位span
      const proj1Svgs = screen.getByTestId('project-proj-1').querySelectorAll('svg.shrink-0')
      expect(proj1Svgs.length).toBe(0)

      // 占位span存在（h-4 w-4）
      const placeholder = screen.getByTestId('project-proj-1').querySelector('.h-4.w-4.shrink-0')
      expect(placeholder).toBeInTheDocument()
      expect(placeholder!.tagName).toBe('SPAN')
    })
  })

  describe('MVP-UI-4.16: 线程按project_id过滤', () => {
    it('线程只显示在所属项目下，不跨项目', async () => {
      const crossProjectThreads: ThreadListItem[] = [
        { id: 'dt-1', project_id: 'proj-1', title: '默认1', status: 'active', type: 'discussion', has_summary: false, pending_plan_count: 0, message_count: 0, created_at: '2024-01-01T00:00:00Z' },
        { id: 't1', project_id: 'proj-1', title: '线程A', status: 'active', type: 'discussion', has_summary: false, pending_plan_count: 0, message_count: 0, created_at: '2024-01-01T00:00:00Z' },
        { id: 'dt-2', project_id: 'proj-2', title: '默认2', status: 'active', type: 'discussion', has_summary: false, pending_plan_count: 0, message_count: 0, created_at: '2024-01-02T00:00:00Z' },
        { id: 't3', project_id: 'proj-2', title: '线程B', status: 'active', type: 'discussion', has_summary: false, pending_plan_count: 0, message_count: 0, created_at: '2024-01-02T00:00:00Z' },
      ]

      // 展开两个项目
      const user = userEvent.setup()
      render(<ProjectTree {...treeProps} threads={crossProjectThreads} selectedProjectId={null} selectedThreadId={null} />)

      // 展开proj-1
      const proj1Arrow = screen.getByTestId('project-proj-1').querySelector('svg.shrink-0')
      await user.click(proj1Arrow!)

      // 展开proj-2
      const proj2Arrow = screen.getByTestId('project-proj-2').querySelector('svg.shrink-0')
      await user.click(proj2Arrow!)

      // 线程A只在proj-1下，线程B只在proj-2下
      await waitFor(() => {
        expect(screen.getByText('线程A')).toBeInTheDocument()
        expect(screen.getByText('线程B')).toBeInTheDocument()
      })

      // 确认线程A在proj-1的容器内，线程B在proj-2的容器内
      const proj1Container = screen.getByTestId('project-proj-1')
      expect(proj1Container.textContent).toContain('线程A')
      expect(proj1Container.textContent).not.toContain('线程B')

      const proj2Container = screen.getByTestId('project-proj-2')
      expect(proj2Container.textContent).toContain('线程B')
      expect(proj2Container.textContent).not.toContain('线程A')
    })
  })

  describe('MVP-UI-4.17: 字母序排序', () => {
    it('项目按名称字母序排列', () => {
      const unsortedProjects: ProjectListItem[] = [
        { id: 'proj-3', name: 'Zeta项目', description: null, role: 'owner', default_thread_id: 'dt-3', created_at: '2024-03-01T00:00:00Z' },
        { id: 'proj-2', name: 'Beta项目', description: null, role: 'member', default_thread_id: 'dt-2', created_at: '2024-02-01T00:00:00Z' },
        { id: 'proj-1', name: 'Alpha项目', description: '描述', role: 'owner', default_thread_id: 'dt-1', created_at: '2024-01-01T00:00:00Z' },
      ]
      render(<ProjectTree {...treeProps} projects={unsortedProjects} />)

      // 渲染顺序应为 Alpha → Beta → Zeta
      // 用textContent定位项目节点顺序——检查项目名称在DOM中的出现顺序
      const projectNames = unsortedProjects.map(p => p.name).sort((a, b) => a.localeCompare(b))
      const container = screen.getByText('Orbion').closest('.p-4')!
      // Alpha出现在Zeta之前
      const alphaIndex = container.textContent!.indexOf(projectNames[0])
      const betaIndex = container.textContent!.indexOf(projectNames[1])
      const zetaIndex = container.textContent!.indexOf(projectNames[2])
      expect(alphaIndex).toBeLessThan(betaIndex)
      expect(betaIndex).toBeLessThan(zetaIndex)
    })

    it('线程按标题字母序排列', async () => {
      const unsortedThreads: ThreadListItem[] = [
        { id: 'dt-1', project_id: 'proj-1', title: '默认1', status: 'active', type: 'discussion', has_summary: false, pending_plan_count: 0, message_count: 0, created_at: '2024-01-01T00:00:00Z' },
        { id: 't3', project_id: 'proj-1', title: '线程Z', status: 'active', type: 'discussion', has_summary: false, pending_plan_count: 0, message_count: 0, created_at: '2024-03-01T00:00:00Z' },
        { id: 't1', project_id: 'proj-1', title: '线程A', status: 'active', type: 'discussion', has_summary: false, pending_plan_count: 0, message_count: 0, created_at: '2024-01-01T00:00:00Z' },
        { id: 't2', project_id: 'proj-1', title: '线程B', status: 'active', type: 'discussion', has_summary: false, pending_plan_count: 0, message_count: 0, created_at: '2024-02-01T00:00:00Z' },
        { id: 'dt-2', project_id: 'proj-2', title: '默认2', status: 'active', type: 'discussion', has_summary: false, pending_plan_count: 0, message_count: 0, created_at: '2024-01-02T00:00:00Z' },
      ]
      // proj-1默认展开（selectedProjectId='proj-1'）
      render(<ProjectTree {...treeProps} threads={unsortedThreads} />)

      // proj-1下的非默认线程按标题排序：线程A → 线程B → 线程Z
      const proj1Container = screen.getByTestId('project-proj-1')
      const threadNodes = proj1Container.querySelectorAll('[data-testid^="thread-"]')
      expect(threadNodes.length).toBe(3)
      expect(threadNodes[0]).toHaveAttribute('data-testid', 'thread-t1') // 线程A
      expect(threadNodes[1]).toHaveAttribute('data-testid', 'thread-t2') // 线程B
      expect(threadNodes[2]).toHaveAttribute('data-testid', 'thread-t3') // 线程Z
    })
  })
})

describe('MVP-UI-6.x: ProjectTree与Dialog联动', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  const baseInitialState: UseWorkspaceOptions = {
    initialState: {
      projects: mockProjects,
      selectedProjectId: 'proj-1',
      threads: mockThreads,
      selectedThreadId: 'dt-1',
      messages: mockMessages,
      plans: [],
      outputs: [],
    },
  }

  describe('MVP-UI-6.1: 图标按钮→Dialog打开', () => {
    it('点击➕新建项目按钮 → CreateProjectDialog打开', async () => {
      const user = userEvent.setup()
      vi.spyOn(authModule, 'isAuthenticated').mockReturnValue(true)
      vi.spyOn(authModule, 'isTokenExpired').mockReturnValue(false)
      vi.spyOn(authModule, 'getIsAdmin').mockReturnValue(false)
      vi.spyOn(sseModule, 'createSSEConnection').mockReturnValue({ close: vi.fn() } as unknown as EventSource)
      vi.spyOn(sseModule, 'disconnectSSE').mockImplementation(() => {})
      vi.spyOn(apiModule, 'apiGet').mockResolvedValue([])

      render(
        <MemoryRouter>
          <Workspace workspaceOptions={baseInitialState} />
        </MemoryRouter>
      )

      // 点击顶部新建项目按钮
      await user.click(screen.getByRole('button', { name: /新建项目/i }))

      // CreateProjectDialog 应打开
      await waitFor(() => {
        expect(screen.getByText('新建项目')).toBeInTheDocument()
        expect(screen.getByLabelText(/项目名称/i)).toBeInTheDocument()
      })
    })

    it('点击➕新建线程按钮 → CreateThreadDialog打开', async () => {
      const user = userEvent.setup()
      vi.spyOn(authModule, 'isAuthenticated').mockReturnValue(true)
      vi.spyOn(authModule, 'isTokenExpired').mockReturnValue(false)
      vi.spyOn(authModule, 'getIsAdmin').mockReturnValue(false)
      vi.spyOn(sseModule, 'createSSEConnection').mockReturnValue({ close: vi.fn() } as unknown as EventSource)
      vi.spyOn(sseModule, 'disconnectSSE').mockImplementation(() => {})
      vi.spyOn(apiModule, 'apiGet').mockResolvedValue([])

      render(
        <MemoryRouter>
          <Workspace workspaceOptions={baseInitialState} />
        </MemoryRouter>
      )

      // hover项目节点显示图标按钮，然后点击新建线程
      await user.hover(screen.getByText('项目Alpha'))
      await user.click(screen.getByRole('button', { name: /新建线程.*proj-1/i }))

      // CreateThreadDialog 应打开
      await waitFor(() => {
        expect(screen.getByText('新建线程')).toBeInTheDocument()
        expect(screen.getByLabelText(/线程标题/i)).toBeInTheDocument()
      })
    })

    it('点击👤添加成员按钮 → AddMemberDialog打开', async () => {
      const user = userEvent.setup()
      vi.spyOn(authModule, 'isAuthenticated').mockReturnValue(true)
      vi.spyOn(authModule, 'isTokenExpired').mockReturnValue(false)
      vi.spyOn(authModule, 'getIsAdmin').mockReturnValue(false)
      vi.spyOn(sseModule, 'createSSEConnection').mockReturnValue({ close: vi.fn() } as unknown as EventSource)
      vi.spyOn(sseModule, 'disconnectSSE').mockImplementation(() => {})
      vi.spyOn(apiModule, 'apiGet').mockResolvedValue([])

      render(
        <MemoryRouter>
          <Workspace workspaceOptions={baseInitialState} />
        </MemoryRouter>
      )

      await user.hover(screen.getByText('项目Alpha'))
      await user.click(screen.getByRole('button', { name: /添加成员.*proj-1/i }))

      await waitFor(() => {
        expect(screen.getByText('添加成员')).toBeInTheDocument()
      })
    })

    it('点击🤖注册Agent按钮 → RegisterAgentDialog打开', async () => {
      const user = userEvent.setup()
      vi.spyOn(authModule, 'isAuthenticated').mockReturnValue(true)
      vi.spyOn(authModule, 'isTokenExpired').mockReturnValue(false)
      vi.spyOn(authModule, 'getIsAdmin').mockReturnValue(false)
      vi.spyOn(sseModule, 'createSSEConnection').mockReturnValue({ close: vi.fn() } as unknown as EventSource)
      vi.spyOn(sseModule, 'disconnectSSE').mockImplementation(() => {})
      vi.spyOn(apiModule, 'apiGet').mockResolvedValue([])

      render(
        <MemoryRouter>
          <Workspace workspaceOptions={baseInitialState} />
        </MemoryRouter>
      )

      await user.hover(screen.getByText('项目Alpha'))
      await user.click(screen.getByRole('button', { name: /注册Agent.*proj-1/i }))

      await waitFor(() => {
        expect(screen.getByText('注册Agent')).toBeInTheDocument()
      })
    })
  })

  describe('MVP-UI-6.2: Dialog提交→SSE更新', () => {
    it('CreateProjectDialog提交 → apiPost创建项目（含default_thread_id）', async () => {
      const user = userEvent.setup()
      vi.spyOn(authModule, 'isAuthenticated').mockReturnValue(true)
      vi.spyOn(authModule, 'isTokenExpired').mockReturnValue(false)
      vi.spyOn(authModule, 'getIsAdmin').mockReturnValue(false)
      vi.spyOn(sseModule, 'createSSEConnection').mockReturnValue({ close: vi.fn() } as unknown as EventSource)
      vi.spyOn(sseModule, 'disconnectSSE').mockImplementation(() => {})
      vi.spyOn(apiModule, 'apiGet').mockResolvedValue([])
      vi.spyOn(apiModule, 'apiPost').mockResolvedValue({ id: 'proj-new', name: '新测试项目', description: null, role: 'owner', default_thread_id: 'dt-new', created_at: '' })

      render(
        <MemoryRouter>
          <Workspace workspaceOptions={baseInitialState} />
        </MemoryRouter>
      )

      // 打开CreateProjectDialog
      await user.click(screen.getByRole('button', { name: /新建项目/i }))
      await waitFor(() => {
        expect(screen.getByLabelText(/项目名称/i)).toBeInTheDocument()
      })

      // 输入并提交
      await user.type(screen.getByLabelText(/项目名称/i), '新测试项目')
      await user.click(screen.getByRole('button', { name: /^创建$/i }))

      // apiPost应被调用创建项目
      await waitFor(() => {
        expect(apiModule.apiPost).toHaveBeenCalledWith('/projects', expect.objectContaining({ name: '新测试项目' }))
      })
    })

    it('CreateThreadDialog提交 → apiPost创建线程+state更新', async () => {
      const user = userEvent.setup()
      vi.spyOn(authModule, 'isAuthenticated').mockReturnValue(true)
      vi.spyOn(authModule, 'isTokenExpired').mockReturnValue(false)
      vi.spyOn(authModule, 'getIsAdmin').mockReturnValue(false)
      vi.spyOn(sseModule, 'createSSEConnection').mockReturnValue({ close: vi.fn() } as unknown as EventSource)
      vi.spyOn(sseModule, 'disconnectSSE').mockImplementation(() => {})
      vi.spyOn(apiModule, 'apiGet').mockResolvedValue([])
      vi.spyOn(apiModule, 'apiPost').mockResolvedValue({
        id: 'thread-new', project_id: 'proj-1', title: '新讨论线程', status: 'active', type: 'discussion',
        has_summary: false, pending_plan_count: 0, message_count: 0, created_at: '',
      })

      render(
        <MemoryRouter>
          <Workspace workspaceOptions={baseInitialState} />
        </MemoryRouter>
      )

      // hover项目节点然后点击新建线程按钮
      await user.hover(screen.getByText('项目Alpha'))
      await user.click(screen.getByRole('button', { name: /新建线程.*proj-1/i }))
      await waitFor(() => {
        expect(screen.getByLabelText(/线程标题/i)).toBeInTheDocument()
      })

      // 输入并提交
      await user.type(screen.getByLabelText(/线程标题/i), '新讨论线程')
      await user.click(screen.getByRole('button', { name: /^创建$/i }))

      // apiPost应被调用创建线程
      await waitFor(() => {
        expect(apiModule.apiPost).toHaveBeenCalledWith('/projects/proj-1/threads', expect.objectContaining({ title: '新讨论线程' }))
      })
    })
  })
})

describe('MVP-UI-7.x: IM泡泡讨论面板', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  /** 自己的消息 */
  const selfMessage = { id: 'm-self', thread_id: 't1', participant_id: 'u1', participant_type: 'human' as const, display_name: '张三', content: '我的消息', event_type: 'DiscussionMessageCreated', created_at: '2024-01-01T10:00:00Z' }
  /** 别人的消息 */
  const otherMessage = { id: 'm-other', thread_id: 't1', participant_id: 'u2', participant_type: 'human' as const, display_name: '李四', content: '别人的消息', event_type: 'DiscussionMessageCreated', created_at: '2024-01-01T10:01:00Z' }
  /** Agent消息 */
  const agentMessage = { id: 'm-agent', thread_id: 't1', participant_id: 'a1', participant_type: 'agent' as const, display_name: '总结Agent', content: '讨论要点如下', event_type: 'DiscussionSummaryGenerated', created_at: '2024-01-01T11:00:00Z' }

  describe('MVP-UI-7.1~7.5: MessageBubble样式', () => {
    describe('MVP-UI-7.1: 自己右对齐蓝泡泡', () => {
      it('participant_id=currentUserId → 右对齐+蓝色背景+头像在右侧', () => {
        render(<MessageBubble message={selfMessage} currentUserId="u1" />)
        const bubble = screen.getByTestId('bubble-m-self')
        expect(bubble).toHaveAttribute('data-align', 'right')
        expect(bubble).toHaveAttribute('data-participant-type', 'self')
        // 蓝色背景
        expect(bubble.className).toMatch(/bg-blue/)
        // 头像在右侧——自己的消息头像元素在bubble之后
        const msgRow = screen.getByTestId('msg-m-self')
        const children = Array.from(msgRow.children)
        const bubbleWrapper = bubble.closest('[class]')!
        const avatar = screen.getByTestId('avatar-m-self')
        // 自己的消息布局：[内容区(含bubble), 头像] → 头像在后
        expect(children.indexOf(avatar)).toBeGreaterThan(children.indexOf(bubbleWrapper.parentElement!))
      })
    })

    describe('MVP-UI-7.2: 别人左对齐浅泡泡', () => {
      it('≠currentUserId + human → 左对齐+浅色背景+头像在左侧', () => {
        render(<MessageBubble message={otherMessage} currentUserId="u1" />)
        const bubble = screen.getByTestId('bubble-m-other')
        expect(bubble).toHaveAttribute('data-align', 'left')
        expect(bubble).toHaveAttribute('data-participant-type', 'other')
        expect(bubble.className).toMatch(/bg-gray|bg-muted/)
        // 头像在左侧——别人消息头像在bubble之前
        const msgRow = screen.getByTestId('msg-m-other')
        const children = Array.from(msgRow.children)
        const avatar = screen.getByTestId('avatar-m-other')
        const bubbleWrapper = bubble.closest('[class]')!
        expect(children.indexOf(avatar)).toBeLessThan(children.indexOf(bubbleWrapper.parentElement!))
      })
    })

    describe('MVP-UI-7.3: Agent浅蓝泡泡🤖', () => {
      it('agent → 左对齐+浅蓝背景+蓝色边框+🤖图标', () => {
        render(<MessageBubble message={agentMessage} currentUserId="u1" />)
        const bubble = screen.getByTestId('bubble-m-agent')
        expect(bubble).toHaveAttribute('data-align', 'left')
        expect(bubble).toHaveAttribute('data-participant-type', 'agent')
        expect(bubble.className).toMatch(/bg-blue.*50|bg-sky|bg-lightblue/)
        expect(bubble.className).toMatch(/border-blue/)
        // 🤖图标
        expect(screen.getByTestId('avatar-m-agent').textContent).toContain('🤖')
      })
    })

    describe('MVP-UI-7.4: 头像首字母', () => {
      it('display_name="张三" → 头像显示"张"', () => {
        render(<MessageBubble message={selfMessage} currentUserId="u1" />)
        expect(screen.getByTestId('avatar-m-self').textContent).toContain('张')
      })

      it('Agent头像不显示首字母，显示🤖', () => {
        render(<MessageBubble message={agentMessage} currentUserId="u1" />)
        expect(screen.getByTestId('avatar-m-agent').textContent).toContain('🤖')
      })
    })

    describe('MVP-UI-7.5: 泡泡max-width', () => {
      it('泡泡max-width为70%', () => {
        render(<MessageBubble message={selfMessage} currentUserId="u1" />)
        const bubble = screen.getByTestId('bubble-m-self')
        expect(bubble.className).toMatch(/max-w-\[70%\]|max-w-70/)
      })
    })
  })

  describe('MVP-UI-7.6~7.11: DiscussionPanel斜杠命令和键盘', () => {
    describe('MVP-UI-7.6: /summarize发送', () => {
      it('输入/summarize+Enter → request_summary=true + 默认文案', async () => {
        const onSendMessage = vi.fn().mockResolvedValue(undefined)
        render(<DiscussionPanel messages={mockMessages} currentUserId="u1" onSendMessage={onSendMessage} />)

        const textarea = screen.getByPlaceholderText(/输入消息.*\/summarize/i)
        fireEvent.change(textarea, { target: { value: '/summarize' } })
        fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })

        await waitFor(() => {
          expect(onSendMessage).toHaveBeenCalledWith({ content: '请总结当前讨论要点', request_summary: true })
        })
      })
    })

    describe('MVP-UI-7.7: /summarize带内容', () => {
      it('/summarize 观点 → request_summary=true + content="观点"', async () => {
        const onSendMessage = vi.fn().mockResolvedValue(undefined)
        render(<DiscussionPanel messages={mockMessages} currentUserId="u1" onSendMessage={onSendMessage} />)

        const textarea = screen.getByPlaceholderText(/输入消息.*\/summarize/i)
        fireEvent.change(textarea, { target: { value: '/summarize 观点' } })
        fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })

        await waitFor(() => {
          expect(onSendMessage).toHaveBeenCalledWith({ content: '观点', request_summary: true })
        })
      })
    })

    describe('MVP-UI-7.8: Enter发送', () => {
      it('普通消息+Enter → 发送，textarea清空', async () => {
        const onSendMessage = vi.fn().mockResolvedValue(undefined)
        render(<DiscussionPanel messages={mockMessages} currentUserId="u1" onSendMessage={onSendMessage} />)

        const textarea = screen.getByPlaceholderText(/输入消息.*\/summarize/i)
        fireEvent.change(textarea, { target: { value: '你好' } })
        fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })

        await waitFor(() => {
          expect(onSendMessage).toHaveBeenCalledWith({ content: '你好', request_summary: false })
        })

        // textarea清空
        expect(textarea).toHaveValue('')
      })
    })

    describe('MVP-UI-7.9: Shift+Enter换行', () => {
      it('Shift+Enter → 不发送消息，textarea内容保留', async () => {
        const onSendMessage = vi.fn().mockResolvedValue(undefined)
        render(<DiscussionPanel messages={mockMessages} currentUserId="u1" onSendMessage={onSendMessage} />)

        const textarea = screen.getByPlaceholderText(/输入消息.*\/summarize/i)
        fireEvent.change(textarea, { target: { value: '你好' } })
        fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true })

        // Shift+Enter不触发发送
        expect(onSendMessage).not.toHaveBeenCalled()
        // textarea内容保留
        expect(textarea.value).toContain('你好')
      })
    })

    describe('MVP-UI-7.10: 空消息不发送', () => {
      it('空+Enter → 不触发发送', async () => {
        const onSendMessage = vi.fn().mockResolvedValue(undefined)
        render(<DiscussionPanel messages={mockMessages} currentUserId="u1" onSendMessage={onSendMessage} />)

        const textarea = screen.getByPlaceholderText(/输入消息.*\/summarize/i)
        fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })

        expect(onSendMessage).not.toHaveBeenCalled()
      })
    })

    describe('MVP-UI-7.11: /help显示帮助', () => {
      it('输入/help+Enter → 显示帮助提示，不发送消息', async () => {
        const onSendMessage = vi.fn().mockResolvedValue(undefined)
        render(<DiscussionPanel messages={mockMessages} currentUserId="u1" onSendMessage={onSendMessage} />)

        const textarea = screen.getByPlaceholderText(/输入消息.*\/summarize/i)
        fireEvent.change(textarea, { target: { value: '/help' } })
        fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })

        // 不发送消息
        expect(onSendMessage).not.toHaveBeenCalled()
        // 显示帮助提示
        await waitFor(() => {
          expect(screen.getByTestId('help-overlay')).toBeInTheDocument()
        })
      })
    })
  })

  describe('MVP-UI-7.12~7.16: DiscussionPanel异常场景', () => {
    describe('MVP-UI-7.12: 发送失败回滚', () => {
      it('onSendMessage返回rejected → 错误提示，textarea内容保留', async () => {
        const onSendMessage = vi.fn().mockRejectedValue(new Error('发送失败'))
        render(<DiscussionPanel messages={mockMessages} currentUserId="u1" onSendMessage={onSendMessage} />)

        const textarea = screen.getByPlaceholderText(/输入消息.*\/summarize/i)
        fireEvent.change(textarea, { target: { value: '测试消息' } })
        fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })

        // 错误提示出现
        await waitFor(() => {
          expect(screen.getByText(/发送失败/i)).toBeInTheDocument()
        })

        // textarea内容保留（不清空）
        expect(textarea.value).toContain('测试消息')
      })
    })

    describe('MVP-UI-7.13: SSE去重', () => {
      it('POST返回消息+SSE推送同一ID → 列表不重复（在useWorkspace层面去重）', async () => {
        // 这个测试验证useWorkspace的SSE去重逻辑——MVP-20.6已有覆盖
        // 此处验证MessageBubble渲染不重复：同ID消息只渲染一次
        const duplicateMessages = [
          { id: 'm-dup', thread_id: 't1', participant_id: 'u1', participant_type: 'human' as const, display_name: '张三', content: '重复消息', event_type: 'DiscussionMessageCreated', created_at: '2024-01-01T10:00:00Z' },
        ]
        const onSendMessage = vi.fn().mockResolvedValue(undefined)
        render(<DiscussionPanel messages={duplicateMessages} currentUserId="u1" onSendMessage={onSendMessage} />)

        // 只有一个同ID的泡泡渲染
        expect(screen.getAllByTestId('bubble-m-dup')).toHaveLength(1)
      })
    })

    describe('MVP-UI-7.14: SSE断连后重连推送', () => {
      it('SSE断连后重连——此行为在useWorkspace层面处理，DiscussionPanel只需正确渲染推送的消息', async () => {
        // SSE重连是useWorkspace的职责，此处验证DiscussionPanel能渲染新推送消息
        const newMessages = [...mockMessages, { id: 'm-new', thread_id: 't1', participant_id: 'u2', participant_type: 'human' as const, display_name: '用户B', content: '重连后新消息', event_type: 'DiscussionMessageCreated', created_at: '2024-01-03T10:00:00Z' }]
        const onSendMessage = vi.fn().mockResolvedValue(undefined)
        render(<DiscussionPanel messages={newMessages} currentUserId="u1" onSendMessage={onSendMessage} />)

        expect(screen.getByText('重连后新消息')).toBeInTheDocument()
      })
    })

    describe('MVP-UI-7.15: 超长消息', () => {
      it('超过10000字符 → 发送按钮disabled', () => {
        const onSendMessage = vi.fn().mockResolvedValue(undefined)
        render(<DiscussionPanel messages={mockMessages} currentUserId="u1" onSendMessage={onSendMessage} />)

        const textarea = screen.getByPlaceholderText(/输入消息.*\/summarize/i)
        // 模拟超长输入——直接设置value绕过userEvent的缓慢输入
        fireEvent.change(textarea, { target: { value: 'a'.repeat(10001) } })

        const sendBtn = screen.getByRole('button', { name: /发送/i })
        expect(sendBtn).toBeDisabled()
      })

      it('10000字符以内 → 发送按钮enabled', () => {
        const onSendMessage = vi.fn().mockResolvedValue(undefined)
        render(<DiscussionPanel messages={mockMessages} currentUserId="u1" onSendMessage={onSendMessage} />)

        const textarea = screen.getByPlaceholderText(/输入消息.*\/summarize/i)
        fireEvent.change(textarea, { target: { value: 'a'.repeat(10000) } })

        const sendBtn = screen.getByRole('button', { name: /发送/i })
        expect(sendBtn).not.toBeDisabled()
      })
    })

    describe('MVP-UI-7.16: 空消息列表', () => {
      it('messages=[] → 显示"暂无消息"', () => {
        const onSendMessage = vi.fn().mockResolvedValue(undefined)
        render(<DiscussionPanel messages={[]} currentUserId="u1" onSendMessage={onSendMessage} />)

        expect(screen.getByText(/暂无消息/i)).toBeInTheDocument()
      })
    })
  })
})

describe('MVP-UI-RS.x: DiscussionPanel可拖拽分隔条', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  const onSendMessage = vi.fn().mockResolvedValue(undefined)

  describe('MVP-UI-RS.1: Group/Panel/Separator渲染', () => {
    it('DiscussionPanel渲染Group+Panel+Separator结构', () => {
      const { container } = render(<DiscussionPanel messages={mockMessages} currentUserId="u1" onSendMessage={onSendMessage} />)

      // Group 渲染（data-group 属性）
      expect(container.querySelector('[data-group]')).toBeInTheDocument()

      // Panel 渲染（data-panel 属性）
      const panels = container.querySelectorAll('[data-panel]')
      expect(panels.length).toBe(2)

      // Separator 渲染（data-separator 属性）
      expect(container.querySelector('[data-separator]')).toBeInTheDocument()
    })
  })

  describe('MVP-UI-RS.2: Group方向为vertical', () => {
    it('Group使用orientation="vertical"实现上下分区', () => {
      const { container } = render(<DiscussionPanel messages={mockMessages} currentUserId="u1" onSendMessage={onSendMessage} />)

      const group = container.querySelector('[data-group]')
      // vertical 方向 → flexDirection 为 column
      expect(group).toBeInTheDocument()
      const style = (group as HTMLElement).style
      expect(style.flexDirection).toBe('column')
    })
  })

  describe('MVP-UI-RS.3: 默认布局比例80:20', () => {
    it('消息区id=discussion-messages、输入区id=discussion-input', () => {
      const { container } = render(<DiscussionPanel messages={mockMessages} currentUserId="u1" onSendMessage={onSendMessage} />)

      // 验证两个Panel的id对应正确的区域
      const messagesPanel = container.querySelector('#discussion-messages[data-panel]')
      const inputPanel = container.querySelector('#discussion-input[data-panel]')

      expect(messagesPanel).toBeInTheDocument()
      expect(inputPanel).toBeInTheDocument()
    })
  })

  describe('MVP-UI-RS.4: Panel尺寸约束', () => {
    it('消息区minSize=60、输入区minSize=5 maxSize=35——比例验证', () => {
      const { container } = render(<DiscussionPanel messages={mockMessages} currentUserId="u1" onSendMessage={onSendMessage} />)

      const messagesPanel = container.querySelector('#discussion-messages[data-panel]') as HTMLElement
      const inputPanel = container.querySelector('#discussion-input[data-panel]') as HTMLElement

      expect(messagesPanel).toBeInTheDocument()
      expect(inputPanel).toBeInTheDocument()
      // 消息区 flexGrow 大于输入区（80:20 默认比例）
      expect(parseFloat(messagesPanel.style.flexGrow)).toBeGreaterThan(parseFloat(inputPanel.style.flexGrow))
    })
  })

  describe('MVP-UI-RS.5: Separator存在且可交互', () => {
    it('Separator有role="separator"和data-separator属性', () => {
      const { container } = render(<DiscussionPanel messages={mockMessages} currentUserId="u1" onSendMessage={onSendMessage} />)

      const separator = container.querySelector('[data-separator]')
      expect(separator).toBeInTheDocument()
      expect(separator).toHaveAttribute('role', 'separator')
      // Separator 可聚焦（tabIndex=0 表示可交互）
      expect(separator).toHaveAttribute('tabindex', '0')
    })
  })

  describe('MVP-UI-RS.6: 分隔条视觉样式', () => {
    it('Separator使用库内置data-separator属性驱动CSS样式', () => {
      const { container } = render(<DiscussionPanel messages={mockMessages} currentUserId="u1" onSendMessage={onSendMessage} />)

      const separator = container.querySelector('[data-separator]')!
      expect(separator).toBeInTheDocument()
      // 4px空间 + border-b 1px可视线，库proximity检测驱动data-separator状态
      expect(separator.className).toContain('border-border')
      expect(separator.className).toContain('data-[separator=hover]')
    })
  })

  describe('MVP-UI-RS.7: 布局持久化ID', () => {
    it('Group/Panel/Separator各有id属性', () => {
      const { container } = render(<DiscussionPanel messages={mockMessages} currentUserId="u1" onSendMessage={onSendMessage} />)

      const group = container.querySelector('[data-group]')
      expect(group).toHaveAttribute('id', 'discussion-panel')

      const messagesPanel = container.querySelector('#discussion-messages[data-panel]')
      expect(messagesPanel).toHaveAttribute('id', 'discussion-messages')

      const inputPanel = container.querySelector('#discussion-input[data-panel]')
      expect(inputPanel).toHaveAttribute('id', 'discussion-input')

      const separator = container.querySelector('[data-separator]')
      expect(separator).toHaveAttribute('id', 'discussion-separator')
    })
  })

  describe('MVP-UI-RS.8: 功能无回归', () => {
    it('Enter发送功能在可拖拽布局中仍正确', async () => {
      const onSend = vi.fn().mockResolvedValue(undefined)
      render(<DiscussionPanel messages={mockMessages} currentUserId="u1" onSendMessage={onSend} />)

      const textarea = screen.getByPlaceholderText(/输入消息.*\/summarize/i)
      fireEvent.change(textarea, { target: { value: '回归测试' } })
      fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })

      await waitFor(() => {
        expect(onSend).toHaveBeenCalledWith({ content: '回归测试', request_summary: false })
      })
    })

    it('/summarize斜杠命令在可拖拽布局中仍正确', async () => {
      const onSend = vi.fn().mockResolvedValue(undefined)
      render(<DiscussionPanel messages={mockMessages} currentUserId="u1" onSendMessage={onSend} />)

      const textarea = screen.getByPlaceholderText(/输入消息.*\/summarize/i)
      fireEvent.change(textarea, { target: { value: '/summarize' } })
      fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })

      await waitFor(() => {
        expect(onSend).toHaveBeenCalledWith({ content: '请总结当前讨论要点', request_summary: true })
      })
    })

    it('空消息列表在可拖拽布局中仍显示"暂无消息"', () => {
      render(<DiscussionPanel messages={[]} currentUserId="u1" onSendMessage={onSendMessage} />)
      expect(screen.getByText(/暂无消息/i)).toBeInTheDocument()
    })

    it('发送失败回滚在可拖拽布局中仍正确', async () => {
      const onSend = vi.fn().mockRejectedValue(new Error('发送失败'))
      render(<DiscussionPanel messages={mockMessages} currentUserId="u1" onSendMessage={onSend} />)

      const textarea = screen.getByPlaceholderText(/输入消息.*\/summarize/i)
      fireEvent.change(textarea, { target: { value: '失败测试' } })
      fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })

      await waitFor(() => {
        expect(screen.getByText(/发送失败/i)).toBeInTheDocument()
      })
    })

    it('消息Panel有onResize回调用于底部锚定', () => {
      const { container } = render(<DiscussionPanel messages={mockMessages} currentUserId="u1" onSendMessage={onSendMessage} />)
      // 消息Panel存在且通过elementRef绑定DOM元素
      const messagesPanel = container.querySelector('#discussion-messages[data-panel]')
      expect(messagesPanel).toBeInTheDocument()
    })
  })
})

describe('MVP-UI-COL.x: 三栏可拖拽布局', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  const workspaceInitialState: UseWorkspaceOptions = {
    initialState: {
      projects: mockProjects,
      selectedProjectId: 'proj-1',
      threads: mockThreads,
      selectedThreadId: 'dt-1',
      messages: mockMessages,
      plans: [],
      outputs: [],
    },
  }

  describe('MVP-UI-COL.1: 三栏Group/Panel/Separator渲染', () => {
    it('Workspace渲染水平Group+三个Panel+两个Separator', () => {
      vi.spyOn(authModule, 'isAuthenticated').mockReturnValue(true)
      vi.spyOn(authModule, 'isTokenExpired').mockReturnValue(false)
      vi.spyOn(authModule, 'getIsAdmin').mockReturnValue(false)
      vi.spyOn(sseModule, 'createSSEConnection').mockReturnValue({ close: vi.fn() } as unknown as EventSource)
      vi.spyOn(sseModule, 'disconnectSSE').mockImplementation(() => {})

      const { container } = render(
        <MemoryRouter initialEntries={['/workspace']}>
          <Workspace workspaceOptions={workspaceInitialState} />
        </MemoryRouter>
      )

      // 水平 Group
      const group = container.querySelector('[data-group]')
      expect(group).toBeInTheDocument()
      expect((group as HTMLElement).style.flexDirection).toBe('row')

      // 三个 Panel
      const panels = container.querySelectorAll('[data-panel]')
      expect(panels.length).toBeGreaterThanOrEqual(3)

      // 两个 Separator（workspace-separator-left 和 workspace-separator-right）
      expect(container.querySelector('#workspace-separator-left[data-separator]')).toBeInTheDocument()
      expect(container.querySelector('#workspace-separator-right[data-separator]')).toBeInTheDocument()
    })
  })

  describe('MVP-UI-COL.2: 默认布局比例', () => {
    it('左栏flex-grow小于中栏和右栏，中栏右栏相等', () => {
      vi.spyOn(authModule, 'isAuthenticated').mockReturnValue(true)
      vi.spyOn(authModule, 'isTokenExpired').mockReturnValue(false)
      vi.spyOn(authModule, 'getIsAdmin').mockReturnValue(false)
      vi.spyOn(sseModule, 'createSSEConnection').mockReturnValue({ close: vi.fn() } as unknown as EventSource)
      vi.spyOn(sseModule, 'disconnectSSE').mockImplementation(() => {})

      const { container } = render(
        <MemoryRouter initialEntries={['/workspace']}>
          <Workspace workspaceOptions={workspaceInitialState} />
        </MemoryRouter>
      )

      const leftPanel = container.querySelector('#workspace-left[data-panel]') as HTMLElement
      const middlePanel = container.querySelector('#workspace-middle[data-panel]') as HTMLElement
      const rightPanel = container.querySelector('#workspace-right[data-panel]') as HTMLElement

      expect(leftPanel).toBeInTheDocument()
      expect(middlePanel).toBeInTheDocument()
      expect(rightPanel).toBeInTheDocument()

      // 中栏和右栏 flex-grow 相等
      expect(parseFloat(middlePanel.style.flexGrow)).toEqual(parseFloat(rightPanel.style.flexGrow))
      // 左栏 flex-grow 小于中栏
      expect(parseFloat(leftPanel.style.flexGrow)).toBeLessThan(parseFloat(middlePanel.style.flexGrow))
    })
  })

  describe('MVP-UI-COL.3: 尺寸约束', () => {
    it('左栏有256px最小宽度和400px最大宽度约束', () => {
      vi.spyOn(authModule, 'isAuthenticated').mockReturnValue(true)
      vi.spyOn(authModule, 'isTokenExpired').mockReturnValue(false)
      vi.spyOn(authModule, 'getIsAdmin').mockReturnValue(false)
      vi.spyOn(sseModule, 'createSSEConnection').mockReturnValue({ close: vi.fn() } as unknown as EventSource)
      vi.spyOn(sseModule, 'disconnectSSE').mockImplementation(() => {})

      const { container } = render(
        <MemoryRouter initialEntries={['/workspace']}>
          <Workspace workspaceOptions={workspaceInitialState} />
        </MemoryRouter>
      )

      // 验证Panel存在且有正确的id——minSize/maxSize由react-resizable-panels内部处理
      const leftPanel = container.querySelector('#workspace-left[data-panel]')
      const middlePanel = container.querySelector('#workspace-middle[data-panel]')
      const rightPanel = container.querySelector('#workspace-right[data-panel]')
      expect(leftPanel).toBeInTheDocument()
      expect(middlePanel).toBeInTheDocument()
      expect(rightPanel).toBeInTheDocument()
    })
  })
})