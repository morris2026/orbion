import { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { apiDelete, ApiError } from '@/lib/api'

interface DeleteConfirmDialogProps {
  open: boolean
  onClose: () => void
  targetName: string
  targetType: 'project' | 'thread'
  deletePath: string
  onDeleted: () => void
}

export default function DeleteConfirmDialog({
  open,
  onClose,
  targetName,
  targetType,
  deletePath,
  onDeleted,
}: DeleteConfirmDialogProps) {
  const [input, setInput] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const matched = input === targetName
  const warningText =
    targetType === 'project'
      ? '此操作不可撤销。项目下所有线程、消息和数据将被永久删除。'
      : '此操作不可撤销。线程内所有消息和数据将被永久删除。'

  const handleSubmit = async () => {
    if (!matched || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      await apiDelete(deletePath)
      onDeleted()
      onClose()
    } catch (e) {
      if (e instanceof ApiError) {
        setError(`删除失败：${e.detail}`)
      } else {
        setError('删除失败')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>确认删除</DialogTitle>
          <DialogDescription>{warningText}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <p className="text-sm text-muted-foreground mb-2">
              请输入 <span className="font-mono font-semibold text-foreground">{targetName}</span> 以确认删除：
            </p>
            <input
              className="w-full p-2 border rounded text-sm font-mono"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={targetName}
              autoFocus
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>取消</DialogClose>
          <Button
            variant="destructive"
            onClick={handleSubmit}
            disabled={!matched || submitting}
          >
            {submitting ? '删除中...' : '删除'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
