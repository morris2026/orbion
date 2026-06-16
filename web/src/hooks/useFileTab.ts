import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { apiGet, apiPut, apiPost } from '@/lib/api'
import type { FileNode, RepoInfo, GitStatusResult } from '@/types/api'

export type ViewMode = 'edit' | 'diff'

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
  const isDirty = useMemo(
    () => fileContent !== null && originalContent !== null && fileContent !== originalContent,
    [fileContent, originalContent]
  )
  const [gitStatus, setGitStatus] = useState<GitStatusResult>({ staged: [], changes: [] })
  const [viewMode, setViewMode] = useState<ViewMode>('edit')

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

    apiGet<{ path: string; content: string }>(`/projects/${projectId}/repos/${selectedRepo}/files`, { path })
      .then((result) => {
        if (fetchIdRef.current !== thisFetch) return
        setFileContent(result.content)
        setOriginalContent(result.content)
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

    // 工作区版本（modified）
    apiGet<{ path: string; content: string }>(`/projects/${projectId}/repos/${selectedRepo}/files`, { path })
      .then((result) => {
        if (fetchIdRef.current !== thisFetch) return
        setFileContent(result.content)
      })
      .catch(() => {
        if (fetchIdRef.current !== thisFetch) return
        setFileContent(null)
      })

    // HEAD 版本（original for DiffEditor）
    apiGet<{ path: string; content: string }>(`/projects/${projectId}/repos/${selectedRepo}/files`, { path, ref: 'HEAD' })
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

  const saveFile = useCallback(async () => {
    if (!projectId || !selectedRepo || !selectedFile || fileContent === null) return

    await apiPut(`/projects/${projectId}/repos/${selectedRepo}/files?path=${encodeURIComponent(selectedFile)}`, {
      content: fileContent,
    })

    setOriginalContent(fileContent)
    refreshGitStatus()
  }, [projectId, selectedRepo, selectedFile, fileContent, refreshGitStatus])

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
    selectRepo,
    selectFile,
    selectFileFromSC,
    saveFile,
    stageFiles,
    unstageFiles,
    commitChanges,
  }
}
