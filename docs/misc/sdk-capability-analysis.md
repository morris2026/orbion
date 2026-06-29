# Agent SDK 能力分析与 Skill 系统重构边界

> 调研日期：2026/06/27
> 调研对象：Claude Agent SDK (Python) + OpenAI Agents SDK (Python)
> 触发原因：步骤 4 Skill 系统实现完成后，code review 反馈指出"用命令匹配决定权限"是 anti-pattern；进一步调研发现 Skill 系统大量功能与 SDK 重叠。
> 目的：识别"哪些能力应该委托 SDK、哪些必须 Orbion 自建"，作为后续步骤 5+ 实施的边界依据。

## 0. 执行摘要

**核心结论**：当前步骤 4 的 Skill 系统实现中，约 **60% 的代码在重造 SDK 已有的轮子**。具体：

- ✅ **9 类能力可完全委托 SDK**：工具注册/调用、超时失败、MCP 接入、流式协议、结构化输出、会话状态、取消中断、追踪、Agent 角色路由
- 🟡 **5 类能力部分委托**：权限评估管线、风险分级二次确认、路径越界、shell 黑名单、审计 hook 点
- 🔴 **5 类能力必须自建（SDK 共同缺口）**：跨项目越权（per-tool authorization, OpenAI issue #2868）、Prompt injection 防护、环境变量隔离、多人协作审批流、Orbion 业务路由

**双 SDK 的本质差异**：

| | Claude Agent SDK | OpenAI Agents SDK |
|---|---|---|
| 形态 | Claude Code CLI 当库用（子进程） | 纯 Python 库 |
| 内置工具 | Read/Write/Edit/Bash/WebSearch 等 | 无（必须自己注册） |
| 集成方式 | **不应该造 file.read 等内置工具**，应该用 SDK 工具 + 权限过滤 | **必须用 `@function_tool` 注册**，SkillDeclaration 设计贴近 |
| 共同缺口 | per-tool authorization（#2868）+ prompt injection 防护 | 同 |

**对步骤 4 的影响**：`MCPManager` 完全多余、`SkillExecutor.execute()` 的参数校验/失败计数多余、`SkillResult`/`SkillDeclaration.parameters` 与 SDK 范式不兼容。**应在步骤 5 dispatch 接入 SDK 前重构**。

---

## 1. Claude Agent SDK 能力全貌

包名 `claude-agent-sdk`（PyPI），Python 3.10+，捆绑 Claude Code CLI。

### 1.1 工具调用机制

| 能力 | API | 详情 |
|------|-----|------|
| 内置工具集 | 默认带 Read/Write/Edit/Bash/Glob/Grep/WebSearch/WebFetch/Monitor/AskUserQuestion/Agent/Skill/Task | 工具执行由 CLI 完成 |
| 自定义工具（in-process MCP） | `@tool(name, desc, schema)` + `create_sdk_mcp_server(name, version, tools=[fn])` + `mcp_servers={"k": server}` | Python 函数即工具，零 IPC |
| 外部 MCP server | `mcp_servers={"k": {"type":"stdio","command":...}}` | 子进程托管 |

### 1.2 权限控制（5 段评估链）

| 能力 | API | 详情 |
|------|-----|------|
| `permission_mode` | `default`/`dontAsk`/`acceptEdits`/`bypassPermissions`/`plan` | `set_permission_mode()` 可动态切换 |
| `allowed_tools` | 白名单（仅控制"是否需 prompt"） | 支持 `mcp__server__*` 通配 |
| `disallowed_tools` | `["Bash"]` 删整个工具；`["Bash(rm *)"]` 仅 deny 子模式（即使 bypass 也生效） | 声明式 |
| `can_use_tool` 回调 | `ClaudeAgentOptions(can_use_tool=async fn)` 返回 `PermissionResultAllow/Deny/Ask` | 运行时人工/规则审批 |
| 评估顺序 | hooks → deny rules → mode → allow rules → can_use_tool | 五段管线 |
| 声明式 rules | `.claude/settings.json`（`setting_sources=["project"]` 时加载） | 项目级配置 |

### 1.3 MCP 集成（原生）

| 能力 | API |
|------|-----|
| stdio 子进程 | `mcp_servers={"k":{"type":"stdio","command":..,"args":..,"env":..}}` |
| HTTP/SSE | 同字段 `type=http/sse` |
| In-process SDK MCP | `create_sdk_mcp_server`（同进程、无 IPC、性能最好） |
| 工具命名空间 | `mcp__<server>__<tool>` |

### 1.4 流式输出

| 能力 | API |
|------|-----|
| 完整消息流 | `async for msg in query(...)` 默认 yield `AssistantMessage` |
| 增量流 | `include_partial_messages=True` → `StreamEvent` 包装原生 API 事件 |
| usage / cost | `ResultMessage.total_cost_usd`、`usage`、`duration_ms`、`session_id`（在最终 ResultMessage） |

### 1.5 Extended thinking / Prompt caching

| 能力 | API |
|------|-----|
| thinking blocks | 模型层支持，SDK 透传 |
| effort 级别 | `AgentDefinition(effort="low"\|"medium"\|"high"\|"xhigh"\|"max"\|int)` |
| Prompt caching | SDK 透传到底层 API 的 `cache_control`，无显式 Python API |

### 1.6 多 Agent 协作

| 能力 | API |
|------|-----|
| Subagents | `agents={"name": AgentDefinition(description, prompt, tools, model, ...)}`，主 agent 经 `Agent` 工具调用 |
| Task tool | 内置 `Task` 工具，等价内置 general-purpose subagent |
| parent_tool_use_id | 子 agent 消息带此字段，可追踪归属 |

### 1.7 会话状态 / Compaction

| 能力 | API |
|------|-----|
| 持久化 | JSONL 落 `~/.claude/projects/<encoded-cwd>/<sid>.jsonl`；Python 总是持久化 |
| resume/fork/continue | `ClaudeAgentOptions(resume=sid, fork=sid, continue_conversation=True)` |
| ClaudeSDKClient | 同 client 多 query 自动续接 |
| Compaction | 自动；边界消息 `SystemMessage(subtype="compact_boundary")` |
| 跨主机 | `SessionStore` 适配器或自管 transcript |
| 管理 API | `list_sessions/get_session_messages/get_session_info/rename_session/tag_session` |

### 1.8 结构化输出

| 能力 | API |
|------|-----|
| JSON Schema | `ClaudeAgentOptions(output_format={"type":"json_schema","schema":<schema>})` |
| Pydantic | `MyModel.model_json_schema()` 喂给上面；强类型回写 `ResultMessage.structured_output` |
| 限制 | 流式阶段不返回 deltas，只在最终 result |

### 1.9 生命周期 Hooks

| 事件 | 用途 | 返回 |
|------|------|------|
| `PreToolUse` | deny/allow/modify 工具调用（如 Bash 命令黑名单） | `{hookSpecificOutput:{permissionDecision:"deny"\|"allow"\|"ask",..}}` |
| `PostToolUse` | 审计、改写结果 | dict |
| `UserPromptSubmit` | 注入/拦截用户输入 | dict |
| `Stop` | 收尾 | dict |
| `SessionStart`/`SessionEnd` | 会话生命周期 | dict |
| 注册 | `HookMatcher(matcher="Bash", hooks=[fn])` + `hooks={"PreToolUse":[...]}` | 仅 ClaudeSDKClient |

### 1.10 取消 / 中断 / 错误处理

| 能力 | 详情 |
|------|------|
| `max_turns` / `max_budget_usd` | 软上限，超限优雅结束 |
| 进程级取消 | `async with` 退出 / task cancel；CLI 子进程随之终止 |
| Checkpointing | 文件改动可回滚（`/rewind`） |
| 错误类型 | `ClaudeSDKError` 基类；`CLINotFoundError`/`CLIConnectionError`/`ProcessError(exit_code)`/`CLIJSONDecodeError` |
| ResultMessage.subtype | `error_max_turns`/`error_max_budget_usd`/`error_max_structured_output_retries` |
| 模型重试/限流 | CLI 内部管理，Python 不暴露策略 |

### 1.11 追踪与可观测性

| 能力 | API |
|------|-----|
| cost/usage | `ResultMessage.total_cost_usd/usage/duration_ms` |
| OpenTelemetry | `CLAUDE_CODE_ENABLE_TELEMETRY=1` + OTLP exporter；traces + metrics（token/cost） |
| Hooks 自建 trace | `PreToolUse`/`PostToolUse` 写自定义日志 |

### 1.12 安全防护

| 能力 | 程度 |
|------|------|
| Prompt injection 防护 | **SDK 不提供**；需自己在 system_prompt/分隔符实现 |
| Jailbreak detection | **不提供** |
| Content filtering | 依赖 API 层（Anthropic 模型自带），SDK 不叠加 |
| 文件系统越界 | 工作目录 `cwd` + `additional_directories` 限制；`disallowed_tools=["Read(../..)"]` 模式 |
| 工具命令黑名单 | `PreToolUse` hook 或 `disallowed_tools=["Bash(rm *)"]` |

---

## 2. OpenAI Agents SDK 能力全貌

包名 `openai-agents`（PyPI）。

### 2.1 工具调用机制

| 能力 | API | 详情 |
|------|-----|------|
| 装饰器声明 | `@function_tool` | 自动从签名+docstring 生成 JSON schema（griffe 解析 + Pydantic 校验） |
| 手动构造 | `FunctionTool(name, description, params_json_schema, on_invoke_tool)` | 完全自定义 |
| 上下文注入 | 首参 `ctx: RunContextWrapper[T]` | 依赖注入 |
| 超时 | `@function_tool(timeout=2.0, timeout_behavior=...)` | `error_as_result` / `raise_exception` / `timeout_error_function` |
| 错误处理 | `failure_error_function` | 默认返回错误文本给 LLM；`None` 时直接抛出 |
| 图像/文件输出 | `ToolOutputImage` / `ToolOutputFileContent` | 工具可返回多模态 |
| Agents as tools | `Agent.as_tool(tool_name, ...)` | 子 agent 作为工具调用 |

### 2.2 权限控制（关键缺口）

| 能力 | API | 详情 |
|------|-----|------|
| 工具级 approval | `@function_tool(needs_approval=True \| async fn)` | 函数签名 `(_ctx, params, _call_id) -> bool` |
| 手动 interruption 流 | `result.interruptions` → `result.to_state()` → `state.approve/reject` → `Runner.run(agent, state)` | 跨 handoff / 嵌套 Agent.as_tool 都通过外层 RunState 统一暂停 |
| 自动 approval | `ShellTool/ApplyPatchTool.on_approval`；`HostedMCPTool.on_approval_request` | 程序化决策，无需暂停 |
| Sticky 决策 | `state.approve(item, always_approve=True)` | 持久化到 RunState，可序列化恢复 |
| 拒绝消息自定义 | `RunConfig.tool_error_formatter` + `state.reject(rejection_message=...)` | 全局/单次双层 |
| **per-tool authorization 中间件** | **❌ 不存在** | Issue #2868：内容校验有 guardrails，但身份/角色/速率限制/审计的细粒度授权层为缺失能力 |

### 2.3 MCP 集成（原生支持，四种传输）

| 类 | 用途 |
|----|------|
| `MCPServerStdio` | 子进程 stdio |
| `MCPServerStreamableHttp` | HTTP Streamable，支持 `cache_tools_list`、`max_retry_attempts` |
| `MCPServerSse` | 旧 SSE（已 deprecated） |
| `HostedMCPTool` | OpenAI 侧托管调用 |
| `MCPServerManager` | 多 server 并发连接，`active_servers` / `failed_servers` / `reconnect()` |
| 工具过滤 | `create_static_tool_filter` 或 `async (ToolFilterContext, tool) -> bool` |
| Approval | `require_approval="always"|"never"` / per-tool map |
| Prompts | `list_prompts()` / `get_prompt(name, args)` → 动态 instructions |
| 配置 | `Agent.mcp_config={convert_schemas_to_strict, failure_error_function, include_server_in_tool_names}` |

### 2.4 流式输出

| 能力 | API |
|------|-----|
| 入口 | `Runner.run_streamed()` → `RunResultStreaming.stream_events()` |
| 事件类型 | `RawResponsesStreamEvent` / `RunItemStreamEvent` / `AgentUpdatedStreamEvent` |
| 原始事件 | OpenAI Responses 格式 `response.output_text.delta` 等 |
| 语义事件名 | `message_output_created`/`tool_called`/`tool_output`/`handoff_occured`/`mcp_approval_requested` |
| usage 位置 | `context_wrapper.usage`（流式末尾才稳定） |
| 取消 | `result.cancel(mode="immediate"\|"after_turn")` |
| 兼容 approval | 暂停后用 `to_state()` → resume `Runner.run_streamed(agent, state)` |

### 2.5 Handoffs

| 能力 | API |
|------|-----|
| 简单声明 | `Agent(handoffs=[agent_a, agent_b])` 自动生成 `transfer_to_<name>` 工具 |
| 定制 | `handoff(agent, tool_name_override, on_handoff, input_type, is_enabled, nest_handoff_history)` |
| 输入过滤 | `input_filter: HandoffInputData -> HandoffInputData`；`agents.extensions.handoff_filters` 预置 |
| 嵌套历史 | `RunConfig.nest_handoff_history` + `handoff_history_mapper`（beta） |
| 边界 | Input guardrails 只在链首 agent；output guardrails 只在最终 agent；tool guardrails 不应用于 handoff |

### 2.6 Guardrails（三层）

| 类型 | 装饰器 | 时机 |
|------|--------|------|
| 输入 | `@input_guardrail` | 链首 agent，默认并行，可 `run_in_parallel=False` 阻断式 |
| 输出 | `@output_guardrail` | 最终 agent，仅串行 |
| 工具 | `@tool_input_guardrail` / `@tool_output_guardrail`（`@function_tool(...)` 注册） | 每次 function tool 调用前后；可 `reject_content` / `allow` / 替换输出 |
| tripwire | `GuardrailFunctionOutput(tripwire_triggered=True)` → 抛异常 |
| 限制 | tool guardrails **只对 function_tool 生效**，handoff / hosted tools / `Agent.as_tool()` 不走此管道 |

### 2.7 会话状态

| 实现 | 用途 |
|------|------|
| `Session` 协议 | `get_items/add_items/pop_item/clear_session` 四方法，可自实现 |
| 内置 | `SQLiteSession` / `AsyncSQLiteSession` / `RedisSession` / `SQLAlchemySession` / `MongoDBSession` / `EncryptedSession` |
| 历史裁剪 | `RunConfig.session_input_callback(history, new_input) -> list`；`SessionSettings(limit=N)` |
| 限制 | 不能与 `conversation_id` / `previous_response_id` 同用 |

### 2.8 结构化输出

| 能力 | API |
|------|-----|
| 类型 | `Agent(output_type=Pydantic BaseModel \| dataclass \| TypedDict \| TypeAdapter 兼容)` |
| 强制工具 | `ModelSettings(tool_choice="auto"\|"required"\|"none"\|"<tool_name>")` |
| 工具行为 | `tool_use_behavior="run_llm_again"\|"stop_on_first_tool"\|StopAtTools(...)\|ToolsToFinalOutputFunction` |

### 2.9 生命周期 hooks

| 范围 | 回调 |
|------|------|
| Run 级 | `RunHooks.on_agent_start/end`、`on_llm_start/end`、`on_tool_start/end`、`on_handoff`、`on_llm_error` |
| Agent 级 | `agent.hooks` (`AgentHooks`) |
| 上下文 | `AgentHookContext`（含 usage） / `RunContextWrapper` / 工具为 `ToolContext` |

### 2.10 取消与中断

- `result.cancel(mode="immediate"|"after_turn")`（仅流式）
- `max_turns` 参数（Runner 级）
- approval interruption → `to_state()` 序列化持久化，可跨进程恢复
- Realtime API 支持 voice 自动打断检测

### 2.11 错误处理 / 重试

| 能力 | API |
|------|-----|
| 模型级重试 | `ModelSettings(retry=ModelRetrySettings(max_retries, backoff, policy))`，runtime-only，opt-in |
| 预置 policy | `retry_policies.never/provider_suggested/network_error/http_status([...])/retry_after/any/all` |
| 安全边界 | abort / provider 标记 replay-unsafe / 已开始流式输出后**不重试** |
| 工具错误 | `failure_error_function` / `failure_error_function=None` 抛出 |
| MCP 错误 | `failure_error_function` per server / agent |

### 2.12 追踪

| 能力 | API |
|------|-----|
| 默认开启 | `trace()` / `agent_span` / `generation_span` / `function_span` / `guardrail_span` / `handoff_span` |
| 禁用 | `OPENAI_AGENTS_DISABLE_TRACING=1` / `set_tracing_disabled(True)` / `RunConfig.tracing_disabled` |
| 自定义导出 | `add_trace_processor()` 追加、`set_trace_processors()` 替换 |
| 敏感数据 | `RunConfig.trace_include_sensitive_data=False` |
| 第三方模型 tracing | `set_tracing_export_api_key(OPENAI_KEY)` 单独传 tracing key |
| 生态 | 30+ 集成（Langfuse / Arize / Datadog / MLflow …） |

### 2.13 安全防护

- ❌ **无内置 prompt injection 防护 / content filter**：guardrails 仅提供框架，内容检测需自己实现
- ✅ `EncryptedSession` 提供 TTL + 透明加密
- ✅ `redact_secrets` 等需自实现

### 2.14 Computer use / Browser use

| 工具 | 状态 |
|------|------|
| `ComputerTool` | 本地 harness，需实现 `Computer`/`AsyncComputer` 接口 |
| `ShellTool` | 本地 / 托管容器双模；本地需 `executor`；可挂载 `ShellToolSkillReference` skills |
| `ApplyPatchTool` | 本地，需实现 `ApplyPatchEditor` |
| `WebSearchTool`/`FileSearchTool`/`CodeInterpreterTool`/`ImageGenerationTool` | hosted，仅 OpenAI Responses 模型 |

---

## 3. Orbion 当前 Skill 系统实现 vs SDK 能力对照

### 3.1 步骤 4 已实现的组件

| 文件 | 行数 | 功能 |
|------|------|------|
| `app/biz/skills/types.py` | ~140 | RiskLevel / SkillDeclaration / SkillResult / AgentEnv / build_agent_env / SkillHandler Protocol |
| `app/biz/skills/declarations.py` | ~25 | AgentDeclaration dataclass |
| `app/biz/skills/registry.py` | ~40 | SkillRegistry (register/get/resolve) |
| `app/biz/skills/agent_registry.py` | ~110 | 6 角色 AgentDeclaration + AgentRegistry |
| `app/biz/skills/executor.py` | ~440 | SkillExecutor 5 段权限管线 + DispatchContext + AuditRecord + AuditWriter |
| `app/biz/skills/audit_writer.py` | ~50 | PgSkillAuditWriter |
| `app/biz/skills/permission_checker.py` | ~40 | DispatchPermissionChecker |
| `app/biz/skills/mcp_manager.py` | ~210 | MCPManager + MCPServerConfig + MCPServerState |
| `app/biz/skills/builtin_skills.py` | ~230 | ShellExecParams + 命令黑名单 + file.read/write + git.commit handler |
| `app/biz/skills/user_content.py` | ~40 | wrap_user_content + build_system_prompt_with_guard |
| `app/biz/skills/injection_guard.py` | ~20 | INJECTION_GUARD_RULE 常量 |
| **合计** | **~1345 行** | |

### 3.2 对照矩阵（详细版）

| Orbion 实现 | SDK 替代能力 | 委托程度 | 重构动作 |
|------------|-------------|---------|---------|
| `SkillDeclaration.parameters` (Pydantic schema) | `@function_tool` 自动生成 / `@tool` 装饰器 | ✅ 完全委托 | 改为 SDK 工具包装 |
| `SkillDeclaration.handler` | SDK 工具调用协议 | ✅ 完全委托 | 删除字段 |
| `SkillRegistry.register/get/resolve` | SDK Agent.tools 列表 / AgentDefinition.tools | ✅ 完全委托 | 删除整个类 |
| `SkillResult.ok/reason` | SDK 工具返回值（OpenAI: 直接 return；Claude: tool_result content） | ✅ 完全委托 | 改为返回 SDK 兼容格式 |
| `SkillExecutor.execute()` 参数校验 | Pydantic 自动校验（SDK 内置） | ✅ 完全委托 | 删除 |
| `SkillExecutor._invoke_handler` (sync/async) | SDK 工具调用协议 | ✅ 完全委托 | 删除 |
| `SkillExecutor` 失败计数 + 3 次中断 | `@function_tool(failure_error_function)` + SDK max_turns | ✅ 完全委托 | 删除 |
| `MCPManager` 全部代码 | `mcp_servers` 配置 / `MCPServerManager` | ✅ 完全委托 | **删除整个模块** |
| `MCPServerConfig` | `MCPServerStdio` 构造参数 | ✅ 完全委托 | 删除 |
| `MCPServerState`（disabled/restart_count） | SDK 内部管理 | ✅ 完全委托 | 删除 |
| `SkillExecutor._check_path_safety` | Claude: `cwd` + `additional_directories` + PreToolUse；OpenAI: 自建 | 🟡 部分委托 | 保留校验逻辑，挪到 hook 内 |
| `SkillExecutor._check_project_scope` | ❌ SDK 共同缺口（#2868） | 🔴 必须自建 | 保留 |
| `is_blacklisted` (shell 黑名单) | Claude: `disallowed_tools=["Bash(rm *)"]` 声明式；OpenAI: hook | 🟡 部分委托 | 改为生成 SDK disallow 模式 |
| shell.exec 门禁（agent_type=implementer + allow_shell） | Claude: `permission_mode` + `allowed_tools` per agent；OpenAI: agent.tool_filter | 🟡 部分委托 | 改为 SDK 配置 |
| `paused_awaiting_approval` 自造状态 | Claude: `can_use_tool` 返回 `Ask`；OpenAI: `needs_approval` + interruption | 🟡 部分委托 | 用 SDK 原生流程 |
| `AuditWriter` Protocol + `_InMemoryAuditWriter` | Claude: PostToolUse hook；OpenAI: `RunHooks.on_tool_end` | 🟡 部分委托 | 改为 SDK hook 实现 |
| `PgSkillAuditWriter` | 持久化是 Orbion 责任，hook 点用 SDK | 🟡 部分委托 | 保留，挂到 SDK hook |
| `DispatchPermissionChecker`（actor 是否项目成员） | ❌ SDK 单 agent 视角，无多租户 | 🔴 必须自建 | 保留 |
| `wrap_user_content` | ❌ SDK 不提供 | 🔴 必须自建 | 保留 |
| `INJECTION_GUARD_RULE` | ❌ SDK 不提供 | 🔴 必须自建 | 保留 |
| `build_agent_env` (env 隔离) | ❌ SDK 不提供（Claude 子进程继承父进程 env） | 🔴 必须自建 | 保留，注入到 SDK 启动参数 |
| 6 角色 `AgentDeclaration` | SDK `Agent` / `AgentDefinition` 是单实例抽象 | 🟡 部分委托 | Orbion 业务路由保留，Agent 实例用 SDK |
| `AgentDeclaration.max_iterations=25` | SDK `max_turns` | ✅ 完全委托 | 删除字段，用 SDK 参数 |
| `AgentDeclaration.system_prompt_template` | SDK Agent.instructions | ✅ 完全委托 | 字段名对齐 |
| `AgentDeclaration.default_skill_set/optional_skills` | SDK Agent.tools 列表 + 动态过滤 | 🟡 部分委托 | 改为 SDK 配置 |

### 3.3 自造轮子清单（应删除）

按代码量估算，**约 800 行可删除/简化**：

| 模块 | 行数 | 处理 |
|------|------|------|
| `mcp_manager.py` | 210 | **完全删除**（用 SDK `mcp_servers`） |
| `executor.py` 参数校验 + 失败计数 + invoke_handler | ~150 | **删除**（用 SDK 内置） |
| `registry.py` | 40 | **完全删除**（用 SDK Agent.tools） |
| `types.py` SkillDeclaration + SkillResult + SkillHandler | ~80 | **改造为 SDK 工具薄包装** |
| `agent_registry.py` 部分（max_iterations/system_prompt_template 等冗余字段） | ~30 | **字段简化** |
| **合计可简化** | **~510 行** | |

保留约 **835 行**（路径校验、跨项目越权、shell 黑名单、env 隔离、Prompt injection 防护、审计持久化、6 角色业务配置）。

---

## 4. 双 SDK 共同的"硬缺口"

以下能力**两个 SDK 都不提供**，Orbion 必须自建：

### 4.1 Per-tool Authorization（身份/越权/项目隔离）

**OpenAI issue [#2868](https://github.com/openai/openai-agents-python/issues/2868)** 明确是 SDK 缺口：
> guardrails 做内容校验，但身份/角色/速率限制/审计的细粒度授权层为缺失能力

Claude Agent SDK 的 `can_use_tool` 也是**单 agent 视角**，不知道"项目""成员""租户"概念。

**Orbion 必须自建**：
- `params.project_id == ctx.project_id` 跨项目校验
- `actor_user_id` 是否项目成员
- 多租户资源隔离

### 4.2 Prompt Injection 防护

两个 SDK **都不提供**任何 prompt injection 防护。

**Orbion 必须自建**：
- `wrap_user_content`（`<user_content>` 分隔符）
- `INJECTION_GUARD_RULE`（system_prompt 末尾防护规则）
- 未来可加：输出侧 jailbreak 检测

### 4.3 环境变量隔离

SDK 都不提供：
- Claude Agent SDK：子进程继承父进程 env，需 Orbion 显式过滤
- OpenAI Agents SDK：纯 Python，无 env 隔离概念

**Orbion 必须自建**：`build_agent_env` 移除 `ORBION_ENCRYPTION_KEY` 等敏感变量。

### 4.4 多人协作 / 事件总线 / 审批流

SDK 都是**单 agent 单 session 视角**，不知道：
- 多用户协作（讨论、共识、审批）
- 事件总线（EventBus）
- artifact 状态机（draft/proposed/approved/rejected）
- task 生命周期（pending/running/paused/completed/timeout/cancelled）

**Orbion 必须自建**：整个 EventBus + artifact + task + 审批 流程。

### 4.5 业务路由

SDK 不知道 Orbion 的 6 角色清单（analyst/architect/designer/planner/implementer/critic）和意图命令（/analyze /design /decompose /implement）。

**Orbion 必须自建**：意图解析 + 路由到对应 SDK Agent 实例。

---

## 5. 双 SDK 集成方式差异

这是设计 Adapter 层时**必须考虑**的关键差异：

### Claude Agent SDK

- **形态**：Claude Code CLI 子进程
- **内置工具**：Read/Write/Edit/Bash/WebSearch/WebFetch/Monitor/AskUserQuestion/Agent/Skill/Task
- **集成方式**：不应该造 file.read/file.write 等内置工具，应该**用 SDK 内置工具 + 权限过滤**
- **MCP**：`mcp_servers={"k": {...}}` 配置式
- **自定义工具**：`@tool` + `create_sdk_mcp_server`（in-process MCP）
- **审计**：PostToolUse hook 写到 Orbion 表
- **会话**：JSONL transcript，可 `SessionStore` 适配

### OpenAI Agents SDK

- **形态**：纯 Python 库
- **内置工具**：无（必须注册）
- **集成方式**：用 `@function_tool` 注册 Orbion 的 Skill 作为 SDK 工具
- **MCP**：`MCPServerStdio` + `MCPServerManager`
- **自定义工具**：`@function_tool` 装饰器
- **审计**：`RunHooks.on_tool_end` 写到 Orbion 表
- **会话**：`Session` 协议（自实现接 PostgreSQL）

### 双 SDK 抽象层设计要点

Orbion 的 `AdapterFactory`（步骤 3 已实现）按 provider 路由到 `ClaudeAgentSDKAdapter` / `OpenAIAgentsSDKAdapter`。**Skill 系统必须在 Adapter 层抽象**：

```
Orbion 业务层
  ├── 6 角色 AgentDeclaration（业务配置）
  ├── 意图路由（/analyze → analyst）
  └── 风险分级 / 跨项目越权 / Prompt injection 防护（业务策略）
        ↓
SkillExecutor（SDK 无关的策略检查器）
  ├── 路径校验
  ├── 项目越权校验
  ├── shell 黑名单
  └── 审计写入
        ↓
ModelAdapter（步骤 3 双 SDK 抽象）
  ├── ClaudeAgentSDKAdapter
  │     └── @tool + create_sdk_mcp_server + can_use_tool callback
  └── OpenAIAgentsSDKAdapter
        └── @function_tool + MCPServerStdio + needs_approval callback
```

**关键约束**：SkillExecutor **不直接执行工具**，只做策略检查；工具执行委托给 SDK。这样 SkillExecutor 是 SDK 无关的纯业务层。

---

## 6. 重构方案对比

### 方案 A：步骤 5 统一重构（保持步骤 4 现状）

- 步骤 4 当前实现作为"业务策略层"保留
- 步骤 5 dispatch 时识别哪些可委托 SDK，把 SkillExecutor 包成 SDK callback

**优点**：不返工步骤 4
**缺点**：
- 步骤 5 复杂度爆炸（既要写 dispatch 流程，又要重构 Skill 系统）
- 当前 `MCPManager` 等代码明知冗余还先合入，违反 YAGNI 反向（"已知不需要的东西还保留"）
- 步骤 4 测试用例与 SDK 范式不一致，步骤 5 重构时大量测试要重写

### 方案 B：现在重构步骤 4（推荐）

- 删除 `MCPManager`（用 SDK `mcp_servers`）
- 简化 `SkillExecutor` 为"策略检查器"：删除参数校验、失败计数、invoke_handler；保留路径/项目/shell 黑名单/审计 hook
- 改造 `SkillDeclaration` 为 SDK 工具的薄包装（保留 risk_level 业务字段）
- 步骤 5 dispatch 时把 SkillExecutor 接入 SDK callback/hook

**优点**：
- 步骤 5 dispatch 只需关注"业务流程编排"，不再纠结"工具怎么执行"
- 步骤 4 测试用例与 SDK 范式一致，后续无需大改
- 当前步骤 4 还没合入主线（用户暂不提交），返工成本最低

**缺点**：步骤 4 需要返工（约 500 行删除 + 200 行改造）

### 方案 C：彻底重新设计

- 抛弃 SkillDeclaration/SkillExecutor 当前形态
- AgentDeclaration 直接映射到 SDK `Agent` / `AgentDefinition`
- 工具调用全部用 SDK 注册，Orbion 只维护"哪些工具给哪个 Agent"的配置
- 平台业务规则全部下沉到 Adapter 内部 hook

**优点**：与 SDK 深度集成，长期最干净
**缺点**：
- 要重新写步骤 4 设计文档（§6.6）+ 测试设计（AR-4.x）
- 步骤 4 测试用例大部分要重写
- 风险：SDK 抽象泄漏到业务层，未来切换 SDK 成本变高

---

## 7. 建议与下一步

### 7.1 推荐方案 B（现在重构步骤 4）

**理由**：
1. 当前步骤 4 未提交，返工成本最低
2. 步骤 5 dispatch 复杂度本来就高（16 步流程），不应再叠加 Skill 系统重构
3. 与 SDK 集成方向对齐，避免后续返工
4. 保留所有"必须自建"的能力（跨项目越权、Prompt injection 防护等）

### 7.2 重构后的步骤 4 边界（建议）

**删除**：
- `app/biz/skills/mcp_manager.py` 整个模块
- `SkillRegistry` 类（用 SDK Agent.tools 配置替代）
- `SkillExecutor.execute()` 中的参数校验、invoke_handler、失败计数逻辑
- `SkillResult.ok/reason` 自定义格式（用 SDK 工具返回格式）
- `AgentDeclaration.max_iterations` 字段（用 SDK max_turns）

**保留并改造**：
- `SkillDeclaration`：保留 `skill_id` / `risk_level`，删除 `parameters` / `handler`（这两个由 SDK 工具定义提供）
- `SkillExecutor`：改为"策略检查器"，只暴露 `check_permission(skill_id, params, ctx) -> PermissionDecision`
- `AgentDeclaration`：保留 `agent_type` / `default_skill_set` / `optional_skills`，删除 `system_prompt_template` / `max_iterations`（用 SDK Agent 字段）
- `AuditWriter` / `PgSkillAuditWriter`：保留，改为 SDK hook 实现
- `PermissionError` / `DispatchPermissionChecker`：保留（SDK 缺口）
- `wrap_user_content` / `INJECTION_GUARD_RULE`：保留（SDK 缺口）
- `build_agent_env`：保留（SDK 缺口）
- `is_blacklisted`：保留，改为生成 SDK disallow 模式的工具函数
- `_check_path_safety`：保留，挪到 SDK hook 内调用
- 6 角色 `AgentDeclaration`：保留为业务配置

**新增**（如果步骤 5 需要）：
- Adapter 层的 `can_use_tool_callback` / `pre_tool_use_hook`，内部调用 SkillExecutor.check_permission

### 7.3 设计文档同步

按用户已选项，在 `docs/superpowers/specs/agent-runtime-refactor-design.md` §6.6 后补一小节 **「6.6.7 SDK 能力委托与平台自建边界」**，明确：
- 委托给 SDK 的能力清单（工具注册、MCP、流式、session、approval 等）
- Orbion 自建的能力清单（跨项目越权、Prompt injection 防护、env 隔离、审计持久化、6 角色路由）
- Adapter 层抽象（双 SDK 差异屏蔽）

### 7.4 后续步骤影响

- **步骤 5（AgentRuntime 核心）**：dispatch 流程中调用 SkillExecutor.check_permission，不再调用 execute
- **步骤 6（事件驱动调度）**：不受影响
- **步骤 7（失败恢复）**：失败重试用 SDK 内置 retry policy，Orbion 不再自建
- **步骤 10（可观测性）**：tracing 用 SDK OTel 能力，Orbion 只补 skill_calls 表写入

---

## 附录 A：双 SDK 文档来源

### Claude Agent SDK
- [Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview)
- [GitHub anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python)
- [Configure permissions](https://code.claude.com/docs/en/agent-sdk/permissions)
- [Intercept and control agent behavior with hooks](https://code.claude.com/docs/en/agent-sdk/hooks)
- [Connect to external tools with MCP](https://code.claude.com/docs/en/agent-sdk/mcp)
- [Stream responses in real-time](https://code.claude.com/docs/en/agent-sdk/streaming-output)
- [Get structured output from agents](https://code.claude.com/docs/en/agent-sdk/structured-outputs)
- [Subagents in the SDK](https://code.claude.com/docs/en/agent-sdk/subagents)
- [Work with sessions](https://code.claude.com/docs/en/agent-sdk/sessions)
- [tool_permission_callback.py example](https://github.com/anthropics/claude-agent-sdk-python/blob/main/examples/tool_permission_callback.py)

### OpenAI Agents SDK
- [OpenAI Agents SDK 首页](https://openai.github.io/openai-agents-python/)
- [Tools](https://openai.github.io/openai-agents-python/tools/)
- [Handoffs](https://openai.github.io/openai-agents-python/handoffs/)
- [Guardrails](https://openai.github.io/openai-agents-python/guardrails/)
- [Streaming](https://openai.github.io/openai-agents-python/streaming/)
- [Human-in-the-loop](https://openai.github.io/openai-agents-python/human_in_the_loop/)
- [MCP](https://openai.github.io/openai-agents-python/mcp/)
- [Sessions](https://openai.github.io/openai-agents-python/sessions/)
- [Tracing](https://openai.github.io/openai-agents-python/tracing/)
- [Models](https://openai.github.io/openai-agents-python/models/)
- [GitHub Issue #2868 Per-tool authorization](https://github.com/openai/openai-agents-python/issues/2868)

### 双 SDK 对比
- [Migrate from Claude Agent SDK to OpenAI Agents SDK](https://developers.openai.com/cookbook/examples/agents_sdk/migrate-from-claude-agent-sdk/readme)
