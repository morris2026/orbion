import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// jsdom 不支持 scrollIntoView、ResizeObserver、getAnimations
Element.prototype.scrollIntoView = vi.fn()
global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
Element.prototype.getAnimations = vi.fn().mockReturnValue([])

// Mock Monaco Editor
vi.mock('@monaco-editor/react', () => ({
  Editor: vi.fn(({ value, onChange }) => (
    <textarea
      data-testid="monaco-editor"
      value={value ?? ''}
      onChange={(e) => onChange?.(e.target.value)}
    />
  )),
  DiffEditor: vi.fn(({ original, modified }) => (
    <div data-testid="monaco-diff-editor" data-original={original} data-modified={modified} />
  )),
}))

// Mock @monaco-editor/loader — default export
vi.mock('@monaco-editor/loader', () => ({
  default: {
    init: vi.fn(() => Promise.resolve({})),
  },
}))

import { FileTab } from '@/components/FileTab'
import * as apiModule from '@/lib/api'
import type { FileNode, RepoInfo, GitStatusResult } from '@/types/api'

const mockRepos: RepoInfo[] = [{ name: 'orbion' }]

const mockFileTree: FileNode[] = [
  { path: 'src', type: 'dir', name: 'src' },
  { path: 'src/main.ts', type: 'file', name: 'main.ts' },
  { path: 'docs', type: 'dir', name: 'docs' },
  { path: 'docs/guide.md', type: 'file', name: 'guide.md' },
  { path: 'README.md', type: 'file', name: 'README.md' },
]

const mockGitStatus: GitStatusResult = {
  staged: [],
  changes: [{ path: 'src/main.ts', status: 'M' }],
}

function setupApiMocks(overrides?: Record<string, unknown>) {
  const defaults: Record<string, unknown> = {
    '/projects/proj-1/repos': mockRepos,
    '/projects/proj-1/repos/orbion/tree': mockFileTree,
    '/projects/proj-1/repos/orbion/status': mockGitStatus,
  }
  const mapping = { ...defaults, ...overrides }

  vi.spyOn(apiModule, 'apiGet').mockImplementation((url: string) => {
    // 文件内容请求：URL 包含 /files
    if (url.includes('/repos/orbion/files')) {
      const fileMock = mapping['/projects/proj-1/repos/orbion/files']
      if (fileMock) return Promise.resolve(fileMock)
      return Promise.resolve({ path: '', content: '' })
    }
    // 精确匹配其他 URL
    for (const [key, value] of Object.entries(mapping)) {
      if (url === key) return Promise.resolve(value)
    }
    return Promise.resolve([])
  })
  vi.spyOn(apiModule, 'apiPost').mockResolvedValue({ status: 'ok' })
  vi.spyOn(apiModule, 'apiPut').mockResolvedValue({})
}

describe('MVP-RE-8.1: 三层布局渲染', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('渲染 FileTab → 活动栏 + 侧边栏 + 主区域均存在；默认显示 ExplorerPanel', async () => {
    setupApiMocks()

    render(<FileTab projectId="proj-1" />)

    // 活动栏
    expect(screen.getByTestId('activity-bar')).toBeInTheDocument()

    // 侧边栏（等待 API 加载后 sidebar 渲染）
    await waitFor(() => {
      expect(screen.getByTestId('sidebar-panel')).toBeInTheDocument()
    })

    // 默认显示 ExplorerPanel（文件树加载后渲染，空树时显示 explorer-empty）
    await waitFor(() => {
      const explorer = screen.queryByTestId('explorer-panel')
      const explorerEmpty = screen.queryByTestId('explorer-empty')
      expect(explorer || explorerEmpty).toBeInTheDocument()
    })

    // 主区域 — FileEditor 占位（未选文件时显示提示）
    expect(screen.getByText('选择文件开始编辑')).toBeInTheDocument()
  })
})

describe('MVP-RE-8.2: 活动栏切换', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('点击 Source Control → 侧边栏切换为 SourceControlPanel；再点 Explorer 切回', async () => {
    const user = userEvent.setup()
    setupApiMocks()

    render(<FileTab projectId="proj-1" />)

    // 默认 Explorer
    await waitFor(() => {
      expect(screen.getByTestId('explorer-panel')).toBeInTheDocument()
    })

    // 点击 Source Control
    await user.click(screen.getByRole('button', { name: /source.?control/i }))
    expect(screen.getByTestId('source-control-panel')).toBeInTheDocument()
    expect(screen.queryByTestId('explorer-panel')).not.toBeInTheDocument()

    // 切回 Explorer
    await user.click(screen.getByRole('button', { name: /explorer/i }))
    expect(screen.getByTestId('explorer-panel')).toBeInTheDocument()
    expect(screen.queryByTestId('source-control-panel')).not.toBeInTheDocument()
  })
})

describe('MVP-RE-8.3: 侧边栏折叠/展开', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('点击折叠按钮 → 侧边栏隐藏；再点击展开', async () => {
    const user = userEvent.setup()
    setupApiMocks()

    render(<FileTab projectId="proj-1" />)

    // 侧边栏可见
    await waitFor(() => {
      expect(screen.getByTestId('sidebar-panel')).toBeInTheDocument()
    })

    // 点击折叠 — collapsible Panel 折叠后 DOM 保留但 size=0，jsdom 无法检测视觉宽度，
    // 通过展开按钮出现来验证折叠生效
    await user.click(screen.getByRole('button', { name: /折叠侧边栏/i }))
    expect(screen.getByRole('button', { name: /展开侧边栏/i })).toBeInTheDocument()
    expect(screen.getByText('选择文件开始编辑')).toBeInTheDocument()

    // 点击展开
    await user.click(screen.getByRole('button', { name: /展开侧边栏/i }))
    expect(screen.getByTestId('sidebar-panel')).toBeInTheDocument()
  })
})

describe('MVP-RE-8.4: Explorer 点击文件 → 主区域显示', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('在 ExplorerPanel 双击文件 → FileEditor 显示文件内容', async () => {
    const user = userEvent.setup()
    vi.spyOn(apiModule, 'apiGet').mockImplementation((url: string) => {
      if (url === '/projects/proj-1/repos') return Promise.resolve(mockRepos)
      if (url === '/projects/proj-1/repos/orbion/tree') return Promise.resolve(mockFileTree)
      if (url === '/projects/proj-1/repos/orbion/status') return Promise.resolve(mockGitStatus)
      if (url.includes('/repos/orbion/files')) {
        return Promise.resolve({ path: 'README.md', content: '# Hello' })
      }
      return Promise.resolve([])
    })

    render(<FileTab projectId="proj-1" />)

    // 等待文件树加载（顶层文件 README.md 可见）
    await waitFor(() => {
      expect(screen.getByText('README.md')).toBeInTheDocument()
    })

    // 双击文件
    await user.dblClick(screen.getByText('README.md'))

    // FileEditor 显示文件内容
    await waitFor(() => {
      const editor = screen.getByTestId('monaco-editor')
      expect(editor).toHaveValue('# Hello')
    })
  })
})

describe('MVP-RE-8.5: Source Control 点击文件 → DiffEditor', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('在 SourceControlPanel 点击变更文件 → DiffEditor 模式', async () => {
    const user = userEvent.setup()
    vi.spyOn(apiModule, 'apiGet').mockImplementation((url: string) => {
      if (url === '/projects/proj-1/repos') return Promise.resolve(mockRepos)
      if (url === '/projects/proj-1/repos/orbion/tree') return Promise.resolve(mockFileTree)
      if (url === '/projects/proj-1/repos/orbion/status') return Promise.resolve(mockGitStatus)
      if (url.includes('/repos/orbion/files')) {
        // selectFileFromSC 会两次调用：一次无 ref（工作区版本），一次 ref=HEAD
        if (url.includes('ref=HEAD')) {
          return Promise.resolve({ path: 'src/main.ts', content: 'original content' })
        }
        return Promise.resolve({ path: 'src/main.ts', content: 'modified content' })
      }
      return Promise.resolve([])
    })
    vi.spyOn(apiModule, 'apiPost').mockResolvedValue({ status: 'ok' })

    render(<FileTab projectId="proj-1" />)

    // 切换到 Source Control
    await user.click(screen.getByRole('button', { name: /source.?control/i }))

    // 等待 SourceControlPanel 渲染
    await waitFor(() => {
      expect(screen.getByTestId('source-control-panel')).toBeInTheDocument()
    })

    // 点击 Changes 中的文件
    const fileItems = screen.getAllByText('src/main.ts')
    await user.click(fileItems[fileItems.length - 1])

    // 主区域切换为 DiffEditor
    await waitFor(() => {
      expect(screen.getByTestId('monaco-diff-editor')).toBeInTheDocument()
    })
  })
})

describe('MVP-RE-8.6: 编辑+预览左右分栏', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('打开 .md 文件并打开预览 → 编辑区在左，预览区在右', async () => {
    const user = userEvent.setup()
    vi.spyOn(apiModule, 'apiGet').mockImplementation((url: string) => {
      if (url === '/projects/proj-1/repos') return Promise.resolve(mockRepos)
      if (url === '/projects/proj-1/repos/orbion/tree') return Promise.resolve(mockFileTree)
      if (url === '/projects/proj-1/repos/orbion/status') return Promise.resolve(mockGitStatus)
      if (url.includes('/repos/orbion/files')) {
        return Promise.resolve({ path: 'README.md', content: '# Hello' })
      }
      return Promise.resolve([])
    })

    render(<FileTab projectId="proj-1" />)

    // 等待文件树加载（顶层文件 README.md 可见）
    await waitFor(() => {
      expect(screen.getByText('README.md')).toBeInTheDocument()
    })

    // 双击打开 .md 文件
    await user.dblClick(screen.getByText('README.md'))

    // 等待编辑器渲染
    await waitFor(() => {
      expect(screen.getByTestId('monaco-editor')).toHaveValue('# Hello')
    })

    // 点击预览按钮
    await user.click(screen.getByRole('button', { name: /预览/i }))

    // 预览区出现
    expect(screen.getByTestId('file-preview')).toBeInTheDocument()
    // 编辑区仍在
    expect(screen.getByTestId('monaco-editor')).toBeInTheDocument()
    // 编辑区和预览区使用 react-resizable-panels 分栏（可拖拽调整宽度）
    // 具体拖拽行为在步骤9 E2E 中验证
  })
})
