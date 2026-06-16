import { useState } from 'react'
import { KeyRoundIcon } from 'lucide-react'
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
import type { ProjectListItem, AddRepoRequest } from '@/types/api'
import CredentialsDialog from '@/components/CredentialsDialog'

interface CreateProjectDialogProps {
  open: boolean
  onClose: () => void
  onCreateProject: (project: ProjectListItem) => void
  onSelectThread: (projectId: string, threadId: string) => void
}

export default function CreateProjectDialog({ open, onClose, onCreateProject, onSelectThread }: CreateProjectDialogProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [repo, setRepo] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showCredentials, setShowCredentials] = useState(false)

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

      // 初始化仓库（不等待完成，clone 在后台进行，结果通过系统消息推送到聊天框）
      const repoValue = repo.trim()
      if (repoValue) {
        const isUrl = /^(https?:\/\/|git@|ssh:\/\/)/.test(repoValue)
        const body: AddRepoRequest = isUrl ? { url: repoValue } : { name: repoValue }
        apiPost(`/projects/${newProject.id}/repos`, body).catch(() => { /* 错误通过系统消息通知 */ })
      }

      onCreateProject(newProject)
      if (newProject.default_thread_id) {
        onSelectThread(newProject.id, newProject.default_thread_id)
      }
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
          <DialogTitle>新建项目</DialogTitle>
          <DialogDescription>创建一个新项目，后端将自动创建默认讨论线程</DialogDescription>
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
          <div>
            <div className="flex items-center justify-between">
              <label htmlFor="project-repo" className="text-sm font-medium">仓库（可选）</label>
              <button
                className="text-muted-foreground hover:text-foreground"
                onClick={() => setShowCredentials(true)}
                aria-label="管理凭据"
                type="button"
              >
                <KeyRoundIcon className="h-4 w-4" />
              </button>
            </div>
            <input
              id="project-repo"
              aria-label="仓库"
              className="w-full mt-1 p-2 border rounded text-sm"
              value={repo}
              onChange={(e) => setRepo(e.target.value)}
              placeholder="Git 仓库 URL 或目录名"
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>取消</DialogClose>
          <Button onClick={handleSubmit} disabled={!canSubmit}>{submitting ? '创建中...' : '创建'}</Button>
        </DialogFooter>
      </DialogContent>
      <CredentialsDialog open={showCredentials} onClose={() => setShowCredentials(false)} />
    </Dialog>
  )
}