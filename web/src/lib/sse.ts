/** SSE连接管理封装 — EventSource wrapper for real-time event stream */

export interface SSEEvent {
  event_type: string
  [key: string]: unknown
}

export function createSSEConnection(
  projectId: string,
  onEvent: (event: SSEEvent) => void,
): EventSource {
  const es = new EventSource(`/events/stream?project_id=${projectId}`)
  es.onmessage = (msg: MessageEvent) => {
    try {
      const parsed = JSON.parse(msg.data as string) as SSEEvent
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