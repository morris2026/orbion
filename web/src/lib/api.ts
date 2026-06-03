/** API调用封装层 — fetch wrapper with JWT header injection */

import { getToken } from './auth'

class ApiError extends Error {
  status: number
  constructor(status: number, statusText: string) {
    super(`API错误: ${status} ${statusText}`)
    this.status = status
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

export async function apiPost<T = unknown>(path: string, body: unknown): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json', ...buildHeaders() }
  const resp = await fetch(path, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  })
  if (!resp.ok) {
    throw new ApiError(resp.status, resp.statusText)
  }
  return resp.json() as Promise<T>
}

export async function apiGet<T = unknown>(path: string): Promise<T> {
  const resp = await fetch(path, {
    method: 'GET',
    headers: buildHeaders(),
  })
  if (!resp.ok) {
    throw new ApiError(resp.status, resp.statusText)
  }
  return resp.json() as Promise<T>
}