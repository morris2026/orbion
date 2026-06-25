import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, renderHook, act, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// jsdom 不支持 scrollIntoView、ResizeObserver、getAnimations
Element.prototype.scrollIntoView = vi.fn()
global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
Element.prototype.getAnimations = vi.fn().mockReturnValue([])

import { ActivityBar } from '@/components/ActivityBar'
import { ExplorerPanel } from '@/components/ExplorerPanel'
import { useFileTab } from '@/hooks/useFileTab'
import * as apiModule from '@/lib/api'
import type { FileNode, RepoInfo, GitStatusResult } from '@/types/api'

/** mock 文件树数据 */
const mockFileTree: FileNode[] = [
  { path: 'src', type: 'dir', name: 'src' },
  { path: 'src/main.ts', type: 'file', name: 'main.ts' },
  { path: 'src/app.tsx', type: 'file', name: 'app.tsx' },
  { path: 'docs', type: 'dir', name: 'docs' },
  { path: 'docs/guide.md', type: 'file', name: 'guide.md' },
  { path: 'README.md', type: 'file', name: 'README.md' },
]

/** mock 仓库列表 */
const mockRepos: RepoInfo[] = [
  { name: 'orbion' },
  { name: 'frontend' },
]

/** mock git status */
const mockGitStatus: GitStatusResult = {
  staged: [{ path: 'src/main.ts', status: 'M' }],
  changes: [{ path: 'docs/guide.md', status: 'M' }],
}

describe('MVP-RE-5.1: ActivityBar 图标切换', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('点击 Source Control 图标 → 高亮切换 + 回调', async () => {
    const user = userEvent.setup()
    const onActivityChange = vi.fn()
    render(<ActivityBar activePanel="explorer" onActivityChange={onActivityChange} />)

    // Explorer 默认高亮
    const explorerBtn = screen.getByRole('button', { name: /explorer/i })
    const gitBtn = screen.getByRole('button', { name: /source.?control/i })

    expect(explorerBtn).toHaveAttribute('data-active', 'true')
    expect(gitBtn).not.toHaveAttribute('data-active', 'true')

    // 点击 Source Control
    await user.click(gitBtn)

    expect(onActivityChange).toHaveBeenCalledWith('git')
  })

  it('点击 Explorer 图标 → 回调 explorer', async () => {
    const user = userEvent.setup()
    const onActivityChange = vi.fn()
    render(<ActivityBar activePanel="git" onActivityChange={onActivityChange} />)

    const explorerBtn = screen.getByRole('button', { name: /explorer/i })
    await user.click(explorerBtn)

    expect(onActivityChange).toHaveBeenCalledWith('explorer')
  })

  it('activePanel=git 时 Source Control 高亮', () => {
    render(<ActivityBar activePanel="git" onActivityChange={vi.fn()} />)

    const gitBtn = screen.getByRole('button', { name: /source.?control/i })
    const explorerBtn = screen.getByRole('button', { name: /explorer/i })

    expect(gitBtn).toHaveAttribute('data-active', 'true')
    expect(explorerBtn).not.toHaveAttribute('data-active', 'true')
  })
})

describe('ExplorerPanel 文件树排序', () => {
  it('文件夹排在文件前面，同类型按字母序', () => {
    const mixedTree: FileNode[] = [
      { path: 'z-file.txt', type: 'file', name: 'z-file.txt' },
      { path: 'a-dir', type: 'dir', name: 'a-dir' },
      { path: 'b-dir', type: 'dir', name: 'b-dir' },
      { path: 'a-file.txt', type: 'file', name: 'a-file.txt' },
      { path: 'a-dir/nested.ts', type: 'file', name: 'nested.ts' },
    ]

    render(
      <ExplorerPanel fileTree={mixedTree} selectedFile={null} onFileSelect={vi.fn()} />
    )

    // 获取顶级节点的文本顺序
    const panel = screen.getByTestId('explorer-panel')
    const nodes = panel.querySelectorAll('[data-testid^="tree-node-"]')
    const names = Array.from(nodes).map(n => n.textContent!.trim())

    // 文件夹优先：a-dir, b-dir 在前；文件在后：a-file.txt, z-file.txt
    expect(names).toEqual(['a-dir', 'b-dir', 'a-file.txt', 'z-file.txt'])
  })
})

describe('MVP-RE-5.2: ExplorerPanel 文件树渲染', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('文件树显示顶级节点', () => {
    render(
      <ExplorerPanel
        fileTree={mockFileTree}
        selectedFile={null}
        onFileSelect={vi.fn()}
      />
    )

    // 顶级目录和文件可见
    expect(screen.getByText('src')).toBeInTheDocument()
    expect(screen.getByText('docs')).toBeInTheDocument()
    expect(screen.getByText('README.md')).toBeInTheDocument()
  })

  it('目录节点有展开/折叠标识', () => {
    render(
      <ExplorerPanel
        fileTree={mockFileTree}
        selectedFile={null}
        onFileSelect={vi.fn()}
      />
    )

    // 目录节点有折叠图标（ChevronRight SVG）
    const srcNode = screen.getByTestId('tree-node-src')
    expect(srcNode.querySelector('svg')).toBeInTheDocument()
  })

  it('空文件树显示空状态', () => {
    render(
      <ExplorerPanel
        fileTree={[]}
        selectedFile={null}
        onFileSelect={vi.fn()}
      />
    )

    expect(screen.getByText(/暂无文件/i)).toBeInTheDocument()
  })
})

describe('ExplorerPanel ResizeObserver 初始化', () => {
  it('首次渲染空文件树后填充数据，ResizeObserver 仍能正确获取容器高度', async () => {
    // 用可追踪的 ResizeObserver mock
    let observerCallback: ResizeObserverCallback | null = null
    const mockObserve = vi.fn()
    const mockDisconnect = vi.fn()
    const OriginalRO = global.ResizeObserver
    global.ResizeObserver = class {
      constructor(cb: ResizeObserverCallback) { observerCallback = cb }
      observe = mockObserve
      unobserve = vi.fn()
      disconnect = mockDisconnect
    }

    const { rerender } = render(
      <ExplorerPanel fileTree={[]} selectedFile={null} onFileSelect={vi.fn()} />
    )

    // 修复后：containerRef 始终挂载，空文件树时 observe 也会被调用
    expect(mockObserve).toHaveBeenCalled()

    // 填充文件树数据
    rerender(
      <ExplorerPanel fileTree={mockFileTree} selectedFile={null} onFileSelect={vi.fn()} />
    )

    // 同一个 observer 实例仍然在监听，不需要重新创建
    expect(mockObserve).toHaveBeenCalledTimes(1)

    global.ResizeObserver = OriginalRO
  })

  it('容器不应产生独立滚动，由 Tree 虚拟滚动控制', () => {
    render(
      <ExplorerPanel
        fileTree={mockFileTree}
        selectedFile={null}
        onFileSelect={vi.fn()}
      />
    )

    const panel = screen.getByTestId('explorer-panel')
    // overflow 不能是 auto，否则与 react-arborist 虚拟滚动产生双重滚动
    expect(panel.className).not.toContain('overflow-auto')
    // 应该由 overflow-hidden 阻止外层滚动，Tree 内部自行管理滚动
    expect(panel.className).toContain('overflow-hidden')
  })
})

describe('MVP-RE-5.3: ExplorerPanel 点击文件', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('双击文件节点 → onFileSelect 回调收到文件路径', async () => {
    const user = userEvent.setup()
    const onFileSelect = vi.fn()
    render(
      <ExplorerPanel
        fileTree={mockFileTree}
        selectedFile={null}
        onFileSelect={onFileSelect}
      />
    )

    // 双击 README.md 文件触发 onActivate
    await user.dblClick(screen.getByText('README.md'))
    expect(onFileSelect).toHaveBeenCalledWith('README.md')
  })

  it('双击目录节点不触发 onFileSelect', async () => {
    const user = userEvent.setup()
    const onFileSelect = vi.fn()
    render(
      <ExplorerPanel
        fileTree={mockFileTree}
        selectedFile={null}
        onFileSelect={onFileSelect}
      />
    )

    await user.dblClick(screen.getByText('src'))
    // 目录双击只展开/折叠，不应触发文件选择
    expect(onFileSelect).not.toHaveBeenCalled()
  })

  it('点击文件夹节点 → 文件夹展开显示子节点', async () => {
    render(
      <ExplorerPanel
        fileTree={mockFileTree}
        selectedFile={null}
        onFileSelect={vi.fn()}
      />
    )

    // src 文件夹初始折叠，子文件不可见
    const srcNode = screen.getByTestId('tree-node-src')
    expect(screen.queryByText('main.ts')).not.toBeInTheDocument()

    // 点击 src 文件夹
    fireEvent.click(srcNode)

    // 文件夹展开，子文件可见
    await waitFor(() => {
      expect(screen.getByText('main.ts')).toBeInTheDocument()
    })
  })

  it('点击已展开的文件夹 → 文件夹折叠隐藏子节点', async () => {
    render(
      <ExplorerPanel
        fileTree={mockFileTree}
        selectedFile={null}
        onFileSelect={vi.fn()}
      />
    )

    // 先展开 src 文件夹
    const srcNode = screen.getByTestId('tree-node-src')
    fireEvent.click(srcNode)
    await waitFor(() => {
      expect(screen.getByText('main.ts')).toBeInTheDocument()
    })

    // 再次点击 → 折叠
    fireEvent.click(srcNode)
    await waitFor(() => {
      expect(screen.queryByText('main.ts')).not.toBeInTheDocument()
    })
    expect(screen.queryByText('main.ts')).not.toBeInTheDocument()
  })
})

describe('MVP-RE-5.4: useFileTab — 加载仓库列表', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('选中项目后加载仓库列表、默认选中第一个仓库、加载文件树', async () => {
    vi.spyOn(apiModule, 'apiGet').mockImplementation((url: string) => {
      // 精确匹配：仓库列表 URL 不包含子路径
      if (url === '/projects/proj-1/repos') return Promise.resolve(mockRepos)
      if (url === '/projects/proj-1/repos/orbion/tree') return Promise.resolve(mockFileTree)
      if (url === '/projects/proj-1/repos/orbion/status') return Promise.resolve(mockGitStatus)
      return Promise.resolve([])
    })

    const { result } = renderHook(() => useFileTab({ projectId: 'proj-1' }))

    await waitFor(() => {
      expect(result.current.repos).toEqual(mockRepos)
    })

    // 默认选中第一个仓库
    expect(result.current.selectedRepo).toBe('orbion')

    // 文件树被加载
    await waitFor(() => {
      expect(result.current.fileTree).toEqual(mockFileTree)
    })
  })
})

describe('MVP-RE-5.5: useFileTab — 切换仓库', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('切换仓库 → 文件树和 git status 重新加载', async () => {
    const repo1Tree: FileNode[] = [{ path: 'a.ts', type: 'file', name: 'a.ts' }]
    const repo2Tree: FileNode[] = [{ path: 'b.ts', type: 'file', name: 'b.ts' }]
    const frontendStatus: GitStatusResult = { staged: [], changes: [] }

    vi.spyOn(apiModule, 'apiGet').mockImplementation((url: string) => {
      if (url === '/projects/proj-1/repos') return Promise.resolve(mockRepos)
      if (url.includes('/repos/orbion/tree')) return Promise.resolve(repo1Tree)
      if (url.includes('/repos/frontend/tree')) return Promise.resolve(repo2Tree)
      if (url.includes('/repos/orbion/status')) return Promise.resolve(mockGitStatus)
      if (url.includes('/repos/frontend/status')) return Promise.resolve(frontendStatus)
      return Promise.resolve([])
    })

    const { result } = renderHook(() => useFileTab({ projectId: 'proj-1' }))

    await waitFor(() => {
      expect(result.current.fileTree).toEqual(repo1Tree)
    })

    // 切换到 frontend 仓库
    act(() => {
      result.current.selectRepo('frontend')
    })

    await waitFor(() => {
      expect(result.current.selectedRepo).toBe('frontend')
      expect(result.current.fileTree).toEqual(repo2Tree)
      expect(result.current.gitStatus).toEqual(frontendStatus)
    })
  })
})

describe('MVP-RE-5.6: useFileTab — 加载文件内容', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('selectFile → 文件内容加载到 fileContent', async () => {
    vi.spyOn(apiModule, 'apiGet').mockImplementation((url: string) => {
      if (url === '/projects/proj-1/repos') return Promise.resolve(mockRepos)
      if (url === '/projects/proj-1/repos/orbion/tree') return Promise.resolve(mockFileTree)
      if (url === '/projects/proj-1/repos/orbion/status') return Promise.resolve(mockGitStatus)
      if (url.includes('/files')) return Promise.resolve({ path: 'README.md', content: '# Hello' })
      return Promise.resolve([])
    })

    const { result } = renderHook(() => useFileTab({ projectId: 'proj-1' }))

    await waitFor(() => {
      expect(result.current.repos.length).toBeGreaterThan(0)
    })

    act(() => {
      result.current.selectFile('README.md')
    })

    await waitFor(() => {
      expect(result.current.fileContent).toBe('# Hello')
    })
  })
})

describe('MVP-RE-5.7: useFileTab — 保存文件', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('修改 fileContent 后 saveFile → apiPutRaw 被调用、isDirty 变 false、git status 刷新', async () => {
    vi.spyOn(apiModule, 'apiGet').mockImplementation((url: string) => {
      if (url === '/projects/proj-1/repos') return Promise.resolve(mockRepos)
      if (url === '/projects/proj-1/repos/orbion/tree') return Promise.resolve(mockFileTree)
      if (url === '/projects/proj-1/repos/orbion/status') return Promise.resolve(mockGitStatus)
      if (url.includes('/files')) return Promise.resolve({ path: 'README.md', content: '# Hello', mtime: 1234567890 })
      return Promise.resolve([])
    })
    vi.spyOn(apiModule, 'apiPutRaw').mockResolvedValue({
      ok: true,
      data: { path: 'README.md', content: '# Hello World', mtime: 1234567891 },
    })

    const { result } = renderHook(() => useFileTab({ projectId: 'proj-1' }))

    await waitFor(() => {
      expect(result.current.repos.length).toBeGreaterThan(0)
    })

    // 先选中文件
    act(() => {
      result.current.selectFile('README.md')
    })

    await waitFor(() => {
      expect(result.current.fileContent).toBe('# Hello')
    })

    // 修改内容 → isDirty 变 true
    act(() => {
      result.current.setFileContent('# Hello World')
    })

    await waitFor(() => {
      expect(result.current.isDirty).toBe(true)
    })

    // 保存
    await act(async () => {
      await result.current.saveFile()
    })

    // apiPutRaw 被调用
    expect(apiModule.apiPutRaw).toHaveBeenCalledWith(
      expect.stringContaining('/files?path=README.md'),
      expect.objectContaining({ content: '# Hello World' })
    )

    // isDirty 变 false
    expect(result.current.isDirty).toBe(false)

    // git status 被刷新（saveFile 后再次调用 apiGet status）
    expect(apiModule.apiGet).toHaveBeenCalledWith(
      '/projects/proj-1/repos/orbion/status'
    )
  })
})

describe('MVP-RE-5.8: useFileTab — 切换项目重置状态', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('切换项目 → 仓库列表、文件树、文件内容、git status 全部重新加载', async () => {
    // 必须在 renderHook 之前设置 mock
    vi.spyOn(apiModule, 'apiGet').mockImplementation((url: string) => {
      if (url === '/projects/proj-1/repos') return Promise.resolve(mockRepos)
      if (url === '/projects/proj-2/repos') return Promise.resolve([{ name: 'other-repo' }])
      if (url === '/projects/proj-1/repos/orbion/tree') return Promise.resolve(mockFileTree)
      if (url === '/projects/proj-1/repos/orbion/status') return Promise.resolve(mockGitStatus)
      if (url === '/projects/proj-2/repos/other-repo/tree') return Promise.resolve([])
      if (url === '/projects/proj-2/repos/other-repo/status') return Promise.resolve({ staged: [], changes: [] })
      if (url.includes('/files')) return Promise.resolve({ path: 'README.md', content: '# Hello' })
      return Promise.resolve([])
    })

    const { result, rerender } = renderHook(
      ({ projectId }: { projectId: string | null }) => useFileTab({ projectId }),
      { initialProps: { projectId: 'proj-1' } }
    )

    // 加载 proj-1 数据
    await waitFor(() => {
      expect(result.current.repos).toEqual(mockRepos)
    })

    // 选中文件
    act(() => {
      result.current.selectFile('README.md')
    })
    await waitFor(() => {
      expect(result.current.fileContent).toBe('# Hello')
    })

    // 切换项目
    rerender({ projectId: 'proj-2' })

    await waitFor(() => {
      // 仓库列表应重新加载
      expect(result.current.repos).toEqual([{ name: 'other-repo' }])
      // 文件树应重新加载
      expect(result.current.fileTree).toEqual([])
      // git status 应重新加载
      expect(result.current.gitStatus).toEqual({ staged: [], changes: [] })
    })

    // 文件内容应重置
    expect(result.current.fileContent).toBeNull()
    expect(result.current.selectedFile).toBeNull()
  })
})

describe('useFileTab — refreshKey 触发重新获取', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('refreshKey 变化 → 仓库列表和文件树重新获取', async () => {
    const initialRepos: RepoInfo[] = [{ name: 'orbion' }]
    const updatedRepos: RepoInfo[] = [{ name: 'orbion' }, { name: 'new-repo' }]
    const initialTree: FileNode[] = [{ path: 'a.ts', type: 'file', name: 'a.ts' }]
    const updatedTree: FileNode[] = [{ path: 'a.ts', type: 'file', name: 'a.ts' }, { path: 'b.ts', type: 'file', name: 'b.ts' }]

    let callCount = 0
    vi.spyOn(apiModule, 'apiGet').mockImplementation((url: string) => {
      if (url === '/projects/proj-1/repos') {
        callCount++
        return Promise.resolve(callCount === 1 ? initialRepos : updatedRepos)
      }
      if (url === '/projects/proj-1/repos/orbion/tree') {
        return Promise.resolve(callCount <= 1 ? initialTree : updatedTree)
      }
      if (url === '/projects/proj-1/repos/orbion/status') {
        return Promise.resolve({ staged: [], changes: [] })
      }
      return Promise.resolve([])
    })

    const { result, rerender } = renderHook(
      ({ refreshKey }: { refreshKey: number }) => useFileTab({ projectId: 'proj-1', refreshKey }),
      { initialProps: { refreshKey: 0 } }
    )

    // 初始加载
    await waitFor(() => {
      expect(result.current.repos).toEqual(initialRepos)
      expect(result.current.fileTree).toEqual(initialTree)
    })

    const reposCallCountBefore = apiModule.apiGet.mock.calls.filter(
      (args: [string]) => args[0] === '/projects/proj-1/repos'
    ).length

    // refreshKey 变化 → 重新获取
    rerender({ refreshKey: 1 })

    await waitFor(() => {
      expect(result.current.repos).toEqual(updatedRepos)
      expect(result.current.fileTree).toEqual(updatedTree)
    })

    // 确认 repos API 被再次调用
    const reposCallCountAfter = apiModule.apiGet.mock.calls.filter(
      (args: [string]) => args[0] === '/projects/proj-1/repos'
    ).length
    expect(reposCallCountAfter).toBeGreaterThan(reposCallCountBefore)
  })

  it('refreshKey 不变 → 不额外请求', async () => {
    vi.spyOn(apiModule, 'apiGet').mockImplementation((url: string) => {
      if (url === '/projects/proj-1/repos') return Promise.resolve(mockRepos)
      if (url === '/projects/proj-1/repos/orbion/tree') return Promise.resolve(mockFileTree)
      if (url === '/projects/proj-1/repos/orbion/status') return Promise.resolve(mockGitStatus)
      return Promise.resolve([])
    })

    const { result, rerender } = renderHook(
      ({ refreshKey }: { refreshKey: number }) => useFileTab({ projectId: 'proj-1', refreshKey }),
      { initialProps: { refreshKey: 0 } }
    )

    await waitFor(() => {
      expect(result.current.repos).toEqual(mockRepos)
    })

    const callCountBefore = apiModule.apiGet.mock.calls.length

    // rerender 但 refreshKey 不变
    rerender({ refreshKey: 0 })

    // 不应有新的 API 请求
    expect(apiModule.apiGet.mock.calls.length).toBe(callCountBefore)
  })
})
