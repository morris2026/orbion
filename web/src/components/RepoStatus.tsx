import { useState } from 'react'
import { ChevronRightIcon, ChevronDownIcon } from 'lucide-react'
import type { GitFileStatus } from '@/types/api'

interface RepoStatusProps {
  staged: GitFileStatus[]
  changes: GitFileStatus[]
  onStage: (paths: string[]) => void
  onUnstage: (paths: string[]) => void
  onCommit: (message: string) => void
  onFileSelect: (path: string) => void
}

const statusColors: Record<string, string> = {
  A: 'text-green-500',
  M: 'text-yellow-500',
  D: 'text-red-500',
  R: 'text-blue-500',
  U: 'text-purple-500',
}

export function RepoStatus({
  staged,
  changes,
  onStage,
  onUnstage,
  onCommit,
  onFileSelect,
}: RepoStatusProps) {
  const [commitMessage, setCommitMessage] = useState('')
  const [collapsed, setCollapsed] = useState(false)

  const handleCommit = () => {
    if (!commitMessage.trim()) return
    onCommit(commitMessage)
    setCommitMessage('')
  }

  const handleCommitKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleCommit()
    }
  }

  return (
    <div className="flex flex-col h-full overflow-auto" data-testid="repo-status">
      {/* 总标题栏 */}
      <button
        className="flex items-center gap-1 w-full px-2 py-1 border-b cursor-pointer hover:bg-muted/50 text-left"
        onClick={() => setCollapsed((prev) => !prev)}
        aria-expanded={!collapsed}
        aria-controls="repo-status-content"
      >
        {collapsed
          ? <ChevronRightIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
          : <ChevronDownIcon className="h-4 w-4 shrink-0 text-muted-foreground" />}
        <span className="text-xs font-medium text-muted-foreground">变更</span>
      </button>

      {!collapsed && (<div id="repo-status-content">
      {/* Staged Changes */}
      {staged.length > 0 && (
        <div className="border-b">
          <div className="px-2 py-1 text-xs font-medium text-muted-foreground">
            Staged Changes
          </div>
          <ul>
            {staged.map((file) => (
              <li key={file.path} className="flex items-center gap-1 px-2 py-0.5 text-sm hover:bg-muted/50">
                <span
                  data-testid={`status-${file.path}`}
                  data-status={file.status}
                  className={`text-[10px] font-mono w-3 text-center ${statusColors[file.status] ?? ''}`}
                >
                  {file.status}
                </span>
                <span
                  className="flex-1 truncate cursor-pointer"
                  onClick={() => onFileSelect(file.path)}
                >
                  {file.path}
                </span>
                <button
                  className="text-xs text-muted-foreground hover:text-foreground"
                  onClick={() => onUnstage([file.path])}
                  aria-label={`unstage ${file.path}`}
                >
                  −
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Changes */}
      {changes.length > 0 && (
        <div className="border-b">
          <div className="px-2 py-1 text-xs font-medium text-muted-foreground">
            Changes
          </div>
          <ul>
            {changes.map((file) => (
              <li key={file.path} className="flex items-center gap-1 px-2 py-0.5 text-sm hover:bg-muted/50">
                <span
                  data-testid={`status-${file.path}`}
                  data-status={file.status}
                  className={`text-[10px] font-mono w-3 text-center ${statusColors[file.status] ?? ''}`}
                >
                  {file.status}
                </span>
                <span
                  className="flex-1 truncate cursor-pointer"
                  onClick={() => onFileSelect(file.path)}
                >
                  {file.path}
                </span>
                <button
                  className="text-xs text-muted-foreground hover:text-foreground"
                  onClick={() => onStage([file.path])}
                  aria-label={`stage ${file.path}`}
                >
                  +
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Commit 输入 */}
      {staged.length > 0 && (
        <div className="p-2 border-t mt-auto">
          <div className="flex gap-1">
            <input
              type="text"
              className="flex-1 px-2 py-1 text-xs bg-background border rounded focus:outline-none focus:ring-1 focus:ring-primary"
              placeholder="Commit message"
              value={commitMessage}
              onChange={(e) => setCommitMessage(e.target.value)}
              onKeyDown={handleCommitKeyDown}
            />
            <button
              className="px-2 py-1 text-xs bg-primary text-primary-foreground rounded hover:bg-primary/90 disabled:opacity-50"
              onClick={handleCommit}
              disabled={!commitMessage.trim()}
              aria-label="Commit"
            >
              Commit
            </button>
          </div>
        </div>
      )}
      </div>)}
    </div>
  )
}
