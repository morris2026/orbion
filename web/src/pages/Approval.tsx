import { useState, useEffect } from 'react'
import { apiGet, apiPost } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

interface PendingUser {
  user_id: string
  username: string
  display_name: string
  status: string
  created_at: string
}

interface ApprovalResult {
  user_id: string
  username: string
  status: string
}

export default function Approval() {
  const [pendingUsers, setPendingUsers] = useState<PendingUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const fetchPending = async () => {
    setLoading(true)
    setError('')
    try {
      const users = await apiGet<PendingUser[]>('/auth/users/pending')
      setPendingUsers(users)
    } catch {
      setPendingUsers([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchPending()
  }, [])

  const handleApprove = async (userId: string) => {
    setError('')
    try {
      await apiPost<ApprovalResult>(`/auth/users/${userId}/approve`, {})
      await fetchPending()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '审批操作失败')
    }
  }

  const handleReject = async (userId: string) => {
    setError('')
    try {
      await apiPost<ApprovalResult>(`/auth/users/${userId}/reject`, { reason: '' })
      await fetchPending()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '拒绝操作失败')
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-background">
        <p className="text-muted-foreground">加载中...</p>
      </div>
    )
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-background p-4">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle>用户审批管理</CardTitle>
        </CardHeader>
        <CardContent>
          {error && <p className="text-destructive mb-4 text-sm">{error}</p>}
          {pendingUsers.length === 0 ? (
            <p className="text-muted-foreground">暂无待审批用户</p>
          ) : (
            <div className="space-y-4">
              {pendingUsers.map((user) => (
                <div key={user.user_id} className="flex items-center justify-between p-3 rounded-lg border">
                  <div>
                    <p className="font-medium">{user.username}</p>
                    <p className="text-sm text-muted-foreground">{user.display_name}</p>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => handleApprove(user.user_id)}>通过</Button>
                    <Button size="sm" variant="destructive" onClick={() => handleReject(user.user_id)}>拒绝</Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}