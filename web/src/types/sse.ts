/** SSE事件类型定义 — 匹配后端sse.py推送的字段名，用户级连接所有事件包含project_id */

export interface SSEMessageCreatedEvent {
  event_type: 'message_created'
  project_id: string
  message_id: string
  thread_id: string
  participant_id: string
  participant_type: 'human' | 'agent' | 'system'
  participant_display_name: string
  content: string
  created_at: string
}

export interface SSESummaryGeneratedEvent {
  event_type: 'summary_generated'
  project_id: string
  summary_id: string
  thread_id: string
  participant_id: string
  participant_type: 'agent'
  participant_display_name: string
  consensus_points: string[]
  divergence_points: string[]
  action_items: string[]
  knowledge_references: string[]
  created_at: string
}

export interface SSEPlanProposedEvent {
  event_type: 'plan_proposed'
  project_id: string
  plan_id: string
  thread_id: string
  participant_id: string
  participant_type: 'agent'
  participant_display_name: string
  tasks: Array<{
    task_id: string
    type: string
    description: string
    dependencies: string[]
    priority: string
    status: string
  }>
  created_at: string
}

export interface SSEPlanApprovedEvent {
  event_type: 'plan_approved'
  project_id: string
  plan_id: string
  participant_id: string
  participant_type: 'human'
  participant_display_name: string
  approved_tasks: string[]
  modifications: Record<string, Record<string, string>> | null
  created_at: string
}

export interface SSEPlanRejectedEvent {
  event_type: 'plan_rejected'
  project_id: string
  plan_id: string
  participant_id: string
  participant_type: 'human'
  participant_display_name: string
  reason: string
  suggestions: string[]
  created_at: string
}

export interface SSEOutputGeneratedEvent {
  event_type: 'output_generated'
  project_id: string
  output_id: string
  task_id: string
  plan_id: string
  participant_id: string
  participant_type: 'agent'
  participant_display_name: string
  output_type: string
  content: string
  diff: string | null
  file_paths: string[]
  created_at: string
}

export interface SSEOutputApprovedEvent {
  event_type: 'output_approved'
  project_id: string
  output_id: string
  participant_id: string
  participant_type: 'human'
  participant_display_name: string
  feedback: string | null
  created_at: string
}

export interface SSERevisionRequestedEvent {
  event_type: 'revision_requested'
  project_id: string
  output_id: string
  task_id: string
  participant_id: string
  participant_type: 'human'
  participant_display_name: string
  issues: string[]
  suggestions: string[]
  created_at: string
}

export interface SSEMemberAddedEvent {
  event_type: 'member_added'
  project_id: string
  participant_id: string
  participant_type: 'human' | 'agent'
  participant_display_name: string
  roles: string[]
  created_at: string
}

export interface SSEProjectCreatedEvent {
  event_type: 'project_created'
  project_id: string
  participant_id: string
  participant_type: 'human'
  participant_display_name: string
  name: string
  description: string | null
  created_at: string
}

export type SSEEvent =
  | SSEMessageCreatedEvent
  | SSESummaryGeneratedEvent
  | SSEPlanProposedEvent
  | SSEPlanApprovedEvent
  | SSEPlanRejectedEvent
  | SSEOutputGeneratedEvent
  | SSEOutputApprovedEvent
  | SSERevisionRequestedEvent
  | SSEMemberAddedEvent
  | SSEProjectCreatedEvent
