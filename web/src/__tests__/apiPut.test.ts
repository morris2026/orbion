import { describe, it, expect, vi } from 'vitest'
import { apiPut } from '@/lib/api'

describe('MVP-RE-4.2: apiPut 函数', () => {
  it('apiPut发送PUT请求并返回响应数据', async () => {
    const mockResponse = { path: 'README.md', content: 'updated' }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockResponse),
    }))

    const result = await apiPut('/projects/p1/repos/r1/files?path=a.ts', { content: 'hello' })
    expect(result).toEqual(mockResponse)
    expect(fetch).toHaveBeenCalledWith('/projects/p1/repos/r1/files?path=a.ts', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: 'hello' }),
    })

    vi.unstubAllGlobals()
  })

  it('apiPut携带Authorization header当JWT存在', async () => {
    localStorage.setItem('orbion_token', 'jwt-456')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ path: 'a.ts', content: 'x' }),
    }))

    await apiPut('/projects/p1/repos/r1/files?path=a.ts', { content: 'x' })
    expect(fetch).toHaveBeenCalledWith('/projects/p1/repos/r1/files?path=a.ts', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer jwt-456' },
      body: JSON.stringify({ content: 'x' }),
    })

    localStorage.clear()
    vi.unstubAllGlobals()
  })

  it('apiPut请求失败时抛出ApiError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      statusText: 'Forbidden',
    }))

    await expect(apiPut('/projects/p1/repos/r1/files?path=a.ts', { content: 'x' })).rejects.toThrow()

    vi.unstubAllGlobals()
  })
})
