import type { MessageResponse } from '@/types/api'

interface MessageBubbleProps {
  message: MessageResponse
  currentUserId: string
}

/** 业界标准时间格式：今天→时间，昨天→"昨天 时间"，更早→日期+时间 */
function formatTimestamp(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today.getTime() - 86400000)
  const msgDay = new Date(date.getFullYear(), date.getMonth(), date.getDate())

  const time = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

  if (msgDay.getTime() === today.getTime()) return time
  if (msgDay.getTime() === yesterday.getTime()) return `昨天 ${time}`
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${time}`
}

export default function MessageBubble({ message, currentUserId }: MessageBubbleProps) {
  const isSelf = message.participant_id === currentUserId && message.participant_type === 'human'
  const isAgent = message.participant_type === 'agent'
  const isSystem = message.participant_type === 'system'

  const avatarContent = isAgent ? '🤖' : isSystem ? '⚙️' : message.display_name.charAt(0)

  // 自己：右对齐蓝色泡泡，名字和时间右对齐（时间→名字）
  // 别人：左对齐浅色泡泡，名字和时间左对齐（名字→时间）
  // Agent：左对齐浅蓝泡泡+蓝色边框，名字和时间左对齐
  // System：左对齐灰色泡泡，名字和时间左对齐
  const align = isSelf ? 'right' : 'left'
  const participantType = isSelf ? 'self' : isAgent ? 'agent' : isSystem ? 'system' : 'other'

  return (
    <div
      data-testid={`msg-${message.id}`}
      className={`flex gap-2 ${isSelf ? 'justify-end' : 'justify-start'}`}
    >
      {/* 头像：自己时在右侧，别人/Agent时在左侧 */}
      {!isSelf && (
        <div
          data-testid={`avatar-${message.id}`}
          className="w-8 h-8 rounded-full bg-muted flex items-center justify-center text-xs shrink-0"
        >
          {avatarContent}
        </div>
      )}

      <div className={`min-w-0 flex flex-col ${isSelf ? 'order-first items-end' : 'items-start'}`}>
        <div className={`flex gap-1 text-xs text-muted-foreground mb-1`}>
          {isSelf ? (
            <>
              <span>{formatTimestamp(message.created_at)}</span>
              <span>{message.display_name}</span>
            </>
          ) : (
            <>
              <span>{message.display_name}</span>
              <span>{formatTimestamp(message.created_at)}</span>
            </>
          )}
        </div>

        <div
          data-testid={`bubble-${message.id}`}
          data-align={align}
          data-participant-type={participantType}
          className={`px-3 py-2 rounded-lg w-fit max-w-[70%] ${
            isSelf
              ? 'bg-blue-500 text-white'
              : isAgent
                ? 'bg-blue-50 border border-blue-200 text-blue-800'
                : isSystem
                  ? 'bg-gray-50 border border-gray-200 text-gray-700'
                  : 'bg-gray-100 text-foreground'
          }`}
        >
          <p className="text-sm whitespace-pre-wrap break-words [word-break:break-word]">{message.content}</p>
        </div>
      </div>

      {/* 自己的头像在右侧 */}
      {isSelf && (
        <div
          data-testid={`avatar-${message.id}`}
          className="w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center text-xs text-white shrink-0"
        >
          {avatarContent}
        </div>
      )}
    </div>
  )
}