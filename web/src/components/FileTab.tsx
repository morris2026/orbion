import { useState, useEffect } from 'react'
import { Group, Panel, Separator } from 'react-resizable-panels'
import loader from '@monaco-editor/loader'
import { ActivityBar } from '@/components/ActivityBar'
import { ExplorerPanel } from '@/components/ExplorerPanel'
import { SourceControlPanel } from '@/components/SourceControlPanel'
import { FileEditor } from '@/components/FileEditor'
import { ConflictDialog } from '@/components/ConflictDialog'
import { StaleFilePrompt } from '@/components/StaleFilePrompt'
import { useFileTab } from '@/hooks/useFileTab'
import type { ActivityPanel } from '@/components/ActivityBar'
import { GitBranch } from 'lucide-react'

interface FileTabProps {
  projectId: string | null
  refreshKey?: number
}

export function FileTab({ projectId, refreshKey }: FileTabProps) {
  const {
    repos,
    selectedRepo,
    worktrees,
    selectedWorktreeId,
    isReadOnly,
    fileTree,
    selectedFile,
    fileContent,
    setFileContent,
    originalContent,
    isDirty,
    gitStatus,
    changeCounts,
    viewMode,
    conflictInfo,
    staleAcknowledged,
    selectRepo,
    selectWorktree,
    selectFile,
    selectFileFromSC,
    saveFile,
    reloadFile,
    resolveConflictManually,
    overwriteConflict,
    cancelConflict,
    stageFiles,
    unstageFiles,
    commitChanges,
  } = useFileTab({ projectId, refreshKey })

  const [activePanel, setActivePanel] = useState<ActivityPanel>('explorer')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [monacoError, setMonacoError] = useState(false)

  // Monaco loader 检测
  useEffect(() => {
    let cancelled = false
    const timeout = setTimeout(() => {
      if (!cancelled) setMonacoError(true)
    }, 15000)

    loader.init()
      .then(() => {
        if (!cancelled) {
          clearTimeout(timeout)
          setMonacoError(false)
        }
      })
      .catch(() => {
        if (!cancelled) {
          clearTimeout(timeout)
          setMonacoError(true)
        }
      })

    return () => {
      cancelled = true
      clearTimeout(timeout)
    }
  }, [])

  // 活动栏图标作为侧边栏开关：同面板→折叠，不同面板→切换
  const handleActivityChange = (panel: ActivityPanel) => {
    if (panel === activePanel && !sidebarCollapsed) {
      setSidebarCollapsed(true)
    } else {
      setActivePanel(panel)
      if (sidebarCollapsed) {
        setSidebarCollapsed(false)
      }
    }
  }

  return (
    <div className="h-full flex flex-col">
      {/* worktree 选择器（设计 §4：file tab 顶部 worktree 选择器下拉） */}
      {worktrees.length > 0 && (
        <div className="flex items-center gap-2 px-3 py-1 border-b bg-muted/30" data-testid="worktree-selector-bar">
          <GitBranch className="h-3.5 w-3.5 text-muted-foreground" />
          <select
            data-testid="worktree-selector"
            value={selectedWorktreeId ?? ''}
            onChange={(e) => selectWorktree(e.target.value)}
            className="text-xs bg-transparent border-none outline-none cursor-pointer hover:bg-accent rounded px-1 py-0.5"
          >
            {worktrees.map((wt) => (
              <option key={wt.id} value={wt.id} data-testid="worktree-option">
                {wt.worktree_type === 'main' ? 'main' : wt.branch_name} ({wt.status})
              </option>
            ))}
          </select>
          {isReadOnly && (
            <span
              className="text-[10px] px-1.5 py-0.5 rounded bg-yellow-500/10 text-yellow-700 dark:text-yellow-400"
              data-testid="readonly-badge"
            >
              只读
            </span>
          )}
        </div>
      )}

      <div className="flex-1 flex min-h-0">
        <ActivityBar activePanel={activePanel} sidebarCollapsed={sidebarCollapsed} onActivityChange={handleActivityChange} />

        <Group orientation="horizontal" className="flex-1">
          {/* 侧边栏 — 折叠时不渲染 */}
          {!sidebarCollapsed && (
            <>
              <Panel
                id="filetab-sidebar"
                minSize={150}
                maxSize={400}
                defaultSize={150}
                className="overflow-hidden border-r"
              >
                <div className="h-full flex flex-col" data-testid="sidebar-panel">
                  {/* 侧边栏头部 */}
                  <div className="flex items-center px-2 py-1 border-b bg-muted/30">
                    <span className="text-xs font-medium text-muted-foreground">
                      {activePanel === 'explorer' ? '资源管理器' : 'Source Control'}
                    </span>
                  </div>

                  {/* 侧边栏内容 */}
                  <div className="flex-1 min-h-0 overflow-auto">
                    {activePanel === 'explorer' ? (
                      <ExplorerPanel
                        fileTree={fileTree}
                        selectedFile={selectedFile}
                        onFileSelect={selectFile}
                      />
                    ) : (
                      <SourceControlPanel
                        repos={repos}
                        selectedRepo={selectedRepo}
                        gitStatus={gitStatus}
                        changeCounts={changeCounts}
                        onSelectRepo={selectRepo}
                        onStage={stageFiles}
                        onUnstage={unstageFiles}
                        onCommit={commitChanges}
                        onFileSelect={selectFileFromSC}
                      />
                    )}
                  </div>
                </div>
              </Panel>

              <Separator className="w-px bg-border" />
            </>
          )}

          {/* 主区域 */}
          <Panel id="filetab-main" minSize={200} className="overflow-hidden">
            <div className="h-full flex items-center">
              <div className="flex-1 h-full min-w-0">
                <FileEditor
                  filePath={selectedFile}
                  fileContent={fileContent}
                  isDirty={isDirty}
                  viewMode={viewMode}
                  originalContent={originalContent}
                  onSave={saveFile}
                  onContentChange={setFileContent}
                  monacoError={monacoError}
                  readOnly={isReadOnly}
                />
              </div>
            </div>
          </Panel>
        </Group>
      </div>

      {/* 409 冲突对话框与 30 分钟过期提示互斥渲染（避免叠加） */}
      {conflictInfo ? (
        <ConflictDialog
          conflictInfo={conflictInfo}
          onResolveManually={resolveConflictManually}
          onOverwrite={overwriteConflict}
          onCancel={cancelConflict}
        />
      ) : staleAcknowledged ? (
        <StaleFilePrompt onReload={reloadFile} onKeep={() => saveFile({ force: false })} />
      ) : null}
    </div>
  )
}
