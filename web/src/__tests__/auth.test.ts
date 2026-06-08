import { describe, it, expect, beforeEach } from 'vitest'
import {
  getToken, setToken, clearToken, isAuthenticated,
  decodeToken, isTokenExpired, getIsAdmin,
} from '@/lib/auth'

/** 辅助：创建简单JWT（base64编码payload，不含签名） */
function createJWT(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  const signature = btoa('fake-signature')
  return `${header}.${body}.${signature}`
}

describe('auth.ts — JWT存储与解码', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  describe('JWT存储', () => {
    it('存储后可读取JWT', () => {
      setToken('test-jwt-token')
      expect(getToken()).toBe('test-jwt-token')
    })

    it('清除后JWT为空', () => {
      setToken('test-jwt-token')
      clearToken()
      expect(getToken()).toBeNull()
    })

    it('未存储时isAuthenticated为false', () => {
      expect(isAuthenticated()).toBe(false)
    })

    it('存储后isAuthenticated为true', () => {
      setToken('test-jwt-token')
      expect(isAuthenticated()).toBe(true)
    })

    it('清除后isAuthenticated为false', () => {
      setToken('test-jwt-token')
      clearToken()
      expect(isAuthenticated()).toBe(false)
    })
  })

  describe('decodeToken', () => {
    it('解码JWT返回payload对象', () => {
      const token = createJWT({ sub: 'user-1', username: 'admin', is_admin: true })
      setToken(token)
      const payload = decodeToken()
      expect(payload).not.toBeNull()
      expect(payload!.sub).toBe('user-1')
      expect(payload!.username).toBe('admin')
      expect(payload!.is_admin).toBe(true)
    })

    it('无JWT时返回null', () => {
      expect(decodeToken()).toBeNull()
    })

    it('格式错误的JWT返回null', () => {
      setToken('not-a-valid-jwt')
      expect(decodeToken()).toBeNull()
    })
  })

  describe('isTokenExpired', () => {
    it('未过期的JWT返回false', () => {
      const exp = Math.floor(Date.now() / 1000) + 3600
      const token = createJWT({ sub: 'user-1', exp })
      setToken(token)
      expect(isTokenExpired()).toBe(false)
    })

    it('已过期的JWT返回true', () => {
      const exp = Math.floor(Date.now() / 1000) - 3600
      const token = createJWT({ sub: 'user-1', exp })
      setToken(token)
      expect(isTokenExpired()).toBe(true)
    })

    it('无JWT时返回true', () => {
      expect(isTokenExpired()).toBe(true)
    })
  })

  describe('getIsAdmin', () => {
    it('is_admin=true时返回true', () => {
      const token = createJWT({ sub: 'user-1', username: 'admin', is_admin: true })
      setToken(token)
      expect(getIsAdmin()).toBe(true)
    })

    it('is_admin=false时返回false', () => {
      const token = createJWT({ sub: 'user-2', username: 'member', is_admin: false })
      setToken(token)
      expect(getIsAdmin()).toBe(false)
    })

    it('无JWT时返回false', () => {
      expect(getIsAdmin()).toBe(false)
    })

    it('payload不含is_admin字段时返回false', () => {
      const token = createJWT({ sub: 'user-3', username: 'viewer' })
      setToken(token)
      expect(getIsAdmin()).toBe(false)
    })
  })
})