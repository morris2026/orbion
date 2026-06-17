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
  return (
    <div className="h-full flex flex-col" data-testid="source-control-panel">
      <div className="overflow-auto flex-shrink-0" style={{ maxHeight: '8.75rem' }}>
        <RepoList
          repos={repos}
          selectedRepo={selectedRepo}
          changeCounts={changeCounts}
          onSelectRepo={onSelectRepo}
        />
      </div>
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
