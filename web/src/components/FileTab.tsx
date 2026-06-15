import { useState, useEffect } from 'react'
import { Group, Panel, Separator } from 'react-resizable-panels'
import loader from '@monaco-editor/loader'
import { ActivityBar } from '@/components/ActivityBar'
import { ExplorerPanel } from '@/components/ExplorerPanel'
import { SourceControlPanel } from '@/components/SourceControlPanel'
import { FileEditor } from '@/components/FileEditor'
import { useFileTab } from '@/hooks/useFileTab'
import type { ActivityPanel } from '@/components/ActivityBar'

interface FileTabProps {
  projectId: string | null
}

export function FileTab({ projectId }: FileTabProps) {
  const {
    repos,
    selectedRepo,
    fileTree,
    selectedFile,
    fileContent,
    setFileContent,
    originalContent,
    isDirty,
    gitStatus,
    changeCounts,
    viewMode,
    selectRepo,
    selectFile,
    selectFileFromSC,
    saveFile,
    stageFiles,
    unstageFiles,
    commitChanges,
  } = useFileTab({ projectId })

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
    <div className="h-full flex">
      <ActivityBar activePanel={activePanel} sidebarCollapsed={sidebarCollapsed} onActivityChange={handleActivityChange} />

      <Group orientation="horizontal" className="flex-1">
        {/* 侧边栏 — 折叠时不渲染 */}
        {!sidebarCollapsed && (
          <>
            <Panel
              id="filetab-sidebar"
              minSize={150}
              maxSize={400}
              defaultSize={240}
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
              />
            </div>
          </div>
        </Panel>
      </Group>
    </div>
  )
}
