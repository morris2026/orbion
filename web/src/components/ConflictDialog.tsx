import { Button } from '@/components/ui/button'
import { GitMerge, Replace, X } from 'lucide-react'
import type { FileConflictInfo } from '@/hooks/useFileTab'

interface ConflictDialogProps {
  conflictInfo: FileConflictInfo
  onResolveManually: () => void
  onOverwrite: () => void
  onCancel: () => void
}

/**
 * 文件保存冲突对话框（设计 §5.2.3）
 *
 * 角色命名：当前用户 = 保存者（mine），对方 = 已写入磁盘的并发修改者（theirs）。
 * 设计文档中 "B" 指当前用户，"A" 指对方——与本文案一致。
 *
 * 三选项（MVP fallback，Agent Runtime 集成后"对比并合并"由 Agent 自动执行）：
 * - 对比并合并：把 merged_content（含冲突标记）载入编辑器，用户手动解决后重存
 * - 覆盖：用当前用户的编辑覆盖磁盘（force=true，跳过 mtime 检测，对方修改丢失）
 * - 取消：保留编辑器内容，不保存
 */
export function ConflictDialog({
  conflictInfo,
  onResolveManually,
  onOverwrite,
  onCancel,
}: ConflictDialogProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      data-testid="conflict-dialog"
    >
      <div className="bg-background border rounded-lg shadow-lg max-w-md w-full mx-4 p-4">
        <div className="flex items-center gap-2 mb-2">
          <GitMerge className="h-4 w-4 text-destructive" />
          <h3 className="text-sm font-medium">文件保存冲突</h3>
        </div>
        <p className="text-xs text-muted-foreground mb-3">
          文件 <span className="font-mono">{conflictInfo.path}</span> 已被其他人修改，
          与你的编辑产生冲突（{conflictInfo.conflict_markers.length} 处）。
          请选择处理方式：
        </p>
        <div className="flex flex-col gap-2">
          <Button
            variant="default"
            size="sm"
            className="justify-start"
            onClick={onResolveManually}
            data-testid="btn-conflict-merge"
          >
            <GitMerge className="h-3.5 w-3.5 mr-2" />
            对比并合并（手动解决冲突）
          </Button>
          <Button
            variant="destructive"
            size="sm"
            className="justify-start"
            onClick={onOverwrite}
            data-testid="btn-conflict-overwrite"
          >
            <Replace className="h-3.5 w-3.5 mr-2" />
            覆盖（丢弃对方的磁盘修改）
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="justify-start"
            onClick={onCancel}
            data-testid="btn-conflict-cancel"
          >
            <X className="h-3.5 w-3.5 mr-2" />
            取消（保留当前编辑不保存）
          </Button>
        </div>
      </div>
    </div>
  )
}
