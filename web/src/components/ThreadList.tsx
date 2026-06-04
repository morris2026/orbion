import type { ThreadListItem } from '@/types/api'

interface ThreadListProps {
  threads: ThreadListItem[]
  onSelect: (threadId: string) => void
}

export default function ThreadList({ threads, onSelect }: ThreadListProps) {
  return (
    <ul className="space-y-1">
      {threads.map((t) => (
        <li
          key={t.id}
          onClick={() => onSelect(t.id)}
          className="p-2 rounded cursor-pointer hover:bg-muted transition-colors"
        >
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">{t.title}</span>
            {t.has_summary && (
              <span data-testid={`${t.id}-summary`} className="text-xs text-green-600">已总结</span>
            )}
          </div>
          <div className="flex gap-2 text-xs text-muted-foreground mt-1">
            <span>{t.pending_plan_count}个待审</span>
            <span>{t.message_count}条消息</span>
          </div>
        </li>
      ))}
    </ul>
  )
}