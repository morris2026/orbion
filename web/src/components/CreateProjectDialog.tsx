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
import type { CreateProjectRequest, ProjectListItem, ThreadListItem } from '@/types/api'

interface CreateProjectDialogProps {
  open: boolean
  onClose: () => void
  onCreateProject: (req: CreateProjectRequest) => void
  onSelectThread: (projectId: string, threadId: string) => void
}

export default function CreateProjectDialog({ open, onClose, onCreateProject, onSelectThread }: CreateProjectDialogProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const canSubmit = name.trim().length > 0 && !submitting

  const handleSubmit = async () => {
    if (!canSubmit) return
    setSubmitting(true)
    setError(null)
    try {
      const newProject: ProjectListItem = await apiPost('/projects', {
        name: name.trim(),
        description: description.trim() || null,
      })
      // 创建项目后自动创建默认线程
      try {
        const defaultThread: ThreadListItem = await apiPost(`/projects/${newProject.id}/threads`, {
          title: newProject.name,
          type: 'discussion',
        })
        onCreateProject({ name: name.trim(), description: description.trim() || null })
        onSelectThread(newProject.id, defaultThread.id)
        onClose()
      } catch {
        // 默认线程失败——项目已在后端存在，通知父组件但不关闭Dialog
        onCreateProject({ name: name.trim(), description: description.trim() || null })
        setError('项目创建成功，但默认线程创建失败')
      }
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
          <DialogTitle>新建项目</DialogTitle>
          <DialogDescription>创建一个新项目并自动生成默认讨论线程</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <label htmlFor="project-name" className="text-sm font-medium">项目名称</label>
            <input
              id="project-name"
              aria-label="项目名称"
              className="w-full mt-1 p-2 border rounded text-sm"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="输入项目名称"
            />
          </div>
          <div>
            <label htmlFor="project-desc" className="text-sm font-medium">项目描述（可选）</label>
            <textarea
              id="project-desc"
              aria-label="项目描述"
              className="w-full mt-1 p-2 border rounded text-sm"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="输入项目描述"
              rows={3}
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