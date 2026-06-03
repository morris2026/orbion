export default function Workspace() {
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
        <div className="p-4">
          <h2 className="text-sm font-semibold text-foreground">审批</h2>
          <p className="text-xs text-muted-foreground mt-1">审批面板将在步骤20实现</p>
        </div>
      </aside>
    </div>
  )
}