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
        collapsed={false}
        onToggleCollapse={vi.fn()}
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
        collapsed={false}
        onToggleCollapse={vi.fn()}
      />
    )

    // orbion 当前选中，显示高亮样式
    const orbionItem = screen.getByText('orbion').closest('li')!
    expect(orbionItem).toHaveClass('bg-muted')

    await user.click(screen.getByText('frontend'))
    expect(onSelectRepo).toHaveBeenCalledWith('frontend')
  })
})

describe('MVP-RE-7.3: RepoList 折叠', () => {
  it('点击折叠按钮 → onToggleCollapse 回调被调用', async () => {
    const user = userEvent.setup()
    const onToggleCollapse = vi.fn()
    render(
      <RepoList
        repos={mockRepos}
        selectedRepo="orbion"
        changeCounts={mockChangeCounts}
        onSelectRepo={vi.fn()}
        collapsed={false}
        onToggleCollapse={onToggleCollapse}
      />
    )

    await user.click(screen.getByRole('button', { name: /折叠/i }))
    expect(onToggleCollapse).toHaveBeenCalled()
  })

  it('折叠状态下仓库列表隐藏，显示展开按钮', () => {
    render(
      <RepoList
        repos={mockRepos}
        selectedRepo="orbion"
        changeCounts={mockChangeCounts}
        onSelectRepo={vi.fn()}
        collapsed={true}
        onToggleCollapse={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: /展开/i })).toBeInTheDocument()
    expect(screen.queryByText('orbion')).not.toBeInTheDocument()
  })
})

describe('MVP-RE-7.3a: 拖拽调高', () => {
  it('拖拽分隔条 → 上栏高度增加，下栏高度随之调整', () => {
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

    const separator = screen.getByTestId('sc-separator')
    const topPanel = screen.getByTestId('sc-top-panel')
    const bottomPanel = screen.getByTestId('repo-status').parentElement!

    // 初始高度 200px
    expect(topPanel).toHaveStyle({ height: '200px' })

    // 拖拽：mouseDown + mouseMove(向下50px) + mouseUp
    fireEvent.mouseDown(separator, { clientY: 100 })
    fireEvent.mouseMove(document, { clientY: 150 })
    fireEvent.mouseUp(document)

    // 上栏高度增加 50px
    expect(topPanel).toHaveStyle({ height: '250px' })
    // 下栏仍存在（flex-1 自动调整）
    expect(bottomPanel).toHaveClass('flex-1')
  })

  it('向上拖拽低于最小值 → 上栏高度截断为 50px', () => {
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

    const separator = screen.getByTestId('sc-separator')
    const topPanel = screen.getByTestId('sc-top-panel')

    // 初始 200px，向上拖 200px → 理论 0px，截断为 50px
    fireEvent.mouseDown(separator, { clientY: 100 })
    fireEvent.mouseMove(document, { clientY: -100 })
    fireEvent.mouseUp(document)

    expect(topPanel).toHaveStyle({ height: '50px' })
  })

  it('向下拖拽超过上限 → 上栏高度被截断', () => {
    // 模拟容器高度 300px 的场景：上限 = 300 - 100 = 200
    // 给容器设置固定高度让 clientHeight 有值
    const { container } = render(
      <div style={{ height: '300px' }}>
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
      </div>
    )

    const separator = screen.getByTestId('sc-separator')
    const topPanel = screen.getByTestId('sc-top-panel')
    const scPanel = container.querySelector('[data-testid="source-control-panel"]') as HTMLElement

    // mock clientHeight 为 300（jsdom 默认为 0）
    vi.spyOn(scPanel, 'clientHeight', 'get').mockReturnValue(300)

    // 初始 200px，向下拖 200px → 理论 400px，上限 200px，截断为 200px
    fireEvent.mouseDown(separator, { clientY: 100 })
    fireEvent.mouseMove(document, { clientY: 300 })
    fireEvent.mouseUp(document)

    // 上限 = 300 - 100 = 200，所以 400 被截断为 200
    expect(topPanel).toHaveStyle({ height: '200px' })
  })
})

describe('MVP-RE-7.4: RepoStatus — Staged 分组', () => {
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

describe('MVP-RE-7.5: RepoStatus — Changes 分组', () => {
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
