import { useState, useRef, useEffect, useCallback } from 'react'
import type { MessageResponse } from '@/types/api'
import MessageBubble from './MessageBubble'
import { parseMessage } from '@/lib/slashCommands'
import { Button } from '@/components/ui/button'
import { Group, Panel, Separator } from 'react-resizable-panels'

interface DiscussionPanelProps {
  messages: MessageResponse[]
  currentUserId: string
  onSendMessage: (opts: { content: string; request_summary?: boolean }) => Promise<void>
}

const MAX_MESSAGE_LENGTH = 10000

const SLASH_HELP_ITEMS = [
  { command: '/summarize', desc: '请求总结当前讨论' },
  { command: '/summarize 观点', desc: '请求总结指定内容' },
  { command: '/help', desc: '查看可用命令' },
]

export default function DiscussionPanel({ messages, currentUserId, onSendMessage }: DiscussionPanelProps) {
  const [input, setInput] = useState('')
  const [showHelp, setShowHelp] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const messagesPanelRef = useRef<HTMLDivElement>(null)

  // 拖拽分隔条时保持底部消息位置不变（VS Code终端式底部锚定）
  // Panel的elementRef指向外层div(overflow:visible)，内层div(overflow:auto)才是滚动容器
  const handleMessagesResize = useCallback(() => {
    const outer = messagesPanelRef.current
    if (!outer) return
    const inner = outer.firstElementChild as HTMLElement | null
    if (!inner) return
    const nearBottom = inner.scrollHeight - inner.scrollTop - inner.clientHeight < 50
    if (nearBottom) {
      inner.scrollTop = inner.scrollHeight - inner.clientHeight
    }
  }, [])

  // 新消息时自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const isOverLength = input.length > MAX_MESSAGE_LENGTH

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleSend = async () => {
    const trimmed = input.trim()
    if (!trimmed) return

    const parsed = parseMessage(trimmed)

    if ('show_help' in parsed) {
      setShowHelp(true)
      setInput('')
      return
    }

    setError(null)

    try {
      await onSendMessage({
        content: parsed.content,
        request_summary: parsed.request_summary ?? false,
      })
      setInput('')
    } catch {
      setError('发送失败')
    }
  }

  return (
    <Group orientation="vertical" className="h-full"
      id="discussion-panel"
      defaultLayout={{ "discussion-messages": 8, "discussion-input": 2 }}
    >
      {/* 消息区域 */}
      <Panel id="discussion-messages" minSize="60"
        className="overflow-y-auto p-4 space-y-3"
        elementRef={messagesPanelRef}
        onResize={handleMessagesResize}>
        {messages.length === 0 && (
          <p className="text-sm text-muted-foreground text-center">暂无消息</p>
        )}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} currentUserId={currentUserId} />
        ))}
        <div ref={messagesEndRef} />
      </Panel>

      {/* 可拖拽分隔条 */}
      <Separator id="discussion-separator"
        className="h-1 bg-border hover:bg-primary/30 active:bg-primary/50 transition-colors cursor-row-resize flex items-center justify-center">
        <div className="w-8 h-0.5 rounded-full bg-muted-foreground/30" />
      </Separator>

      {/* 输入区域 */}
      <Panel id="discussion-input" minSize="4.5rem" maxSize="35"
        className="flex flex-col p-3 gap-2">
        {error && (
          <p className="text-sm text-red-500 shrink-0" data-testid="send-error">{error}</p>
        )}

        {showHelp && (
          <div className="bg-muted rounded-lg p-3 text-sm space-y-1 shrink-0" data-testid="help-overlay">
            <p className="font-medium">可用命令：</p>
            {SLASH_HELP_ITEMS.map((item) => (
              <p key={item.command}>
                <span className="font-mono">{item.command}</span> — {item.desc}
              </p>
            ))}
            <Button variant="ghost" size="sm" onClick={() => setShowHelp(false)}>关闭</Button>
          </div>
        )}

        <div className="flex gap-2 items-stretch flex-1 min-h-0">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入消息，或 /summarize 请求总结..."
            className="flex-1 px-3 py-2 text-sm border rounded-md bg-background resize-none focus:outline-none focus:ring-1 focus:ring-ring"
          />
          <Button
            variant="default"
            size="sm"
            onClick={handleSend}
            disabled={!input.trim() || isOverLength}
            className="self-end shrink-0"
          >
            发送
          </Button>
        </div>
      </Panel>
    </Group>
  )
}