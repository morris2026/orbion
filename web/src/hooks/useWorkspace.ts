import { useState, useEffect, useCallback } from 'react'
import { apiGet, apiPost } from '@/lib/api'
import { createSSEConnection, disconnectSSE, SSERawEvent } from '@/lib/sse'
import type { ProjectListItem, ThreadListItem, MessageResponse, PlanResponse, PlanTask, OutputResponse } from '@/types/api'
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

  // 初始数据未注入时从API加载项目列表
  useEffect(() => {
    if (init?.projects) return
    apiGet<ProjectListItem[]>('/projects')
      .then(setProjects)
      .catch(() => {})
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // 选中项目后加载线程（初始数据未注入时）
  useEffect(() => {
    if (!selectedProjectId) return
    if (init?.threads && init?.selectedProjectId === selectedProjectId) return
    apiGet<ThreadListItem[]>(`/projects/${selectedProjectId}/threads`)
      .then(setThreads)
      .catch(() => {})
  }, [selectedProjectId]) // eslint-disable-line react-hooks/exhaustive-deps

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

  // SSE实时更新
  useEffect(() => {
    if (!selectedProjectId) return
    const es = createSSEConnection(selectedProjectId, (raw: SSERawEvent) => {
      const type = raw.event_type
      if (type === 'message_created') {
        const event = raw as unknown as SSEMessageCreatedEvent
        if (event.thread_id === selectedThreadId) {
          setMessages((prev) => [...prev, mapMessageFromSSE(event)])
        }
      } else if (type === 'summary_generated') {
        const event = raw as unknown as SSESummaryGeneratedEvent
        if (event.thread_id === selectedThreadId) {
          setMessages((prev) => [...prev, mapSummaryFromSSE(event)])
        }
      } else if (type === 'plan_proposed') {
        const event = raw as unknown as SSEPlanProposedEvent
        setPlans((prev) => [...prev, mapPlanFromSSE(event)])
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
  }, [selectedProjectId, selectedThreadId])

  // 发送消息（含request_summary）
  const handleSendMessage = useCallback(
    (opts: { content: string; request_summary?: boolean }) => {
      if (!selectedThreadId) return
      apiPost(`/threads/${selectedThreadId}/messages`, {
        content: opts.content,
        request_summary: opts.request_summary ?? false,
      }).catch(() => {})
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

  return {
    projects, selectedProjectId, setSelectedProjectId,
    threads, selectedThreadId, setSelectedThreadId,
    messages, plans, outputs,
    handleSendMessage, handleApprovePlan, handleRejectPlan,
  }
}