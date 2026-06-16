import { ChevronRightIcon, ChevronDownIcon } from 'lucide-react'
import type { RepoInfo } from '@/types/api'

interface RepoListProps {
  repos: RepoInfo[]
  selectedRepo: string | null
  changeCounts: Record<string, number>
  onSelectRepo: (name: string) => void
  collapsed: boolean
  onToggleCollapse: () => void
}

export function RepoList({
  repos,
  selectedRepo,
  changeCounts,
  onSelectRepo,
  collapsed,
  onToggleCollapse,
}: RepoListProps) {
  return (
    <div className="flex flex-col" data-testid="repo-list">
      <button
        className="flex items-center gap-1 w-full px-2 py-1 border-b cursor-pointer hover:bg-muted/50 text-left"
        onClick={onToggleCollapse}
        aria-expanded={!collapsed}
        aria-controls="repo-list-content"
      >
        {collapsed
          ? <ChevronRightIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
          : <ChevronDownIcon className="h-4 w-4 shrink-0 text-muted-foreground" />}
        <span className="text-xs font-medium text-muted-foreground">仓库列表</span>
      </button>
      {!collapsed && (
        <ul id="repo-list-content" className="overflow-auto">
          {repos.map((repo) => (
            <li
              key={repo.name}
              className={`flex items-center justify-between px-2 py-1 text-sm cursor-pointer hover:bg-muted/50 ${
                repo.name === selectedRepo ? 'bg-muted text-foreground' : 'text-muted-foreground'
              }`}
              onClick={() => onSelectRepo(repo.name)}
            >
              <span className="truncate">{repo.name}</span>
              {changeCounts[repo.name] > 0 && (
                <span
                  data-testid={`repo-badge-${repo.name}`}
                  className="ml-1 px-1.5 text-[10px] rounded-full bg-primary/20 text-primary"
                >
                  {changeCounts[repo.name]}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
