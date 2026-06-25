/** API响应类型定义 — 对应后端Pydantic模型的TypeScript interface */

export interface ProjectListItem {
  id: string
  name: string
  description: string | null
  role: string
  default_thread_id: string | null
  created_at: string
}

export interface ThreadListItem {
  id: string
  project_id: string
  title: string
  status: 'active' | 'archived' | 'resolved'
  type: string
  has_summary: boolean
  pending_plan_count: number
  message_count: number
  unread_count?: number
  created_at: string
}

export interface MessageResponse {
  id: string
  thread_id: string
  participant_id: string
  participant_type: 'human' | 'agent' | 'system'
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

export interface UserItem {
  user_id: string
  username: string
  display_name: string
  status: string
  created_at: string
}

export interface CreateProjectRequest {
  name: string
  description: string | null
}

export interface CreateThreadRequest {
  title: string
  type: string
}

export interface RegisterAgentRequest {
  agent_type: 'summary' | 'decompose' | 'execute'
  model_id: string
  display_name: string
}

export interface AddMemberRequest {
  user_id: string
  role: 'owner' | 'admin' | 'member' | 'viewer'
}

export interface FileNode {
  path: string
  type: 'file' | 'dir'
  name: string
}

export interface FileContent {
  path: string
  content: string
}

export interface WriteFileRequest {
  content: string
}

export interface RepoInfo {
  name: string
}

export interface AddRepoRequest {
  url?: string
  name?: string
}

export interface GitFileStatus {
  path: string
  status: 'A' | 'M' | 'D' | 'R' | 'U'
}

export interface GitStatusResult {
  staged: GitFileStatus[]
  changes: GitFileStatus[]
}

export interface StageRequest {
  paths: string[]
}

export interface CommitRequest {
  message: string
}

export type CredentialType = 'github'

export interface Credential {
  id: string
  type: CredentialType
  name: string
  created_at: string
}

export interface CreateCredentialRequest {
  type: CredentialType
  name: string
  token: string
}
export interface WorktreeInfo {
  id: string
  project_id: string
  repo_name: string
  worktree_type: 'main' | 'task'
  branch_name: string
  path: string
  status: string
  created_by: string
  task_id: string | null
  conflict_regen_count: number
}
