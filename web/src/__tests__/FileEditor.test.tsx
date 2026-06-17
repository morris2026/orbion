import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// jsdom 不支持 scrollIntoView、ResizeObserver、getAnimations
Element.prototype.scrollIntoView = vi.fn()
global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
Element.prototype.getAnimations = vi.fn().mockReturnValue([])

// Mock Monaco Editor — jsdom 无法加载真实 Monaco
const mockUpdateOptions = vi.fn()
vi.mock('@monaco-editor/react', () => ({
  Editor: vi.fn(({ value, onChange, onMount }) => {
    const handleEditorMount = (el: HTMLTextAreaElement) => {
      onMount?.({ getValue: () => el.value, focus: vi.fn(), updateOptions: mockUpdateOptions })
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

describe('MVP-RE-6.5: Markdown 预览优先', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('.md 文件默认只显示预览，不显示编辑器', () => {
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

    expect(screen.getByTestId('file-preview')).toBeInTheDocument()
    expect(screen.queryByTestId('monaco-editor')).not.toBeInTheDocument()
  })

  it('.md 文件工具栏显示编辑和预览按钮', () => {
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

    expect(screen.getByTestId('btn-editor')).toBeInTheDocument()
    expect(screen.getByTestId('btn-preview')).toBeInTheDocument()
  })

  it('默认状态：编辑按钮未激活，预览按钮激活', () => {
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

    expect(screen.getByTestId('btn-editor')).not.toHaveClass('bg-primary/10')
    expect(screen.getByTestId('btn-preview')).toHaveClass('bg-primary/10')
  })
})

describe('MVP-RE-6.6: 编辑/预览按钮切换', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('点击编辑按钮 → 编辑器和预览同时显示（side-by-side）', async () => {
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

    await user.click(screen.getByTestId('btn-editor'))

    expect(screen.getByTestId('monaco-editor')).toBeInTheDocument()
    expect(screen.getByTestId('file-preview')).toBeInTheDocument()
  })

  it('编辑+预览模式下点击预览按钮 → 关闭预览，只剩编辑器', async () => {
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

    // 先打开编辑
    await user.click(screen.getByTestId('btn-editor'))
    expect(screen.getByTestId('monaco-editor')).toBeInTheDocument()

    // 关闭预览
    await user.click(screen.getByTestId('btn-preview'))
    expect(screen.queryByTestId('file-preview')).not.toBeInTheDocument()
    expect(screen.getByTestId('monaco-editor')).toBeInTheDocument()
  })

  it('仅编辑模式下点击编辑按钮 → 按钮禁用，不能关闭', async () => {
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

    // 打开编辑，关闭预览
    await user.click(screen.getByTestId('btn-editor'))
    await user.click(screen.getByTestId('btn-preview'))

    // 编辑按钮应禁用（不能同时隐藏两个面板）
    expect(screen.getByTestId('btn-editor')).toBeDisabled()
  })

  it('仅预览模式下点击预览按钮 → 按钮禁用，不能关闭', () => {
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

    // 默认仅预览模式，预览按钮应禁用
    expect(screen.getByTestId('btn-preview')).toBeDisabled()
  })

  it('编辑+预览模式下两个按钮都可点击', async () => {
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

    await user.click(screen.getByTestId('btn-editor'))

    expect(screen.getByTestId('btn-editor')).not.toBeDisabled()
    expect(screen.getByTestId('btn-preview')).not.toBeDisabled()
  })

  it('编辑按钮激活样式随状态切换', async () => {
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

    // 初始：编辑按钮未激活
    expect(screen.getByTestId('btn-editor')).not.toHaveClass('bg-primary/10')

    // 点击后：编辑按钮激活
    await user.click(screen.getByTestId('btn-editor'))
    expect(screen.getByTestId('btn-editor')).toHaveClass('bg-primary/10')
  })
})

describe('MVP-RE-6.6a: Toggle 按钮切换编辑/预览', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('仅预览模式下点击 toggle → 切换为仅编辑', async () => {
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

    expect(screen.getByTestId('file-preview')).toBeInTheDocument()
    expect(screen.queryByTestId('monaco-editor')).not.toBeInTheDocument()

    await user.click(screen.getByTestId('btn-toggle'))

    expect(screen.getByTestId('monaco-editor')).toBeInTheDocument()
    expect(screen.queryByTestId('file-preview')).not.toBeInTheDocument()
  })

  it('仅编辑模式下点击 toggle → 切换为仅预览', async () => {
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

    // 先切到仅编辑
    await user.click(screen.getByTestId('btn-editor'))
    await user.click(screen.getByTestId('btn-preview'))
    expect(screen.getByTestId('monaco-editor')).toBeInTheDocument()
    expect(screen.queryByTestId('file-preview')).not.toBeInTheDocument()

    // toggle 切回仅预览
    await user.click(screen.getByTestId('btn-toggle'))
    expect(screen.getByTestId('file-preview')).toBeInTheDocument()
    expect(screen.queryByTestId('monaco-editor')).not.toBeInTheDocument()
  })

  it('编辑+预览模式下点击 toggle → 关闭编辑，只留预览', async () => {
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

    // 打开编辑（进入编辑+预览模式）
    await user.click(screen.getByTestId('btn-editor'))
    expect(screen.getByTestId('monaco-editor')).toBeInTheDocument()
    expect(screen.getByTestId('file-preview')).toBeInTheDocument()

    // toggle 关闭编辑
    await user.click(screen.getByTestId('btn-toggle'))
    expect(screen.getByTestId('file-preview')).toBeInTheDocument()
    expect(screen.queryByTestId('monaco-editor')).not.toBeInTheDocument()
  })

  it('toggle 按钮始终可点击', () => {
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

    expect(screen.getByTestId('btn-toggle')).not.toBeDisabled()
  })
})

describe('MVP-RE-6.7: 非 Markdown 文件无编辑/预览按钮', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('.ts 文件不显示编辑和预览按钮', () => {
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

    expect(screen.queryByTestId('btn-editor')).not.toBeInTheDocument()
    expect(screen.queryByTestId('btn-preview')).not.toBeInTheDocument()
  })

  it('.ts 文件直接显示编辑器', () => {
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

    expect(screen.getByTestId('monaco-editor')).toBeInTheDocument()
    expect(screen.queryByTestId('file-preview')).not.toBeInTheDocument()
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

  it('编辑+预览模式下编辑内容变更 → 预览 debounce 后更新', async () => {
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

    // 打开编辑器（进入编辑+预览模式）
    await userEvent.setup().click(screen.getByTestId('btn-editor'))

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

  it('纯预览模式下内容变更 → 预览直接同步（无 debounce）', () => {
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

    // 纯预览模式（默认），内容变更直接同步
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

    expect(screen.getByTestId('file-preview').textContent).toContain('Hello World')
  })
})

describe('MVP-RE-6.10: 切换文件', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('从 .md 切换到 .ts → 编辑器出现，预览消失', () => {
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

    expect(screen.getByTestId('file-preview')).toBeInTheDocument()
    expect(screen.queryByTestId('monaco-editor')).not.toBeInTheDocument()

    rerender(
      <FileEditor
        filePath="src/main.ts"
        fileContent="content B"
        isDirty={false}
        viewMode="edit"
        originalContent={null}
        onSave={vi.fn()}
        onContentChange={vi.fn()}
      />
    )

    expect(screen.getByTestId('monaco-editor')).toBeInTheDocument()
    expect(screen.queryByTestId('file-preview')).not.toBeInTheDocument()
  })

  it('从 .ts 切换到 .md → 预览出现，编辑器消失', () => {
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

    expect(screen.getByTestId('monaco-editor')).toBeInTheDocument()

    rerender(
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

    expect(screen.getByTestId('file-preview')).toBeInTheDocument()
    expect(screen.queryByTestId('monaco-editor')).not.toBeInTheDocument()
  })

  it('.md 文件打开编辑后再切换文件 → 状态重置为默认预览', async () => {
    const user = userEvent.setup()
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

    // 打开编辑
    await user.click(screen.getByTestId('btn-editor'))
    expect(screen.getByTestId('monaco-editor')).toBeInTheDocument()

    // 切换到另一个 .md 文件
    rerender(
      <FileEditor
        filePath="docs/other.md"
        fileContent="# Other"
        isDirty={false}
        viewMode="edit"
        originalContent={null}
        onSave={vi.fn()}
        onContentChange={vi.fn()}
      />
    )

    // 应重置为仅预览
    expect(screen.getByTestId('file-preview')).toBeInTheDocument()
    expect(screen.queryByTestId('monaco-editor')).not.toBeInTheDocument()
  })
})

describe('MVP-RE-6.12: 编辑器选项 — Unicode 高亮', () => {
  beforeEach(() => {
    mockUpdateOptions.mockClear()
  })

  it('mount 时关闭 unicodeHighlight 避免中文标点显示小框', () => {
    render(
      <FileEditor
        filePath="src/main.ts"
        fileContent="const x = [1, 2]"
        isDirty={false}
        viewMode="edit"
        originalContent={null}
        onSave={vi.fn()}
        onContentChange={vi.fn()}
      />
    )

    expect(mockUpdateOptions).toHaveBeenCalledWith(
      expect.objectContaining({
        unicodeHighlight: { nonBasicASCII: false, ambiguousCharacters: false, invisibleCharacters: false },
      })
    )
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

  it('monacoError={true} 时 .md 文件不显示编辑和预览按钮', () => {
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

    expect(screen.queryByTestId('btn-editor')).not.toBeInTheDocument()
    expect(screen.queryByTestId('btn-preview')).not.toBeInTheDocument()
  })

  it('monacoError={true} 时 .md 文件显示降级 textarea 而非预览', () => {
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

    // Monaco 失败时，编辑器应可见（降级 textarea），预览不显示
    expect(screen.getByTestId('fallback-editor')).toBeInTheDocument()
    expect(screen.queryByTestId('file-preview')).not.toBeInTheDocument()
  })
})
