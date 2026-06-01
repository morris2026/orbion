# Orbion MVP Phase 1 测试设计

本文档为 [1-mvp-implementation-plan](1-mvp-implementation-plan.md) 的配套测试设计，按实施计划步骤顺序组织。每个步骤的验证标准在此展开为具体用例划分、主体流程和检查项。

## 用例格式

每个用例包含：
- **用例名**：概括测试意图
- **类型**：UT / API / 集成 / E2E / Benchmark / 构建验证
- **主体流程**：操作序列
- **检查项**：断言要点

---

## 步骤 1：项目脚手架与开发环境

### TC-1.1 空FastAPI应用启动

- **类型**：UT
- **主体流程**：导入 app.main 模块，创建 FastAPI 实例
- **检查项**：app 对象存在，app.title 为 "Orbion MVP"

### TC-1.2 Settings默认值加载

- **类型**：UT
- **主体流程**：无环境变量时创建 Settings 实例
- **检查项**：postgres_url 为默认值，jwt_secret 为默认值，anthropic_api_key 为空字符串，repo_path 为 "./repo"，memory_base_path 为 "./data/memory"

### TC-1.3 Settings环境变量覆盖

- **类型**：UT
- **主体流程**：设置 ORBION_POSTGRES_URL 等环境变量后创建 Settings 实例
- **检查项**：对应字段值被环境变量覆盖

### TC-1.4 PostgreSQL连接

- **类型**：集成
- **主体流程**：docker compose up -d 启动 PostgreSQL，用 asyncpg 连接 postgres_url
- **检查项**：连接成功，可执行 SELECT 1

---

## 步骤 2：数据库schema与核心模型定义

### TC-2.1 数据库迁移执行

- **类型**：集成
- **主体流程**：执行 migrations/001_initial.sql
- **检查项**：8张表全部创建成功（event_log、users、projects、project_members、threads、thread_messages、execution_plans、task_outputs），7个索引全部创建成功（含idx_users_status部分索引）

### TC-2.2 Event模型校验

- **类型**：UT
- **主体流程**：创建 Event 实例，测试必填字段缺失、类型错误
- **检查项**：正常创建成功；project_id缺失报错；participant_type不在human/agent范围报错；payload默认为空dict

### TC-2.3 EventType枚举完整性

- **类型**：UT
- **主体流程**：遍历 EventType 枚举成员
- **检查项**：10个MVP事件类型全部存在（DiscussionMessageCreated、DiscussionSummaryGenerated、ExecutionPlanProposed、ExecutionPlanApproved、ExecutionPlanRejected、TaskOutputGenerated、TaskOutputApproved、TaskOutputRevisionRequested、MemberAdded、UserRegistered）；值与字符串名称一致

### TC-2.4 EventPayload schema结构与字段级验证

每个子用例验证一种 EventPayload 的字段存在性、类型约束、必填/选填、默认值。

#### TC-2.4.1 DiscussionMessageCreated payload

- **类型**：UT
- **主体流程**：创建 DiscussionMessageCreated 实例（thread_id, content, request_summary）→ 测试字段缺失 → 测试字段类型错误 → 测试默认值
- **检查项**：正常创建成功；thread_id（str）和content（str）必填，缺失报错；request_summary（bool）默认false；content非str类型报错

#### TC-2.4.2 DiscussionSummaryGenerated payload

- **类型**：UT
- **主体流程**：创建 DiscussionSummaryGenerated 实例（consensus_points, divergence_points, action_items）→ 测试字段缺失 → 测试字段类型错误
- **检查项**：正常创建成功；consensus_points/divergence_points/action_items 均为 list[str]，缺失报错；传入 list[int] 类型报错

#### TC-2.4.3 ExecutionPlanProposed payload

- **类型**：UT
- **主体流程**：创建 ExecutionPlanProposed 实例（plan_id, tasks）→ 测试 tasks 内部结构 → 测试字段缺失
- **检查项**：正常创建成功；plan_id（str）必填；tasks 为 list，每项含 task_id（str）/type（str）/description（str）/dependencies（list[str]）/priority（str，限定high/medium/low）；priority 非法值报错

#### TC-2.4.4 ExecutionPlanApproved payload

- **类型**：UT
- **主体流程**：创建 ExecutionPlanApproved 实例（approved_tasks, modifications）→ 测试选填字段
- **检查项**：正常创建成功；approved_tasks（list）必填；modifications（str）选填，默认None

#### TC-2.4.5 ExecutionPlanRejected payload

- **类型**：UT
- **主体流程**：创建 ExecutionPlanRejected 实例（reason, suggestions）→ 测试字段缺失
- **检查项**：正常创建成功；reason（str）必填；suggestions（list[str]）必填

#### TC-2.4.6 TaskOutputGenerated payload

- **类型**：UT
- **主体流程**：创建 TaskOutputGenerated 实例（task_id, plan_id, output_id, output_type, content, diff, file_paths）→ 测试字段类型和选填
- **检查项**：正常创建成功；task_id/plan_id/output_id/output_type/content（str）必填；output_type 限定 code/document；diff（str）选填（output_type=code时）；file_paths（list[str]）选填

#### TC-2.4.7 TaskOutputApproved payload

- **类型**：UT
- **主体流程**：创建 TaskOutputApproved 实例（output_id, feedback）→ 测试选填字段
- **检查项**：正常创建成功；output_id（str）必填；feedback（str）选填，默认None

#### TC-2.4.8 TaskOutputRevisionRequested payload

- **类型**：UT
- **主体流程**：创建 TaskOutputRevisionRequested 实例（output_id, task_id, issues, suggestions）→ 测试字段缺失
- **检查项**：正常创建成功；output_id/task_id（str）必填；issues（list[str]）/suggestions（list[str]）必填

#### TC-2.4.9 MemberAdded payload

- **类型**：UT
- **主体流程**：创建 MemberAdded 实例（participant_id, project_id, participant_type, display_name, roles）→ 测试字段缺失 → 测试默认值
- **检查项**：正常创建成功；participant_id/project_id/display_name（str）必填；participant_type 限定 human/agent；roles（list[str]）默认空列表

#### TC-2.4.10 UserRegistered payload

- **类型**：UT
- **主体流程**：创建 UserRegisteredPayload 实例（username, display_name, status, is_admin）→ 测试字段缺失 → 测试默认值
- **检查项**：正常创建成功；username/display_name（str）必填；status（str）限定 pending/active/rejected；is_admin（bool）默认false

### TC-2.5 User模型校验

- **类型**：UT
- **主体流程**：创建 UserRegister、UserLogin、UserResponse、RegistrationResponse、RegistrationDecision、PendingUserResponse、ApprovalResponse 实例
- **检查项**：username 长度限制3-32、pattern限制字母数字下划线；password 最小长度8；display_name 最小长度1；RegistrationResponse.access_token可选（仅active状态）；RegistrationDecision.status限定pending/active

### TC-2.6 Project/Member/Thread/Message模型校验

- **类型**：UT
- **主体流程**：创建 ProjectCreate、ProjectResponse、MemberAdd、MemberResponse、ThreadCreate、ThreadResponse、MessageCreate、MessageResponse 实例
- **检查项**：各模型必填字段校验生效，长度限制生效，默认值正确（如 ThreadCreate.type默认"discussion"，MessageCreate.request_summary默认false）

### TC-2.7 PlanTask/PlanResponse/OutputResponse模型校验

- **类型**：UT
- **主体流程**：创建 PlanTask、PlanResponse、PlanApprove、PlanReject、OutputResponse、OutputApprove、OutputRequestRevision 实例
- **检查项**：PlanTask.status默认"pending"；PlanApprove.modifications可选；OutputResponse.diff可选（output_type=code时）；version默认1

### TC-2.8 Agent模型校验

- **类型**：UT
- **主体流程**：创建 AgentCreate、AgentResponse、AgentStatus 实例
- **检查项**：AgentCreate.agent_type限定summary/decompose/execute；AgentResponse.subscribed_events为列表；AgentStatus.current_task可选

---

## 步骤 3：EventBus抽象接口与进程内实现

### TC-3.1 publish后subscribe的handler收到payload

- **类型**：UT
- **主体流程**：subscribe("TestEvent", handler) → publish("TestEvent", payload)
- **检查项**：handler被调用一次，收到的payload与publish传入的一致

### TC-3.2 unsubscribe后不再收到事件

- **类型**：UT
- **主体流程**：subscribe("TestEvent", handler) → 获取subscription_id → unsubscribe(subscription_id) → publish("TestEvent", payload)
- **检查项**：handler不被调用

### TC-3.3 多handler订阅同一事件类型

- **类型**：UT
- **主体流程**：subscribe("TestEvent", handler1) → subscribe("TestEvent", handler2) → publish("TestEvent", payload)
- **检查项**：handler1和handler2都被调用，都收到相同payload

### TC-3.4 handler异常不阻塞publish和其他handler

- **类型**：UT
- **主体流程**：subscribe("TestEvent", bad_handler) → subscribe("TestEvent", good_handler) → publish("TestEvent", payload)；bad_handler抛异常
- **检查项**：publish不抛异常；good_handler正常收到payload

### TC-3.5 未订阅的事件类型publish无异常

- **类型**：UT
- **主体流程**：publish("UnknownEvent", payload)
- **检查项**：无异常抛出，无handler被调用

### TC-3.6 handler异步不阻塞publish

- **类型**：UT
- **主体流程**：subscribe("TestEvent", slow_handler) → publish("TestEvent", payload)；slow_handler需要1秒执行
- **检查项**：publish立即返回，不需要等待handler完成

---

## 步骤 4：Event Store PostgreSQL持久化

### TC-4.1 append写入事件

- **类型**：集成
- **主体流程**：创建Event → store.append(event) → 查询event_log表
- **检查项**：event_log表有对应记录，event_id/project_id/event_type/participant_id/participant_type/payload/correlation_id值正确，created_at自动生成

### TC-4.2 get_events_by_correlation按链路查询

- **类型**：集成
- **主体流程**：append多个Event（同一correlation_id，不同event_type） → store.get_events_by_correlation(correlation_id)
- **检查项**：返回所有同correlation_id的事件，按created_at排序，数量与写入一致

### TC-4.3 get_events_by_project项目边界硬隔离

- **类型**：集成
- **主体流程**：append事件到proj-A → append事件到proj-B → store.get_events_by_project("proj-A")
- **检查项**：只返回proj-A的事件，不含proj-B的事件

### TC-4.4 event_type可选过滤

- **类型**：集成
- **主体流程**：append不同类型事件到同一project → store.get_events_by_project("proj-X", event_type="DiscussionMessageCreated")
- **检查项**：只返回指定类型的事件

### TC-4.5 causation_id为null的事件

- **类型**：集成
- **主体流程**：append Event（causation_id=None） → 查询验证
- **检查项**：causation_id字段为NULL，查询正常返回

### TC-4.6 重复event_id写入

- **类型**：集成
- **主体流程**：append Event（event_id="dup-1"） → 再append同一event_id的Event
- **检查项**：第二次写入失败（PRIMARY KEY冲突），第一次记录不受影响

---

## 步骤 5：CQRS投影更新与查询

### TC-5.1 DiscussionMessageCreated → thread_messages投影

- **类型**：集成
- **主体流程**：publish DiscussionMessageCreated事件 → 投影handler更新thread_messages → 查询thread_messages(thread_id)
- **检查项**：投影表有新记录，participant_id/content/event_type与事件payload一致，project_id正确

### TC-5.2 DiscussionSummaryGenerated → thread_messages投影

- **类型**：集成
- **主体流程**：publish DiscussionSummaryGenerated事件 → 投影更新thread_messages → 查询
- **检查项**：Agent产出也进入thread_messages投影，participant_type="agent"，event_type="DiscussionSummaryGenerated"

### TC-5.3 ExecutionPlanProposed → execution_plans投影

- **类型**：集成
- **主体流程**：publish ExecutionPlanProposed事件 → 投影更新execution_plans → 查询
- **检查项**：状态为"proposed"，tasks JSONB内容正确，proposed_by为agent participant_id

### TC-5.4 ExecutionPlanApproved → execution_plans状态变更

- **类型**：集成
- **主体流程**：先写入proposed计划 → publish ExecutionPlanApproved → 投影更新 → 查询
- **检查项**：状态从"proposed"变为"approved"，approved_by列表追加审批者信息

### TC-5.5 ExecutionPlanRejected → execution_plans状态变更

- **类型**：集成
- **主体流程**：先写入proposed计划 → publish ExecutionPlanRejected → 投影更新 → 查询
- **检查项**：状态变为"rejected"

### TC-5.6 TaskOutputGenerated → task_outputs投影

- **类型**：集成
- **主体流程**：publish TaskOutputGenerated事件 → 投影更新task_outputs → 查询
- **检查项**：状态为"generated"，diff/file_paths内容正确

### TC-5.7 TaskOutputApproved/RevisionRequested → task_outputs状态变更

- **类型**：集成
- **主体流程**：分别publish TaskOutputApproved和TaskOutputRevisionRequested → 投影更新 → 查询
- **检查项**：Approved后状态为"approved"；RevisionRequested后状态为"revision_requested"

### TC-5.8 MemberAdded → project_members投影

- **类型**：集成
- **主体流程**：publish MemberAdded事件 → 投影更新project_members → 查询
- **检查项**：成员信息正确（participant_id/project_id/type/display_name/roles）

### TC-5.9 投影查询返回结构化数据

- **类型**：集成
- **主体流程**：写入多种事件后查询各投影
- **检查项**：查询返回可直接用于前端响应的结构（字段名和类型与Pydantic模型对应）

### TC-5.10 correlation_id多跳链路追踪

- **类型**：集成
- **主体流程**：模拟完整协作链：写入 DiscussionMessageCreated（correlation_id="chain-1"）→ 写入 DiscussionSummaryGenerated（correlation_id="chain-1"，causation_id指向上一跳）→ 写入 ExecutionPlanProposed（correlation_id="chain-1"，causation_id指向上一跳）→ 写入 ExecutionPlanApproved（correlation_id="chain-1"，causation_id指向上一跳）→ 写入 TaskOutputGenerated（correlation_id="chain-1"，causation_id指向上一跳）→ store.get_events_by_correlation("chain-1")
- **检查项**：返回5条事件，correlation_id全部为"chain-1"；每跳的causation_id正确指向上一跳的event_id；按created_at排序

### TC-5.11 project_members联合主键约束

- **类型**：集成
- **主体流程**：通过投影写入 user-A 到 proj-X 的成员记录 → 再次尝试写入 user-A 到 proj-X
- **检查项**：第二次写入因 PRIMARY KEY(participant_id, project_id) 冲突失败（或幂等返回已存在记录，不产生重复数据）

---

## 步骤 6：EventStore/EventProjections Protocol接口抽象与注册表

### TC-6.1 PostgresEventStore满足EventStoreProtocol契约

- **类型**：UT
- **主体流程**：创建PostgresEventStore实例 → isinstance(store, EventStoreProtocol)
- **检查项**：返回True，Protocol契约验证通过

### TC-6.2 PostgresEventProjections满足EventProjectionsProtocol契约

- **类型**：UT
- **主体流程**：创建PostgresEventProjections实例 → isinstance(projections, EventProjectionsProtocol)
- **检查项**：返回True，Protocol契约验证通过

### TC-6.3 load_store_impl按注册表动态加载实现类

- **类型**：UT
- **主体流程**：load_store_impl("postgres") → 返回PostgresEventStore类；load_store_impl("unknown") → 抛ValueError
- **检查项**：注册表中有"postgres"映射；动态加载返回正确类；未注册名抛ValueError

### TC-6.4 load_projections_impl按注册表动态加载实现类

- **类型**：UT
- **主体流程**：load_projections_impl("postgres") → 返回PostgresEventProjections类；load_projections_impl("unknown") → 抛ValueError
- **检查项**：注册表中有"postgres"映射；动态加载返回正确类；未注册名抛ValueError

---

## 步骤 7：JWT认证与Admin审批注册

### TC-7.1 用户注册成功（非首个用户，pending状态）

- **类型**：API
- **主体流程**：先创建一个admin用户 → POST /auth/register（username/password/display_name）
- **检查项**：返回user_id/username/display_name/status="pending"/message含"awaiting approval"；无access_token；users表有新记录，status为pending，is_admin为false，password_hash为bcrypt格式

### TC-7.2 第一个用户注册自动审批（active状态+JWT+is_admin）

- **类型**：API
- **主体流程**：空users表 → POST /auth/register（username/password/display_name）
- **检查项**：返回user_id/username/display_name/status="active"/access_token/token_type="bearer"/message含"first admin"；users表status为active，is_admin为true；JWT payload含is_admin=true

### TC-7.3 用户登录成功（active用户）

- **类型**：API
- **主体流程**：先注册并审批用户 → POST /auth/login（username/password）
- **检查项**：返回access_token；JWT payload含sub/username/is_admin/exp/iat/iss="orbion"

### TC-7.4 pending用户登录返回403

- **类型**：API
- **主体流程**：注册用户（pending状态） → POST /auth/login（username/password）
- **检查项**：返回403，detail含"pending approval"

### TC-7.5 rejected用户登录返回403

- **类型**：API
- **主体流程**：注册用户 → admin拒绝 → POST /auth/login（username/password）
- **检查项**：返回403，detail含"rejected"

### TC-7.6 重复用户名注册

- **类型**：API
- **主体流程**：注册用户A → 再用相同username注册
- **检查项**：返回409，detail含"已存在"类信息

### TC-7.7 错误密码登录

- **类型**：API
- **主体流程**：注册并审批用户 → POST /auth/login（正确username+错误password）
- **检查项**：返回401

### TC-7.8 JWT过期

- **类型**：UT
- **主体流程**：创建一个exp为过去时间的JWT → 用get_current_user解码
- **检查项**：抛出401异常

### TC-7.9 get_current_user正常返回

- **类型**：UT
- **主体流程**：创建有效JWT（含is_admin=true） → get_current_user解码
- **检查项**：返回User对象，id/username/is_admin与JWT payload一致

### TC-7.10 require_admin拦截非管理员

- **类型**：UT
- **主体流程**：创建JWT（is_admin=false） → 调用require_admin依赖
- **检查项**：抛出403异常，detail含"Admin required"

### TC-7.11 管理员审批用户

- **类型**：API
- **主体流程**：admin注册 → 新用户注册（pending） → admin POST /auth/users/{id}/approve
- **检查项**：返回user_id/username/status="active"；users表status变为active；被审批用户可以正常登录

### TC-7.12 管理员拒绝用户

- **类型**：API
- **主体流程**：admin注册 → 新用户注册（pending） → admin POST /auth/users/{id}/reject（reason="不符合要求"）
- **检查项**：返回user_id/username/status="rejected"/reason="不符合要求"；users表status变为rejected

### TC-7.13 列出待审批用户

- **类型**：API
- **主体流程**：admin注册 → 注册2个新用户 → admin GET /auth/users/pending
- **检查项**：返回2个pending用户，含user_id/username/display_name/status="pending"/created_at

### TC-7.14 非管理员审批返回403

- **类型**：API
- **主体流程**：注册非admin用户 → 用该用户token POST /auth/users/{id}/approve
- **检查项**：返回403

### TC-7.15 注册事件写入EventStore

- **类型**：集成
- **主体流程**：注册用户 → 查询EventStore按participant_id查询事件
- **检查项**：有UserRegistered事件记录；event_type正确；participant_id为新注册用户的user_id；participant_type="human"；project_id为空字符串（用户注册不关联项目）；payload含username/display_name/status

### TC-7.16 JWT生成和验证

- **类型**：UT
- **主体流程**：jwt生成（含is_admin字段） → jwt解码验证
- **检查项**：payload含sub/username/is_admin/exp/iat/iss="orbion"；HS256算法；密钥从config读取

### TC-7.17 密码哈希与验证

- **类型**：UT
- **主体流程**：bcrypt哈希密码 → 验证正确密码 → 验证错误密码
- **检查项**：正确密码验证成功；错误密码验证失败；哈希长度符合bcrypt格式

### TC-7.18 无JWT访问受保护端点

- **类型**：API
- **主体流程**：不带Authorization header请求受保护端点
- **检查项**：返回401

### TC-7.19 AdminApprovalPolicy Protocol契约验证

- **类型**：UT
- **主体流程**：创建AdminApprovalPolicy实例 → isinstance(policy, RegistrationPolicy)
- **检查项**：返回True，Protocol契约验证通过

### TC-7.20 对已active用户审批返回400

- **类型**：API
- **主体流程**：admin注册 → 第二个用户注册并审批 → admin POST /auth/users/{id}/approve（对已active用户）
- **检查项**：返回400，detail含"already active"

### TC-7.21 对不存在用户审批返回404

- **类型**：API
- **主体流程**：admin注册 → admin POST /auth/users/{不存在的id}/approve
- **检查项**：返回404

---

## 步骤 8：Bitmask权限位与角色映射

### TC-8.1 HumanPermission位值正确

- **类型**：UT
- **主体流程**：遍历HumanPermission枚举
- **检查项**：VIEW_DISCUSSION=1<<0, CREATE_MESSAGE=1<<1, EDIT_OWN_MESSAGE=1<<2, APPROVE_PLAN=1<<3, REJECT_PLAN=1<<4, VIEW_KNOWLEDGE=1<<5, EDIT_KNOWLEDGE=1<<6, MANAGE_MEMBERS=1<<7, MANAGE_AGENTS=1<<8, MANAGE_SPACE=1<<9, MANAGE_PROJECT=1<<10, ADMINISTRATOR=1<<11；共12个成员

### TC-8.2 AgentPermission位值正确

- **类型**：UT
- **主体流程**：遍历AgentPermission枚举
- **检查项**：QUERY_KNOWLEDGE=1<<0到MANAGE_AGENTS=1<<10；共11个成员

### TC-8.3 人类角色→权限位映射

- **类型**：UT
- **主体流程**：计算各角色的权限位组合值
- **检查项**：Owner=4095(all_bits)，Admin=2047(all_bits-ADMINISTRATOR)，Member=31(VIEW+CREATE+EDIT+APPROVE+REJECT)，Viewer=1(VIEW_DISCUSSION)

### TC-8.4 Agent角色→权限位映射

- **类型**：UT
- **主体流程**：计算各Agent角色的权限位组合值
- **检查项**：SummaryAgent=4(POST_DISCUSSION)，DecomposeAgent=76(POST+GENERATE_PLAN+REQUEST_APPROVAL)，ExecuteAgent=100(GENERATE_CODE+GENERATE_DOCUMENT+REQUEST_APPROVAL)

### TC-8.5 compute_permissions deny胜过allow

- **类型**：UT
- **主体流程**：compute_permissions(allow_bits=VIEW+CREATE, permission=VIEW_DISCUSSION, deny_bits=VIEW_DISCUSSION)
- **检查项**：返回False

### TC-8.6 compute_permissions allow位存在

- **类型**：UT
- **主体流程**：compute_permissions(allow_bits=Owner_all_bits, permission=APPROVE_PLAN, deny_bits=0)
- **检查项**：返回True

### TC-8.7 compute_permissions无allow位

- **类型**：UT
- **主体流程**：compute_permissions(allow_bits=VIEW_DISCUSSION, permission=APPROVE_PLAN, deny_bits=0)
- **检查项**：返回False

### TC-8.8 require_permission有权限→请求继续

- **类型**：API
- **主体流程**：创建Owner角色成员 → 请求需要APPROVE_PLAN权限的端点
- **检查项**：请求正常返回，不被拦截

### TC-8.9 require_permission无权限→403

- **类型**：API
- **主体流程**：创建Viewer角色成员 → 请求需要APPROVE_PLAN权限的端点
- **检查项**：返回403

### TC-8.10 ADMINISTRATOR位绕过所有权限检查

- **类型**：UT
- **主体流程**：compute_permissions(allow_bits含ADMINISTRATOR, permission=任意权限位, deny_bits=0)
- **检查项**：返回True

### TC-8.11 Admin角色权限验证

- **类型**：API
- **主体流程**：创建项目（Owner）→ 添加Admin角色成员 → Admin执行MANAGE_MEMBERS操作（添加成员）→ Admin执行MANAGE_AGENTS操作（注册Agent）→ Admin执行MANAGE_PROJECT级操作
- **检查项**：Admin可执行MANAGE_MEMBERS和MANAGE_AGENTS操作；Admin无法绕过ADMINISTRATOR级限制（如删除项目返回403）

### TC-8.12 错误响应格式统一验证

- **类型**：API
- **主体流程**：分别触发400（参数校验失败）、401（无JWT）、403（权限不足）、404（资源不存在）、409（冲突）错误
- **检查项**：所有错误响应均为 `{"detail": "string"}` 格式，Content-Type为application/json

---

## 步骤 9：项目与成员管理API

### TC-9.1 创建项目→创建者自动成为Owner

- **类型**：API
- **主体流程**：注册用户 → POST /projects（name/description）
- **检查项**：返回项目id/name/description/tenant_id/created_at；project_members投影有Owner记录（roles=4095）；EventStore有项目创建事件

### TC-9.2 列出用户参与的项目含role字段

- **类型**：API
- **主体流程**：用户A创建项目 → 用户A GET /projects
- **检查项**：返回列表含该项目，role字段为"owner"

### TC-9.3 项目详情→非成员返回404

- **类型**：API
- **主体流程**：用户A创建项目 → 用户B GET /projects/{id}
- **检查项**：返回404（非成员视为项目不存在）

### TC-9.4 添加成员→默认Member角色

- **类型**：API
- **主体流程**：Owner POST /projects/{id}/members（user_id/role="member"）
- **检查项**：返回MemberResponse；project_members投影有新成员记录（roles=31）

### TC-9.5 非Owner/Admin添加成员→403

- **类型**：API
- **主体流程**：Member角色用户 POST /projects/{id}/members
- **检查项**：返回403

### TC-9.6 项目创建事件+投影更新链路

- **类型**：集成
- **主体流程**：创建项目 → 查询EventStore → 查询project_members投影
- **检查项**：EventStore有事件记录；投影有Owner成员数据

### TC-9.7 MANAGE_MEMBERS权限位显式验证

- **类型**：API
- **主体流程**：创建Viewer角色成员 → Viewer POST /projects/{id}/members（user_id/role="member"）
- **检查项**：返回403，确认是MANAGE_MEMBERS权限位生效

---

## 步骤 10：讨论线程与消息API

### TC-10.1 创建线程

- **类型**：API
- **主体流程**：项目成员 POST /projects/{id}/threads（title）
- **检查项**：返回id/project_id/title/status="active"/type="discussion"/created_at

### TC-10.2 线程列表含聚合字段

- **类型**：API
- **主体流程**：创建线程 → 发送消息 → GET /projects/{id}/threads
- **检查项**：has_summary=false；pending_plan_count=0；message_count正确

### TC-10.3 发送消息→事件持久化+投影更新

- **类型**：集成
- **主体流程**：POST /threads/{id}/messages（content） → 查询EventStore → 查询thread_messages投影
- **检查项**：EventStore有DiscussionMessageCreated事件；thread_messages投影有新记录

### TC-10.4 消息列表游标分页

- **类型**：API
- **主体流程**：发送50条消息 → GET /threads/{id}/messages（无参数） → GET /threads/{id}/messages?before={最后一条id}&limit=20
- **检查项**：无参数返回最近50条；before参数返回指定ID之前的消息；limit限制条数；人类和Agent消息同流

### TC-10.5 request_summary标志

- **类型**：API
- **主体流程**：POST /threads/{id}/messages（content, request_summary=true）
- **检查项**：DiscussionMessageCreated事件payload中request_summary=true

### TC-10.6 非项目成员发送消息→403

- **类型**：API
- **主体流程**：非项目成员 POST /threads/{id}/messages
- **检查项**：返回403

### TC-10.7 消息发送错误路径

- **类型**：API
- **主体流程**：发送空字符串content → 发送超长content（10001字符）→ 对不存在的thread_id发送消息
- **检查项**：空content返回400；超长content返回400；不存在的thread_id返回404

---

## 步骤 11：SSE推送与事件流端点

### TC-11.1 建立SSE长连接

- **类型**：集成
- **主体流程**：注册→登录→GET /events/stream?project_id={id}&token={jwt}
- **检查项**：连接建立成功，返回Content-Type: text/event-stream

### TC-11.2 DiscussionMessageCreated→SSE推送message_created

- **类型**：集成
- **主体流程**：建立SSE连接 → 发送消息（触发DiscussionMessageCreated） → 等待SSE推送
- **检查项**：SSE收到event=message_created，data含消息内容

### TC-11.3 DiscussionSummaryGenerated→SSE推送summary_generated

- **类型**：集成
- **主体流程**：建立SSE连接 → 触发Agent产出摘要 → 等待SSE推送
- **检查项**：SSE收到event=summary_generated

### TC-11.4 所有9种业务事件+agent_status_changed通过SSE推送

- **类型**：集成
- **主体流程**：建立SSE连接 → 分别触发9种业务事件和1种Agent状态事件 → 等待SSE推送
- **检查项**：每种事件都有对应SSE推送（共10种SSE event类型）

### TC-11.5 无JWT→连接拒绝

- **类型**：API
- **主体流程**：GET /events/stream?project_id={id}（无token）
- **检查项**：返回401

### TC-11.6 project_id过滤

- **类型**：集成
- **主体流程**：订阅proj-A的SSE → 在proj-B发布事件 → 等待
- **检查项**：proj-A的SSE连接不收到proj-B的事件

---

## 步骤 12：Agent声明与事件调度器

### TC-12.1 注册Agent→project_members投影+权限位自动分配

- **类型**：API
- **主体流程**：POST /projects/{id}/agents（agent_type="summary"/display_name/model_id）
- **检查项**：返回AgentResponse含participant_id/project_id/type="agent"/agent_type/model_id/status="idle"/subscribed_events/roles；project_members投影有Agent成员（type="agent", agent_type="summary", roles=4）

### TC-12.2 SummaryAgent→DiscussionMessageCreated调度

- **类型**：集成
- **主体流程**：注册summary Agent → publish DiscussionMessageCreated(request_summary=true)
- **检查项**：AgentScheduler调用runtime.dispatch("summary", payload)

### TC-12.3 DecomposeAgent→DiscussionSummaryGenerated调度

- **类型**：集成
- **主体流程**：注册decompose Agent → publish DiscussionSummaryGenerated
- **检查项**：AgentScheduler调用runtime.dispatch("decompose", payload)

### TC-12.4 ExecuteAgent→ExecutionPlanApproved调度

- **类型**：集成
- **主体流程**：注册execute Agent → publish ExecutionPlanApproved
- **检查项**：AgentScheduler调用runtime.dispatch("execute", payload)

### TC-12.5 ExecuteAgent→TaskOutputRevisionRequested调度

- **类型**：集成
- **主体流程**：注册execute Agent → publish TaskOutputRevisionRequested
- **检查项**：AgentScheduler调用runtime.dispatch("execute", payload)

### TC-12.6 Agent状态转换idle→running→idle

- **类型**：UT
- **主体流程**：dispatch→Agent开始执行→产出完成→回到idle
- **检查项**：状态转换序列正确

### TC-12.7 Agent状态转换idle→running→error

- **类型**：UT
- **主体流程**：dispatch→Agent执行失败→状态变为error
- **检查项**：error状态记录错误信息

### TC-12.8 Agent列表含状态

- **类型**：API
- **主体流程**：GET /projects/{id}/agents
- **检查项**：返回列表含每个Agent的status字段

### TC-12.9 Agent详细状态

- **类型**：API
- **主体流程**：GET /projects/{id}/agents/{id}/status
- **检查项**：返回AgentStatus含completed_count/error_count/last_execution_at/current_task

### TC-12.10 Summary Agent阈值触发

- **类型**：集成
- **主体流程**：注册summary Agent → 连续发送10条消息（request_summary=false）→ 验证Agent触发
- **检查项**：第10条消息后Agent自动触发摘要生成；request_summary=true时立即触发（不等待阈值）

### TC-12.11 Agent不并发执行

- **类型**：UT
- **主体流程**：dispatch Agent（状态变为running）→ 再次dispatch同一Agent
- **检查项**：第二次dispatch被拒绝（Agent处于running时不接受新任务）；Agent回到idle后可再次dispatch

### TC-12.12 Agent管理API权限检查

- **类型**：API
- **主体流程**：Member角色 POST /projects/{id}/agents（agent_type="summary"）
- **检查项**：返回403（需MANAGE_AGENTS权限位，仅Owner/Admin拥有）

---

## 步骤 13：模型适配与Prompt组装流程

### TC-13.1 system_prompt组装

- **类型**：UT
- **主体流程**：从AgentDeclaration取role/goal/backstory → 组装system_prompt
- **检查项**：system_prompt含role/goal/backstory三段内容

### TC-13.2 history从correlation_id事件链获取

- **类型**：UT（mock EventStore）
- **主体流程**：mock EventStore返回事件列表 → 转换为EventSummary
- **检查项**：EventSummary.event_type/participant_id/participant_type/content/created_at字段正确；human→role="user"，agent→role="assistant"

### TC-13.3 task描述转换规则

- **类型**：UT
- **主体流程**：分别传入4种事件payload → 转换为task描述
- **检查项**：DiscussionMessageCreated→"请总结以下讨论线程..."；DiscussionSummaryGenerated→"请根据共识点和行动项分解..."；ExecutionPlanApproved→"请执行审批通过的代码任务..."；TaskOutputRevisionRequested→"请根据修改意见重新生成..."

### TC-13.4 PromptInput合并

- **类型**：UT
- **主体流程**：组装7步各部分 → 合并为PromptInput
- **检查项**：system_prompt/context(MVP为空)/memory/task/history字段齐全

### TC-13.5 mock ModelAdapter→产出解析→新事件构建

- **类型**：集成（mock LLM）
- **主体流程**：dispatch Agent → mock ModelAdapter返回ModelOutput → 解析产出 → 构建新事件payload → publish到EventBus + append到EventStore
- **检查项**：新事件event_type与AgentDeclaration.output_event_type一致；correlation_id继承触发事件的值；causation_id指向触发事件event_id；payload内容与ModelOutput对应

### TC-13.6 ClaudeAdapter调用格式

- **类型**：UT
- **主体流程**：构建PromptInput → 调用ClaudeAdapter._build_system/_build_messages
- **检查项**：system含role/goal/backstory+memory+context；messages含history(user/assistant映射)+task(user role)

---

## 步骤 14：Agent层次化记忆管理

### TC-14.1 层次加载平台→项目→Agent

- **类型**：UT
- **主体流程**：写入3层memory.md → load_memory_chain(project_id, agent_type)
- **检查项**：返回3层内容拼接，顺序为平台→项目→Agent

### TC-14.2 任务级memory加载

- **类型**：UT
- **主体流程**：写入4层memory.md → load_memory_chain(project_id, agent_type, correlation_id)
- **检查项**：返回4层内容拼接，任务层在最末

### TC-14.3 后加载覆盖前面的设置

- **类型**：UT
- **主体流程**：平台层写"使用英文" → Agent层写"使用中文" → load_memory_chain
- **检查项**：最终结果中"使用中文"生效（Agent层覆盖平台层）

### TC-14.4 不存在的层级→空字符串

- **类型**：UT
- **主体流程**：只写平台层 → load_memory_chain（无项目层和Agent层文件）
- **检查项**：返回平台层内容+空内容，不报错

### TC-14.5 write_memory写入指定层级

- **类型**：UT
- **主体流程**：write_memory("project/proj-1/agents/summary", "内容") → read_memory验证
- **检查项**：文件创建成功，内容正确

### TC-14.6 reset_agent_memory清空内容

- **类型**：UT
- **主体流程**：write_memory → reset_agent_memory → read_memory
- **检查项**：返回空字符串，文件仍存在（不删除）

### TC-14.7 memory注入PromptInput

- **类型**：集成
- **主体流程**：写入memory → Agent执行prompt组装 → 检查PromptInput.memory字段
- **检查项**：memory内容出现在PromptInput.memory中

---

## 步骤 15：执行计划审批API

### TC-15.1 计划列表可按thread_id和status过滤

- **类型**：API
- **主体流程**：创建多个计划（不同thread_id和status） → GET /projects/{id}/plans?thread_id=X&status=proposed
- **检查项**：只返回符合条件的计划

### TC-15.2 部分审批→状态approved+事件发布+投影更新

- **类型**：集成
- **主体流程**：POST /plans/{id}/approve（只批准部分task_id） → 查询execution_plans投影 → 查询EventStore
- **检查项**：计划状态变为approved；approved_tasks列表只有批准的task；EventStore有ExecutionPlanApproved事件；投影updated_at更新

### TC-15.3 拒绝+修改意见→状态rejected+事件发布

- **类型**：集成
- **主体流程**：POST /plans/{id}/reject（reason+suggestions） → 查询execution_plans投影 → 查询EventStore
- **检查项**：计划状态变为rejected；EventStore有ExecutionPlanRejected事件；reason和suggestions在payload中

### TC-15.4 APPROVE_PLAN权限位检查

- **类型**：API
- **主体流程**：Viewer角色用户 → POST /plans/{id}/approve
- **检查项**：返回403

### TC-15.5 计划状态机proposed→approved/rejected

- **类型**：API
- **主体流程**：proposed计划 → approve → 查询状态；proposed计划 → reject → 查询状态
- **检查项**：状态转换正确，无中间状态

### TC-15.6 REJECT_PLAN权限位验证

- **类型**：API
- **主体流程**：Viewer角色 POST /plans/{id}/reject（reason="test"）
- **检查项**：返回403（需REJECT_PLAN权限位，Viewer只有VIEW_DISCUSSION）

### TC-15.7 计划错误路径

- **类型**：API
- **主体流程**：对已approved计划再次approve → 对不存在的plan_id调用approve → 对已rejected计划再次reject
- **检查项**：非法状态转换返回400；不存在的ID返回404

---

## 步骤 16：任务产出审批API

### TC-16.1 产出列表可按plan_id过滤

- **类型**：API
- **主体流程**：创建多个产出（不同plan_id） → GET /projects/{id}/outputs?plan_id=X
- **检查项**：只返回该plan_id的产出

### TC-16.2 产出审批通过→状态approved+事件发布

- **类型**：集成
- **主体流程**：POST /outputs/{id}/approve → 查询task_outputs投影 → 查询EventStore
- **检查项**：产出状态变为approved；EventStore有TaskOutputApproved事件

### TC-16.3 产出要求修改→状态revision_requested+事件发布

- **类型**：集成
- **主体流程**：POST /outputs/{id}/request-revision（issues+suggestions） → 查询task_outputs投影 → 查询EventStore
- **检查项**：产出状态变为revision_requested；EventStore有TaskOutputRevisionRequested事件；issues和suggestions在payload中

### TC-16.4 产出状态机generated→approved/revision_requested

- **类型**：API
- **主体流程**：generated产出 → approve → 查询状态；generated产出 → request-revision → 查询状态
- **检查项**：状态转换正确

### TC-16.5 产出version自增

- **类型**：集成
- **主体流程**：Agent生成产出（version=1）→ request-revision → Agent重新生成产出 → 查询产出
- **检查项**：重新生成的产出version=2

### TC-16.6 产出错误路径

- **类型**：API
- **主体流程**：对已approved产出再次approve → 对不存在的output_id调用approve
- **检查项**：非法状态转换返回400；不存在的ID返回404

---

## 步骤 17：Git集成与审批后自动commit

### TC-17.1 产出审批通过→Git commit

- **类型**：集成
- **主体流程**：产出审批通过 → GitService执行commit → 查询git log
- **检查项**：本地repo有新commit；commit消息含产出信息；commit内容与file_paths和content/diff一致

### TC-17.2 产出要求修改→不触发commit

- **类型**：集成
- **主体流程**：产出request-revision → 查询git log
- **检查项**：无新commit产生

### TC-17.3 产出审批拒绝→不触发commit

- **类型**：集成
- **主体流程**：产出reject → 查询git log
- **检查项**：无新commit产生

### TC-17.4 本地repo不存在→自动初始化

- **类型**：集成
- **主体流程**：删除本地repo → 产出审批通过 → 查询repo
- **检查项**：repo自动初始化（git init），commit成功执行

---

## 步骤 18：前端项目脚手架与三栏布局骨架

### TC-18.1 Vite开发服务器启动

- **类型**：构建验证
- **主体流程**：npm run dev
- **检查项**：启动无错，可通过localhost:5173访问

### TC-18.2 API封装层调用后端

- **类型**：UT（Vitest）
- **主体流程**：api.ts封装各端点调用 → 通过Vite代理调用后端
- **检查项**：封装函数返回正确类型

### TC-18.3 SSE封装层建立连接

- **类型**：UT（Vitest）
- **主体流程**：sse.ts封装EventSource连接 → 建立连接 → 监听事件
- **检查项**：连接建立成功，事件解析正确

### TC-18.4 auth封装JWT存储

- **类型**：UT（Vitest）
- **主体流程**：auth.ts存储JWT → 读取JWT → 清除JWT
- **检查项**：存储后可读取，清除后为空

---

## 步骤 19：前端登录注册与JWT管理

### TC-19.1 注册表单→pending状态提示

- **类型**：UT（Vitest）
- **主体流程**：填写注册表单 → 提交 → 显示"等待管理员审批"提示
- **检查项**：响应status为pending时显示等待提示；不存储JWT；停留在注册页面或跳转至等待审批提示页

### TC-19.2 第一个用户注册→自动审批→跳转工作区

- **类型**：UT（Vitest）
- **主体流程**：第一个用户注册 → status为active → JWT存储 → 路由跳转
- **检查项**：JWT写入localStorage/sessionStorage；路由切换到/workspace

### TC-19.3 登录表单→JWT存储→跳转工作区

- **类型**：UT（Vitest）
- **主体流程**：填写登录表单 → 提交 → JWT存储 → 路由跳转
- **检查项**：JWT写入存储；路由切换到/workspace

### TC-19.4 pending用户登录→403提示

- **类型**：UT（Vitest）
- **主体流程**：pending用户尝试登录 → 收到403 → 显示"等待管理员审批"提示
- **检查项**：不存储JWT；显示pending状态提示

### TC-19.5 管理员审批面板→待审批用户列表

- **类型**：UT（Vitest）
- **主体流程**：admin登录 → 打开审批面板 → 渲染待审批用户列表
- **检查项**：列出pending用户；每个用户有approve/reject按钮

### TC-19.6 管理员审批操作→用户变为active

- **类型**：UT（Vitest）
- **主体流程**：admin点击approve按钮 → API调用 → 用户状态变为active
- **检查项**：approve按钮触发POST /auth/users/{id}/approve；用户从待审批列表移除

### TC-19.7 JWT过期→重定向登录页

- **类型**：UT（Vitest）
- **主体流程**：存储一个过期JWT → 路由守卫检查
- **检查项**：重定向到/login

### TC-19.8 未登录访问工作区→重定向登录页

- **类型**：UT（Vitest）
- **主体流程**：无JWT → 尝试访问/workspace路由
- **检查项**：重定向到/login

### TC-19.9 登出流程

- **类型**：UT（Vitest）
- **主体流程**：已登录状态（JWT已存储）→ 执行登出操作 → 验证JWT清除 → 验证路由重定向
- **检查项**：JWT从localStorage/sessionStorage中移除；路由切换到/login

---

## 步骤 20：前端三栏工作区完整交互

### TC-20.1 线程列表展示聚合字段

- **类型**：组件测试（Vitest）
- **主体流程**：mock线程列表数据 → 渲染ThreadList
- **检查项**：has_summary标记（有摘要时显示）；pending_plan_count正确显示；选择线程触发onSelect回调

### TC-20.2 人类/Agent消息样式区分

- **类型**：组件测试（Vitest）
- **主体流程**：mock人类消息和Agent消息 → 渲染MessageItem
- **检查项**：participant_type="human"时普通样式；participant_type="agent"时特殊卡片样式（如不同背景色、Agent图标）

### TC-20.3 request_summary按钮

- **类型**：组件测试（Vitest）
- **主体流程**：渲染DiscussionPanel → 点击request_summary按钮
- **检查项**：按钮点击触发API调用，request_summary=true

### TC-20.4 计划卡片审批操作

- **类型**：组件测试（Vitest）
- **主体流程**：mock计划数据 → 渲染PlanCard → 点击approve/reject
- **检查项**：approve按钮触发审批API调用；reject按钮触发拒绝API调用

### TC-20.5 产出diff预览

- **类型**：组件测试（Vitest）
- **主体流程**：mock产出数据（含diff） → 渲染OutputDiff
- **检查项**：diff内容正确渲染

### TC-20.6 SSE实时更新面板

- **类型**：组件测试（Vitest）
- **主体流程**：mock SSE事件 → 组件监听 → 状态更新
- **检查项**：message_created事件 → 中栏消息列表新增；plan_proposed事件 → 右栏计划卡片新增

---

## 步骤 21：Playwright E2E自我构建9点验证

### TC-21.1 验证点1：创建项目+添加成员+创建线程

- **类型**：E2E
- **主体流程**：注册用户 → 登录 → 创建项目 → 验证创建者自动成为Owner → 添加成员 → 创建线程
- **检查项**：项目创建成功；Owner角色正确；成员添加成功；线程创建成功

### TC-21.2 验证点2：人类在讨论线程中发言

- **类型**：E2E
- **主体流程**：进入线程 → 发送消息 → 验证消息出现在讨论流
- **检查项**：消息显示在讨论面板，人类样式正确

### TC-21.3 验证点3：总结Agent产出摘要

- **类型**：E2E
- **主体流程**：发送消息request_summary=true → 等待 → 验证摘要出现在消息流
- **检查项**：Agent消息出现在讨论面板，Agent样式正确；含consensus_points/divergence_points/action_items

### TC-21.4 验证点4：分解Agent产出执行计划

- **类型**：E2E
- **主体流程**：等待摘要生成 → 验证计划出现在右栏
- **检查项**：计划卡片显示，含tasks列表

### TC-21.5 验证点5：人类审批执行计划

- **类型**：E2E
- **主体流程**：点击approve部分task → 验证计划状态变为approved
- **检查项**：审批后计划状态更新，SSE推送plan_approved事件

### TC-21.6 验证点6：执行Agent产出代码diff

- **类型**：E2E
- **主体流程**：审批通过后等待 → 验证产出出现在右栏
- **检查项**：diff预览显示在产出面板

### TC-21.7 验证点7：人类审查diff→Approve/Request Revision

- **类型**：E2E
- **主体流程**：点击approve产出 → 验证状态变更；或点击request-revision → 验证状态变更
- **检查项**：审批后状态正确；要求修改后Agent重新生成

### TC-21.8 验证点8：审批通过→Git commit

- **类型**：E2E
- **主体流程**：审批产出 → 验证git log有新commit
- **检查项**：commit内容与产出一致

### TC-21.9 验证点9：三栏实时展示+SSE推送

- **类型**：E2E
- **主体流程**：全程操作过程中验证SSE实时更新
- **检查项**：消息出现时中栏自动更新；计划出现时右栏自动更新；无需手动刷新页面

---

## 步骤 22：性能基准测试与基线数据

### TC-22.1 EventStore append吞吐

- **类型**：Benchmark
- **主体流程**：连续append N个事件 → 计算吞吐（事件/秒）
- **检查项**：记录基线数据，不设硬性阈值

### TC-22.2 EventStore查询延迟（correlation_id）

- **类型**：Benchmark
- **主体流程**：写入事件 → get_events_by_correlation → 计算延迟
- **检查项**：记录基线数据

### TC-22.3 EventStore查询延迟（project_id）

- **类型**：Benchmark
- **主体流程**：写入事件 → get_events_by_project → 计算延迟
- **检查项**：记录基线数据

### TC-22.4 InProcessEventBus调度延迟

- **类型**：Benchmark
- **主体流程**：subscribe → publish → 等待handler执行 → 计算publish到handler开始执行的延迟
- **检查项**：记录基线数据

### TC-22.5 CQRS投影更新延迟

- **类型**：Benchmark
- **主体流程**：publish事件 → 投影handler更新数据库 → 计算从publish到投影表写入完成的延迟
- **检查项**：记录基线数据

### TC-22.6 SSE推送延迟

- **类型**：Benchmark
- **主体流程**：建立SSE连接 → publish事件 → 前端收到SSE推送 → 计算从事件发布到前端收到的延迟
- **检查项**：记录基线数据