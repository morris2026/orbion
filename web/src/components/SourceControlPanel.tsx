import { useState, useEffect, useCallback, useRef } from 'react'
import { RepoList } from '@/components/RepoList'
import { RepoStatus } from '@/components/RepoStatus'
import type { RepoInfo, GitStatusResult } from '@/types/api'

interface SourceControlPanelProps {
  repos: RepoInfo[]
  selectedRepo: string | null
  gitStatus: GitStatusResult
  changeCounts: Record<string, number>
  onSelectRepo: (name: string) => void
  onStage: (paths: string[]) => void
  onUnstage: (paths: string[]) => void
  onCommit: (message: string) => void
  onFileSelect: (path: string) => void
}

export function SourceControlPanel({
  repos,
  selectedRepo,
  gitStatus,
  changeCounts,
  onSelectRepo,
  onStage,
  onUnstage,
  onCommit,
  onFileSelect,
}: SourceControlPanelProps) {
  const [collapsed, setCollapsed] = useState(false)
  const [topHeight, setTopHeight] = useState(200)
  const topHeightRef = useRef(200)
  const dragRef = useRef<{ startY: number; startHeight: number } | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)

  const updateTopHeight = useCallback((value: number) => {
    topHeightRef.current = value
    setTopHeight(value)
  }, [])

  const handleToggleCollapse = useCallback(() => {
    setCollapsed((prev) => !prev)
  }, [])

  const handleSeparatorMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    dragRef.current = { startY: e.clientY, startHeight: topHeightRef.current }
  }, [])

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!dragRef.current) return
      const delta = e.clientY - dragRef.current.startY
      const containerHeight = containerRef.current?.clientHeight ?? 0
      // 下栏最小保留 100px，上栏最小 50px
      const maxHeight = containerHeight > 150 ? containerHeight - 100 : containerHeight > 0 ? 50 : Infinity
      updateTopHeight(Math.max(50, Math.min(maxHeight, dragRef.current.startHeight + delta)))
    }
    const handleMouseUp = () => {
      dragRef.current = null
    }
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
  }, [])

  return (
    <div className="h-full flex flex-col" data-testid="source-control-panel" ref={containerRef}>
      {/* 上栏：RepoList */}
      <div style={{ height: collapsed ? 'auto' : `${topHeight}px` }} data-testid="sc-top-panel">
        <RepoList
          repos={repos}
          selectedRepo={selectedRepo}
          changeCounts={changeCounts}
          onSelectRepo={onSelectRepo}
          collapsed={collapsed}
          onToggleCollapse={handleToggleCollapse}
        />
      </div>

      {/* 分隔条 */}
      <div
        data-testid="sc-separator"
        className="h-1 cursor-row-resize bg-border hover:bg-primary/50 flex-shrink-0"
        onMouseDown={handleSeparatorMouseDown}
      />

      {/* 下栏：RepoStatus */}
      <div className="flex-1 min-h-0">
        <RepoStatus
          staged={gitStatus.staged}
          changes={gitStatus.changes}
          onStage={onStage}
          onUnstage={onUnstage}
          onCommit={onCommit}
          onFileSelect={onFileSelect}
        />
      </div>
    </div>
  )
}
