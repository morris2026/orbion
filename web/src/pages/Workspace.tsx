import { useState } from 'react'
import { clearToken, getIsAdmin } from '@/lib/auth'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import ProjectTree from '@/components/ProjectTree'
import DiscussionPanel from '@/components/DiscussionPanel'
import ExecutionPanel from '@/components/ExecutionPanel'
import CreateProjectDialog from '@/components/CreateProjectDialog'
import CreateThreadDialog from '@/components/CreateThreadDialog'
import AddMemberDialog from '@/components/AddMemberDialog'
import RegisterAgentDialog from '@/components/RegisterAgentDialog'
import { useWorkspace } from '@/hooks/useWorkspace'
import type { UseWorkspaceOptions } from '@/hooks/useWorkspace'

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
    <div className="flex h-screen bg-background">
      {/* 左栏：项目树形导航 */}
      <aside className="w-64 border-r bg-card overflow-hidden">
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
        />
      </aside>

      {/* 中栏：讨论面板 */}
      <main className="flex-1 overflow-hidden">
        {ws.selectedThreadId ? (
          <DiscussionPanel
            messages={ws.messages}
            onSendMessage={ws.handleSendMessage}
          />
        ) : (
          <div className="p-4">
            <p className="text-sm text-muted-foreground">选择线程开始讨论</p>
          </div>
        )}
      </main>

      {/* 右栏：执行计划与产出审批 */}
      <aside className="w-64 border-l bg-card overflow-hidden">
        <div className="flex flex-col h-full">
          <div className="p-4 flex flex-col gap-2 border-b">
            <h2 className="text-sm font-semibold text-foreground">审批</h2>
            {getIsAdmin() && (
              <Button variant="outline" size="sm" onClick={() => navigate('/approval')}>用户审批管理</Button>
            )}
            <Button variant="ghost" size="sm" onClick={handleLogout}>登出</Button>
          </div>
          <ExecutionPanel
            plans={ws.plans}
            outputs={ws.outputs}
            onApprovePlan={ws.handleApprovePlan}
            onRejectPlan={ws.handleRejectPlan}
          />
        </div>
      </aside>

      {/* Dialogs */}
      <CreateProjectDialog
        open={showCreateProject}
        onClose={() => setShowCreateProject(false)}
        onCreateProject={(project) => {
          ws.setProjects((prev) => [...prev, project])
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
              ws.setThreads((prev) => [...prev, thread])
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