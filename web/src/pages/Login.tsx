import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { setToken } from '@/lib/auth'
import { apiPost, ApiError } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

type ViewMode = 'login' | 'register' | 'pending' | 'rejected'

const USERNAME_PATTERN = /^[a-zA-Z0-9_]+$/

export default function Login() {
  const navigate = useNavigate()
  const [mode, setMode] = useState<ViewMode>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [error, setError] = useState('')
  const [validationErrors, setValidationErrors] = useState<string[]>([])
  const [loading, setLoading] = useState(false)

  const validateRegister = (): string[] => {
    const errors: string[] = []
    if (username.length < 3) errors.push('用户名至少3个字符')
    if (!USERNAME_PATTERN.test(username)) errors.push('用户名只能包含字母、数字或下划线')
    if (password.length < 8) errors.push('密码长度不足8个字符')
    return errors
  }

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setValidationErrors([])
    setLoading(true)
    try {
      const resp = await apiPost<{ access_token: string }>('/auth/login', { username, password })
      setToken(resp.access_token)
      navigate('/workspace')
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 403 && err.detail.toLowerCase().includes('pending')) {
          setMode('pending')
        } else if (err.status === 403 && err.detail.toLowerCase().includes('rejected')) {
          setMode('rejected')
        } else {
          setError(err.detail)
        }
      } else {
        setError('登录失败')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleRegister = async (e: FormEvent) => {
    e.preventDefault()
    const errors = validateRegister()
    setValidationErrors(errors)
    if (errors.length > 0) return

    setError('')
    setLoading(true)
    try {
      const resp = await apiPost<{
        status: string
        access_token: string | null
        message: string
      }>('/auth/register', { username, password, display_name: displayName || username })

      if (resp.status === 'active' && resp.access_token) {
        setToken(resp.access_token)
        navigate('/workspace')
      } else {
        setMode('pending')
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.detail)
      } else {
        setError('注册失败')
      }
    } finally {
      setLoading(false)
    }
  }

  const resetForm = () => {
    setMode('login')
    setUsername('')
    setPassword('')
    setDisplayName('')
    setError('')
    setValidationErrors([])
  }

  if (mode === 'pending') {
    return (
      <div className="flex items-center justify-center min-h-screen bg-background">
        <Card className="w-full max-w-sm">
          <CardHeader>
            <CardTitle>等待管理员审批</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground">您的注册申请已提交，正在等待管理员审批。审批通过后您将可以登录使用。</p>
            <Button className="mt-4 w-full" onClick={resetForm}>返回登录</Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (mode === 'rejected') {
    return (
      <div className="flex items-center justify-center min-h-screen bg-background">
        <Card className="w-full max-w-sm">
          <CardHeader>
            <CardTitle>注册申请被拒绝</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground">您的注册申请已被管理员拒绝，请联系管理员或重新注册。</p>
            <Button className="mt-4 w-full" onClick={resetForm}>返回登录</Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-background">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>{mode === 'login' ? '登录 Orbion' : '注册 Orbion'}</CardTitle>
        </CardHeader>
        <CardContent>
          {validationErrors.length > 0 && (
            <ul className="text-destructive mb-4 text-sm list-disc pl-4">
              {validationErrors.map((msg) => <li key={msg}>{msg}</li>)}
            </ul>
          )}
          {error && <p className="text-destructive mb-4 text-sm">{error}</p>}
          <form onSubmit={mode === 'login' ? handleLogin : handleRegister} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username">用户名</Label>
              <Input id="username" value={username} onChange={(e) => setUsername(e.target.value)} />
              {mode === 'register' && <p className="text-xs text-muted-foreground">3-32个字符，仅限字母、数字、下划线</p>}
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">密码</Label>
              <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
              {mode === 'register' && <p className="text-xs text-muted-foreground">至少8个字符</p>}
            </div>
            {mode === 'register' && (
              <div className="space-y-2">
                <Label htmlFor="displayName">显示名称（可选）</Label>
                <Input id="displayName" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
                <p className="text-xs text-muted-foreground">不填则使用用户名</p>
              </div>
            )}
            <Button type="submit" className="w-full" disabled={loading}>
              {mode === 'login' ? '登录' : '提交注册'}
            </Button>
          </form>
          <div className="mt-4 text-center">
            {mode === 'login' ? (
              <Button variant="ghost" onClick={() => setMode('register')}>注册</Button>
            ) : (
              <Button variant="ghost" onClick={() => setMode('login')}>返回登录</Button>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}