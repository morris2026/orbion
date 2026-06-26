/**
 * Bug 复现：行内 code 渲染保留了反引号
 *
 * 根因：@tailwindcss/typography 默认给 `.prose code::before` 和 `code::after`
 * 设 `content: '"`"'`，会自动在行内 code 前后渲染一个反引号。
 * 项目自定义样式只覆盖了颜色/背景，未覆盖伪元素 content。
 *
 * 设计目标：行内 `code` 渲染为带样式的 <code>，前后不显示反引号；
 * 多行代码块 `<pre><code>` 默认就是 content: none，不受影响。
 *
 * 测试策略：CSS 是声明性资源，jsdom 不解析 Tailwind 构建产物，
 * 因此直接断言源码中存在「针对该伪元素的规则体且包含 content: none」。
 * 接受两种合法写法：单独规则 `.prose code::before { content: none }`
 * 或合并选择器 `.prose code::before, .prose code::after { content: none }`。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const cssPath = resolve(__dirname, '../index.css')
const cssContent = readFileSync(cssPath, 'utf8')

/** 从 CSS 源码中提取「选择器列表 => 规则体」的映射（不支持嵌套，当前项目无嵌套 CSS） */
function extractRuleMap(css: string): Array<{ selectors: string; body: string }> {
  const rules: Array<{ selectors: string; body: string }> = []
  const pattern = /([^{}]+)\{([^{}]*)\}/g
  let match: RegExpExecArray | null
  while ((match = pattern.exec(css)) !== null) {
    rules.push({ selectors: match[1].trim(), body: match[2] })
  }
  return rules
}

describe('FilePreview 行内 code 反引号渲染', () => {
  // 校验某个伪元素选择器是否被规则覆盖。
  // 完整选择器列表按逗号切分后逐个 trim，去注释，再精确比对，
  // 防止「破坏 ::before 改成 ::before XYZ」这种破坏无法被识别。
  function isCovered(pseudo: '::before' | '::after'): boolean {
    const rules = extractRuleMap(cssContent)
    return rules.some((r) => {
      const selectors = r.selectors.replace(/\/\*[\s\S]*?\*\//g, '')
      const list = selectors.split(',').map((s) => s.trim()).filter(Boolean)
      const target = `.prose code${pseudo}`
      return list.includes(target) && /content:\s*none/.test(r.body)
    })
  }

  it('存在规则把 .prose code::before 的 content 重置为 none', () => {
    expect(isCovered('::before')).toBe(true)
  })

  it('存在规则把 .prose code::after 的 content 重置为 none', () => {
    expect(isCovered('::after')).toBe(true)
  })
})
