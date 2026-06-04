import { clearToken } from '@/lib/auth'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { getIsAdmin } from '@/lib/auth'

export default function Workspace() {
  const navigate = useNavigate()

  const handleLogout = () => {
    clearToken()
    navigate('/login')
  }

  return (
    <div className="flex h-screen bg-background">
      {/* 左栏：项目列表 */}
      <aside className="w-64 border-r bg-card overflow-y-auto">
        <div className="p-4">
          <h2 className="text-sm font-semibold text-foreground">项目</h2>
          <p className="text-xs text-muted-foreground mt-1">项目列表将在步骤20实现</p>
        </div>
      </aside>

      {/* 中栏：讨论线程 */}
      <main className="flex-1 overflow-y-auto">
        <div className="p-4">
          <h2 className="text-sm font-semibold text-foreground">讨论</h2>
          <p className="text-xs text-muted-foreground mt-1">线程与消息将在步骤20实现</p>
        </div>
      </main>

      {/* 右栏：计划/产出审批 */}
      <aside className="w-64 border-l bg-card overflow-y-auto">
        <div className="p-4 flex flex-col gap-2">
          <h2 className="text-sm font-semibold text-foreground">审批</h2>
          <p className="text-xs text-muted-foreground mt-1">审批面板将在步骤20实现</p>
          {getIsAdmin() && (
            <Button variant="outline" size="sm" onClick={() => navigate('/approval')}>用户审批管理</Button>
          )}
          <Button variant="ghost" size="sm" onClick={handleLogout}>登出</Button>
        </div>
      </aside>
    </div>
  )
}