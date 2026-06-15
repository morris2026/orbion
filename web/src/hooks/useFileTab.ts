import { useState, useEffect, useCallback, useRef } from 'react'
import { apiGet, apiPut } from '@/lib/api'
import type { FileNode, RepoInfo, GitStatusResult } from '@/types/api'

export interface UseFileTabOptions {
  projectId: string | null
}

export function useFileTab({ projectId }: UseFileTabOptions) {
  const [repos, setRepos] = useState<RepoInfo[]>([])
  const [selectedRepo, setSelectedRepo] = useState<string | null>(null)
  const [fileTree, setFileTree] = useState<FileNode[]>([])
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [fileContent, setFileContent] = useState<string | null>(null)
  const [originalContent, setOriginalContent] = useState<string | null>(null)
  const [isDirty, setIsDirty] = useState(false)
  const [gitStatus, setGitStatus] = useState<GitStatusResult>({ staged: [], changes: [] })

  const prevProjectIdRef = useRef<string | null>(null)
  // 防止竞态：快速切换文件时旧响应覆盖新响应
  const fetchIdRef = useRef(0)

  // 加载仓库列表
  useEffect(() => {
    if (!projectId) {
      setRepos([])
      setSelectedRepo(null)
      setFileTree([])
      setSelectedFile(null)
      setFileContent(null)
      setOriginalContent(null)
      setIsDirty(false)
      setGitStatus({ staged: [], changes: [] })
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
      setIsDirty(false)
    }
    prevProjectIdRef.current = projectId
  }, [projectId])

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
  }, [projectId, selectedRepo])

  const selectRepo = useCallback((repoName: string) => {
    setSelectedRepo(repoName)
    setSelectedFile(null)
    setFileContent(null)
    setOriginalContent(null)
    setIsDirty(false)
  }, [])

  const selectFile = useCallback((path: string) => {
    if (!projectId || !selectedRepo) return

    // 递增 fetchId 防止竞态
    const thisFetch = ++fetchIdRef.current
    setSelectedFile(path)
    setIsDirty(false)

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

  const saveFile = useCallback(async () => {
    if (!projectId || !selectedRepo || !selectedFile || fileContent === null) return

    await apiPut(`/projects/${projectId}/repos/${selectedRepo}/files?path=${encodeURIComponent(selectedFile)}`, {
      content: fileContent,
    })

    setOriginalContent(fileContent)

    apiGet<GitStatusResult>(`/projects/${projectId}/repos/${selectedRepo}/status`)
      .then(setGitStatus)
      .catch(() => {})
  }, [projectId, selectedRepo, selectedFile, fileContent])

  // isDirty 由 fileContent 和 originalContent 派生
  useEffect(() => {
    setIsDirty(fileContent !== null && originalContent !== null && fileContent !== originalContent)
  }, [fileContent, originalContent])

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
    selectRepo,
    selectFile,
    saveFile,
  }
}
