import { useState, useEffect } from 'react'
import type { ProjectListItem, ThreadListItem } from '@/types/api'
import { PlusIcon, UserPlusIcon, BotIcon, ChevronRightIcon, ChevronDownIcon, XIcon } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import LongPressButton from '@/components/LongPressButton'
import DeleteConfirmDialog from '@/components/DeleteConfirmDialog'

interface ProjectTreeProps {
  projects: ProjectListItem[]
  threads: ThreadListItem[]
  selectedProjectId: string | null
  selectedThreadId: string | null
  onSelectThread: (threadId: string | null) => void
  onSelectProject: (projectId: string) => void
  onCreateProject: () => void
  onCreateThread: (projectId: string) => void
  onAddMember: (projectId: string) => void
  onRegisterAgent: (projectId: string) => void
  onDeleteProject: (projectId: string) => void
  onDeleteThread: (threadId: string, projectId: string) => void
}

/** 计算项目的总未读数，排除当前选中线程的未读 */
function projectUnreadCount(
  threads: ThreadListItem[],
  selectedThreadId: string | null,
): number {
  return threads.reduce(
    (sum, t) => sum + (t.id === selectedThreadId ? 0 : (t.unread_count ?? 0)),
    0,
  )
}

export default function ProjectTree({
  projects,
  threads,
  selectedProjectId,
  selectedThreadId,
  onSelectThread,
  onSelectProject,
  onCreateProject,
  onCreateThread,
  onAddMember,
  onRegisterAgent,
  onDeleteProject,
  onDeleteThread,
}: ProjectTreeProps) {
  // tooltip hover 协调：CSS group-hover 无法感知 portaled tooltip 的打开状态，
  // 用 JS state 统一控制按钮可见性
  const [hoveredProjectId, setHoveredProjectId] = useState<string | null>(null)
  const [openTooltipProjectId, setOpenTooltipProjectId] = useState<string | null>(null)
  const [expandedProjects, setExpandedProjects] = useState<Set<string>>(
    new Set(selectedProjectId ? [selectedProjectId] : [])
  )
  const [deleteTarget, setDeleteTarget] = useState<{
    type: 'project' | 'thread'
    id: string
    projectId: string
    name: string
    deletePath: string
  } | null>(null)
  // 外部选中项目时自动展开
  useEffect(() => {
    if (selectedProjectId && !expandedProjects.has(selectedProjectId)) {
      setExpandedProjects((prev) => new Set([...prev, selectedProjectId]))
    }
  }, [selectedProjectId])

  if (projects.length === 0) {
    return (
      <TooltipProvider delay={0}>
        <div className="p-4">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-semibold">Orbion</h2>
            <Tooltip>
              <TooltipTrigger render={<Button variant="ghost" size="icon" className="h-6 w-6 rounded-md bg-primary/10 hover:bg-primary/20" onClick={onCreateProject} aria-label="新建项目" />}>
                <PlusIcon className="h-4 w-4" />
              </TooltipTrigger>
              <TooltipContent>新建项目</TooltipContent>
            </Tooltip>
          </div>
          <p className="text-sm text-muted-foreground">暂无项目</p>
        </div>
      </TooltipProvider>
    )
  }

  return (
    <TooltipProvider delay={0}>
      <ScrollArea className="h-full">
        <div className="p-4 space-y-2">
          {/* 顶部新建项目按钮 */}
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-semibold">Orbion</h2>
            <Tooltip>
              <TooltipTrigger render={<Button variant="ghost" size="icon" className="h-6 w-6 rounded-md bg-primary/10 hover:bg-primary/20" onClick={onCreateProject} aria-label="新建项目" />}>
                <PlusIcon className="h-4 w-4" />
              </TooltipTrigger>
              <TooltipContent>新建项目</TooltipContent>
            </Tooltip>
          </div>

          {/* 项目列表——按名称排序 */}
          {[...projects].sort((a, b) => a.name.localeCompare(b.name)).map((project) => {
            const projectThreads = threads
              .filter((t) => t.project_id === project.id && t.id !== (project.default_thread_id ?? ''))
              .sort((a, b) => a.title.localeCompare(b.title))
            const projectUnread = projectUnreadCount(projectThreads, selectedThreadId)
            const isSelected = selectedProjectId === project.id
            const isExpanded = expandedProjects.has(project.id)
            return (
              <div
                key={project.id}
                data-testid={`project-${project.id}`}
                data-selected={isSelected ? 'true' : undefined}
              >
                {/* 项目节点 */}
                <div
                  className={`flex items-center justify-between p-2 rounded cursor-pointer transition-colors ${isSelected && selectedThreadId === project.default_thread_id ? 'bg-accent' : 'hover:bg-muted'}`}
                  onClick={() => {
                    onSelectProject(project.id)
                    const dtId = project.default_thread_id ?? ''
                    if (dtId) onSelectThread(dtId)
                    // 切换折叠
                    setExpandedProjects((prev) => {
                      const next = new Set(prev)
                      if (isExpanded) {
                        next.delete(project.id)
                      } else {
                        next.add(project.id)
                      }
                      return next
                    })
                  }}
                  onMouseEnter={() => setHoveredProjectId(project.id)}
                  onMouseLeave={() => setHoveredProjectId(null)}
                >
                  <div className="flex items-center gap-2">
                    {projectThreads.length > 0
                      ? isExpanded
                        ? <ChevronDownIcon className="h-4 w-4 shrink-0" />
                        : <ChevronRightIcon className="h-4 w-4 shrink-0" />
                      : <span className="h-4 w-4 shrink-0" />}
                    <span className="text-sm font-medium">{project.name}</span>
                    {/* 项目级未读聚合：非选中项目显示蓝色圆点 */}
                    {projectUnread > 0 && (
                      <span className="inline-block h-2 w-2 rounded-full bg-blue-500" data-testid={`project-${project.id}-unread`} />
                    )}
                  </div>
                  {/* 图标按钮组：JS state 控制可见性（hover 或 tooltip 打开时显示） */}
                  <div className={`flex gap-1 transition-opacity ${hoveredProjectId === project.id || openTooltipProjectId === project.id ? 'opacity-100' : 'opacity-0'}`}>
                    <Tooltip onOpenChange={(open) => { setOpenTooltipProjectId(open ? project.id : null) }}>
                      <TooltipTrigger render={<Button variant="ghost" size="icon" className="h-5 w-5" onClick={(e) => { e.stopPropagation(); onCreateThread(project.id) }} aria-label={`新建线程-${project.id}`} />}>
                          <PlusIcon className="h-3 w-3" />
                        </TooltipTrigger>
                      <TooltipContent>新建线程</TooltipContent>
                    </Tooltip>
                    <Tooltip onOpenChange={(open) => { setOpenTooltipProjectId(open ? project.id : null) }}>
                      <TooltipTrigger render={<Button variant="ghost" size="icon" className="h-5 w-5" onClick={(e) => { e.stopPropagation(); onAddMember(project.id) }} aria-label={`添加成员-${project.id}`} />}>
                          <UserPlusIcon className="h-3 w-3" />
                        </TooltipTrigger>
                      <TooltipContent>添加成员</TooltipContent>
                    </Tooltip>
                    <Tooltip onOpenChange={(open) => { setOpenTooltipProjectId(open ? project.id : null) }}>
                       <TooltipTrigger render={<Button variant="ghost" size="icon" className="h-5 w-5" onClick={(e) => { e.stopPropagation(); onRegisterAgent(project.id) }} aria-label={`注册Agent-${project.id}`} />}>
                           <BotIcon className="h-3 w-3" />
                         </TooltipTrigger>
                       <TooltipContent>注册Agent</TooltipContent>
                     </Tooltip>
                     <Tooltip onOpenChange={(open) => { setOpenTooltipProjectId(open ? project.id : null) }}>
                       <TooltipTrigger render={
                          <LongPressButton
                            className="size-5 p-0 text-red-500 hover:text-red-600"
                            onLongPress={() => setDeleteTarget({
                              type: 'project',
                              id: project.id,
                              projectId: project.id,
                              name: project.name,
                              deletePath: `/projects/${project.id}`,
                            })}
                            aria-label={`删除项目-${project.id}`}
                          >
                            <XIcon className="size-3" />
                          </LongPressButton>
                       } />
                       <TooltipContent>长按3秒删除项目</TooltipContent>
                     </Tooltip>
                  </div>
                </div>

                {/* 展开项目的子线程 */}
                {isExpanded && projectThreads.length > 0 && (
                  <div className="ml-4 space-y-1">
                    {projectThreads.map((thread) => {
                      const uc = thread.unread_count ?? 0
                      const showUnread = uc > 0 && selectedThreadId !== thread.id
                      return (
                        <div
                          key={thread.id}
                          data-testid={`thread-${thread.id}`}
                          data-selected={selectedThreadId === thread.id ? 'true' : undefined}
                          data-unread={showUnread ? 'true' : undefined}
                          className={`group flex items-center justify-between p-2 rounded cursor-pointer transition-colors ${selectedThreadId === thread.id ? 'bg-accent' : 'hover:bg-muted'}`}
                          onClick={() => { onSelectProject(thread.project_id); onSelectThread(thread.id) }}
                        >
                          <div className="flex items-center gap-2">
                            <span className="text-sm">{thread.title}</span>
                            {showUnread && uc === 1 && (
                              <span className="inline-block h-2 w-2 rounded-full bg-blue-500" data-unread="true" />
                            )}
                            {showUnread && uc > 1 && (
                              <Badge variant="default" className="h-5 min-w-[20px] text-xs" data-unread="true">
                                {uc}
                              </Badge>
                            )}
                          </div>
                          {thread.has_summary && (
                            <span data-testid={`${thread.id}-summary`} className="text-xs text-green-600">已总结</span>
                          )}
                          <div className="flex gap-2 text-xs text-muted-foreground">
                             <span>{thread.pending_plan_count}个待审</span>
                             <span>{thread.message_count}条消息</span>
                           </div>
                            <LongPressButton
                              className="size-4 p-0 text-red-500 hover:text-red-600 opacity-0 group-hover:opacity-100"
                              onLongPress={() => setDeleteTarget({
                                type: 'thread',
                                id: thread.id,
                                projectId: thread.project_id,
                                name: `${project.name}/${thread.title}`,
                                deletePath: `/projects/${thread.project_id}/threads/${thread.id}`,
                              })}
                              aria-label={`删除线程-${thread.id}`}
                            >
                              <XIcon className="size-2.5" />
                            </LongPressButton>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </ScrollArea>
      {deleteTarget && (
        <DeleteConfirmDialog
          open={!!deleteTarget}
          onClose={() => setDeleteTarget(null)}
          targetName={deleteTarget.name}
          targetType={deleteTarget.type}
          deletePath={deleteTarget.deletePath}
          onDeleted={() => {
            if (deleteTarget.type === 'project') {
              onDeleteProject(deleteTarget.id)
            } else {
              onDeleteThread(deleteTarget.id, deleteTarget.projectId)
            }
          }}
        />
      )}
    </TooltipProvider>
  )
}