/** SSE连接管理封装 — EventSource wrapper with JWT auth and typed event parsing */

import { getToken } from './auth'

export interface SSERawEvent {
  event_type: string
  [key: string]: unknown
}

/** 后端SSE推送的named event类型列表 */
const SSE_EVENT_TYPES = [
  'message_created',
  'summary_generated',
  'plan_proposed',
  'plan_approved',
  'plan_rejected',
  'output_generated',
  'output_approved',
  'revision_requested',
  'member_added',
]

export function createSSEConnection(
  projectId: string,
  onEvent: (event: SSERawEvent) => void,
): EventSource {
  const token = getToken()
  const url = `/events/stream?project_id=${projectId}${token ? `&token=${token}` : ''}`
  const es = new EventSource(url)

  // 后端推送named events（event: message_created等），必须用addEventListener接收
  // onmessage只接收无名事件（缺省event: message类型），不适用于named events
  for (const eventType of SSE_EVENT_TYPES) {
    es.addEventListener(eventType, (msg: MessageEvent) => {
      try {
        const parsed = JSON.parse(msg.data as string) as Record<string, unknown>
        onEvent({ ...parsed, event_type: eventType })
      } catch {
        // 非JSON数据忽略
      }
    })
  }

  return es
}

export function disconnectSSE(es: EventSource): void {
  es.close()
}