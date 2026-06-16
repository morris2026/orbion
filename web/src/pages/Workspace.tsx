import { useState } from 'react'
import { clearToken, getIsAdmin, getCurrentUserId } from '@/lib/auth'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Group, Panel, Separator } from 'react-resizable-panels'
import ProjectTree from '@/components/ProjectTree'
import DiscussionPanel from '@/components/DiscussionPanel'
import { RightPanelTabs } from '@/components/RightPanelTabs'
import CreateProjectDialog from '@/components/CreateProjectDialog'
import CreateThreadDialog from '@/components/CreateThreadDialog'
import AddMemberDialog from '@/components/AddMemberDialog'
import RegisterAgentDialog from '@/components/RegisterAgentDialog'
import { useWorkspace } from '@/hooks/useWorkspace'
import type { UseWorkspaceOptions } from '@/hooks/useWorkspace'

// 分隔条：4px空间 + border-r画1px可视线 + 库内置proximity hover/drag检测
// 库通过data-separator属性暴露状态（inactive/hover/active/focus/disabled）
// 用TailwindCSS data variant做纯CSS样式切换，无需JS状态管理
const SEP_CLASS = 'w-1 border-r border-border bg-transparent transition-[border-width,border-color] duration-150 cursor-col-resize data-[separator=hover]:border-r-[4px] data-[separator=hover]:border-primary/40 data-[separator=hover]:duration-75 data-[separator=active]:border-r-[4px] data-[separator=active]:border-primary data-[separator=focus]:border-r-[4px] data-[separator=focus]:border-primary/40'

interface WorkspaceProps {
  workspaceOptions?: UseWorkspaceOptions
}

export default function Workspace({ workspaceOptions }: WorkspaceProps) {
  const navigate = useNavigate()
  const ws = useWorkspace(workspaceOptions)

  const [showCreateProject, setShowCreateProject] = useState(false)
  const [showCreateThread, setShowCreateThread] = useState(false)
  const [showAddMember, setShowAddMember] = useState(false)
  const [showRegisterAgent, setShowRegisterAgent] = useState(false)
  const [dialogProjectId, setDialogProjectId] = useState<string | null>(null)

  const handleLogout = () => {
    clearToken()
    navigate('/login')
  }

  const openProjectDialog = (setter: React.Dispatch<React.SetStateAction<boolean>>, projectId: string) => {
    setDialogProjectId(projectId)
    setter(true)
  }

  return (
    <div className="h-screen bg-background">
      <Group orientation="horizontal" className="h-full"
        id="workspace-columns"
                defaultLayout={{ "workspace-left": 20, "workspace-middle": 40, "workspace-right": 40 }}>
        {/* 左栏：项目树形导航 */}
        <Panel id="workspace-left" minSize={256} maxSize={400}
          className="bg-card overflow-hidden">
          <ProjectTree
            projects={ws.projects}
            threads={ws.threads}
            selectedProjectId={ws.selectedProjectId}
            selectedThreadId={ws.selectedThreadId}
            onSelectThread={ws.setSelectedThreadId}
            onSelectProject={ws.setSelectedProjectId}
            onCreateProject={() => setShowCreateProject(true)}
            onCreateThread={(projectId) => openProjectDialog(setShowCreateThread, projectId)}
            onAddMember={(projectId) => openProjectDialog(setShowAddMember, projectId)}
            onRegisterAgent={(projectId) => openProjectDialog(setShowRegisterAgent, projectId)}
            onDeleteProject={(projectId) => {
              ws.setProjects((prev) => prev.filter((p) => p.id !== projectId))
              ws.setThreads((prev) => prev.filter((t) => t.project_id !== projectId))
              if (ws.selectedProjectId === projectId) {
                ws.setSelectedProjectId(null)
                ws.setSelectedThreadId(null)
                ws.setMessages([])
                ws.setPlans([])
                ws.setOutputs([])
              }
            }}
            onDeleteThread={(threadId, _projectId) => {
              ws.setThreads((prev) => prev.filter((t) => t.id !== threadId))
              if (ws.selectedThreadId === threadId) {
                ws.setSelectedThreadId(null)
                ws.setMessages([])
              }
            }}
          />
        </Panel>

        <Separator id="workspace-separator-left"
          className={SEP_CLASS} />

        {/* 中栏：讨论面板 */}
        <Panel id="workspace-middle" minSize="20"
          className="overflow-hidden">
          {ws.selectedThreadId ? (
            <DiscussionPanel
              messages={ws.messages}
              currentUserId={getCurrentUserId() ?? ''}
              onSendMessage={ws.handleSendMessage}
            />
          ) : (
            <div className="p-4">
              <p className="text-sm text-muted-foreground">选择线程开始讨论</p>
            </div>
          )}
        </Panel>

        <Separator id="workspace-separator-right"
          className={SEP_CLASS} />

        {/* 右栏：Tab 容器 */}
        <Panel id="workspace-right" minSize="20"
          className="bg-card overflow-hidden">
          <div className="flex flex-col h-full">
            <div className="flex items-center gap-1 px-2 py-1 border-b">
              {getIsAdmin() && (
                <Button variant="outline" size="sm" onClick={() => navigate('/approval')}>用户审批管理</Button>
              )}
              <div className="flex-1" />
              <Button variant="ghost" size="sm" onClick={handleLogout}>登出</Button>
            </div>
            <RightPanelTabs
              projectId={ws.selectedProjectId}
              selectedTab={ws.selectedRightTab}
              onTabChange={ws.setSelectedRightTab}
              plans={ws.plans}
              outputs={ws.outputs}
              onApprovePlan={ws.handleApprovePlan}
              onRejectPlan={ws.handleRejectPlan}
              fileTreeRefreshKey={ws.fileTreeRefreshKey}
            />
          </div>
        </Panel>
      </Group>

      {/* Dialogs */}
      <CreateProjectDialog
        open={showCreateProject}
        onClose={() => setShowCreateProject(false)}
        onCreateProject={(project) => {
          ws.setProjects((prev) => [...prev, project].sort((a, b) => a.name.localeCompare(b.name)))
          ws.setSelectedProjectId(project.id)
        }}
        onSelectThread={(projectId, threadId) => {
          ws.setSelectedProjectId(projectId)
          ws.setSelectedThreadId(threadId)
        }}
      />
      {dialogProjectId && (
        <>
          <CreateThreadDialog
            open={showCreateThread}
            projectId={dialogProjectId}
            onClose={() => setShowCreateThread(false)}
            onCreateThread={(projectId, thread) => {
              ws.setThreads((prev) => [...prev, thread].sort((a, b) => a.title.localeCompare(b.title)))
              ws.setSelectedProjectId(projectId)
              ws.setSelectedThreadId(thread.id)
            }}
          />
          <AddMemberDialog
            open={showAddMember}
            projectId={dialogProjectId}
            onClose={() => setShowAddMember(false)}
            onAddMember={(projectId) => ws.setSelectedProjectId(projectId)}
          />
          <RegisterAgentDialog
            open={showRegisterAgent}
            projectId={dialogProjectId}
            onClose={() => setShowRegisterAgent(false)}
            onRegisterAgent={(projectId) => ws.setSelectedProjectId(projectId)}
          />
        </>
      )}
    </div>
  )
}