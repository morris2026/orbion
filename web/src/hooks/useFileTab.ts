import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { apiGet, apiPost, apiPutRaw } from '@/lib/api'
import type { FileNode, RepoInfo, GitStatusResult, WorktreeInfo } from '@/types/api'

export type ViewMode = 'edit' | 'diff'

/** 30 分钟阈值（毫秒）：打开超过此时长未保存，提示重新加载（设计 §5.2.2 适用边界） */
const STALE_THRESHOLD_MS = 30 * 60 * 1000

/** 409 Conflict 响应体（后端 FileConflictResponse） */
export interface FileConflictInfo {
  path: string
  merged_content: string
  conflict_markers: string[]
  current_mtime: number
}

export interface UseFileTabOptions {
  projectId: string | null
  refreshKey?: number
}

export function useFileTab({ projectId, refreshKey }: UseFileTabOptions) {
  const [repos, setRepos] = useState<RepoInfo[]>([])
  const [selectedRepo, setSelectedRepo] = useState<string | null>(null)
  const [worktrees, setWorktrees] = useState<WorktreeInfo[]>([])
  const [selectedWorktreeId, setSelectedWorktreeId] = useState<string | null>(null)
  const [fileTree, setFileTree] = useState<FileNode[]>([])
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [fileContent, setFileContent] = useState<string | null>(null)
  const [originalContent, setOriginalContent] = useState<string | null>(null)
  /** 打开文件时记录的 mtime（Unix 秒），保存时作为 expected_mtime 回传 */
  const fileMtimeRef = useRef<number | null>(null)
  /** 打开文件时的时间戳（毫秒），用于 30 分钟过期检测 */
  const loadedAtRef = useRef<number | null>(null)
  /** 用户主动声明文件已过期需重新加载（点确认后置 true，阻止重复弹窗） */
  const [staleAcknowledged, setStaleAcknowledged] = useState(false)
  const isDirty = useMemo(
    () => fileContent !== null && originalContent !== null && fileContent !== originalContent,
    [fileContent, originalContent]
  )
  const [gitStatus, setGitStatus] = useState<GitStatusResult>({ staged: [], changes: [] })
  const [viewMode, setViewMode] = useState<ViewMode>('edit')
  /** 409 冲突信息（非 null 时显示冲突对话框） */
  const [conflictInfo, setConflictInfo] = useState<FileConflictInfo | null>(null)

  const prevProjectIdRef = useRef<string | null>(null)
  // 防止竞态：快速切换文件时旧响应覆盖新响应
  const fetchIdRef = useRef(0)

  // changeCounts：基于当前 git status 计算选中仓库的变更数
  const changeCounts = useMemo(() => {
    if (!selectedRepo) return {}
    const staged = gitStatus?.staged ?? []
    const changes = gitStatus?.changes ?? []
    const count = staged.length + changes.length
    return { [selectedRepo]: count }
  }, [selectedRepo, gitStatus])

  // main worktree 只读（设计 §10.1：main 对所有用户只读）
  // 无 worktree 数据时不强制只读（兼容旧项目无 worktree 的场景）
  const selectedWorktree = worktrees.find((w) => w.id === selectedWorktreeId) ?? null
  const isReadOnly = worktrees.length > 0 && selectedWorktree?.worktree_type === 'main'

  const selectWorktree = useCallback((id: string) => {
    setSelectedWorktreeId(id)
    setSelectedFile(null)
    setFileContent(null)
    setOriginalContent(null)
    fileMtimeRef.current = null
    loadedAtRef.current = null
    setStaleAcknowledged(false)
    setConflictInfo(null)
    setViewMode('edit')
  }, [])

  // 当前选中的 worktree 的 API 上下文路径
  // main worktree → 用旧 repo 端点（与非 bare 仓库兼容）
  // task worktree → 用 worktree 上下文端点（§13.2）
  const fileApiBase = useMemo(() => {
    if (!projectId) return null
    // task worktree → 用 worktree 上下文端点
    if (selectedWorktree?.worktree_type === 'task' && selectedWorktreeId) {
      return `/projects/${projectId}/worktrees/${selectedWorktreeId}`
    }
    // main worktree 或无 worktree 数据 → 旧 repo 端点（兼容旧项目）
    if (selectedRepo) {
      return `/projects/${projectId}/repos/${selectedRepo}`
    }
    return null
  }, [projectId, selectedWorktree, selectedWorktreeId, selectedRepo])

  // 加载仓库列表 + worktree 列表
  useEffect(() => {
    if (!projectId) {
      setRepos([])
      setSelectedRepo(null)
      setFileTree([])
      setSelectedFile(null)
      setFileContent(null)
      setOriginalContent(null)
      setGitStatus({ staged: [], changes: [] })
      setViewMode('edit')
      setWorktrees([])
      setSelectedWorktreeId(null)
      return
    }

    apiGet<RepoInfo[]>(`/projects/${projectId}/repos`)
      .then((repoList) => {
        setRepos(repoList)
        if (repoList.length > 0) {
          setSelectedRepo(repoList[0].name)
        } else {
          setSelectedRepo(null)
        }
      })
      .catch(() => {
        setRepos([])
        setSelectedRepo(null)
      })

    // 加载 worktree 列表（设计 §4 worktree 选择器）
    apiGet<WorktreeInfo[]>(`/projects/${projectId}/worktrees`)
      .then((wtList) => {
        setWorktrees(wtList)
        // 默认选中 main worktree
        const mainWt = wtList.find((w) => w.worktree_type === 'main')
        setSelectedWorktreeId(mainWt ? mainWt.id : (wtList.length > 0 ? wtList[0].id : null))
      })
      .catch(() => {
        setWorktrees([])
        setSelectedWorktreeId(null)
      })

    if (prevProjectIdRef.current !== null && prevProjectIdRef.current !== projectId) {
      setSelectedFile(null)
      setFileContent(null)
      setOriginalContent(null)

      setViewMode('edit')
    }
    prevProjectIdRef.current = projectId
  }, [projectId, refreshKey])

  // 加载文件树和 git status（切换 worktree 时重新加载）
  useEffect(() => {
    if (!fileApiBase) {
      setFileTree([])
      setGitStatus({ staged: [], changes: [] })
      return
    }

    // worktree 上下文用 /files/tree，repo 上下文用 /tree
    const treeUrl = selectedWorktree?.worktree_type === 'task'
      ? `${fileApiBase}/files/tree`
      : `${fileApiBase}/tree`
    apiGet<FileNode[]>(treeUrl)
      .then(setFileTree)
      .catch(() => setFileTree([]))

    // git status 仅 repo 上下文有端点（worktree SC 端点待 step 6+ 扩展）
    if (selectedWorktree?.worktree_type !== 'task') {
      apiGet<GitStatusResult>(`${fileApiBase}/status`)
        .then(setGitStatus)
        .catch(() => setGitStatus({ staged: [], changes: [] }))
    } else {
      setGitStatus({ staged: [], changes: [] })
    }
  }, [fileApiBase, selectedWorktree, refreshKey])

  const selectRepo = useCallback((repoName: string) => {
    setSelectedRepo(repoName)
    setSelectedFile(null)
    setFileContent(null)
    setOriginalContent(null)
    setViewMode('edit')
    fileMtimeRef.current = null
    loadedAtRef.current = null
    setStaleAcknowledged(false)
    setConflictInfo(null)
  }, [])

  // Explorer 点击文件 → 编辑模式
  const selectFile = useCallback((path: string) => {
    if (!fileApiBase) return

    const thisFetch = ++fetchIdRef.current
    setSelectedFile(path)
    setViewMode('edit')
    setFileContent(null)
    setOriginalContent(null)
    fileMtimeRef.current = null
    loadedAtRef.current = null
    setStaleAcknowledged(false)
    setConflictInfo(null)

    apiGet<{ path: string; content: string; mtime?: number }>(
      `${fileApiBase}/files`,
      { path }
    )
      .then((result) => {
        if (fetchIdRef.current !== thisFetch) return
        setFileContent(result.content)
        setOriginalContent(result.content)
        fileMtimeRef.current = result.mtime ?? null
        loadedAtRef.current = Date.now()
      })
      .catch(() => {
        if (fetchIdRef.current !== thisFetch) return
        setFileContent(null)
        setOriginalContent(null)
      })
  }, [fileApiBase])

  // Source Control 点击文件 → Diff 模式
  const selectFileFromSC = useCallback((path: string) => {
    if (!fileApiBase) return

    const thisFetch = ++fetchIdRef.current
    setSelectedFile(path)
    setViewMode('diff')
    setFileContent(null)
    setOriginalContent(null)
    fileMtimeRef.current = null
    loadedAtRef.current = null
    setStaleAcknowledged(false)
    setConflictInfo(null)

    // 工作区版本（modified）
    apiGet<{ path: string; content: string; mtime?: number }>(
      `${fileApiBase}/files`,
      { path }
    )
      .then((result) => {
        if (fetchIdRef.current !== thisFetch) return
        setFileContent(result.content)
        fileMtimeRef.current = result.mtime ?? null
        loadedAtRef.current = Date.now()
      })
      .catch(() => {
        if (fetchIdRef.current !== thisFetch) return
        setFileContent(null)
      })

    // HEAD 版本（original for DiffEditor）— 仅 repo 上下文有 ref=HEAD 支持
    if (selectedWorktree?.worktree_type !== 'task') {
      apiGet<{ path: string; content: string }>(
        `${fileApiBase}/files`,
        { path, ref: 'HEAD' }
      )
        .then((result) => {
          if (fetchIdRef.current !== thisFetch) return
          setOriginalContent(result.content)
        })
        .catch(() => {
          if (fetchIdRef.current !== thisFetch) return
          setOriginalContent('')
        })
    }
  }, [fileApiBase, selectedWorktree])

  const refreshGitStatus = useCallback(() => {
    if (!fileApiBase || selectedWorktree?.worktree_type === 'task') return
    apiGet<GitStatusResult>(`${fileApiBase}/status`)
      .then(setGitStatus)
      .catch(() => {})
  }, [fileApiBase, selectedWorktree])

  /** 重新加载当前文件（放弃当前编辑） */
  const reloadFile = useCallback(async () => {
    if (!fileApiBase || !selectedFile) return
    const result = await apiGet<{ path: string; content: string; mtime?: number }>(
      `${fileApiBase}/files`,
      { path: selectedFile }
    )
    setFileContent(result.content)
    setOriginalContent(result.content)
    fileMtimeRef.current = result.mtime ?? null
    loadedAtRef.current = Date.now()
    setStaleAcknowledged(false)
    setConflictInfo(null)
  }, [fileApiBase, selectedFile])

  /**
   * 保存文件：发送 expected_mtime + original_content，处理 409 冲突
   * - expected_mtime 与磁盘一致 → 直接保存
   * - expected_mtime 过期 → 后端三方合并；成功 200 / 冲突 409
   * - 30 分钟未保存 → 提示重新加载（设计 §5.2.2 适用边界）
   * - force=true → 跳过 mtime 检测，直接覆盖（"覆盖"选项用）
   */
  const saveFile = useCallback(
    async (opts?: { force?: boolean }) => {
      if (!fileApiBase || !selectedFile || fileContent === null) return

      // 30 分钟过期检测（非 force 路径）
      if (!opts?.force && loadedAtRef.current !== null && !staleAcknowledged) {
        const elapsed = Date.now() - loadedAtRef.current
        if (elapsed > STALE_THRESHOLD_MS) {
          // 标记过期，UI 层会展示提示对话框
          setStaleAcknowledged(true)
          return
        }
      }

      // force=true 时跳过 mtime/original（直接覆盖）
      const payload: Record<string, unknown> = { content: fileContent }
      if (!opts?.force) {
        if (fileMtimeRef.current !== null) {
          payload.expected_mtime = fileMtimeRef.current
        }
        if (originalContent !== null) {
          payload.original_content = originalContent
        }
      }

      const result = await apiPutRaw<{ path: string; content: string; mtime?: number }>(
        `${fileApiBase}/files?path=${encodeURIComponent(selectedFile)}`,
        payload
      )

      if (result.ok) {
        // 200：保存成功，更新 originalContent + mtime
        setOriginalContent(result.data.content)
        fileMtimeRef.current = result.data.mtime ?? fileMtimeRef.current
        loadedAtRef.current = Date.now()
        setStaleAcknowledged(false)
        setConflictInfo(null)
        refreshGitStatus()
        return
      }

      if (result.status === 409) {
        // 三方合并冲突：展示冲突对话框
        // 同时清掉 staleAcknowledged，避免 StaleFilePrompt 与 ConflictDialog 叠加
        const conflict = result.data as FileConflictInfo
        setStaleAcknowledged(false)
        setConflictInfo(conflict)
        return
      }

      // 其他错误：抛出让调用方处理
      throw new Error(`保存失败: ${result.status}`)
    },
    [
      fileApiBase,
      selectedFile,
      fileContent,
      originalContent,
      staleAcknowledged,
      refreshGitStatus,
    ]
  )

  /**
   * 冲突对话框：用户选择"对比并合并"
   * MVP 偏差：设计 §5.2.3 要求 Monaco Diff Editor 展示冲突，当前实现退化为
   * edit 模式 + 冲突标记（<<<<<<< / ======= / >>>>>>>）可见。用户手动删除标记后重存。
   * Why：Diff Editor 需要 originalContent=磁盘版本 / fileContent=merged_content 的
   * 双输入，与现有 selectFileFromSC 的 diff 模式状态管理冲突。MVP 接受退化，
   * SaaS 阶段引入专用冲突解决视图。
   */
  const resolveConflictManually = useCallback(() => {
    if (!conflictInfo) return
    setFileContent(conflictInfo.merged_content)
    setViewMode('edit')
    setConflictInfo(null)
  }, [conflictInfo])

  /** 冲突对话框：用户选择"覆盖"——用当前编辑覆盖磁盘 */
  const overwriteConflict = useCallback(async () => {
    setConflictInfo(null)
    await saveFile({ force: true })
  }, [saveFile])

  /** 冲突对话框：用户选择"取消"——保留编辑器内容 */
  const cancelConflict = useCallback(() => {
    setConflictInfo(null)
  }, [])

  const stageFiles = useCallback(async (paths: string[]) => {
    if (!projectId || !selectedRepo) return
    await apiPost(`/projects/${projectId}/repos/${selectedRepo}/stage`, { paths })
    refreshGitStatus()
  }, [fileApiBase, refreshGitStatus])

  const unstageFiles = useCallback(async (paths: string[]) => {
    if (!projectId || !selectedRepo) return
    await apiPost(`/projects/${projectId}/repos/${selectedRepo}/unstage`, { paths })
    refreshGitStatus()
  }, [fileApiBase, refreshGitStatus])

  const commitChanges = useCallback(async (message: string) => {
    if (!projectId || !selectedRepo) return
    await apiPost(`/projects/${projectId}/repos/${selectedRepo}/commit`, { message })
    refreshGitStatus()
  }, [fileApiBase, refreshGitStatus])

  return {
    repos,
    selectedRepo,
    worktrees,
    selectedWorktreeId,
    selectedWorktree,
    isReadOnly,
    fileTree,
    selectedFile,
    fileContent,
    setFileContent,
    originalContent,
    isDirty,
    gitStatus,
    changeCounts,
    viewMode,
    conflictInfo,
    staleAcknowledged,
    selectRepo,
    selectWorktree,
    selectFile,
    selectFileFromSC,
    saveFile,
    reloadFile,
    resolveConflictManually,
    overwriteConflict,
    cancelConflict,
    stageFiles,
    unstageFiles,
    commitChanges,
  }
}
