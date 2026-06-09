# 遗留问题跟踪

## L-1: shadcn `"use client"` 指令不一致

**发现步骤**：步骤2（shadcn组件+resizable依赖安装）

**问题**：10个 shadcn/ui 组件文件中，只有3个包含 `"use client"` 指令（dialog.tsx、scroll-area.tsx、tabs.tsx），其余7个不含（badge.tsx、tooltip.tsx、separator.tsx、button.tsx、card.tsx、input.tsx、label.tsx）。根因是 shadcn `base-nova` 样式模板对不同组件的生成规则不一致。

**影响**：当前无影响。本项目是 Vite SPA（非 Next.js RSC），`"use client"` 在 Vite bundler 中无功能意义——它是 React Server Components 的边界标记，Vite 不识别也不处理。不一致不会导致任何运行时或构建问题。

**处置建议**：无需修复。后续安装新 shadcn 组件时无需关注此问题。

---

## L-2: shadcn `components.json` tailwind.config 为空

**发现步骤**：步骤2（shadcn组件+resizable依赖安装）

**问题**：`web/components.json` 中 `tailwind.config` 字段为空字符串（`""`）。本项目使用 Tailwind v4（CSS-first 配置模式，通过 `@tailwindcss/vite` 插件集成），没有传统的 `tailwind.config.ts` 文件，因此该字段确实无值可填。

**影响**：当前无影响。已安装的5个组件（Dialog、Badge、Tooltip、ScrollArea、Separator）不需要读取 Tailwind 配置文件，所以安装和运行均正常。但未来安装需要读取 Tailwind 配置的 shadcn 组件时（如需要注入 CSS 变量或主题扩展的组件），shadcn CLI 可能找不到配置文件路径，导致这些组件的样式自定义步骤被跳过或报错。

**处置建议**：后续安装 shadcn 组件时如遇到 Tailwind config 相关错误，需在此字段填入适当的配置路径或按 Tailwind v4 方式手动补充样式变量。