import type { MessageResponse } from '@/types/api'

interface MessageItemProps {
  message: MessageResponse
}

export default function MessageItem({ message }: MessageItemProps) {
  const isAgent = message.participant_type === 'agent'

  return (
    <div
      data-testid={`message-${message.id}`}
      data-participant-type={message.participant_type}
      className={`p-2 rounded ${isAgent ? 'bg-blue-50 border border-blue-200' : 'bg-white'}`}
    >
      <div className="flex items-center gap-1 mb-1">
        <span className={`text-xs font-medium ${isAgent ? 'text-blue-700' : 'text-foreground'}`}>
          {isAgent && '🤖 '}{message.display_name}
        </span>
        <span className="text-xs text-muted-foreground">
          {new Date(message.created_at).toLocaleString()}
        </span>
      </div>
      <p className={`text-sm ${isAgent ? 'text-blue-800' : 'text-foreground'}`}>
        {message.content}
      </p>
    </div>
  )
}