import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { apiGet, apiPost, apiPutRaw } from '@/lib/api'
import type { FileNode, RepoInfo, GitStatusResult } from '@/types/api'

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

  // 加载仓库列表
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

    if (prevProjectIdRef.current !== null && prevProjectIdRef.current !== projectId) {
      setSelectedFile(null)
      setFileContent(null)
      setOriginalContent(null)

      setViewMode('edit')
    }
    prevProjectIdRef.current = projectId
  }, [projectId, refreshKey])

  // 加载文件树和 git status
  useEffect(() => {
    if (!projectId || !selectedRepo) {
      setFileTree([])
      setGitStatus({ staged: [], changes: [] })
      return
    }

    apiGet<FileNode[]>(`/projects/${projectId}/repos/${selectedRepo}/tree`)
      .then(setFileTree)
      .catch(() => setFileTree([]))

    apiGet<GitStatusResult>(`/projects/${projectId}/repos/${selectedRepo}/status`)
      .then(setGitStatus)
      .catch(() => setGitStatus({ staged: [], changes: [] }))
  }, [projectId, selectedRepo, refreshKey])

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
    if (!projectId || !selectedRepo) return

    const thisFetch = ++fetchIdRef.current
    setSelectedFile(path)
    setViewMode('edit')
    // 先清空内容，isDirty 自动变 false；异步加载后同步更新
    setFileContent(null)
    setOriginalContent(null)
    fileMtimeRef.current = null
    loadedAtRef.current = null
    setStaleAcknowledged(false)
    setConflictInfo(null)

    apiGet<{ path: string; content: string; mtime?: number }>(
      `/projects/${projectId}/repos/${selectedRepo}/files`,
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
  }, [projectId, selectedRepo])

  // Source Control 点击文件 → Diff 模式
  const selectFileFromSC = useCallback((path: string) => {
    if (!projectId || !selectedRepo) return

    const thisFetch = ++fetchIdRef.current
    setSelectedFile(path)
    setViewMode('diff')
    // 先清空内容，isDirty 自动变 false
    setFileContent(null)
    setOriginalContent(null)
    fileMtimeRef.current = null
    loadedAtRef.current = null
    setStaleAcknowledged(false)
    setConflictInfo(null)

    // 工作区版本（modified）
    apiGet<{ path: string; content: string; mtime?: number }>(
      `/projects/${projectId}/repos/${selectedRepo}/files`,
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

    // HEAD 版本（original for DiffEditor）
    apiGet<{ path: string; content: string }>(
      `/projects/${projectId}/repos/${selectedRepo}/files`,
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
  }, [projectId, selectedRepo])

  const refreshGitStatus = useCallback(() => {
    if (!projectId || !selectedRepo) return
    apiGet<GitStatusResult>(`/projects/${projectId}/repos/${selectedRepo}/status`)
      .then(setGitStatus)
      .catch(() => {})
  }, [projectId, selectedRepo])

  /** 重新加载当前文件（放弃当前编辑） */
  const reloadFile = useCallback(async () => {
    if (!projectId || !selectedRepo || !selectedFile) return
    const result = await apiGet<{ path: string; content: string; mtime?: number }>(
      `/projects/${projectId}/repos/${selectedRepo}/files`,
      { path: selectedFile }
    )
    setFileContent(result.content)
    setOriginalContent(result.content)
    fileMtimeRef.current = result.mtime ?? null
    loadedAtRef.current = Date.now()
    setStaleAcknowledged(false)
    setConflictInfo(null)
  }, [projectId, selectedRepo, selectedFile])

  /**
   * 保存文件：发送 expected_mtime + original_content，处理 409 冲突
   * - expected_mtime 与磁盘一致 → 直接保存
   * - expected_mtime 过期 → 后端三方合并；成功 200 / 冲突 409
   * - 30 分钟未保存 → 提示重新加载（设计 §5.2.2 适用边界）
   * - force=true → 跳过 mtime 检测，直接覆盖（"覆盖"选项用）
   */
  const saveFile = useCallback(
    async (opts?: { force?: boolean }) => {
      if (!projectId || !selectedRepo || !selectedFile || fileContent === null) return

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
        `/projects/${projectId}/repos/${selectedRepo}/files?path=${encodeURIComponent(selectedFile)}`,
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
      projectId,
      selectedRepo,
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
  }, [projectId, selectedRepo, refreshGitStatus])

  const unstageFiles = useCallback(async (paths: string[]) => {
    if (!projectId || !selectedRepo) return
    await apiPost(`/projects/${projectId}/repos/${selectedRepo}/unstage`, { paths })
    refreshGitStatus()
  }, [projectId, selectedRepo, refreshGitStatus])

  const commitChanges = useCallback(async (message: string) => {
    if (!projectId || !selectedRepo) return
    await apiPost(`/projects/${projectId}/repos/${selectedRepo}/commit`, { message })
    refreshGitStatus()
  }, [projectId, selectedRepo, refreshGitStatus])

  return {
    repos,
    selectedRepo,
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
