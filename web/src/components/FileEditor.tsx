import { useState, useEffect, useCallback, useRef } from 'react'
import { Editor, DiffEditor } from '@monaco-editor/react'
import { Group, Panel, Separator } from 'react-resizable-panels'
import { FilePreview } from '@/components/FilePreview'
import { Button } from '@/components/ui/button'
import type { editor } from 'monaco-editor'
import type { ViewMode } from '@/hooks/useFileTab'

interface FileEditorProps {
  filePath: string | null
  fileContent: string | null
  isDirty: boolean
  viewMode: ViewMode
  originalContent: string | null
  onSave: () => void
  onContentChange: (value: string) => void
  /** Monaco 加载失败时为 true，渲染降级 textarea；由 FileTab 层通过 loader.init().catch() + 超时检测 */
  monacoError?: boolean
}

export function FileEditor({
  filePath,
  fileContent,
  isDirty,
  viewMode,
  originalContent,
  onSave,
  onContentChange,
  monacoError = false,
}: FileEditorProps) {
  const [showPreview, setShowPreview] = useState(false)
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null)
  const [previewContent, setPreviewContent] = useState(fileContent ?? '')
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // 切换文件时关闭预览
  useEffect(() => {
    setShowPreview(false)
  }, [filePath, viewMode])

  // 预览内容 debounce 300ms 跟随编辑内容
  useEffect(() => {
    if (!showPreview) return
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current)
    debounceTimerRef.current = setTimeout(() => {
      setPreviewContent(fileContent ?? '')
    }, 300)
    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current)
    }
  }, [fileContent, showPreview])

  // Ctrl+S 快捷键
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault()
        onSave()
      }
    },
    [onSave]
  )

  const isMarkdown = filePath?.endsWith('.md') ?? false

  const handleEditorMount = useCallback((editor: editor.IStandaloneCodeEditor) => {
    editorRef.current = editor
    editor.updateOptions({
      unicodeHighlight: { nonBasicASCII: false, ambiguousCharacters: false, invisibleCharacters: false },
    })
  }, [])

  // 无文件时显示占位
  if (!filePath || fileContent === null) {
    return (
      <div className="h-full flex items-center justify-center text-muted-foreground text-sm">
        选择文件开始编辑
      </div>
    )
  }

  const renderEditor = () => {
    if (monacoError) {
      return (
        <textarea
          data-testid="fallback-editor"
          className="w-full h-full p-2 bg-background text-foreground font-mono text-sm resize-none border-0 outline-none"
          value={fileContent}
          onChange={(e) => onContentChange(e.target.value)}
        />
      )
    }
    if (viewMode === 'diff') {
      return (
        <DiffEditor
          original={originalContent ?? ''}
          modified={fileContent}
          height="100%"
          theme="vs"
          options={{ readOnly: true, renderSideBySide: true }}
        />
      )
    }
    return (
      <Editor
        height="100%"
        language={getLanguage(filePath)}
        value={fileContent}
        theme="vs"
        onChange={(value) => onContentChange(value ?? '')}
        onMount={handleEditorMount}
        options={{
          minimap: { enabled: false },
          fontSize: 13,
          lineNumbers: 'on',
          scrollBeyondLastLine: false,
          wordWrap: 'on',
        }}
      />
    )
  }

  return (
    <div className="h-full flex flex-col" data-testid="file-editor-area" onKeyDown={handleKeyDown} tabIndex={0}>
      {/* Tab 栏 + 工具栏 */}
      <div className="flex items-center justify-between px-3 py-1 border-b bg-muted/30">
        <div className="flex items-center gap-2">
          <span className="text-sm truncate max-w-[200px]" title={filePath}>
            {filePath}
          </span>
          {isDirty && (
            <span className="w-2 h-2 rounded-full bg-foreground" data-testid="dirty-dot" />
          )}
        </div>
        <div className="flex items-center gap-1">
          {isMarkdown && !monacoError && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs"
              onClick={() => setShowPreview(!showPreview)}
              aria-label={showPreview ? '关闭预览' : '预览'}
            >
              {showPreview ? '关闭预览' : '预览'}
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs"
            onClick={onSave}
            disabled={!isDirty}
            aria-label="保存"
          >
            保存
          </Button>
        </div>
      </div>

      {/* 编辑区 + 预览区 */}
      {showPreview && isMarkdown && !monacoError ? (
        <Group orientation="horizontal" className="flex-1 min-h-0" data-testid="editor-preview-group">
          <Panel id="editor-panel" minSize="20%" defaultSize="50%" className="overflow-hidden">
            {renderEditor()}
          </Panel>
          <Separator className="w-px bg-border" />
          <Panel id="preview-panel" minSize="20%" defaultSize="50%" className="overflow-hidden">
            <FilePreview content={previewContent} onClose={() => setShowPreview(false)} />
          </Panel>
        </Group>
      ) : (
        <div className="flex-1 min-h-0">
          {renderEditor()}
        </div>
      )}
    </div>
  )
}

function getLanguage(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase() ?? ''
  const map: Record<string, string> = {
    ts: 'typescript',
    tsx: 'typescript',
    js: 'javascript',
    jsx: 'javascript',
    py: 'python',
    md: 'markdown',
    json: 'json',
    yaml: 'yaml',
    yml: 'yaml',
    css: 'css',
    html: 'html',
    sql: 'sql',
    sh: 'shell',
    bash: 'shell',
  }
  return map[ext] ?? 'plaintext'
}
