/** API调用封装层 — fetch wrapper with JWT header injection and error detail parsing */

import { getToken } from './auth'

export class ApiError extends Error {
  status: number
  detail: string
  constructor(status: number, detail: string) {
    super(`API错误: ${status} ${detail}`)
    this.status = status
    this.detail = detail
  }
}

function buildHeaders(): Record<string, string> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}

async function parseErrorDetail(resp: Response): Promise<string> {
  let detail = resp.statusText
  try {
    const errorBody = await resp.json()
    if (typeof errorBody?.detail === 'string') detail = errorBody.detail
  } catch {
    // 响应体解析失败，使用statusText
  }
  return detail
}

export async function apiPost<T = unknown>(path: string, body: unknown): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json', ...buildHeaders() }
  const resp = await fetch(path, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  })
  if (!resp.ok) {
    throw new ApiError(resp.status, await parseErrorDetail(resp))
  }
  return resp.json() as Promise<T>
}

export async function apiGet<T = unknown>(path: string, params?: Record<string, string>): Promise<T> {
  let url = path
  if (params && Object.keys(params).length > 0) {
    url = `${path}?${new URLSearchParams(params).toString()}`
  }
  const resp = await fetch(url, {
    method: 'GET',
    headers: buildHeaders(),
  })
  if (!resp.ok) {
    throw new ApiError(resp.status, await parseErrorDetail(resp))
  }
  return resp.json() as Promise<T>
}

export async function apiDelete<T = unknown>(path: string): Promise<T> {
  const resp = await fetch(path, {
    method: 'DELETE',
    headers: buildHeaders(),
  })
  if (!resp.ok) {
    throw new ApiError(resp.status, await parseErrorDetail(resp))
  }
  return resp.json() as Promise<T>
}

export async function apiPut<T = unknown>(path: string, body: unknown): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json', ...buildHeaders() }
  const resp = await fetch(path, {
    method: 'PUT',
    headers,
    body: JSON.stringify(body),
  })
  if (!resp.ok) {
    throw new ApiError(resp.status, await parseErrorDetail(resp))
  }
  return resp.json() as Promise<T>
}