import { describe, it, expect } from 'vitest'
import { parseMessage } from '@/lib/slashCommands'

describe('slashCommands.ts — 斜杠命令解析', () => {
  it('MVP-UI-3.4: /summarize解析为request_summary=true+固定文案', () => {
    const result = parseMessage('/summarize')
    expect(result).toEqual({ request_summary: true, content: '请总结当前讨论要点' })
  })

  it('MVP-UI-3.5: /summarize带消息内容', () => {
    const result = parseMessage('/summarize 这是观点')
    expect(result).toEqual({ request_summary: true, content: '这是观点' })
  })

  it('MVP-UI-3.6: /help解析为show_help=true', () => {
    const result = parseMessage('/help')
    expect(result).toEqual({ show_help: true })
  })

  it('MVP-UI-3.7: 普通消息不触发斜杠命令', () => {
    const result = parseMessage('你好')
    expect(result).toEqual({ request_summary: false, content: '你好' })
  })

  it('MVP-UI-3.8: 未知斜杠命令作为普通消息', () => {
    const result = parseMessage('/unknown')
    expect(result).toEqual({ request_summary: false, content: '/unknown' })
  })

  it('MVP-UI-3.9: 斜杠在消息中间不触发命令', () => {
    const result = parseMessage('你好 /summarize')
    expect(result).toEqual({ request_summary: false, content: '你好 /summarize' })
  })
})