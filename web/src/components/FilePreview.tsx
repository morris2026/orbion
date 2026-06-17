import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface FilePreviewProps {
  content: string
}

export function FilePreview({ content }: FilePreviewProps) {
  return (
    <div className="h-full overflow-auto p-4 prose dark:prose-invert max-w-none" data-testid="file-preview">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  )
}
