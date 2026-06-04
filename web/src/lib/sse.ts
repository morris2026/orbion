/** SSE连接管理封装 — EventSource wrapper with JWT auth and typed event parsing */

import { getToken } from './auth'
import type { SSEEvent } from '@/types/sse'

export interface SSERawEvent {
  event_type: string
  [key: string]: unknown
}

export function createSSEConnection(
  projectId: string,
  onEvent: (event: SSERawEvent) => void,
): EventSource {
  const token = getToken()
  const url = `/events/stream?project_id=${projectId}${token ? `&token=${token}` : ''}`
  const es = new EventSource(url)
  es.onmessage = (msg: MessageEvent) => {
    try {
      const parsed = JSON.parse(msg.data as string) as SSERawEvent
      onEvent(parsed)
    } catch {
      // 非JSON数据忽略
    }
  }
  return es
}

export function disconnectSSE(es: EventSource): void {
  es.close()
}