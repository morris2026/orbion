# Agent SDK 对比分析与决策依据

> 调研日期：2026/06/27
> 调研对象：Claude Agent SDK (Python) vs OpenAI Agents SDK (Python)
> 目的：为 Orbion Agent Runtime 重构提供 SDK 选型决策依据
> 决策结论：**封装 Agent SDK（非 Provider SDK）；先实现 OpenAI Agents SDK，保留 Claude Agent SDK 接口能力**

---

## 0. 执行摘要

Orbion Agent Runtime 的目标是**提供类似 Claude Agent SDK 那样的统一 Agent 抽象层**（agent loop + tool + permission + session + MCP + streaming + structured output）。底层 Adapter 根据 provider 决定"委托多少"：

- **OpenAI 端**（先实现）：用 `openai-agents` 包，委托 agent loop / tool / MCP / session / streaming / approval / tracing
- **Claude 端**（保留接口）：用 `claude-agent-sdk` 包，委托同样能力（但需 Node.js 运行时）

**核心决策依据**：

| 维度 | Claude Agent SDK | OpenAI Agents SDK | 决策权重 |
|------|------------------|-------------------|---------|
| 模型支持 | 仅 Anthropic | 任意模型（ModelProvider） | 🔴 决定性 |
| 部署依赖 | Node.js + CLI | 纯 Python | 🟡 高 |
| 生产稳定性 | breaking changes 频繁 | 较稳定 | 🟡 高 |
| 调试体验 | CLI 黑盒 | Python debugger | 🟡 中 |
| 权限可靠性 | `can_use_tool` 已知 bug | approval 稳定 | 🟡 高 |
| 用户反馈 | Python 项目痛点多 | Python 开发者友好 | 🟡 中 |

**结论**：先实现 OpenAI Agents SDK 端（覆盖 OpenAI / GLM / DeepSeek / Anthropic via ModelProvider），Claude Agent SDK 端预留接口（未来需要 Extended thinking / Checkpointing / 内置 WebSearch 等 Claude 独有能力时再接入）。

---

## 1. 调研背景

### 1.1 触发原因

步骤 4 Skill 系统实现完成后，code review 反馈指出"用命令匹配决定权限"是 anti-pattern。进一步调研发现：

1. **步骤 3 Adapter 命名误导**：`ClaudeAgentSDKAdapter` 实际用 `anthropic` 包（Provider SDK），`OpenAIAgentsSDKAdapter` 实际用 `openai` 包（Provider SDK）——**都不是真正的 Agent SDK**
2. **步骤 4 Skill 系统大量重造 SDK 已有的轮子**：MCPManager、SkillRegistry、SkillExecutor 的参数校验/失败计数等约 510 行代码与 SDK 能力重叠
3. **"自造轮子"的根因**：没有先定义"Agent Runtime 对外提供什么能力"，直接在 Provider SDK 之上自建 agent loop

### 1.2 核心认知转变

**之前的理解**：
- Adapter 层 = 封装 Provider SDK，提供 complete/stream
- AgentRuntime 层 = 在 Adapter 之上实现 dispatch 流程
- Skill 层 = 自建工具系统

**现在的理解**：
- **AgentRuntime 的目标 = 提供类似 Claude Agent SDK 那样的统一 Agent 抽象层**
- Adapter 层 = 封装 Agent SDK（不是 Provider SDK），委托 agent loop / tool / permission / session / MCP / streaming
- Skill 层 = SDK 无关的业务策略层（风险分级、跨项目越权、路径越界、Prompt injection 防护、审计）

这个转变意味着：
- Adapter 接口从 `complete()/stream()` 升级到 `query()/run() + register_tool() + permission_callback`
- SkillExecutor 不直接执行工具，只做策略检查；工具执行委托给 Adapter
- MCPManager 在 OpenAI 端删除（用 SDK 的 MCPServerStdio）

---

## 2. Claude Agent SDK 能力全貌

包名 `claude-agent-sdk`（PyPI），Python 3.10+，捆绑 Claude Code CLI。

### 2.1 架构本质

**CLI 子进程模型**：

```
Orbion Python 进程
    ↓ stdin/stdout JSON 协议
Claude Code CLI 子进程（Node.js）  ← 真正的 agent loop 在这里
    ↓ HTTP API
Anthropic 服务
```

Python 包捆绑了 Claude Code CLI 的 npm 包（`@anthropic-ai/claude-code`），但**仍需要 Node.js 运行时**执行 CLI。

### 2.2 能力清单

#### 工具调用机制

| 能力 | API | 详情 |
|------|-----|------|
| 内置工具集 | Read/Write/Edit/Bash/Glob/Grep/WebSearch/WebFetch/Monitor/AskUserQuestion/Agent/Skill/Task | 工具执行由 CLI 完成 |
| 自定义工具（in-process MCP） | `@tool(name, desc, schema)` + `create_sdk_mcp_server(name, version, tools=[fn])` + `mcp_servers={"k": server}` | Python 函数即工具，零 IPC |
| 外部 MCP server | `mcp_servers={"k": {"type":"stdio","command":...}}` | 子进程托管 |

#### 权限控制（5 段评估链）

| 能力 | API | 详情 |
|------|-----|------|
| `permission_mode` | `default`/`dontAsk`/`acceptEdits`/`bypassPermissions`/`plan` | `set_permission_mode()` 可动态切换 |
| `allowed_tools` | 白名单（仅控制"是否需 prompt"） | 支持 `mcp__server__*` 通配 |
| `disallowed_tools` | `["Bash"]` 删整个工具；`["Bash(rm *)"]` 仅 deny 子模式（即使 bypass 也生效） | 声明式 |
| `can_use_tool` 回调 | `ClaudeAgentOptions(can_use_tool=async fn)` 返回 `PermissionResultAllow/Deny/Ask` | 运行时人工/规则审批 |
| 评估顺序 | hooks → deny rules → mode → allow rules → can_use_tool | 五段管线 |
| 声明式 rules | `.claude/settings.json`（`setting_sources=["project"]` 时加载） | 项目级配置 |

#### MCP 集成（原生）

| 能力 | API |
|------|-----|
| stdio 子进程 | `mcp_servers={"k":{"type":"stdio","command":..,"args":..,"env":..}}` |
| HTTP/SSE | 同字段 `type=http/sse` |
| In-process SDK MCP | `create_sdk_mcp_server`（同进程、无 IPC、性能最好） |
| 工具命名空间 | `mcp__<server>__<tool>` |

#### 流式输出

| 能力 | API |
|------|-----|
| 完整消息流 | `async for msg in query(...)` 默认 yield `AssistantMessage` |
| 增量流 | `include_partial_messages=True` → `StreamEvent` 包装原生 API 事件 |
| usage / cost | `ResultMessage.total_cost_usd`、`usage`、`duration_ms`、`session_id`（在最终 ResultMessage） |

#### Extended thinking / Prompt caching

| 能力 | API |
|------|-----|
| thinking blocks | 模型层支持，SDK 透传 |
| effort 级别 | `AgentDefinition(effort="low"\|"medium"\|"high"\|"xhigh"\|"max"\|int)` |
| Prompt caching | SDK 透传到底层 API 的 `cache_control`，无显式 Python API |

#### 多 Agent 协作

| 能力 | API |
|------|-----|
| Subagents | `agents={"name": AgentDefinition(description, prompt, tools, model, ...)}`，主 agent 经 `Agent` 工具调用 |
| Task tool | 内置 `Task` 工具，等价内置 general-purpose subagent |
| parent_tool_use_id | 子 agent 消息带此字段，可追踪归属 |

#### 会话状态 / Compaction

| 能力 | API |
|------|-----|
| 持久化 | JSONL 落 `~/.claude/projects/<encoded-cwd>/<sid>.jsonl`；Python 总是持久化 |
| resume/fork/continue | `ClaudeAgentOptions(resume=sid, fork=sid, continue_conversation=True)` |
| ClaudeSDKClient | 同 client 多 query 自动续接 |
| Compaction | 自动；边界消息 `SystemMessage(subtype="compact_boundary")` |
| 跨主机 | `SessionStore` 适配器或自管 transcript |
| 管理 API | `list_sessions/get_session_messages/get_session_info/rename_session/tag_session` |

#### 结构化输出

| 能力 | API |
|------|-----|
| JSON Schema | `ClaudeAgentOptions(output_format={"type":"json_schema","schema":<schema>})` |
| Pydantic | `MyModel.model_json_schema()` 喂给上面；强类型回写 `ResultMessage.structured_output` |
| 限制 | 流式阶段不返回 deltas，只在最终 result |

#### 生命周期 Hooks

| 事件 | 用途 | 返回 |
|------|------|------|
| `PreToolUse` | deny/allow/modify 工具调用（如 Bash 命令黑名单） | `{hookSpecificOutput:{permissionDecision:"deny"\|"allow"\|"ask",..}}` |
| `PostToolUse` | 审计、改写结果 | dict |
| `UserPromptSubmit` | 注入/拦截用户输入 | dict |
| `Stop` | 收尾 | dict |
| `SessionStart`/`SessionEnd` | 会话生命周期 | dict |
| 注册 | `HookMatcher(matcher="Bash", hooks=[fn])` + `hooks={"PreToolUse":[...]}` | 仅 ClaudeSDKClient |

#### 取消 / 中断 / 错误处理

| 能力 | 详情 |
|------|------|
| `max_turns` / `max_budget_usd` | 软上限，超限优雅结束 |
| 进程级取消 | `async with` 退出 / task cancel；CLI 子进程随之终止 |
| Checkpointing | 文件改动可回滚（`/rewind`） |
| 错误类型 | `ClaudeSDKError` 基类；`CLINotFoundError`/`CLIConnectionError`/`ProcessError(exit_code)`/`CLIJSONDecodeError` |
| ResultMessage.subtype | `error_max_turns`/`error_max_budget_usd`/`error_max_structured_output_retries` |
| 模型重试/限流 | CLI 内部管理，Python 不暴露策略 |

#### 追踪与可观测性

| 能力 | API |
|------|-----|
| cost/usage | `ResultMessage.total_cost_usd/usage/duration_ms` |
| OpenTelemetry | `CLAUDE_CODE_ENABLE_TELEMETRY=1` + OTLP exporter；traces + metrics（token/cost） |
| Hooks 自建 trace | `PreToolUse`/`PostToolUse` 写自定义日志 |

#### 安全防护

| 能力 | 程度 |
|------|------|
| Prompt injection 防护 | **SDK 不提供**；需自己在 system_prompt/分隔符实现 |
| Jailbreak detection | **不提供** |
| Content filtering | 依赖 API 层（Anthropic 模型自带），SDK 不叠加 |
| 文件系统越界 | 工作目录 `cwd` + `additional_directories` 限制；`disallowed_tools=["Read(../..)"]` 模式 |
| 工具命令黑名单 | `PreToolUse` hook 或 `disallowed_tools=["Bash(rm *)"]` |

---

## 3. OpenAI Agents SDK 能力全貌

包名 `openai-agents`（PyPI），纯 Python 库。

### 3.1 架构本质

**纯 Python 进程内调用**：

```
Orbion Python 进程
    ↓ 直接调用 Runner.run() / Runner.run_streamed()
agent loop 在 Python 进程内执行
    ↓ HTTP API（via ModelProvider）
OpenAI / Anthropic / GLM / DeepSeek 服务
```

无子进程，无 Node.js 依赖，agent loop / 工具执行 / session 全部在 Python 进程内。

### 3.2 能力清单

#### 工具调用机制

| 能力 | API | 详情 |
|------|-----|------|
| 装饰器声明 | `@function_tool` | 自动从签名+docstring 生成 JSON schema（griffe 解析 + Pydantic 校验） |
| 手动构造 | `FunctionTool(name, description, params_json_schema, on_invoke_tool)` | 完全自定义 |
| 上下文注入 | 首参 `ctx: RunContextWrapper[T]` | 依赖注入 |
| 超时 | `@function_tool(timeout=2.0, timeout_behavior=...)` | `error_as_result` / `raise_exception` / `timeout_error_function` |
| 错误处理 | `failure_error_function` | 默认返回错误文本给 LLM；`None` 时直接抛出 |
| 图像/文件输出 | `ToolOutputImage` / `ToolOutputFileContent` | 工具可返回多模态 |
| Agents as tools | `Agent.as_tool(tool_name, ...)` | 子 agent 作为工具调用 |

#### 权限控制（关键缺口）

| 能力 | API | 详情 |
|------|-----|------|
| 工具级 approval | `@function_tool(needs_approval=True \| async fn)` | 函数签名 `(_ctx, params, _call_id) -> bool` |
| 手动 interruption 流 | `result.interruptions` → `result.to_state()` → `state.approve/reject` → `Runner.run(agent, state)` | 跨 handoff / 嵌套 Agent.as_tool 都通过外层 RunState 统一暂停 |
| 自动 approval | `ShellTool/ApplyPatchTool.on_approval`；`HostedMCPTool.on_approval_request` | 程序化决策，无需暂停 |
| Sticky 决策 | `state.approve(item, always_approve=True)` | 持久化到 RunState，可序列化恢复 |
| 拒绝消息自定义 | `RunConfig.tool_error_formatter` + `state.reject(rejection_message=...)` | 全局/单次双层 |
| **per-tool authorization 中间件** | **❌ 不存在** | Issue #2868：内容校验有 guardrails，但身份/角色/速率限制/审计的细粒度授权层为缺失能力 |

#### MCP 集成（原生支持，四种传输）

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

#### 流式输出

| 能力 | API |
|------|-----|
| 入口 | `Runner.run_streamed()` → `RunResultStreaming.stream_events()` |
| 事件类型 | `RawResponsesStreamEvent` / `RunItemStreamEvent` / `AgentUpdatedStreamEvent` |
| 原始事件 | OpenAI Responses 格式 `response.output_text.delta` 等 |
| 语义事件名 | `message_output_created`/`tool_called`/`tool_output`/`handoff_occured`/`mcp_approval_requested` |
| usage 位置 | `context_wrapper.usage`（流式末尾才稳定） |
| 取消 | `result.cancel(mode="immediate"\|"after_turn")` |
| 兼容 approval | 暂停后用 `to_state()` → resume `Runner.run_streamed(agent, state)` |

#### Handoffs

| 能力 | API |
|------|-----|
| 简单声明 | `Agent(handoffs=[agent_a, agent_b])` 自动生成 `transfer_to_<name>` 工具 |
| 定制 | `handoff(agent, tool_name_override, on_handoff, input_type, is_enabled, nest_handoff_history)` |
| 输入过滤 | `input_filter: HandoffInputData -> HandoffInputData`；`agents.extensions.handoff_filters` 预置 |
| 嵌套历史 | `RunConfig.nest_handoff_history` + `handoff_history_mapper`（beta） |
| 边界 | Input guardrails 只在链首 agent；output guardrails 只在最终 agent；tool guardrails 不应用于 handoff |

#### Guardrails（三层）

| 类型 | 装饰器 | 时机 |
|------|--------|------|
| 输入 | `@input_guardrail` | 链首 agent，默认并行，可 `run_in_parallel=False` 阻断式 |
| 输出 | `@output_guardrail` | 最终 agent，仅串行 |
| 工具 | `@tool_input_guardrail` / `@tool_output_guardrail`（`@function_tool(...)` 注册） | 每次 function tool 调用前后；可 `reject_content` / `allow` / 替换输出 |
| tripwire | `GuardrailFunctionOutput(tripwire_triggered=True)` → 抛异常 |
| 限制 | tool guardrails **只对 function_tool 生效**，handoff / hosted tools / `Agent.as_tool()` 不走此管道 |

#### 会话状态

| 实现 | 用途 |
|------|------|
| `Session` 协议 | `get_items/add_items/pop_item/clear_session` 四方法，可自实现 |
| 内置 | `SQLiteSession` / `AsyncSQLiteSession` / `RedisSession` / `SQLAlchemySession` / `MongoDBSession` / `EncryptedSession` |
| 历史裁剪 | `RunConfig.session_input_callback(history, new_input) -> list`；`SessionSettings(limit=N)` |
| 限制 | 不能与 `conversation_id` / `previous_response_id` 同用 |

#### 结构化输出

| 能力 | API |
|------|-----|
| 类型 | `Agent(output_type=Pydantic BaseModel \| dataclass \| TypedDict \| TypeAdapter 兼容)` |
| 强制工具 | `ModelSettings(tool_choice="auto"\|"required"\|"none"\|"<tool_name>")` |
| 工具行为 | `tool_use_behavior="run_llm_again"\|"stop_on_first_tool"\|StopAtTools(...)\|ToolsToFinalOutputFunction` |

#### 生命周期 hooks

| 范围 | 回调 |
|------|------|
| Run 级 | `RunHooks.on_agent_start/end`、`on_llm_start/end`、`on_tool_start/end`、`on_handoff`、`on_llm_error` |
| Agent 级 | `agent.hooks` (`AgentHooks`) |
| 上下文 | `AgentHookContext`（含 usage） / `RunContextWrapper` / 工具为 `ToolContext` |

#### 取消与中断

- `result.cancel(mode="immediate"|"after_turn")`（仅流式）
- `max_turns` 参数（Runner 级）
- approval interruption → `to_state()` 序列化持久化，可跨进程恢复
- Realtime API 支持 voice 自动打断检测

#### 错误处理 / 重试

| 能力 | API |
|------|-----|
| 模型级重试 | `ModelSettings(retry=ModelRetrySettings(max_retries, backoff, policy))`，runtime-only，opt-in |
| 预置 policy | `retry_policies.never/provider_suggested/network_error/http_status([...])/retry_after/any/all` |
| 安全边界 | abort / provider 标记 replay-unsafe / 已开始流式输出后**不重试** |
| 工具错误 | `failure_error_function` / `failure_error_function=None` 抛出 |
| MCP 错误 | `failure_error_function` per server / agent |

#### 追踪

| 能力 | API |
|------|-----|
| 默认开启 | `trace()` / `agent_span` / `generation_span` / `function_span` / `guardrail_span` / `handoff_span` |
| 禁用 | `OPENAI_AGENTS_DISABLE_TRACING=1` / `set_tracing_disabled(True)` / `RunConfig.tracing_disabled` |
| 自定义导出 | `add_trace_processor()` 追加、`set_trace_processors()` 替换 |
| 敏感数据 | `RunConfig.trace_include_sensitive_data=False` |
| 第三方模型 tracing | `set_tracing_export_api_key(OPENAI_KEY)` 单独传 tracing key |
| 生态 | 30+ 集成（Langfuse / Arize / Datadog / MLflow …） |

#### 安全防护

- ❌ **无内置 prompt injection 防护 / content filter**：guardrails 仅提供框架，内容检测需自己实现
- ✅ `EncryptedSession` 提供 TTL + 透明加密
- ✅ `redact_secrets` 等需自实现

#### Computer use / Browser use

| 工具 | 状态 |
|------|------|
| `ComputerTool` | 本地 harness，需实现 `Computer`/`AsyncComputer` 接口 |
| `ShellTool` | 本地 / 托管容器双模；本地需 `executor`；可挂载 `ShellToolSkillReference` skills |
| `ApplyPatchTool` | 本地，需实现 `ApplyPatchEditor` |
| `WebSearchTool`/`FileSearchTool`/`CodeInterpreterTool`/`ImageGenerationTool` | hosted，仅 OpenAI Responses 模型 |

#### ModelProvider 抽象（关键）

| 能力 | API |
|------|-----|
| ModelProvider 接口 | `get_model(model_name: str \| None) -> Model` |
| Model 接口 | `async def get_response(system_instructions, input, model_settings, tools, output_schema, handoffs, tracing)` |
| 内置 Provider | `OpenAIModelProvider`、`OpenAIChatCompletionsModel`（兼容 OpenAI compat 端点） |
| 社区 Provider | `AnthropicModelProvider`（参考社区实现，~200-300 行） |
| 自定义 base_url | 支持，覆盖 GLM/DeepSeek 等 OpenAI 兼容接口 |

---

## 4. 技术能力对比矩阵

### 4.1 核心能力重叠度约 75%

| 能力 | Claude Agent SDK | OpenAI Agents SDK | 差距 |
|------|------------------|-------------------|------|
| Agent loop | ✅ CLI 内部 | ✅ Runner.run() | 对等 |
| 工具注册/调用 | ✅ @tool + 内置工具 | ✅ @function_tool + Computer/Shell/ApplyPatch | OpenAI 内置工具类更多 |
| MCP | ✅ stdio/http/in-process | ✅ stdio/streamable http/sse/hosted | 基本对等 |
| 流式输出 | ✅ StreamEvent | ✅ stream_events | 对等 |
| 结构化输出 | ✅ output_format + Pydantic | ✅ output_type + Pydantic | 对等 |
| Session | ✅ JSONL 自动持久化 + resume/fork/compaction | ✅ Session 协议 + SQLite/Redis/SQLAlchemy/MongoDB/Encrypted | OpenAI 后端更多样 |
| Permission | ✅ 5 段管线 | ✅ approval callback + guardrails | Claude 更精细，OpenAI 更灵活 |
| 生命周期 hooks | ✅ PreToolUse/PostToolUse/UserPromptSubmit/Stop/SessionStart/SessionEnd | ✅ RunHooks + AgentHooks | Claude 更细，OpenAI 更结构化 |
| 取消/中断 | ⚠️ 进程 cancel（非协作式） | ✅ result.cancel(mode=)（协作式） | OpenAI 更精细 |
| 错误重试 | ⚠️ CLI 内部管理，不暴露策略 | ✅ ModelRetrySettings + 预置 policies | OpenAI 更可控 |
| Tracing | ✅ OTel + cost/usage | ✅ add_trace_processor + 30+ 集成 | OpenAI 生态更丰富 |
| Compaction | ✅ 自动 | ✅ OpenAIResponsesCompactionSession | 对等 |

### 4.2 Claude Agent SDK 独有/更强

| 能力 | 影响 |
|------|------|
| Extended thinking（effort 级别） | 推理深度可控，Claude 模型特有 |
| Checkpointing（/rewind 文件回滚） | 工具执行的文件改动可回滚 |
| 内置 WebSearch/WebFetch/Monitor 工具 | 开箱即用 |
| Prompt caching 透明管理 | CLI 自动设置 cache_control |
| Session 零配置持久化 | CLI 自动写 JSONL |

### 4.3 OpenAI Agents SDK 独有/更强

| 能力 | 影响 |
|------|------|
| **ModelProvider 抽象** | 支持任意模型—— **Orbion 双 SDK 需求的决定性差异** |
| 纯 Python，无 Node.js 依赖 | 部署简单 |
| Guardrails 框架（三层） | 内容校验结构化 |
| Handoffs（多 Agent 切换） | input_filter 可定制 |
| 协作式取消 | 等当前工具完成再取消 |
| 错误重试策略可控 | retry_policies 预置 |
| Tracing 生态（30+ 集成） | 可观测性成熟 |
| Computer/Shell/ApplyPatch 内置工具 | 本地 harness |
| Session 存储后端多样 | 含 EncryptedSession |

---

## 5. 用户反馈对比

> 注：基于 GitHub issues + 社区帖子（非实时数据，建议实地核查）

### 5.1 综合反馈矩阵

| 维度 | Claude Agent SDK | OpenAI Agents SDK |
|------|------------------|-------------------|
| 文档质量 | ⚠️ 较稀疏，迁移指南不完整 | ✅ 较完整，有迁移指南 |
| API 稳定性 | 🔴 **频繁 breaking changes**（minor 版本间也改） | 🟡 较稳定（2025 年从 Swarm 演进时有大改） |
| 工具调用可靠性 | 🔴 `can_use_tool` callback 已知 bug | ✅ `needs_approval` 较稳定 |
| 错误信息 | 🔴 CLI 子进程错误不透明 | ✅ Python 异常栈清晰 |
| 调试体验 | 🔴 难（agent loop 在 CLI 子进程内） | ✅ 好（纯 Python，可直接 step through） |
| 流式输出 | 🟡 偶有 chunk 顺序错乱 | ✅ stream_events 语义事件名清晰 |
| session 管理 | ✅ 零配置自动持久化 | 🟡 需自己选 Session 后端 |
| 部署复杂度 | 🔴 **Node.js + CLI 依赖是主要吐槽点** | ✅ 纯 Python，部署简单 |
| 上手难度 | 🟡 中等（CLI 子进程模型 + settings.json + permission_mode） | ✅ 较低（Python 开发者熟悉的范式） |
| 社区活跃度 | 🟡 仓库较新，issue 响应较快但解决率参差 | ✅ 仓库活跃，OpenAI 团队维护 |
| 多模型支持反馈 | 🔴 强制绑定 Anthropic | ✅ ModelProvider 抽象被广泛点赞 |
| MCP 集成反馈 | ✅ 原生支持，配置简单 | ✅ 原生支持，MCPServerManager 被点赞 |
| Token 计费透明度 | 🔴 CLI 黑盒，token 消耗不透明 | ✅ context_wrapper.usage 清晰 |
| 取消/中断体验 | 🔴 进程终止被认为是"粗暴"的取消方式 | ✅ 协作式取消被点赞 |

### 5.2 关键用户痛点（具体 issue）

#### Claude Agent SDK

- **#27203**：`canUseTool` callback 对 background subagent 不触发——**权限校验失效**
- **#227**："Can Use Tool is not working"——多版本回归，开发者踩坑
- **breaking changes 频繁**：Reddit 多个帖子建议"pin 版本，别用 latest"
- **CLI 子进程错误难诊断**：`ProcessError(exit_code=1)` 不告诉具体哪步失败

#### OpenAI Agents SDK

- **#2868**：per-tool authorization 缺口——但这是设计限制不是 bug，可上层补
- **tool guardrails 只对 function_tool 生效**：handoff / hosted tools 不走此管道（文档已说明，但仍被吐槽）
- **Session 不能与 conversation_id 同用**：迁移到 Sessions 时有限制

### 5.3 用户画像

#### Claude Agent SDK 的用户画像
- **喜欢的**：Claude Code 用户、想要"开箱即用"agent 能力的、不在乎 Node.js 依赖的 Node.js 项目
- **不喜欢的**：Python 项目（跨语言 IPC 痛点）、需要精细控制 agent loop 的、生产环境（稳定性顾虑）

#### OpenAI Agents SDK 的用户画像
- **喜欢的**：Python 开发者、需要多模型支持、生产环境（稳定性 + 可观测性）、想要 Pythonic 体验的
- **不喜欢的**：需要 Claude Agent SDK 独有能力（Extended thinking / Checkpointing）的、想要"零配置 session"的

---

## 6. 部署与运维对比

### 6.1 进程模型差异

| 维度 | Claude Agent SDK | OpenAI Agents SDK |
|------|------------------|-------------------|
| 进程模型 | Python + CLI 子进程 | 纯 Python 进程内 |
| 通信 | stdin/stdout JSON | HTTP API |
| 状态 | CLI 持有 session（自动持久化 JSONL） | 无状态（每次请求带 messages） |
| 工具执行位置 | **CLI 子进程内** | Python 进程内 |
| 启动开销 | 每次启动 CLI 子进程 | 无 |
| 部署依赖 | 需要 Claude Code CLI 二进制（Node.js 运行时） | 无 |
| 错误模型 | `ProcessError` / `CLIJSONDecodeError` / `CLINotFoundError` | HTTPError |
| 取消 | 进程终止（非协作式） | `result.cancel(mode=)` 协作式 |
| session resume | CLI 自动加载 JSONL | 需自己实现 |

### 6.2 Docker 镜像影响

| 项 | 不用 Agent SDK | 用 Claude Agent SDK | 用 OpenAI Agents SDK |
|---|---|---|---|
| Node.js 运行时 | ❌ 不需要 | ✅ **必须装** | ❌ 不需要 |
| 全局 npm install | ❌ 不需要 | ❌ 不需要（CLI 已捆绑在 wheel 里） | ❌ 不需要 |
| Docker 基础镜像 | `python:3.12-slim` | 需 multi-stage 或自定义（Python + Node.js） | `python:3.12-slim` |
| 镜像体积增量 | — | +约 100-200MB（Node.js + CLI） | 无 |
| 网络依赖（构建时） | 无 | 无（CLI 在 wheel 里） | 无 |
| 网络依赖（运行时） | 无 | 无（CLI 子进程本地） | 无 |

### 6.3 工具执行位置差异对安全策略的影响

- **Claude 模式**：工具在 CLI 子进程执行，Orbion Python 进程只能通过 `can_use_tool` callback 在工具执行**前**拦截。路径越界、跨项目越权、shell 黑名单必须写成 callback，不能直接在 handler 内做。
- **OpenAI 模式**：工具 handler 在 Orbion Python 进程内执行，业务规则可以直接在 handler 入口做。

### 6.4 myco 案例参考

myco（sst/opencode 同期项目）的部署经验：

| 项 | myco |
|---|---|
| 语言 | Node.js 20（Alpine Docker） |
| Agent SDK | `@anthropic-ai/claude-agent-sdk`（npm 包） |
| CLI 安装 | Docker Builder 阶段全局 `npm install -g @anthropic-ai/claude-code` |
| 镜像基础 | `node:20-alpine` + bash, git, openssh, ca-certificates, curl, Caddy |
| 架构 | amd64 + arm64 动态检测 |
| 入口脚本 | 150 行（首次初始化、数据迁移、企业代理、Git credential、Caddy 启动） |

myco 是 Node.js 项目，用 Claude Agent SDK 是"同语言生态"自然选择。Orbion 是 Python 项目，用 Claude Agent SDK 意味着在 Python 进程里 spawn Node.js 子进程——跨语言 IPC，运维复杂度比 myco 高。

### 6.5 opencode 案例参考

opencode（sst/opencode）选择**自研 runtime**，不用任何 Agent SDK：

| 项 | opencode |
|---|---|
| 语言 | Go（核心 + TUI 用 Bubble Tea） |
| Agent runtime | 自研（provider 抽象层 + agent loop + session + tool） |
| 用 Claude Agent SDK？ | ❌ 不用 |
| 用 OpenAI Agents SDK？ | ❌ 不用 |
| 自研原因 | Go 生态无 Agent SDK + 多 provider 抽象需求（含本地模型） |

opencode 自研是因为**被迫**（Go 生态空白）+ **多 provider 抽象需求**（含本地模型）。Orbion 的情况不同：Python 生态有现成 Agent SDK，且不需要支持本地模型。所以 opencode 的"自研 runtime"路线**不是 Orbion 必须模仿的**。

---

## 7. 对 Orbion 已实施步骤的影响

### 7.1 步骤 1（数据模型基础）

**不受影响**。`user_models`/`artifacts`/`tasks`/`agent_runs`/`skill_calls`/`outbox_events` 等表都是 Orbion 业务数据，SDK 不关心。

### 7.2 步骤 2（用户模型配置 + 加密）

**不受影响**。UserModel、AES-GCM 加密、AgentModelMapping 四级解析都是 Orbion 平台层，SDK 不参与。

### 7.3 步骤 3（ModelAdapter 双 SDK 适配器）

**影响最大，需要重构**。

#### 当前问题

- `ClaudeAgentSDKAdapter` 实际用 `anthropic` 包（Provider SDK），**不是** `claude-agent-sdk` 包
- `OpenAIAgentsSDKAdapter` 实际用 `openai` 包（Provider SDK），**不是** `openai-agents` 包
- 命名误导：名为"AgentSDK"实为"ProviderSDK"
- 接口仅 `complete()/stream()`，未提供 Agent SDK 能力（agent loop / tool / permission / session / MCP）

#### 重构方向

- Adapter 接口从 `complete()/stream()` 升级到 `query()/run() + register_tool() + permission_callback`
- `OpenAIAgentRuntimeAdapter`：用 `openai-agents` 包（先实现），委托 agent loop / tool / MCP / session / streaming
- `ClaudeAgentRuntimeAdapter`：用 `claude-agent-sdk` 包（保留接口，未来实现）
- AdapterFactory 缓存策略保留

### 7.4 步骤 4（Skill 系统）

**影响中等，需要简化**。

#### 当前问题

- `MCPManager` 完全冗余（SDK 已提供 MCPServerStdio / mcp_servers）
- `SkillExecutor.execute()` 的参数校验、失败计数、invoke_handler 与 SDK 重叠
- `SkillDeclaration.parameters` / `handler` 与 SDK 工具定义范式冲突
- `SkillResult.ok/reason` 自定义格式与 SDK 工具返回格式不一致
- `AgentDeclaration.max_iterations=25` 与 SDK `max_turns` 重复

#### 重构方向

**删除**：
- `app/biz/skills/mcp_manager.py` 整个模块（用 SDK `MCPServerStdio`）
- `SkillRegistry` 类（用 SDK Agent.tools 配置）
- `SkillExecutor.execute()` 中的参数校验、invoke_handler、失败计数逻辑
- `SkillResult.ok/reason` 自定义格式
- `AgentDeclaration.max_iterations` 字段

**保留并改造**：
- `SkillDeclaration`：保留 `skill_id` / `risk_level`，删除 `parameters` / `handler`（由 SDK 工具定义提供）
- `SkillExecutor`：改为"策略检查器"，只暴露 `check_permission(skill_id, params, ctx) -> PermissionDecision`
- `AuditWriter` / `PgSkillAuditWriter`：保留，改为 SDK hook 实现
- `PermissionError` / `DispatchPermissionChecker`：保留（SDK 缺口，per-tool authorization #2868）
- `wrap_user_content` / `INJECTION_GUARD_RULE`：保留（SDK 缺口，prompt injection 防护）
- `build_agent_env`：保留（SDK 缺口，env 隔离）
- `is_blacklisted`：保留，改为生成 SDK disallow 模式的工具函数
- `_check_path_safety`：保留，挪到 SDK hook 内调用
- 6 角色 `AgentDeclaration`：保留为业务配置

### 7.5 步骤 5（AgentRuntime 核心 dispatch）

**未实施，重构方向决定其形态**。

- dispatch 流程调用 Adapter 的 `query()/run()`，不再自己写 agent loop
- 上下文组装保持不变
- agent loop 内的 tool 调用、permission 检查、streaming 分发都由 Adapter 负责

### 7.6 步骤 6-10

- **步骤 6（事件驱动调度）**：不受影响
- **步骤 7（失败恢复）**：失败重试用 SDK 内置 retry policy，Orbion 不再自建
- **步骤 10（可观测性）**：tracing 用 SDK OTel 能力，Orbion 只补 skill_calls 表写入

---

## 8. 决策与实施路径

### 8.1 决策结论

**封装 Agent SDK（非 Provider SDK）；先实现 OpenAI Agents SDK，保留 Claude Agent SDK 接口能力**。

### 8.2 决策依据

| 维度 | Claude Agent SDK | OpenAI Agents SDK | 决策权重 |
|------|------------------|-------------------|---------|
| 模型支持 | 仅 Anthropic | 任意模型（ModelProvider） | 🔴 决定性 |
| 部署依赖 | Node.js + CLI | 纯 Python | 🟡 高 |
| 生产稳定性 | breaking changes 频繁 | 较稳定 | 🟡 高 |
| 调试体验 | CLI 黑盒 | Python debugger | 🟡 中 |
| 权限可靠性 | `can_use_tool` 已知 bug | approval 稳定 | 🟡 高 |
| 用户反馈 | Python 项目痛点多 | Python 开发者友好 | 🟡 中 |

### 8.3 为什么先实现 OpenAI Agents SDK

1. **模型覆盖广**：OpenAI Agents SDK 通过 ModelProvider 可覆盖 OpenAI / Anthropic / GLM / DeepSeek 全部主流模型——**一个实现覆盖所有 provider**
2. **部署简单**：纯 Python，无 Node.js 依赖，Docker 镜像不变
3. **生产稳定**：API 稳定性好于 Claude Agent SDK
4. **调试友好**：纯 Python，可直接 step through
5. **权限可靠**：approval callback 无已知 bug

### 8.4 为什么保留 Claude Agent SDK 接口能力

1. **Claude 独有能力**：Extended thinking / Checkpointing / 内置 WebSearch 等 OpenAI Agents SDK 没有
2. **未来演进**：Claude Agent SDK 还在快速演进（0.2.x 版本），稳定后可接入
3. **避免锁定**：保留切换能力，未来如果 OpenAI Agents SDK 方向不利可切换
4. **Adapter 抽象层**：双 Adapter 共用统一接口，上层 dispatch 不感知差异

### 8.5 实施路径

#### 阶段 1：定义统一 Agent Runtime 接口契约

定义 SDK 无关的 Agent Runtime 接口（query/run + tool 注册 + permission callback + session + streaming），作为步骤 3 Adapter 重构、步骤 4 Skill 系统重构、步骤 5 dispatch 重写的共同基准。

#### 阶段 2：重构步骤 3 Adapter

- 新增 `OpenAIAgentRuntimeAdapter`：用 `openai-agents` 包
  - OpenAI 模型：用 `OpenAIModelProvider`
  - Anthropic 模型：写 `AnthropicModelProvider`（参考社区实现，~200-300 行）
  - GLM/DeepSeek：用 `OpenAIModelProvider` + 自定义 base_url
- 新增 `ClaudeAgentRuntimeAdapter`：预留接口（`NotImplementedError`），未来用 `claude-agent-sdk` 包
- AdapterFactory 按 provider 路由

#### 阶段 3：重构步骤 4 Skill 系统

- 删除 `MCPManager`（用 SDK `MCPServerStdio`）
- `SkillExecutor` 简化为策略检查器
- `SkillDeclaration` 改为 SDK 工具薄包装
- 保留：跨项目越权、路径越界、Prompt injection 防护、env 隔离、审计持久化、6 角色配置

#### 阶段 4：实施步骤 5 dispatch

- dispatch 调用 Adapter 的 `query()/run()`
- 上下文组装保持不变
- 业务规则挂 SDK hooks（PreToolUse / can_use_tool / RunHooks.on_tool_end）

#### 阶段 5：未来接入 Claude Agent SDK（可选）

当需要 Extended thinking / Checkpointing / 内置 WebSearch 等 Claude 独有能力时，实施 `ClaudeAgentRuntimeAdapter`。

### 8.6 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| OpenAI Agents SDK #2868 per-tool authorization 缺口 | Orbion 自建 `DispatchPermissionChecker` + `SkillExecutor.check_permission`，作为 Adapter 层 hook 注入 |
| `AnthropicModelProvider` 需自己写 | 参考社区实现，~200-300 行；先做 spike 验证可行性 |
| OpenAI Agents SDK 绑定 OpenAI 生态 | ModelProvider 抽象协议开放，可迁移；保留 Claude Adapter 接口作为后备 |
| 双 Adapter 行为一致性 | 统一接口契约 + 双 Adapter 行为测试 |
| 步骤 3-4 返工成本 | 当前步骤 4 未提交到主线（本地 commit），返工成本最低 |

---

## 9. 附录：来源

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
- [GitHub issue #27203: canUseTool callback not invoked](https://github.com/anthropics/claude-agent-sdk-python/issues/27203)
- [GitHub issue #227: Can Use Tool is not working](https://github.com/anthropics/claude-agent-sdk-python/issues/227)

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
- [GitHub issue #2868: Per-tool authorization](https://github.com/openai/openai-agents-python/issues/2868)

### 双 SDK 对比与迁移
- [Migrate from Claude Agent SDK to OpenAI Agents SDK](https://developers.openai.com/cookbook/examples/agents_sdk/migrate-from-claude-agent-sdk/readme)

### 参考案例
- myco 分析报告（项目内 `temp/myco-analysis.md`）
- opencode（[sst/opencode on GitHub](https://github.com/sst/opencode)）
