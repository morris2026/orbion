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
import { apiPost, ApiError } from '@/lib/api'
import type { CreateThreadRequest } from '@/types/api'

interface CreateThreadDialogProps {
  open: boolean
  projectId: string
  onClose: () => void
  onCreateThread: (projectId: string, req: CreateThreadRequest) => void
}

export default function CreateThreadDialog({ open, projectId, onClose, onCreateThread }: CreateThreadDialogProps) {
  const [title, setTitle] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const canSubmit = title.trim().length > 0 && !submitting

  const handleSubmit = async () => {
    if (!canSubmit) return
    setSubmitting(true)
    setError(null)
    try {
      await apiPost(`/projects/${projectId}/threads`, {
        title: title.trim(),
        type: 'discussion',
      })
      onCreateThread(projectId, { title: title.trim(), type: 'discussion' })
      onClose()
    } catch (e) {
      if (e instanceof ApiError) {
        setError(`创建失败：${e.detail}`)
      } else {
        setError('创建失败')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>新建线程</DialogTitle>
          <DialogDescription>在当前项目下创建一个新的讨论线程</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <label htmlFor="thread-title" className="text-sm font-medium">线程标题</label>
            <input
              id="thread-title"
              aria-label="线程标题"
              className="w-full mt-1 p-2 border rounded text-sm"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="输入线程标题"
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>取消</DialogClose>
          <Button onClick={handleSubmit} disabled={!canSubmit}>{submitting ? '创建中...' : '创建'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}