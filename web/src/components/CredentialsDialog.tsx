import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogClose,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { apiGet, apiPost, apiDelete, ApiError } from '@/lib/api'
import type { Credential, CreateCredentialRequest } from '@/types/api'

interface CredentialsDialogProps {
  open: boolean
  onClose: () => void
}

export default function CredentialsDialog({ open, onClose }: CredentialsDialogProps) {
  const [credentials, setCredentials] = useState<Credential[]>([])
  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [token, setToken] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      loadCredentials()
      setShowForm(false)
      setName('')
      setToken('')
      setError(null)
    }
  }, [open])

  const loadCredentials = async () => {
    try {
      const data = await apiGet<Credential[]>('/users/me/credentials')
      setCredentials(data)
    } catch {
      setCredentials([])
    }
  }

  const handleCreate = async () => {
    if (!name.trim() || !token.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      const body: CreateCredentialRequest = { type: 'github', name: name.trim(), token: token.trim() }
      await apiPost('/users/me/credentials', body)
      setName('')
      setToken('')
      setShowForm(false)
      await loadCredentials()
    } catch (e) {
      if (e instanceof ApiError) {
        setError(`添加失败：${e.detail}`)
      } else {
        setError('添加失败')
      }
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await apiDelete(`/users/me/credentials/${id}`)
      await loadCredentials()
    } catch {
      setError('删除失败')
    }
  }

  const canSubmit = name.trim().length > 0 && token.trim().length > 0 && !submitting

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Git 凭据</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          {credentials.length === 0 && !showForm && (
            <p className="text-sm text-muted-foreground">暂无凭据，点击下方按钮添加</p>
          )}
          {credentials.map((c) => (
            <div key={c.id} className="flex items-center justify-between p-2 border rounded">
              <div className="flex items-center gap-2">
                <span className="text-xs px-1.5 py-0.5 rounded bg-muted">{c.type}</span>
                <span className="text-sm">{c.name}</span>
              </div>
              <button
                className="text-xs text-muted-foreground hover:text-destructive"
                onClick={() => handleDelete(c.id)}
                aria-label={`删除 ${c.name}`}
              >
                删除
              </button>
            </div>
          ))}
          {showForm && (
            <div className="space-y-2 p-2 border rounded">
              <div>
                <label htmlFor="cred-name" className="text-sm font-medium">名称</label>
                <input
                  id="cred-name"
                  className="w-full mt-1 p-2 border rounded text-sm"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="我的 GitHub"
                />
              </div>
              <div>
                <label htmlFor="cred-token" className="text-sm font-medium">Token</label>
                <input
                  id="cred-token"
                  type="password"
                  className="w-full mt-1 p-2 border rounded text-sm"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="ghp_xxxx"
                />
              </div>
              {error && <p className="text-sm text-destructive">{error}</p>}
              <div className="flex gap-2">
                <Button size="sm" onClick={handleCreate} disabled={!canSubmit}>
                  {submitting ? '添加中...' : '保存'}
                </Button>
                <Button size="sm" variant="outline" onClick={() => { setShowForm(false); setError(null) }}>取消</Button>
              </div>
            </div>
          )}
          {!showForm && (
            <Button size="sm" variant="outline" onClick={() => setShowForm(true)}>添加凭据</Button>
          )}
        </div>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>关闭</DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
