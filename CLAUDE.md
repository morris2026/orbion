# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Orbion — 多人 + 多 Agent 双协作的 AI 开发平台。核心模式：人类讨论达成共识 → AI 总结/分解/执行 → 人类审批产出。事件驱动架构，Agent 通过订阅事件参与协作。

## 设计文档

- `docs/specs/0.1-arch.md` — 架构规格文档，索引了所有详细设计文档

实现新模块前必须先阅读设计文档中的相关章节。

## 设计文档编写规则（严格执行）

- **0.1 架构文档只写目标架构和渐进式总体原则**：不写具体实现细节、MVP 裁剪决策、数据字段精确值。裁剪决策和实现细节放到各阶段的 overview 文档
- **标题就是标题，其他内容放到章节内部**：标题行只做标题用，不在标题行中塞入注释、裁剪标注、实现说明等。具体内容必须放到章节正文或子章节中
- **设计文档只记录结果，不记录修改过程**：修改过程由 git 追踪。多方案对比分析（如 0.3 架构附录）属于设计决策依据，需要保留

## 技术栈

- 前端：React + Vite（SPA）+ TypeScript + TailwindCSS + shadcn/ui
- 后端：Python/FastAPI
- 事件总线：EventBus Protocol 抽象接口，PostgreSQL Event Store
- 端侧：Web 优先，手机 App 后期做轻量版

## 编码规范

- Python：遵循 PEP 8，类型注解必须，使用 Pydantic 做数据校验
- TypeScript：strict mode，ESLint + Prettier
- 注释和 commit message 使用中文
- 注释规则：不写 What 注释（代码自解释），只写 Why 注释（设计决策、跨库约束、令人意外的行为），公开 API 的 docstring 写接口契约（调用者必须知道的语义约定）
- 接口设计遵循设计文档中的抽象协议（KnowledgeStore/KnowledgeRetriever/KnowledgeGraph/ModelAdapter 等），不绕过抽象层直接实现

## 提交规范

- 提交前必须与用户确认，未经允许不得自动提交
- commit message 一句话概括意图，控制在70字符以内，不写实现细节（如 `feat: 实现 Event Store 写端` 而非 `feat: 实现 Event Store 写端，包含 event_log 表创建/事件插入/...`）

## 测试规范

- **问题处理态度（严格执行）**：发现问题追根究底不推卸，无论是否本次修改引入都要确认根因，不推诿说"不属于当前步骤"
