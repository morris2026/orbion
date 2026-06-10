import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, renderHook, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import ProjectTree from '@/components/ProjectTree'
import MessageItem from '@/components/MessageItem'
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

/** mock线程数据 */
const mockThreads: ThreadListItem[] = [
  { id: 't1', title: '线程1', status: 'active', type: 'discussion', has_summary: true, pending_plan_count: 2, message_count: 5, unread_count: 3, created_at: '2024-01-01T00:00:00Z' },
  { id: 't2', title: '线程2', status: 'active', type: 'discussion', has_summary: false, pending_plan_count: 0, message_count: 3, unread_count: 0, created_at: '2024-01-02T00:00:00Z' },
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

  describe('MVP-20.1: 线程列表展示聚合字段', () => {
    it('has_summary标记：有摘要时显示标记', () => {
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
      expect(screen.getByTestId('t1-summary')).toBeInTheDocument()

      expect(screen.getByText('线程2')).toBeInTheDocument()
      expect(screen.queryByTestId('t2-summary')).not.toBeInTheDocument()
    })

    it('pending_plan_count和message_count正确显示', () => {
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

      expect(screen.getByText(/2.*待审/)).toBeInTheDocument()
      expect(screen.getByText(/0.*待审/)).toBeInTheDocument()

      expect(screen.getByText(/5.*消息/)).toBeInTheDocument()
      expect(screen.getByText(/3.*消息/)).toBeInTheDocument()
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

  describe('MVP-UI-4.3: 点击项目选中默认线程', () => {
    it('点击项目 → onSelectProject和onSelectThread分别收到项目ID和默认线程ID', async () => {
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
    it('点击线程 → onSelectThread收到线程ID', async () => {
      const user = userEvent.setup()
      const onSelectThread = vi.fn()
      render(<ProjectTree {...treeProps} onSelectThread={onSelectThread} />)

      await user.click(screen.getByText('线程1'))
      expect(onSelectThread).toHaveBeenCalledWith('t1')
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
        { id: 't1', title: '线程1', status: 'active', type: 'discussion', has_summary: false, pending_plan_count: 0, message_count: 0, unread_count: 1, created_at: '2024-01-01T00:00:00Z' },
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
        { id: 'dt-1', title: '默认线程', status: 'active', type: 'discussion', has_summary: false, pending_plan_count: 0, message_count: 0, unread_count: 0, created_at: '2024-01-01T00:00:00Z' },
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
    it('has_summary/pending_plan/message_count在新组件中仍正确显示', () => {
      render(<ProjectTree {...treeProps} />)

      // 线程1 has_summary=true → 显示标记
      expect(screen.getByTestId('t1-summary')).toBeInTheDocument()

      // 线程2 has_summary=false → 不显示标记
      expect(screen.queryByTestId('t2-summary')).not.toBeInTheDocument()

      // pending_plan_count
      expect(screen.getByText(/2.*待审/)).toBeInTheDocument()
      expect(screen.getByText(/0.*待审/)).toBeInTheDocument()

      // message_count
      expect(screen.getByText(/5.*消息/)).toBeInTheDocument()
      expect(screen.getByText(/3.*消息/)).toBeInTheDocument()
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
        id: 'thread-new', title: '新讨论线程', status: 'active', type: 'discussion',
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