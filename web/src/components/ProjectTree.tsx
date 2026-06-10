import { useState } from 'react'
import type { ProjectListItem, ThreadListItem } from '@/types/api'
import { PlusIcon, UserPlusIcon, BotIcon } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

interface ProjectTreeProps {
  projects: ProjectListItem[]
  threads: ThreadListItem[]
  selectedProjectId: string | null
  selectedThreadId: string | null
  onSelectThread: (threadId: string) => void
  onSelectProject: (projectId: string) => void
  onCreateProject: () => void
  onCreateThread: (projectId: string) => void
  onAddMember: (projectId: string) => void
  onRegisterAgent: (projectId: string) => void
}

/** 计算项目的总未读数，排除当前选中线程的未读 */
function projectUnreadCount(
  allThreads: ThreadListItem[],
  selectedThreadId: string | null,
): number {
  return allThreads.reduce(
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
}: ProjectTreeProps) {
  // tooltip hover 协调：CSS group-hover 无法感知 portaled tooltip 的打开状态，
  // 用 JS state 统一控制按钮可见性
  const [hoveredProjectId, setHoveredProjectId] = useState<string | null>(null)
  const [openTooltipProjectId, setOpenTooltipProjectId] = useState<string | null>(null)

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

  const selectedProject = projects.find((p) => p.id === selectedProjectId)
  // 选中项目的非默认线程（子线程）
  const childThreads = selectedProject
    ? threads.filter((t) => t.id !== (selectedProject.default_thread_id ?? ''))
    : []

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

          {/* 项目列表 */}
          {projects.map((project) => {
            const projectUnread = projectUnreadCount(selectedProjectId === project.id ? threads : [], selectedThreadId)
            return (
              <div
                key={project.id}
                data-testid={`project-${project.id}`}
                data-selected={selectedProjectId === project.id ? 'true' : undefined}
              >
                {/* 项目节点 */}
                <div
                  className="flex items-center justify-between p-2 rounded cursor-pointer hover:bg-muted transition-colors"
                  onClick={() => {
                    onSelectProject(project.id)
                    const dtId = project.default_thread_id ?? ''
                    if (dtId) onSelectThread(dtId)
                  }}
                  onMouseEnter={() => setHoveredProjectId(project.id)}
                  onMouseLeave={() => setHoveredProjectId(null)}
                >
                  <div className="flex items-center gap-2">
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
                  </div>
                </div>

                {/* 选中项目的子线程 */}
                {selectedProjectId === project.id && childThreads.length > 0 && (
                  <div className="ml-4 space-y-1">
                    {childThreads.map((thread) => {
                      const uc = thread.unread_count ?? 0
                      const showUnread = uc > 0 && selectedThreadId !== thread.id
                      return (
                        <div
                          key={thread.id}
                          data-testid={`thread-${thread.id}`}
                          data-selected={selectedThreadId === thread.id ? 'true' : undefined}
                          data-unread={showUnread ? 'true' : undefined}
                          className="flex items-center justify-between p-2 rounded cursor-pointer hover:bg-muted transition-colors"
                          onClick={() => onSelectThread(thread.id)}
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
    </TooltipProvider>
  )
}