import { describe, it, expect, beforeEach } from 'vitest'
import { getToken, setToken, clearToken, isAuthenticated } from '@/lib/auth'

describe('auth.ts — JWT存储封装', () => {
  beforeEach(() => {
    localStorage.clear()
  })

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