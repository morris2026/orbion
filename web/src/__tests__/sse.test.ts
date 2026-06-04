import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createSSEConnection, disconnectSSE } from '@/lib/sse'
import * as authModule from '@/lib/auth'

class MockEventSource {
  url: string
  onopen: ((ev: Event) => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  onerror: ((ev: Event) => void) | null = null
  close = vi.fn()

  constructor(url: string) {
    this.url = url
  }
}

describe('sse.ts — SSE连接管理封装', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('创建EventSource连接到/events/stream端点并附带JWT token', () => {
    vi.stubGlobal('EventSource', MockEventSource)
    vi.spyOn(authModule, 'getToken').mockReturnValue('jwt-abc')

    const onEvent = vi.fn()
    const conn = createSSEConnection('proj-1', onEvent)

    expect(conn.url).toBe('/events/stream?project_id=proj-1&token=jwt-abc')

    vi.unstubAllGlobals()
  })

  it('无JWT token时不附带到URL', () => {
    vi.stubGlobal('EventSource', MockEventSource)
    vi.spyOn(authModule, 'getToken').mockReturnValue(null)

    const onEvent = vi.fn()
    const conn = createSSEConnection('proj-1', onEvent)

    expect(conn.url).toBe('/events/stream?project_id=proj-1')

    vi.unstubAllGlobals()
  })

  it('收到事件时调用回调并解析JSON', () => {
    vi.stubGlobal('EventSource', MockEventSource)
    vi.spyOn(authModule, 'getToken').mockReturnValue('jwt-abc')

    const onEvent = vi.fn()
    const conn = createSSEConnection('proj-1', onEvent)

    conn.onmessage!({ data: '{"event_type":"message_created","content":"hello"}' } as MessageEvent)
    expect(onEvent).toHaveBeenCalledWith({
      event_type: 'message_created',
      content: 'hello',
    })

    vi.unstubAllGlobals()
  })

  it('disconnectSSE关闭连接', () => {
    vi.stubGlobal('EventSource', MockEventSource)
    vi.spyOn(authModule, 'getToken').mockReturnValue('jwt-abc')

    const onEvent = vi.fn()
    const conn = createSSEConnection('proj-1', onEvent)
    disconnectSSE(conn)

    expect(conn.close).toHaveBeenCalled()

    vi.unstubAllGlobals()
  })
})