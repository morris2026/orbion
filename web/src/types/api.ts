/** API响应类型定义 — 对应后端Pydantic模型的TypeScript interface */

export interface ProjectListItem {
  id: string
  name: string
  description: string | null
  role: string
  created_at: string
}

export interface ThreadListItem {
  id: string
  title: string
  status: 'active' | 'archived' | 'resolved'
  type: string
  has_summary: boolean
  pending_plan_count: number
  message_count: number
  created_at: string
}

export interface MessageResponse {
  id: string
  thread_id: string
  participant_id: string
  participant_type: 'human' | 'agent'
  display_name: string
  content: string
  event_type: string
  created_at: string
}

export interface PlanTask {
  task_id: string
  type: string
  description: string | null
  dependencies: string[]
  priority: string
  status: string
}

export interface PlanResponse {
  id: string
  thread_id: string
  status: 'proposed' | 'approved' | 'rejected' | 'executing' | 'completed'
  proposed_by: string
  tasks: PlanTask[]
  created_at: string
}

export interface OutputResponse {
  id: string
  task_id: string
  plan_id: string
  output_type: string
  content: string
  diff?: string
  file_paths: string[]
  status: string
  version: number
  created_at: string
}