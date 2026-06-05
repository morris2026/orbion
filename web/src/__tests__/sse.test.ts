import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createSSEConnection, disconnectSSE } from '@/lib/sse'
import * as authModule from '@/lib/auth'

class MockEventSource {
  url: string
  onopen: ((ev: Event) => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  onerror: ((ev: Event) => void) | null = null
  close = vi.fn()
  private _listeners: Map<string, EventListener[]> = new Map()

  constructor(url: string) {
    this.url = url
  }

  addEventListener(type: string, listener: EventListener) {
    if (!this._listeners.has(type)) {
      this._listeners.set(type, [])
    }
    this._listeners.get(type)!.push(listener)
  }

  /** 模拟后端推送named event */
  emit(type: string, data: string) {
    const listeners = this._listeners.get(type) ?? []
    const msg = new MessageEvent(type, { data })
    for (const listener of listeners) {
      listener(msg)
    }
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

  it('named event触发addEventListener回调并解析JSON+注入event_type', () => {
    vi.stubGlobal('EventSource', MockEventSource)
    vi.spyOn(authModule, 'getToken').mockReturnValue('jwt-abc')

    const onEvent = vi.fn()
    const conn = createSSEConnection('proj-1', onEvent) as MockEventSource

    // 模拟后端推送message_created named event
    conn.emit('message_created', '{"message_id":"m1","content":"hello"}')
    expect(onEvent).toHaveBeenCalledWith({
      event_type: 'message_created',
      message_id: 'm1',
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