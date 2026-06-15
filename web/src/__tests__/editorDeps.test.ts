import { describe, it, expect } from 'vitest'

describe('MVP-RE-4.1: npm 包安装验证', () => {
  it('@monaco-editor/react 可导入', async () => {
    const mod = await import('@monaco-editor/react')
    expect(mod).toBeDefined()
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
