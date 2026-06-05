import { useState } from 'react'
import type { MessageResponse } from '@/types/api'
import MessageItem from './MessageItem'
import { Button } from '@/components/ui/button'

interface DiscussionPanelProps {
  messages: MessageResponse[]
  onSendMessage: (opts: { content: string; request_summary?: boolean }) => void
}

export default function DiscussionPanel({ messages, onSendMessage }: DiscussionPanelProps) {
  const [input, setInput] = useState('')

  const handleSend = () => {
    if (!input.trim()) return
    onSendMessage({ content: input.trim() })
    setInput('')
  }

  const handleRequestSummary = () => {
    const content = input.trim() || '请总结当前讨论要点'
    onSendMessage({ content, request_summary: true })
    setInput('')
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        {messages.map((msg) => (
          <MessageItem key={msg.id} message={msg} />
        ))}
      </div>
      <div className="p-4 border-t flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="输入消息..."
          className="flex-1 px-3 py-1 text-sm border rounded bg-background"
        />
        <Button variant="default" size="sm" onClick={handleSend}>发送</Button>
        <Button variant="outline" size="sm" onClick={handleRequestSummary}>请求总结</Button>
      </div>
    </div>
  )
}