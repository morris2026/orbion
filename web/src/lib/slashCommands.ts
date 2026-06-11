/** 斜杠命令解析 — /summarize、/help 及普通消息的区分 */

export interface ParsedSummarize {
  request_summary: true
  content: string
}

export interface ParsedHelp {
  show_help: true
}

export interface ParsedNormal {
  request_summary: false
  content: string
}

export type ParsedMessage = ParsedSummarize | ParsedHelp | ParsedNormal

export function parseMessage(input: string): ParsedMessage {
  const trimmed = input.trim()

  if (trimmed.startsWith('/summarize')) {
    const rest = trimmed.slice('/summarize'.length).trim()
    return {
      request_summary: true,
      content: rest || '请总结当前讨论要点',
    }
  }

  if (trimmed === '/help') {
    return { show_help: true }
  }

  return {
    request_summary: false,
    content: trimmed,
  }
}