import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// jsdom 不支持 scrollIntoView、ResizeObserver、getAnimations
Element.prototype.scrollIntoView = vi.fn()
global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
Element.prototype.getAnimations = vi.fn().mockReturnValue([])

import { RepoList } from '@/components/RepoList'
import { RepoStatus } from '@/components/RepoStatus'
import { SourceControlPanel } from '@/components/SourceControlPanel'
import type { RepoInfo, GitFileStatus } from '@/types/api'

const mockRepos: RepoInfo[] = [
  { name: 'orbion' },
  { name: 'frontend' },
  { name: 'docs' },
]

const mockChangeCounts: Record<string, number> = {
  orbion: 3,
  frontend: 1,
  docs: 0,
}

const mockStaged: GitFileStatus[] = [
  { path: 'src/new.ts', status: 'A' },
  { path: 'src/main.ts', status: 'M' },
]

const mockChanges: GitFileStatus[] = [
  { path: 'src/util.ts', status: 'M' },
  { path: 'src/helper.ts', status: 'M' },
]

describe('MVP-RE-7.1: RepoList 渲染', () => {
  it('传入仓库列表，显示所有仓库名和变更文件数 Badge', () => {
    render(
      <RepoList
        repos={mockRepos}
        selectedRepo="orbion"
        changeCounts={mockChangeCounts}
        onSelectRepo={vi.fn()}
      />
    )

    expect(screen.getByText('orbion')).toBeInTheDocument()
    expect(screen.getByText('frontend')).toBeInTheDocument()
    expect(screen.getByText('docs')).toBeInTheDocument()

    // 有变更的仓库显示 Badge
    expect(screen.getByTestId('repo-badge-orbion')).toHaveTextContent('3')
    expect(screen.getByTestId('repo-badge-frontend')).toHaveTextContent('1')
    // 变更数为 0 的仓库不显示 Badge
    expect(screen.queryByTestId('repo-badge-docs')).not.toBeInTheDocument()
  })
})

describe('MVP-RE-7.2: RepoList 选中仓库', () => {
  it('点击 frontend 仓库 → frontend 高亮；onSelectRepo 回调收到 "frontend"', async () => {
    const user = userEvent.setup()
    const onSelectRepo = vi.fn()
    render(
      <RepoList
        repos={mockRepos}
        selectedRepo="orbion"
        changeCounts={mockChangeCounts}
        onSelectRepo={onSelectRepo}
      />
    )

    // orbion 当前选中，显示高亮样式
    const orbionItem = screen.getByText('orbion').closest('li')!
    expect(orbionItem).toHaveClass('bg-muted')

    await user.click(screen.getByText('frontend'))
    expect(onSelectRepo).toHaveBeenCalledWith('frontend')
  })
})

describe('MVP-RE-7.3: 仓库列表高度自适应', () => {
  it('仓库列表容器使用 rem 单位的 maxHeight，随根字号缩放', () => {
    render(
      <SourceControlPanel
        repos={mockRepos}
        selectedRepo="orbion"
        gitStatus={{ staged: mockStaged, changes: mockChanges }}
        changeCounts={mockChangeCounts}
        onSelectRepo={vi.fn()}
        onStage={vi.fn()}
        onUnstage={vi.fn()}
        onCommit={vi.fn()}
        onFileSelect={vi.fn()}
      />
    )

    const repoContainer = screen.getByTestId('repo-list').parentElement!
    expect(repoContainer).toHaveStyle({ maxHeight: '8.75rem' })
  })

  it('仓库列表容器可滚动', () => {
    render(
      <SourceControlPanel
        repos={mockRepos}
        selectedRepo="orbion"
        gitStatus={{ staged: mockStaged, changes: mockChanges }}
        changeCounts={mockChangeCounts}
        onSelectRepo={vi.fn()}
        onStage={vi.fn()}
        onUnstage={vi.fn()}
        onCommit={vi.fn()}
        onFileSelect={vi.fn()}
      />
    )

    const repoContainer = screen.getByTestId('repo-list').parentElement!
    expect(repoContainer).toHaveClass('overflow-auto')
  })

  it('无拖拽分隔条', () => {
    render(
      <SourceControlPanel
        repos={mockRepos}
        selectedRepo="orbion"
        gitStatus={{ staged: mockStaged, changes: mockChanges }}
        changeCounts={mockChangeCounts}
        onSelectRepo={vi.fn()}
        onStage={vi.fn()}
        onUnstage={vi.fn()}
        onCommit={vi.fn()}
        onFileSelect={vi.fn()}
      />
    )

    expect(screen.queryByTestId('sc-separator')).not.toBeInTheDocument()
  })
})

describe('MVP-RE-7.4: RepoStatus 总标题栏折叠', () => {
  it('点击"变更"标题行 → 折叠下栏内容，文件列表和 Commit 输入框都隐藏', async () => {
    const user = userEvent.setup()
    render(
      <RepoStatus
        staged={mockStaged}
        changes={mockChanges}
        onStage={vi.fn()}
        onUnstage={vi.fn()}
        onCommit={vi.fn()}
        onFileSelect={vi.fn()}
      />
    )

    // 初始展开：文件可见
    expect(screen.getByText('src/new.ts')).toBeInTheDocument()
    expect(screen.getByText('src/util.ts')).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/commit message/i)).toBeInTheDocument()

    // 点击"变更"标题折叠
    await user.click(screen.getByText('变更'))
    expect(screen.queryByText('src/new.ts')).not.toBeInTheDocument()
    expect(screen.queryByText('src/util.ts')).not.toBeInTheDocument()
    expect(screen.queryByPlaceholderText(/commit message/i)).not.toBeInTheDocument()

    // 再次点击展开
    await user.click(screen.getByText('变更'))
    expect(screen.getByText('src/new.ts')).toBeInTheDocument()
  })

  it('折叠时显示 ChevronRight，展开时显示 ChevronDown', () => {
    render(
      <RepoStatus
        staged={mockStaged}
        changes={[]}
        onStage={vi.fn()}
        onUnstage={vi.fn()}
        onCommit={vi.fn()}
        onFileSelect={vi.fn()}
      />
    )

    // 初始展开：ChevronDown
    const titleRow = screen.getByText('变更').closest('button')!
    expect(titleRow.querySelector('.lucide-chevron-down')).toBeInTheDocument()

    // 点击折叠
    fireEvent.click(screen.getByText('变更'))
    expect(titleRow.querySelector('.lucide-chevron-right')).toBeInTheDocument()
  })
})

describe('MVP-RE-7.4b: RepoStatus — Staged 分组', () => {
  it('Staged Changes 分组显示 2 个文件，状态标识正确', () => {
    render(
      <RepoStatus
        staged={mockStaged}
        changes={[]}
        onStage={vi.fn()}
        onUnstage={vi.fn()}
        onCommit={vi.fn()}
        onFileSelect={vi.fn()}
      />
    )

    expect(screen.getByText('Staged Changes')).toBeInTheDocument()
    expect(screen.getByText('src/new.ts')).toBeInTheDocument()
    expect(screen.getByText('src/main.ts')).toBeInTheDocument()

    // 状态标识：A = 绿色，M = 黄色
    const statusA = screen.getByTestId('status-src/new.ts')
    expect(statusA).toHaveAttribute('data-status', 'A')
    expect(statusA).toHaveClass('text-green-500')

    const statusM = screen.getByTestId('status-src/main.ts')
    expect(statusM).toHaveAttribute('data-status', 'M')
    expect(statusM).toHaveClass('text-yellow-500')
  })
})

describe('MVP-RE-7.5b: RepoStatus — Changes 分组', () => {
  it('Changes 分组显示 2 个文件，状态标识 M 黄色', () => {
    render(
      <RepoStatus
        staged={[]}
        changes={mockChanges}
        onStage={vi.fn()}
        onUnstage={vi.fn()}
        onCommit={vi.fn()}
        onFileSelect={vi.fn()}
      />
    )

    expect(screen.getByText('Changes')).toBeInTheDocument()
    expect(screen.getByText('src/util.ts')).toBeInTheDocument()
    expect(screen.getByText('src/helper.ts')).toBeInTheDocument()

    const statusUtil = screen.getByTestId('status-src/util.ts')
    expect(statusUtil).toHaveAttribute('data-status', 'M')
    expect(statusUtil).toHaveClass('text-yellow-500')
  })
})

describe('MVP-RE-7.6: stage/unstage 操作', () => {
  it('点击 Changes 文件的 "+" 按钮 → onStage 回调收到文件路径', async () => {
    const user = userEvent.setup()
    const onStage = vi.fn()
    render(
      <RepoStatus
        staged={[]}
        changes={mockChanges}
        onStage={onStage}
        onUnstage={vi.fn()}
        onCommit={vi.fn()}
        onFileSelect={vi.fn()}
      />
    )

    await user.click(screen.getByRole('button', { name: /stage src\/util\.ts/i }))
    expect(onStage).toHaveBeenCalledWith(['src/util.ts'])
  })

  it('点击 Staged 文件的 "−" 按钮 → onUnstage 回调收到文件路径', async () => {
    const user = userEvent.setup()
    const onUnstage = vi.fn()
    render(
      <RepoStatus
        staged={mockStaged}
        changes={[]}
        onStage={vi.fn()}
        onUnstage={onUnstage}
        onCommit={vi.fn()}
        onFileSelect={vi.fn()}
      />
    )

    await user.click(screen.getByRole('button', { name: /unstage src\/new\.ts/i }))
    expect(onUnstage).toHaveBeenCalledWith(['src/new.ts'])
  })
})

describe('MVP-RE-7.7: commit 操作', () => {
  it('有 staged 文件，输入 commit message，点击 Commit → onCommit 回调收到 message；输入框清空', async () => {
    const user = userEvent.setup()
    const onCommit = vi.fn()
    render(
      <RepoStatus
        staged={mockStaged}
        changes={[]}
        onStage={vi.fn()}
        onUnstage={vi.fn()}
        onCommit={onCommit}
        onFileSelect={vi.fn()}
      />
    )

    const input = screen.getByPlaceholderText(/commit message/i)
    await user.type(input, 'fix: 修复bug')
    await user.click(screen.getByRole('button', { name: /commit/i }))

    expect(onCommit).toHaveBeenCalledWith('fix: 修复bug')
    expect(input).toHaveValue('')
  })
})

describe('MVP-RE-7.8: 点击变更文件', () => {
  it('点击 Changes 中的文件 → onFileSelect 回调收到文件路径', async () => {
    const user = userEvent.setup()
    const onFileSelect = vi.fn()
    render(
      <RepoStatus
        staged={[]}
        changes={mockChanges}
        onStage={vi.fn()}
        onUnstage={vi.fn()}
        onCommit={vi.fn()}
        onFileSelect={onFileSelect}
      />
    )

    await user.click(screen.getByText('src/util.ts'))
    expect(onFileSelect).toHaveBeenCalledWith('src/util.ts')
  })
})
