import { useState, useEffect, useRef, useCallback } from 'react'
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
import { ScrollArea } from '@/components/ui/scroll-area'
import { apiGet, apiPost, ApiError } from '@/lib/api'
import type { UserItem, AddMemberRequest } from '@/types/api'

interface AddMemberDialogProps {
  open: boolean
  projectId: string
  onClose: () => void
  onAddMember: (projectId: string, req: AddMemberRequest) => void
}

const ROLES: AddMemberRequest['role'][] = ['owner', 'admin', 'member', 'viewer']

export default function AddMemberDialog({ open, projectId, onClose, onAddMember }: AddMemberDialogProps) {
  const [allUsers, setAllUsers] = useState<UserItem[]>([])
  const [searchResults, setSearchResults] = useState<UserItem[]>([])
  const [search, setSearch] = useState('')
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null)
  const [role, setRole] = useState<AddMemberRequest['role']>('member')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const displayUsers = search.trim().length > 0 ? searchResults : allUsers
  const canSubmit = selectedUserId !== null && !submitting

  // Dialog打开时加载全量列表+重置状态
  useEffect(() => {
    if (!open) return
    setSearch('')
    setSelectedUserId(null)
    setRole('member')
    setError(null)
    setSearchResults([])
    apiGet<UserItem[]>('/auth/users').then(setAllUsers).catch(() => setAllUsers([]))
  }, [open])

  // 搜索debounce：输入稳定300ms后才触发搜索API
  const doSearch = useCallback((term: string) => {
    apiGet<UserItem[]>('/auth/users/search', { username: term })
      .then(setSearchResults)
      .catch(() => {
        // 搜索失败时回退显示全量列表
        setSearchResults(allUsers)
      })
  }, [allUsers])

  useEffect(() => {
    if (!open || search.trim().length === 0) {
      setSearchResults([])
      return
    }
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    debounceTimer.current = setTimeout(() => {
      doSearch(search.trim())
    }, 300)
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current)
    }
  }, [open, search, doSearch])

  const handleSubmit = async () => {
    if (!canSubmit || !selectedUserId) return
    setSubmitting(true)
    setError(null)
    try {
      await apiPost(`/projects/${projectId}/members`, { user_id: selectedUserId, role })
      onAddMember(projectId, { user_id: selectedUserId, role })
      onClose()
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.status === 409) {
          setError('添加失败：成员已存在')
        } else {
          setError(`添加失败：${e.detail}`)
        }
      } else {
        setError('添加失败')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>添加成员</DialogTitle>
          <DialogDescription>搜索并选择用户，分配项目角色</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <input
            id="member-search"
            aria-label="搜索用户名"
            className="w-full p-2 border rounded text-sm"
            placeholder="搜索用户名"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setSelectedUserId(null) }}
          />
          <ScrollArea className="h-[200px]">
            {displayUsers.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">
                {search.trim().length > 0 ? '无匹配用户' : '暂无用户'}
              </p>
            ) : (
              <ul className="space-y-1">
                {displayUsers.map((u) => (
                  <li
                    key={u.user_id}
                    className={`p-2 rounded cursor-pointer text-sm ${selectedUserId === u.user_id ? 'bg-primary/10 font-medium' : 'hover:bg-muted'}`}
                    onClick={() => setSelectedUserId(u.user_id)}
                  >
                    {u.display_name}
                  </li>
                ))}
              </ul>
            )}
          </ScrollArea>
          <div>
            <label htmlFor="member-role" className="text-sm font-medium">角色</label>
            <select
              id="member-role"
              className="w-full mt-1 p-2 border rounded text-sm"
              value={role}
              onChange={(e) => setRole(e.target.value as AddMemberRequest['role'])}
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>取消</DialogClose>
          <Button onClick={handleSubmit} disabled={!canSubmit}>{submitting ? '添加中...' : '添加'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}