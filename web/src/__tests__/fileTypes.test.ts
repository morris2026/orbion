import { describe, it, expect } from 'vitest'
import type { FileNode, RepoInfo, GitFileStatus, GitStatusResult, StageRequest, CommitRequest, FileContent, WriteFileRequest } from '@/types/api'

describe('MVP-RE-4.2a: 文件操作类型定义', () => {
  it('FileNode类型字段完整', () => {
    const node: FileNode = { path: 'src/main.ts', type: 'file', name: 'main.ts' }
    expect(node.path).toBe('src/main.ts')
    expect(node.type).toBe('file')
    expect(node.name).toBe('main.ts')
  })

  it('RepoInfo类型字段完整', () => {
    const repo: RepoInfo = { name: 'myrepo' }
    expect(repo.name).toBe('myrepo')
  })

  it('GitFileStatus类型字段完整', () => {
    const status: GitFileStatus = { path: 'README.md', status: 'M' }
    expect(status.path).toBe('README.md')
    expect(status.status).toBe('M')
  })

  it('GitStatusResult类型字段完整', () => {
    const result: GitStatusResult = {
      staged: [{ path: 'new.txt', status: 'A' }],
      changes: [{ path: 'README.md', status: 'M' }],
    }
    expect(result.staged).toHaveLength(1)
    expect(result.changes).toHaveLength(1)
  })

  it('StageRequest类型字段完整', () => {
    const req: StageRequest = { paths: ['README.md'] }
    expect(req.paths).toHaveLength(1)
  })

  it('CommitRequest类型字段完整', () => {
    const req: CommitRequest = { message: 'initial commit' }
    expect(req.message).toBe('initial commit')
  })

  it('FileContent类型字段完整', () => {
    const fc: FileContent = { path: 'README.md', content: '# hello' }
    expect(fc.path).toBe('README.md')
    expect(fc.content).toBe('# hello')
  })

  it('WriteFileRequest类型字段完整', () => {
    const req: WriteFileRequest = { content: 'new content' }
    expect(req.content).toBe('new content')
  })
})
