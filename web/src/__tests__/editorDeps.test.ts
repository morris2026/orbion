import { describe, it, expect } from 'vitest'

describe('MVP-RE-4.1: npm 包安装验证', () => {
  it('@monaco-editor/react 可导入', async () => {
    const mod = await import('@monaco-editor/react')
    expect(mod).toBeDefined()
  })

  it('monaco-editor 包已安装', async () => {
    // Why: monaco-editor 直接 import 会触发 worker 加载导致测试超时，
    // 改为验证包的 package.json 存在
    const pkg = await import('monaco-editor/package.json')
    expect(pkg.name).toBe('monaco-editor')
  })

  it('react-arborist 可导入', async () => {
    const mod = await import('react-arborist')
    expect(mod).toBeDefined()
  })

  it('react-markdown 可导入', async () => {
    const mod = await import('react-markdown')
    expect(mod).toBeDefined()
  })

  it('remark-gfm 可导入', async () => {
    const mod = await import('remark-gfm')
    expect(mod).toBeDefined()
  })
})
