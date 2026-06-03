import { describe, it, expect, vi } from 'vitest'
import { apiPost, apiGet } from '@/lib/api'

describe('api.ts — API调用封装层', () => {
  it('apiPost发送POST请求并返回响应数据', async () => {
    const mockResponse = { status: 'active', access_token: 'jwt-123' }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockResponse),
    }))

    const result = await apiPost('/auth/login', { username: 'admin', password: 'pass' })
    expect(result).toEqual(mockResponse)
    expect(fetch).toHaveBeenCalledWith('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'admin', password: 'pass' }),
    })

    vi.unstubAllGlobals()
  })

  it('apiGet发送GET请求并返回响应数据', async () => {
    const mockResponse = [{ id: 'proj-1', name: 'Test Project' }]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockResponse),
    }))

    const result = await apiGet('/projects')
    expect(result).toEqual(mockResponse)
    expect(fetch).toHaveBeenCalledWith('/projects', {
      method: 'GET',
      headers: {},
    })

    vi.unstubAllGlobals()
  })

  it('apiGet携带Authorization header当JWT存在', async () => {
    localStorage.setItem('orbion_token', 'jwt-123')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    }))

    await apiGet('/projects')
    expect(fetch).toHaveBeenCalledWith('/projects', {
      method: 'GET',
      headers: { Authorization: 'Bearer jwt-123' },
    })

    localStorage.clear()
    vi.unstubAllGlobals()
  })

  it('请求失败时抛出错误', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      statusText: 'Forbidden',
    }))

    await expect(apiGet('/projects')).rejects.toThrow()

    vi.unstubAllGlobals()
  })
})