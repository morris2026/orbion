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
      />
    )

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
    render(
      <FileEditor
        filePath="docs/guide.md"
        fileContent="# Hello"
        isDirty={false}
        viewMode="edit"
        originalContent={null}
        onSave={vi.fn()}
        onContentChange={vi.fn()}
      />
    )

    // 预览按钮存在
    const previewBtn = screen.getByRole('button', { name: /预览/i })
    expect(previewBtn).toBeInTheDocument()

    // 点击预览 → FilePreview 面板出现
    await user.click(previewBtn)
    expect(screen.getByTestId('file-preview')).toBeInTheDocument()
  })

  it('showPreview 内部状态为 true 时显示 FilePreview 面板', async () => {
    const user = userEvent.setup()
    render(
      <FileEditor
        filePath="docs/guide.md"
        fileContent="# Hello"
        isDirty={false}
        viewMode="edit"
        originalContent={null}
        onSave={vi.fn()}
        onContentChange={vi.fn()}
      />
    )

    // 点击预览按钮打开
    await user.click(screen.getByRole('button', { name: /预览/i }))
    expect(screen.getByTestId('file-preview')).toBeInTheDocument()
  })
})

describe('MVP-RE-6.6: 预览关闭', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('预览打开时点击关闭 → FilePreview 消失', async () => {
    const user = userEvent.setup()
    render(
      <FileEditor
        filePath="docs/guide.md"
        fileContent="# Hello"
        isDirty={false}
        viewMode="edit"
        originalContent={null}
        onSave={vi.fn()}
        onContentChange={vi.fn()}
      />
    )

    // 先打开预览
    await user.click(screen.getByRole('button', { name: /预览/i }))
    expect(screen.getByTestId('file-preview')).toBeInTheDocument()

    // 点击关闭预览
    await user.click(screen.getByRole('button', { name: /^关闭预览$/i }))
    expect(screen.queryByTestId('file-preview')).not.toBeInTheDocument()
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
      />
    )

    expect(screen.getByTestId('monaco-diff-editor')).toBeInTheDocument()
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
      />
    )

    expect(screen.getByTestId('monaco-diff-editor')).toBeInTheDocument()

    rerender(
      <FileEditor
        filePath="src/main.ts"
        fileContent="modified"
        isDirty={true}
        viewMode="edit"
        originalContent={null}
        onSave={vi.fn()}
        onContentChange={vi.fn()}
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
      />
    )

    // 打开预览
    await userEvent.setup().click(screen.getByRole('button', { name: /预览/i }))
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
      />
    )

    expect(screen.getByTestId('monaco-editor')).toHaveValue('content A')

    rerender(
      <FileEditor
        filePath="docs/guide.md"
        fileContent="content B"
        isDirty={false}
        viewMode="edit"
        originalContent={null}
        onSave={vi.fn()}
        onContentChange={vi.fn()}
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
        monacoError={true}
      />
    )

    const fallbackTextarea = screen.getByTestId('fallback-editor')
    expect(fallbackTextarea).toBeInTheDocument()
    expect(fallbackTextarea).toHaveValue('fallback content')
    expect(screen.queryByTestId('monaco-editor')).not.toBeInTheDocument()

    fireEvent.change(fallbackTextarea, { target: { value: 'edited' } })
    expect(onContentChange).toHaveBeenCalledWith('edited')

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
        monacoError={true}
      />
    )

    expect(screen.queryByRole('button', { name: /预览/i })).not.toBeInTheDocument()
  })
})
