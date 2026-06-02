# Orbion MVP Phase 1 实施计划

## 策略

**基础层 + 迭代切片**：先建稳固基础层（EventBus + EventStore + Auth + Permissions），然后沿核心循环的4个阶段做迭代切片，后端全部完成后整体做前端，最后E2E验证和性能基准。

选择理由：
- 基础层是所有业务的硬依赖，拆成小步TDD每步独立可验证
- 4个迭代切片自然对应核心循环阶段边界（讨论→智能→审批→执行），每步增量清晰
- 前端整体跟进，后端API稳定后联调顺畅，Playwright有完整后端可测
- 与设计文档的模块划分（hub层先建、biz层迭代）天然对齐

## 约束

1. 每步大小合适，可独立验证
2. 步骤依赖关系正确，标注可并行的步骤对
3. 严格符合1.1-1.6设计文档目标，不缩水不遗漏
4. 每步遵循TDD流程（写测试→验证失败→实现→验证通过→commit）
5. 计划不含实现细节（无代码、无函数签名、无SQL）
6. 每步有总结好的commit message
7. 完备测试覆盖：UT、API测试、集成测试、Playwright E2E、性能Benchmark

## 步骤总览

共22步，6节：

| 节 | 步骤 | 核心增量 | 对应验证点 |
|----|------|---------|-----------|
| 基础层 | 1-8 | EventBus/EventStore/Protocol/Auth/Permissions | 基础设施就绪 |
| 讨论切片 | 9-11 | 项目+成员+线程+消息+SSE | 验证点1-2 + SSE |
| Agent切片 | 12-14 | Agent声明+调度+ModelAdapter+Prompt+Memory | 验证点3-4 |
| 审批切片 | 15-17 | 计划审批+产出审批+Git | 验证点5-8 |
| 前端 | 18-20 | 三栏工作区完整交互 | 验证点9 |
| 验证 | 21-22 | 9点E2E + 性能Benchmark | 全部验证点 |

---

## 第1节：基础层（8步）

严格顺序依赖，每步TDD。

### - [x] 步骤 1：项目脚手架与开发环境

**增量**：FastAPI应用入口、pyproject.toml（uv管理）、docker-compose.yml（PostgreSQL only）、目录结构（app/hub/ + app/biz/）、Settings配置类、gitignore、hub/channels/static.py骨架（Vite SPA 静态文件挂载预留点）

**依赖**：无

**测试设计**：见 [1-mvp-test-design](1-mvp-test-design.md) TC-1.1–TC-1.4

**commit message**：`init: 项目脚手架与开发环境`

---

### - [x] 步骤 2：数据库schema与核心模型定义

**增量**：migrations/001_initial.sql（8张MVP表+索引）、Event Pydantic模型、EventType枚举（9个MVP事件）、EventPayload schema（9种payload结构）、User/Project/Thread/Member/Plan/Output/Agent等全部Pydantic模型

> 本步包含 8 张表 SQL + 16+ Pydantic 模型类，工作量约为其他基础层步骤的 2-3 倍。

**依赖**：步骤1

**测试设计**：见 [1-mvp-test-design](1-mvp-test-design.md) TC-2.1–TC-2.8

**commit message**：`feat: 数据库初始化与核心模型定义`

---

### - [x] 步骤 3：EventBus抽象接口与进程内实现

**增量**：EventBus Protocol定义、InProcessEventBus实现（asyncio.create_task调度handler）

**依赖**：步骤2（EventType枚举）

**测试设计**：见 [1-mvp-test-design](1-mvp-test-design.md) TC-3.1–TC-3.6

**commit message**：`feat: EventBus抽象接口与进程内实现`

---

### - [x] 步骤 4：Event Store PostgreSQL持久化

**增量**：EventStore类（append、get_events_by_correlation、get_events_by_project）

**依赖**：步骤2（Event模型、表结构）

**测试设计**：见 [1-mvp-test-design](1-mvp-test-design.md) TC-4.1–TC-4.6

**commit message**：`feat: Event Store PostgreSQL持久化`

---

### - [x] 步骤 5：CQRS投影更新与查询

**增量**：EventProjections类（4个MVP投影的更新和查询方法）、投影作为EventBus subscriber注册。触发事件来源：thread_messages投影由DiscussionMessageCreated/DiscussionSummaryGenerated触发、execution_plans投影由ExecutionPlanProposed/Approved/Rejected触发、task_outputs投影由TaskOutputGenerated/Approved/RevisionRequested触发、project_members投影由MemberAdded触发

**依赖**：步骤3（EventBus）、步骤4（EventStore）

**测试设计**：见 [1-mvp-test-design](1-mvp-test-design.md) TC-5.1–TC-5.11

**commit message**：`feat: CQRS投影更新与查询`

---

### - [x] 步骤 6：EventStore/EventProjections Protocol接口抽象与注册表

**增量**：EventStoreProtocol和EventProjectionsProtocol从实现文件分离到独立接口文件、PostgresEventStore实现移到postgres_store.py新文件、PostgresEventProjections实现移到postgres_projections.py新文件、注册表模式（STORE_IMPLEMENTATIONS/PROJECTIONS_IMPLEMENTATIONS dict + load_*_impl()动态加载函数）、Protocol契约isinstance测试 + 注册表动态加载测试

**依赖**：步骤3（EventBus Protocol模式参照）、步骤4（EventStore实现类改名）、步骤5（EventProjections实现类改名）

**测试设计**：见 [1-mvp-test-design](1-mvp-test-design.md) TC-6.1–TC-6.4

**commit message**：`feat: EventStore/EventProjections Protocol接口抽象`

---

### - [x] 步骤 7：JWT认证与Admin审批注册

**增量**：auth模块（routes、models、service、policy、repository、postgres_repo）、修改migrations/001_initial.sql（users表增加status/is_admin列+部分索引）、UserRepositoryProtocol(ABC) CRUD接口 + UserRepositoryProvider(ABC) connect/close/scoped生命周期 + REPO_PROVIDER_IMPLEMENTATIONS注册表 + load_user_repo_provider()动态加载、PostgresUserRepository + PostgresUserRepositoryProvider self-managed pool + scoped()事务模式、EventType枚举新增UserRegistered+UserRegisteredPayload、JWT签发/验证、get_current_user和require_admin FastAPI依赖（合并到routes.py）、bcrypt密码哈希、RegistrationPolicy Protocol定义（evaluate参数为repo:UserRepositoryProtocol）、AdminApprovalPolicy实现（首个用户自动审批+is_admin，后续用户pending）、3个审批端点（GET /auth/users/pending、POST /auth/users/{id}/approve、POST /auth/users/{id}/reject）、注册响应含status字段（pending/active）、登录检查用户状态（pending/rejected返回403）

**依赖**：步骤2（User模型、users表）、步骤4（EventStore，注册事件持久化）

**测试设计**：见 [1-mvp-test-design](1-mvp-test-design.md) TC-7.1–TC-7.21

**commit message**：`feat: JWT认证与Admin审批注册`

---

### - [x] 步骤 8：Bitmask权限位与角色映射

**增量**：HumanPermission/AgentPermission枚举、角色→权限位映射、compute_permissions函数、require_permission FastAPI依赖注入

**依赖**：步骤2（project_members表结构）、步骤7（get_current_user依赖）

**测试设计**：见 [1-mvp-test-design](1-mvp-test-design.md) TC-8.1–TC-8.12

**commit message**：`feat: Bitmask权限位与角色映射`

---

## 第2节：讨论切片（3步）

验证点1-2 + SSE推送能力。顺序依赖基础层全部完成。

### - [x] 步骤 9：项目与成员管理API

**增量**：projects模块（routes、models、service）、POST/GET /projects、GET /projects/{id}、POST /projects/{id}/members、创建者自动成为Owner、项目列表只返回用户参与的项目

**依赖**：步骤1-8全部完成

**测试设计**：见 [1-mvp-test-design](1-mvp-test-design.md) TC-9.1–TC-9.7

**commit message**：`feat: 项目与成员管理API`

---

### - [x] 步骤 10：讨论线程与消息API

**增量**：threads模块（routes、models、service）、POST/GET /projects/{id}/threads、POST/GET /threads/{id}/messages（游标分页）、request_summary标志、消息发送时发布DiscussionMessageCreated事件

**依赖**：步骤9（项目API，线程属于项目）

**测试设计**：见 [1-mvp-test-design](1-mvp-test-design.md) TC-10.1–TC-10.7

**commit message**：`feat: 讨论线程与消息API`

---

### - [ ] 步骤 11：SSE推送与事件流端点

**增量**：channels模块（ChannelAdapter Protocol、SSEChannel实现）、GET /events/stream端点、SSE连接管理（按project_id分组）、SSE推送10种事件类型（9业务+agent_status_changed）

**依赖**：步骤10（消息API，SSE推送消息事件）

**测试设计**：见 [1-mvp-test-design](1-mvp-test-design.md) TC-11.1–TC-11.6

**commit message**：`feat: SSE推送与事件流端点`

---

## 第3节：Agent切片（3步）

验证点3-4。顺序依赖基础层+讨论切片。

### - [ ] 步骤 12：Agent声明与事件调度器

**增量**：agents模块（AgentDeclaration定义含skills字段、3个内置Agent声明模板、AgentScheduler、AgentRuntime生命周期管理）、app/biz/agents/skills.py（SkillDeclaration数据结构定义）、ModelAdapter Protocol骨架定义（仅接口，ClaudeAdapter在步骤13实现）、POST/GET /projects/{id}/agents API、GET /projects/{id}/agents/{id}/status API、Agent注册时自动分配角色权限位、Agent状态机idle→running→idle/error

**依赖**：步骤1-11全部完成（Agent订阅讨论事件、写入投影）

**测试设计**：见 [1-mvp-test-design](1-mvp-test-design.md) TC-12.1–TC-12.12

**commit message**：`feat: Agent声明与事件调度器`

---

### - [ ] 步骤 13：模型适配与Prompt组装流程

**增量**：ModelAdapter Protocol定义、ClaudeAdapter实现（Anthropic SDK）、PromptInput/ModelOutput/ModelConfig/EventSummary结构、7步prompt组装流程、task描述转换规则、产出解析→发布新事件

**依赖**：步骤12（Agent声明和调度器，prompt组装需要AgentDeclaration）

**测试设计**：见 [1-mvp-test-design](1-mvp-test-design.md) TC-13.1–TC-13.6

**commit message**：`feat: 模型适配与Prompt组装流程`

---

### - [ ] 步骤 14：Agent层次化记忆管理

**增量**：memory模块（AgentMemory类）、层次化memory.md读写（平台→项目→Agent→任务4层）、记忆注入prompt流程

**依赖**：步骤13（prompt组装流程，memory注入是7步中的第4步）

**测试设计**：见 [1-mvp-test-design](1-mvp-test-design.md) TC-14.1–TC-14.7

**commit message**：`feat: Agent层次化记忆管理`

---

## 第4节：审批切片（3步）

验证点5-8。顺序依赖基础层+讨论切片+Agent切片。

### - [ ] 步骤 15：执行计划审批API

**增量**：plans模块（routes、models、service）、GET /projects/{id}/plans（可按thread_id和status过滤）、POST /plans/{id}/approve（部分审批）、POST /plans/{id}/reject、计划状态机（proposed→approved/rejected）

**依赖**：步骤1-14全部完成（计划由Agent产出、审批事件触发Agent）

**测试设计**：见 [1-mvp-test-design](1-mvp-test-design.md) TC-15.1–TC-15.7

**commit message**：`feat: 执行计划审批API`

---

### - [ ] 步骤 16：任务产出审批API

**增量**：outputs模块（routes、models、service）、GET /projects/{id}/outputs（可按plan_id过滤）、POST /outputs/{id}/approve、POST /outputs/{id}/request-revision、产出状态机（generated→approved/revision_requested）、产出version自增逻辑

**依赖**：步骤15（计划审批完成后才有产出可审批）

**测试设计**：见 [1-mvp-test-design](1-mvp-test-design.md) TC-16.1–TC-16.6

**commit message**：`feat: 任务产出审批API`

---

### - [ ] 步骤 17：Git集成与审批后自动commit

**增量**：git模块（GitService）、产出审批通过后自动commit到本地仓库、commit内容与产出一致、要求修改不触发commit

**依赖**：步骤16（产出审批API，审批通过触发Git commit）

**测试设计**：见 [1-mvp-test-design](1-mvp-test-design.md) TC-17.1–TC-17.4

**commit message**：`feat: Git集成与审批后自动commit`

---

## 第5节：前端（3步）

验证点9。后端全部完成后整体跟进。

### - [ ] 步骤 18：前端项目脚手架与三栏布局骨架

**增量**：Vite+React+TypeScript+TailwindCSS+shadcn/ui 项目初始化、App.tsx路由结构、Workspace.tsx三栏布局骨架、API调用封装层（api.ts）、SSE连接管理封装（sse.ts）、JWT存储封装（auth.ts）、Vite开发代理配置、hub/channels/static.py实际配置（挂载web/dist/到FastAPI）

**依赖**：步骤1-17全部完成（后端API已稳定）

**测试设计**：见 [1-mvp-test-design](1-mvp-test-design.md) TC-18.1–TC-18.4

**commit message**：`feat: 前端项目脚手架与三栏布局骨架`

---

### - [ ] 步骤 19：前端登录注册与JWT管理

**增量**：登录表单、注册表单（含pending状态提示）、管理员审批面板（待审批用户列表+approve/reject按钮）、JWT存储/刷新逻辑、登出流程、未登录重定向、pending/rejected状态提示页、登录后跳转工作区

**依赖**：步骤18（前端骨架）

**测试设计**：见 [1-mvp-test-design](1-mvp-test-design.md) TC-19.1–TC-19.9

**commit message**：`feat: 前端登录注册与JWT管理`

---

### - [ ] 步骤 20：前端三栏工作区完整交互

**增量**：ThreadList组件（线程列表+状态标记+成员列表）、DiscussionPanel组件（消息流+人类/Agent不同样式+request_summary按钮）、ExecutionPanel组件（计划卡片+审批操作+产出diff预览+Agent状态）、MessageItem组件（人类/Agent样式区分）、PlanCard组件、OutputDiff组件、SSE实时更新全部面板

**依赖**：步骤19（登录后才能进入工作区）

**测试设计**：见 [1-mvp-test-design](1-mvp-test-design.md) TC-20.1–TC-20.6

**commit message**：`feat: 前端三栏工作区完整交互`

---

## 第6节：E2E验证与性能基准（2步）

### - [ ] 步骤 21：Playwright E2E自我构建9点验证

**增量**：Playwright测试套件覆盖自我构建9点验证标准

**依赖**：步骤1-20全部完成

**测试设计**：见 [1-mvp-test-design](1-mvp-test-design.md) TC-21.1–TC-21.9

**commit message**：`test: Playwright E2E自我构建9点验证`

---

### - [ ] 步骤 22：性能基准测试与基线数据

**增量**：性能基准测试套件（EventStore、InProcessEventBus、CQRS投影、SSE推送）

**依赖**：步骤21（E2E通过后才有可基准测试的完整系统）

**测试设计**：见 [1-mvp-test-design](1-mvp-test-design.md) TC-22.1–TC-22.6

**commit message**：`test: 性能基准测试与基线数据`

---

## 设计文档覆盖映射

确保1.1-1.6每项设计要求均有对应步骤，不缩水不遗漏。

| 设计文档 | 覆盖内容 | 对应步骤 |
|---------|---------|---------|
| 1.1 MVP总体设计 | 单服务架构、模块划分(hub/biz)、模块间通信(EventBus)、外部依赖、启动流程、开发环境、测试策略、部署、CI/CD(MVP不做)、static.py骨架 | 1, 3, 9-17, 18(static.py配置), 21-22 |
| 1.2 事件基础设施 | EventBus Protocol、InProcessEventBus、EventStoreProtocol+PostgresEventStore、EventProjectionsProtocol+PostgresEventProjections、CQRS投影(4视图)、EventPayload Schema(9种)、correlation_id/causation_id、ChannelAdapter Protocol、SSEChannel | 2-6, 11(ChannelAdapter+SSE), 13 |
| 1.3 数据模型 | 8张MVP表+索引、全部Pydantic模型、迁移策略、项目边界硬隔离、读写分离 | 2, 4-5, 9-10, 15-16 |
| 1.4 权限模型 | HumanPermission/AgentPermission bitmask、角色映射(4人类+3Agent)、compute_permissions、require_permission依赖、各端点权限要求 | 8, 9-16 |
| 1.5 API与认证 | JWT认证流程、21个REST端点+1个SSE流、FastAPI路由组织、错误响应格式、UserRepositoryProtocol+Provider ABC+注册表+scoped()事务模式 | 7, 9-11, 12, 15-16 |
| 1.6 Agent Runtime | 3个Agent声明(含skills字段)、SkillDeclaration数据结构、ModelAdapter Protocol骨架+ClaudeAdapter、生命周期(idle/running/error)、PromptInput/ModelOutput、7步prompt组装、AgentScheduler、AgentRuntime、memory.md管理 | 12(skills+Protocol骨架), 13-14 |

## 依赖关系图

```
步骤1 → 步骤2 → 步骤3 ─┐
                  └→ 步骤4 → 步骤5 → 步骤6 → 步骤7 → 步骤8
                                                      ↓
                                            步骤9 → 步骤10 → 步骤11
                                                      ↓
                                            步骤12 → 步骤13 → 步骤14
                                                      ↓
                                            步骤15 → 步骤16 → 步骤17
                                                      ↓
                                            步骤18 → 步骤19 → 步骤20
                                                      ↓
                                            步骤21 → 步骤22
```

标注可并行的步骤对：
- 步骤3和步骤4可并行（都只依赖步骤2，EventBus与EventStore互相不依赖）
- 步骤7和步骤8的UT部分可并行（compute_permissions是纯位运算，不依赖JWT；但步骤8的API测试需步骤7的get_current_user）

每步完成且验证通过后才进入下一步。