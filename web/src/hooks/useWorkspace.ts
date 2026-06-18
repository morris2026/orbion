import { useState, useEffect, useCallback, useRef } from 'react'
import { apiGet, apiPost } from '@/lib/api'
import { createSSEConnection, disconnectSSE } from '@/lib/sse'
import type { SSERawEvent } from '@/lib/sse'
import type { RightTab } from '@/components/RightPanelTabs'
import type { ProjectListItem, ThreadListItem, MessageResponse, PlanResponse, PlanTask, OutputResponse, CreateProjectRequest, CreateThreadRequest, RegisterAgentRequest, AddMemberRequest } from '@/types/api'
import type {
  SSEMessageCreatedEvent,
  SSESummaryGeneratedEvent,
  SSEPlanProposedEvent,
  SSEPlanApprovedEvent,
  SSEPlanRejectedEvent,
  SSEOutputGeneratedEvent,
  SSEOutputApprovedEvent,
  SSERevisionRequestedEvent,
} from '@/types/sse'

export interface WorkspaceState {
  projects: ProjectListItem[]
  selectedProjectId: string | null
  threads: ThreadListItem[]
  selectedThreadId: string | null
  messages: MessageResponse[]
  plans: PlanResponse[]
  outputs: OutputResponse[]
  selectedRightTab: RightTab
}

export interface UseWorkspaceOptions {
  initialState?: Partial<WorkspaceState>
}

/** SSE事件 → MessageResponse 映射 */
function mapMessageFromSSE(e: SSEMessageCreatedEvent): MessageResponse {
  return {
    id: e.message_id,
    thread_id: e.thread_id,
    participant_id: e.participant_id,
    participant_type: e.participant_type,
    display_name: e.participant_display_name,
    content: e.content,
    event_type: 'DiscussionMessageCreated',
    created_at: e.created_at,
  }
}

function mapSummaryFromSSE(e: SSESummaryGeneratedEvent): MessageResponse {
  return {
    id: e.summary_id,
    thread_id: e.thread_id,
    participant_id: e.participant_id,
    participant_type: e.participant_type,
    display_name: e.participant_display_name,
    content: `共识要点：${e.consensus_points.join('；')}`,
    event_type: 'DiscussionSummaryGenerated',
    created_at: e.created_at,
  }
}

/** SSE事件 → PlanResponse 映射 */
function mapPlanFromSSE(e: SSEPlanProposedEvent): PlanResponse {
  return {
    id: e.plan_id,
    thread_id: e.thread_id,
    status: 'proposed',
    proposed_by: e.participant_id,
    tasks: e.tasks.map((t): PlanTask => ({
      task_id: t.task_id,
      type: t.type,
      description: t.description,
      dependencies: t.dependencies,
      priority: t.priority,
      status: t.status,
    })),
    created_at: e.created_at,
  }
}

/** SSE事件 → OutputResponse 映射 */
function mapOutputFromSSE(e: SSEOutputGeneratedEvent): OutputResponse {
  return {
    id: e.output_id,
    task_id: e.task_id,
    plan_id: e.plan_id,
    output_type: e.output_type,
    content: e.content,
    diff: e.diff ?? undefined,
    file_paths: e.file_paths,
    status: 'generated',
    version: 1,
    created_at: e.created_at,
  }
}

export function useWorkspace(options?: UseWorkspaceOptions) {
  const init = options?.initialState

  const [projects, setProjects] = useState<ProjectListItem[]>(init?.projects ?? [])
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(init?.selectedProjectId ?? null)
  const [threads, setThreads] = useState<ThreadListItem[]>(init?.threads ?? [])
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(init?.selectedThreadId ?? null)
  const [messages, setMessages] = useState<MessageResponse[]>(init?.messages ?? [])
  const [plans, setPlans] = useState<PlanResponse[]>(init?.plans ?? [])
  const [outputs, setOutputs] = useState<OutputResponse[]>(init?.outputs ?? [])
  const [selectedRightTab, setSelectedRightTab] = useState<RightTab>(init?.selectedRightTab ?? 'flow')
  const [fileTreeRefreshKey, setFileTreeRefreshKey] = useState(0)

  // SSE回调需实时读取当前projectId/threadId，但不应触发连接重建
  const selectedProjectIdRef = useRef(selectedProjectId)
  const selectedThreadIdRef = useRef(selectedThreadId)
  useEffect(() => { selectedProjectIdRef.current = selectedProjectId })
  useEffect(() => { selectedThreadIdRef.current = selectedThreadId })

  // 初始数据未注入时从API加载项目列表，然后加载所有项目的线程
  useEffect(() => {
    if (init?.projects) return
    apiGet<ProjectListItem[]>('/projects')
      .then((projects) => {
        setProjects([...projects].sort((a, b) => a.name.localeCompare(b.name)))
        // 并行加载所有项目的线程
        Promise.all(
          projects.map((p) =>
            apiGet<ThreadListItem[]>(`/projects/${p.id}/threads`)
              .catch(() => [] as ThreadListItem[])
          )
        ).then((results) => {
          setThreads(results.flat().sort((a, b) => a.title.localeCompare(b.title)))
        })
      })
      .catch(() => {})
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // 选中线程后加载消息（初始数据未注入时）
  useEffect(() => {
    if (!selectedThreadId) return
    if (init?.messages && init?.selectedThreadId === selectedThreadId) return
    apiGet<MessageResponse[]>(`/threads/${selectedThreadId}/messages`)
      .then(setMessages)
      .catch(() => {})
  }, [selectedThreadId]) // eslint-disable-line react-hooks/exhaustive-deps

  // 选中项目后加载计划（初始数据未注入时）
  useEffect(() => {
    if (!selectedProjectId) return
    if (init?.plans && init?.selectedProjectId === selectedProjectId) return
    apiGet<PlanResponse[]>(`/projects/${selectedProjectId}/plans`)
      .then(setPlans)
      .catch(() => {})
  }, [selectedProjectId]) // eslint-disable-line react-hooks/exhaustive-deps

  // 用户级SSE实时更新（登录后一次性建立，不随项目切换重建）
  useEffect(() => {
    const es = createSSEConnection((raw: SSERawEvent) => {
      const type = raw.event_type
      const projectId = (raw as Record<string, unknown>).project_id as string | undefined
      const currentProjectId = selectedProjectIdRef.current

      // 用户级连接：按project_id过滤，只处理当前选中项目的事件
      // member_added和project_created是跨项目事件，需要特殊处理
      if (type === 'project_created') {
        // 收到project_created事件，刷新项目列表
        apiGet<ProjectListItem[]>('/projects')
          .then((freshProjects) => {
            setProjects([...freshProjects].sort((a, b) => a.name.localeCompare(b.name)))
          })
          .catch(() => {})
        return
      }

      // 非当前项目的事件直接忽略（member_added除外）
      // Why: 用户级连接收到所有项目事件，但UI只展示当前选中项目的计划/产出/消息
      // 未选中项目时也忽略，避免数据混入空状态
      if (!projectId || projectId !== currentProjectId) {
        // member_added可能是其他项目添加成员，刷新项目列表即可
        if (type === 'member_added') {
          apiGet<ProjectListItem[]>('/projects')
            .then((freshProjects) => {
              setProjects([...freshProjects].sort((a, b) => a.name.localeCompare(b.name)))
            })
            .catch(() => {})
        }
        return
      }

      if (type === 'message_created') {
        const event = raw as unknown as SSEMessageCreatedEvent
        if (event.thread_id === selectedThreadIdRef.current) {
          setMessages((prev) => [...prev, mapMessageFromSSE(event)])
        }
        // 仓库相关系统消息 → 刷新文件树
        if (event.participant_type === 'system' && (event.content?.includes('已克隆') || event.content?.includes('已初始化'))) {
          setFileTreeRefreshKey((k) => k + 1)
        }
      } else if (type === 'summary_generated') {
        const event = raw as unknown as SSESummaryGeneratedEvent
        if (event.thread_id === selectedThreadIdRef.current) {
          setMessages((prev) => [...prev, mapSummaryFromSSE(event)])
        }
      } else if (type === 'plan_proposed') {
        const event = raw as unknown as SSEPlanProposedEvent
        setPlans((prev) => [...prev, mapPlanFromSSE(event)])
        setSelectedRightTab('flow')
      } else if (type === 'plan_approved') {
        const event = raw as unknown as SSEPlanApprovedEvent
        setPlans((prev) =>
          prev.map((p) => p.id === event.plan_id ? { ...p, status: 'approved' } : p)
        )
      } else if (type === 'plan_rejected') {
        const event = raw as unknown as SSEPlanRejectedEvent
        setPlans((prev) =>
          prev.map((p) => p.id === event.plan_id ? { ...p, status: 'rejected' } : p)
        )
      } else if (type === 'output_generated') {
        const event = raw as unknown as SSEOutputGeneratedEvent
        setOutputs((prev) => [...prev, mapOutputFromSSE(event)])
        setSelectedRightTab('flow')
      } else if (type === 'output_approved') {
        const event = raw as unknown as SSEOutputApprovedEvent
        setOutputs((prev) =>
          prev.map((o) => o.id === event.output_id ? { ...o, status: 'approved' } : o)
        )
      } else if (type === 'revision_requested') {
        const event = raw as unknown as SSERevisionRequestedEvent
        setOutputs((prev) =>
          prev.map((o) => o.id === event.output_id ? { ...o, status: 'revision_requested' } : o)
        )
      }
    })
    return () => disconnectSSE(es)
  }, [])

  // 发送消息（POST仅触发后端发布事件，前端通过SSE回传显示——避免重复）
  const handleSendMessage = useCallback(
    async (opts: { content: string; request_summary?: boolean }): Promise<void> => {
      if (!selectedThreadId) throw new Error('未选择线程')
      await apiPost(`/threads/${selectedThreadId}/messages`, {
        content: opts.content,
        request_summary: opts.request_summary ?? false,
      })
    },
    [selectedThreadId]
  )

  // 计划审批：发送所有task_ids
  const handleApprovePlan = useCallback(
    (planId: string) => {
      const plan = plans.find((p) => p.id === planId)
      if (!plan) return
      apiPost(`/plans/${planId}/approve`, {
        approved_tasks: plan.tasks.map((t) => t.task_id),
      }).catch(() => {})
    },
    [plans]
  )

  // 计划拒绝：需要reason
  const handleRejectPlan = useCallback(
    (planId: string, reason: string) => {
      apiPost(`/plans/${planId}/reject`, {
        reason,
        suggestions: [],
      }).catch(() => {})
    },
    []
  )

  // 创建项目（非Dialog路径使用：Dialog路径由Dialog自己做API调用+回调更新state）
  const handleCreateProject = useCallback(
    (req: CreateProjectRequest) => {
      apiPost<ProjectListItem>('/projects', req).then((newProject) => {
        setProjects((prev) => [...prev, newProject].sort((a, b) => a.name.localeCompare(b.name)))
      }).catch(() => {})
    },
    []
  )

  // 创建线程（非Dialog路径使用：Dialog路径由Dialog自己做API调用+回调更新state）
  const handleCreateThread = useCallback(
    (req: CreateThreadRequest) => {
      if (!selectedProjectId) return
      apiPost<ThreadListItem>(`/projects/${selectedProjectId}/threads`, req).then((newThread) => {
        setThreads((prev) => [...prev, newThread].sort((a, b) => a.title.localeCompare(b.title)))
        setSelectedThreadId(newThread.id)
      }).catch(() => {})
    },
    [selectedProjectId]
  )

  // 注册Agent
  const handleRegisterAgent = useCallback(
    (req: RegisterAgentRequest) => {
      if (!selectedProjectId) return
      apiPost(`/projects/${selectedProjectId}/agents`, req).catch(() => {})
    },
    [selectedProjectId]
  )

  // 添加成员
  const handleAddMember = useCallback(
    (req: AddMemberRequest) => {
      if (!selectedProjectId) return
      apiPost(`/projects/${selectedProjectId}/members`, req).catch(() => {})
    },
    [selectedProjectId]
  )

  // 批准产出
  const handleApproveOutput = useCallback(
    (outputId: string, feedback?: string) => {
      apiPost(`/outputs/${outputId}/approve`, { feedback: feedback ?? null }).catch(() => {})
    },
    []
  )

  // 要求修改产出
  const handleRequestRevision = useCallback(
    (outputId: string, issues: string[], suggestions?: string[]) => {
      apiPost(`/outputs/${outputId}/request-revision`, {
        issues,
        suggestions: suggestions ?? [],
      }).catch(() => {})
    },
    []
  )

  return {
    projects, setProjects, selectedProjectId, setSelectedProjectId,
    threads, setThreads, selectedThreadId, setSelectedThreadId,
    messages, setMessages, plans, setPlans, outputs, setOutputs,
    selectedRightTab, setSelectedRightTab,
    fileTreeRefreshKey,
    handleSendMessage, handleApprovePlan, handleRejectPlan,
    handleCreateProject, handleCreateThread, handleRegisterAgent,
    handleAddMember, handleApproveOutput, handleRequestRevision,
  }
}
