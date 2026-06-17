import type { RepoInfo } from '@/types/api'

interface RepoListProps {
  repos: RepoInfo[]
  selectedRepo: string | null
  changeCounts: Record<string, number>
  onSelectRepo: (name: string) => void
}

export function RepoList({
  repos,
  selectedRepo,
  changeCounts,
  onSelectRepo,
}: RepoListProps) {
  return (
    <div className="flex flex-col" data-testid="repo-list">
      <div className="flex items-center gap-1 px-2 py-1 border-b">
        <span className="text-xs font-medium text-muted-foreground">仓库列表</span>
      </div>
      <ul>
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
    </div>
  )
}
