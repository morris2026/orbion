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

---

## L-3: `/help` 斜杠命令要求精确匹配

**发现步骤**：步骤3（slashCommands.ts）

**问题**：`parseMessage` 中 `/help` 使用 `trimmed === '/help'` 严格相等判断，用户输入 `/help summarize` 等带后缀的变体会被当作普通消息发送而非触发帮助显示。大多数IM应用（Slack/Discord）中 `/help` 带后缀仍触发帮助。

**影响**：用户可能困惑，但TC-3.6只测试精确 `/help`，设计规格也未明确带后缀的行为，当前行为不偏离规格。如果后续需要支持 `/help` 带后缀，只需将 `===` 改为 `startsWith`。

**处置建议**：暂不修复。如用户反馈困惑，改为 `startsWith('/help')` 即可。

---

## L-4: ParsedMessage 使用双 discriminant 字段

**发现步骤**：步骤3（slashCommands.ts）

**问题**：`ParsedMessage` union 用 `request_summary`(true/false) 和 `show_help`(true) 两个字段区分三种结果，而非经典的单 discriminant 模式（如 `type: 'summarize' | 'help' | 'normal'`）。消费者需先检查 `show_help` 再检查 `request_summary`，顺序敏感。

**影响**：当前设计直接映射 `handleSendMessage` 的 `{ content, request_summary }` 签名，实用性好。但后续新增斜杠命令时（如 `/plan`），双 discriminant 模式不便于扩展，可能需要重构为单 discriminant。

**处置建议**：暂不修复。步骤7实现DiscussionPanel时如发现扩展不便，可重构为单 discriminant。

---

## L-5: TC-3.10 只测试一个回调的 state 隔离

**发现步骤**：步骤3（Workspace.test.tsx）

**问题**：TC-3.10 只验证 `handleCreateProject` 不影响 initialState，没有测试其余5个回调（handleCreateThread、handleRegisterAgent 等）的 state 隔离。

**影响**：每个回调操作不同 state 切片（projects/threads/outputs），逻辑上不可能互相干扰，风险低。步骤5-8的 Dialog 测试会覆盖各回调的实际行为，间接验证 state 隔离。

**处置建议**：不修复。后续步骤的 Dialog 测试已覆盖。

---

## L-6: CreateThreadRequest 省略 type 字段

**发现步骤**：步骤3（types/api.ts）

**问题**：前端 `CreateThreadRequest` 只包含 `title`，不传 `type` 字段，依赖后端 `ThreadCreate.type` 默认值 `"discussion"`。

**影响**：MVP 只有 discussion 线程，省略是合理的裁剪决策。如果后端改默认值或需要创建其他类型线程（如 decision 线程），前端需补字段。

**处置建议**：暂不修复。MVP 阶段保持现状，如需要其他线程类型时再扩展。