import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// jsdom 不支持 scrollIntoView、ResizeObserver、getAnimations
Element.prototype.scrollIntoView = vi.fn()
global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
Element.prototype.getAnimations = vi.fn().mockReturnValue([])

// Mock Monaco Editor — jsdom 无法加载真实 Monaco
vi.mock('@monaco-editor/react', () => ({
  Editor: vi.fn(({ value, onChange, onMount }) => {
    // 模拟编辑器挂载，暴露 getValue/setValue
    const handleEditorMount = (el: HTMLTextAreaElement) => {
      onMount?.({ getValue: () => el.value, focus: vi.fn() })
    }
    return (
      <textarea
        data-testid="monaco-editor"
        value={value ?? ''}
        onChange={(e) => onChange?.(e.target.value)}
        ref={handleEditorMount}
      />
    )
  }),
  DiffEditor: vi.fn(({ original, modified }) => (
    <div data-testid="monaco-diff-editor" data-original={original} data-modified={modified} />
  )),
}))

import { FileEditor } from '@/components/FileEditor'

describe('MVP-RE-6.1: Monaco 编辑器渲染', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('传入 fileContent 和 filePath，Monaco 编辑器渲染', () => {
    render(
      <FileEditor
        filePath="src/main.ts"
        fileContent="console.log('hello')"
        isDirty={false}
        viewMode="edit"
        originalContent={null}
        onSave={vi.fn()}
        onContentChange={vi.fn()}
        onOpenPreview={vi.fn()}
        onClosePreview={vi.fn()}
        showPreview={false}
      />
    )

    const editor = screen.getByTestId('monaco-editor')
    expect(editor).toBeInTheDocument()
    expect(editor).toHaveValue("console.log('hello')")
  })
})

describe('MVP-RE-6.2: 保存按钮', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('点击保存按钮 → onSave 回调被调用', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    render(
      <FileEditor
        filePath="src/main.ts"
        fileContent="modified"
        isDirty={true}
        viewMode="edit"
        originalContent={null}
        onSave={onSave}
        onContentChange={vi.fn()}
        onOpenPreview={vi.fn()}
        onClosePreview={vi.fn()}
        showPreview={false}
      />
    )

    await user.click(screen.getByRole('button', { name: /保存/i }))
    expect(onSave).toHaveBeenCalled()
  })
})

describe('MVP-RE-6.3: Ctrl+S 快捷键', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('编辑器聚焦时按 Ctrl+S → onSave 回调被调用', () => {
    const onSave = vi.fn()
    render(
      <FileEditor
        filePath="src/main.ts"
        fileContent="modified"
        isDirty={true}
        viewMode="edit"
        originalContent={null}
        onSave={onSave}
        onContentChange={vi.fn()}
        onOpenPreview={vi.fn()}
        onClosePreview={vi.fn()}
        showPreview={false}
      />
    )

    // 在编辑器区域触发 Ctrl+S
    const editorArea = screen.getByTestId('file-editor-area')
    fireEvent.keyDown(editorArea, { key: 's', ctrlKey: true })

    expect(onSave).toHaveBeenCalled()
  })
})

describe('MVP-RE-6.4: 修改圆点标记', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('isDirty=true 时 Tab 栏显示修改圆点', () => {
    render(
      <FileEditor
        filePath="src/main.ts"
        fileContent="modified"
        isDirty={true}
        viewMode="edit"
        originalContent={null}
        onSave={vi.fn()}
        onContentChange={vi.fn()}
        onOpenPreview={vi.fn()}
        onClosePreview={vi.fn()}
        showPreview={false}
      />
    )

    expect(screen.getByTestId('dirty-dot')).toBeInTheDocument()
  })

  it('isDirty=false 时 Tab 栏无修改圆点', () => {
    render(
      <FileEditor
        filePath="src/main.ts"
        fileContent="original"
        isDirty={false}
        viewMode="edit"
        originalContent={null}
        onSave={vi.fn()}
        onContentChange={vi.fn()}
        onOpenPreview={vi.fn()}
        onClosePreview={vi.fn()}
        showPreview={false}
      />
    )

    expect(screen.queryByTestId('dirty-dot')).not.toBeInTheDocument()
  })
})

describe('MVP-RE-6.5: 预览开关 — Markdown 文件', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('.md 文件显示预览按钮，点击后显示 FilePreview', async () => {
    const user = userEvent.setup()
    const onOpenPreview = vi.fn()
    render(
      <FileEditor
        filePath="docs/guide.md"
        fileContent="# Hello"
        isDirty={false}
        viewMode="edit"
        originalContent={null}
        onSave={vi.fn()}
        onContentChange={vi.fn()}
        onOpenPreview={onOpenPreview}
        onClosePreview={vi.fn()}
        showPreview={false}
      />
    )

    // 预览按钮存在
    const previewBtn = screen.getByRole('button', { name: /预览/i })
    expect(previewBtn).toBeInTheDocument()

    // 点击预览
    await user.click(previewBtn)
    expect(onOpenPreview).toHaveBeenCalled()
  })

  it('showPreview=true 时显示 FilePreview 面板', () => {
    render(
      <FileEditor
        filePath="docs/guide.md"
        fileContent="# Hello"
        isDirty={false}
        viewMode="edit"
        originalContent={null}
        onSave={vi.fn()}
        onContentChange={vi.fn()}
        onOpenPreview={vi.fn()}
        onClosePreview={vi.fn()}
        showPreview={true}
      />
    )

    expect(screen.getByTestId('file-preview')).toBeInTheDocument()
  })
})

describe('MVP-RE-6.6: 预览关闭', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('预览打开时点击关闭 → onClosePreview 回调被调用', async () => {
    const user = userEvent.setup()
    const onClosePreview = vi.fn()
    render(
      <FileEditor
        filePath="docs/guide.md"
        fileContent="# Hello"
        isDirty={false}
        viewMode="edit"
        originalContent={null}
        onSave={vi.fn()}
        onContentChange={vi.fn()}
        onOpenPreview={vi.fn()}
        onClosePreview={onClosePreview}
        showPreview={true}
      />
    )

    await user.click(screen.getByRole('button', { name: /^关闭预览$/i }))
    expect(onClosePreview).toHaveBeenCalled()
  })
})

describe('MVP-RE-6.7: 非 Markdown 文件无预览开关', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('.ts 文件不显示预览按钮', () => {
    render(
      <FileEditor
        filePath="src/main.ts"
        fileContent="console.log('hello')"
        isDirty={false}
        viewMode="edit"
        originalContent={null}
        onSave={vi.fn()}
        onContentChange={vi.fn()}
        onOpenPreview={vi.fn()}
        onClosePreview={vi.fn()}
        showPreview={false}
      />
    )

    expect(screen.queryByRole('button', { name: /预览/i })).not.toBeInTheDocument()
  })
})

describe('MVP-RE-6.8: DiffEditor 模式', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('viewMode="diff" 时渲染 DiffEditor 而非普通 Editor', () => {
    render(
      <FileEditor
        filePath="src/main.ts"
        fileContent="modified content"
        isDirty={true}
        viewMode="diff"
        originalContent="original content"
        onSave={vi.fn()}
        onContentChange={vi.fn()}
        onOpenPreview={vi.fn()}
        onClosePreview={vi.fn()}
        showPreview={false}
      />
    )

    // DiffEditor 被渲染
    expect(screen.getByTestId('monaco-diff-editor')).toBeInTheDocument()
    // 普通 Editor 不被渲染
    expect(screen.queryByTestId('monaco-editor')).not.toBeInTheDocument()
  })
})

describe('MVP-RE-6.8a: DiffEditor 切换回普通 Editor', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('viewMode 从 "diff" 变为 "edit" 时切换回普通 Editor', () => {
    const { rerender } = render(
      <FileEditor
        filePath="src/main.ts"
        fileContent="modified"
        isDirty={true}
        viewMode="diff"
        originalContent="original"
        onSave={vi.fn()}
        onContentChange={vi.fn()}
        onOpenPreview={vi.fn()}
        onClosePreview={vi.fn()}
        showPreview={false}
      />
    )

    expect(screen.getByTestId('monaco-diff-editor')).toBeInTheDocument()

    // 切换回 edit 模式
    rerender(
      <FileEditor
        filePath="src/main.ts"
        fileContent="modified"
        isDirty={true}
        viewMode="edit"
        originalContent={null}
        onSave={vi.fn()}
        onContentChange={vi.fn()}
        onOpenPreview={vi.fn()}
        onClosePreview={vi.fn()}
        showPreview={false}
      />
    )

    expect(screen.getByTestId('monaco-editor')).toBeInTheDocument()
    expect(screen.queryByTestId('monaco-diff-editor')).not.toBeInTheDocument()
  })
})

describe('MVP-RE-6.9: 预览实时更新', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('预览打开时编辑内容变更 → 预览 debounce 后更新', async () => {
    const { rerender } = render(
      <FileEditor
        filePath="docs/guide.md"
        fileContent="# Hello"
        isDirty={false}
        viewMode="edit"
        originalContent={null}
        onSave={vi.fn()}
        onContentChange={vi.fn()}
        onOpenPreview={vi.fn()}
        onClosePreview={vi.fn()}
        showPreview={true}
      />
    )

    // 预览面板存在
    expect(screen.getByTestId('file-preview')).toBeInTheDocument()

    // 内容变更
    rerender(
      <FileEditor
        filePath="docs/guide.md"
        fileContent="# Hello World"
        isDirty={true}
        viewMode="edit"
        originalContent="# Hello"
        onSave={vi.fn()}
        onContentChange={vi.fn()}
        onOpenPreview={vi.fn()}
        onClosePreview={vi.fn()}
        showPreview={true}
      />
    )

    // 等待 debounce（300ms）
    act(() => {
      vi.advanceTimersByTime(350)
    })

    // 预览内容更新
    await waitFor(() => {
      expect(screen.getByTestId('file-preview').textContent).toContain('Hello World')
    })
  })
})

describe('MVP-RE-6.10: 切换文件', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('切换 filePath 和 fileContent → 编辑器内容更新', () => {
    const { rerender } = render(
      <FileEditor
        filePath="src/main.ts"
        fileContent="content A"
        isDirty={false}
        viewMode="edit"
        originalContent={null}
        onSave={vi.fn()}
        onContentChange={vi.fn()}
        onOpenPreview={vi.fn()}
        onClosePreview={vi.fn()}
        showPreview={false}
      />
    )

    expect(screen.getByTestId('monaco-editor')).toHaveValue('content A')

    // 切换到 B 文件
    rerender(
      <FileEditor
        filePath="docs/guide.md"
        fileContent="content B"
        isDirty={false}
        viewMode="edit"
        originalContent={null}
        onSave={vi.fn()}
        onContentChange={vi.fn()}
        onOpenPreview={vi.fn()}
        onClosePreview={vi.fn()}
        showPreview={false}
      />
    )

    expect(screen.getByTestId('monaco-editor')).toHaveValue('content B')
  })
})

describe('MVP-RE-6.11: Monaco 加载失败降级', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('monacoError={true} → 显示降级 textarea，仍可编辑和保存', async () => {
    const onContentChange = vi.fn()
    const onSave = vi.fn()

    render(
      <FileEditor
        filePath="src/main.ts"
        fileContent="fallback content"
        isDirty={true}
        viewMode="edit"
        originalContent={null}
        onSave={onSave}
        onContentChange={onContentChange}
        onOpenPreview={vi.fn()}
        onClosePreview={vi.fn()}
        showPreview={false}
        monacoError={true}
      />
    )

    // 降级 textarea 出现，Monaco Editor 不渲染
    const fallbackTextarea = screen.getByTestId('fallback-editor')
    expect(fallbackTextarea).toBeInTheDocument()
    expect(fallbackTextarea).toHaveValue('fallback content')
    expect(screen.queryByTestId('monaco-editor')).not.toBeInTheDocument()

    // 可编辑
    fireEvent.change(fallbackTextarea, { target: { value: 'edited' } })
    expect(onContentChange).toHaveBeenCalledWith('edited')

    // 可保存
    await userEvent.setup().click(screen.getByRole('button', { name: /保存/i }))
    expect(onSave).toHaveBeenCalled()
  })

  it('monacoError={true} 时不显示预览开关', () => {
    render(
      <FileEditor
        filePath="docs/guide.md"
        fileContent="# Hello"
        isDirty={false}
        viewMode="edit"
        originalContent={null}
        onSave={vi.fn()}
        onContentChange={vi.fn()}
        onOpenPreview={vi.fn()}
        onClosePreview={vi.fn()}
        showPreview={false}
        monacoError={true}
      />
    )

    // 降级模式下即使是 .md 文件也不显示预览开关
    expect(screen.queryByRole('button', { name: /预览/i })).not.toBeInTheDocument()
  })
})
