import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface FilePreviewProps {
  content: string
  onClose: () => void
}

export function FilePreview({ content, onClose }: FilePreviewProps) {
  return (
    <div className="h-full flex flex-col border-l" data-testid="file-preview">
      <div className="flex items-center justify-between px-3 py-1 border-b bg-muted/30">
        <span className="text-xs text-muted-foreground">预览</span>
        <button
          className="text-xs text-muted-foreground hover:text-foreground"
          onClick={onClose}
          aria-label="关闭预览面板"
        >
          ✕
        </button>
      </div>
      <div className="flex-1 overflow-auto p-4 prose prose-sm dark:prose-invert max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>
    </div>
  )
}
