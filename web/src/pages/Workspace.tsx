import { clearToken, getIsAdmin } from '@/lib/auth'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import ThreadList from '@/components/ThreadList'
import DiscussionPanel from '@/components/DiscussionPanel'
import ExecutionPanel from '@/components/ExecutionPanel'
import { useWorkspace } from '@/hooks/useWorkspace'
import type { UseWorkspaceOptions } from '@/hooks/useWorkspace'

interface WorkspaceProps {
  workspaceOptions?: UseWorkspaceOptions
}

export default function Workspace({ workspaceOptions }: WorkspaceProps) {
  const navigate = useNavigate()
  const ws = useWorkspace(workspaceOptions)

  const handleLogout = () => {
    clearToken()
    navigate('/login')
  }

  return (
    <div className="flex h-screen bg-background">
      {/* 左栏：项目与线程列表 */}
      <aside className="w-64 border-r bg-card overflow-y-auto">
        <div className="p-4 space-y-4">
          <div>
            <h2 className="text-sm font-semibold text-foreground mb-2">项目</h2>
            {ws.projects.map((p) => (
              <button
                key={p.id}
                onClick={() => ws.setSelectedProjectId(p.id)}
                className={`w-full text-left p-2 rounded text-sm ${ws.selectedProjectId === p.id ? 'bg-primary/10 font-medium' : 'hover:bg-muted'}`}
              >
                {p.name}
              </button>
            ))}
          </div>
          {ws.selectedProjectId && (
            <div>
              <h2 className="text-sm font-semibold text-foreground mb-2">线程</h2>
              <ThreadList threads={ws.threads} onSelect={ws.setSelectedThreadId} />
            </div>
          )}
        </div>
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
    </div>
  )
}