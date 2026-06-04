/** JWT存储封装 — localStorage读写管理与JWT解析 */

const TOKEN_KEY = 'orbion_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

export function isAuthenticated(): boolean {
  return getToken() !== null
}

/** 解析JWT payload部分（不验证签名，仅用于读取claims） */
export function decodeToken(): Record<string, unknown> | null {
  const token = getToken()
  if (!token) return null
  const parts = token.split('.')
  if (parts.length !== 3) return null
  try {
    // JWT使用Base64url编码，需转换为标准Base64再解码
    const base64url = parts[1]
    const base64 = base64url.replace(/-/g, '+').replace(/_/g, '/')
    const padded = base64 + '='.repeat((4 - base64.length % 4) % 4)
    const payload = atob(padded)
    return JSON.parse(payload)
  } catch {
    return null
  }
}

/** 检查JWT是否已过期 */
export function isTokenExpired(): boolean {
  const payload = decodeToken()
  if (!payload) return true
  if (typeof payload.exp !== 'number') return true
  // exp是秒级时间戳，需乘1000与Date.now()比较
  return payload.exp * 1000 < Date.now()
}

/** 获取当前用户是否为管理员 */
export function getIsAdmin(): boolean {
  const payload = decodeToken()
  if (!payload) return false
  return payload.is_admin === true
}