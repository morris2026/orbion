# EventStore/EventProjections Protocol 接口抽象与文件拆分设计

## 背景

步骤4和5将 EventStore 和 EventProjections 的 Protocol 定义与 PostgreSQL 实现放在同一文件中（store.py、projections.py），导致：
1. 实现与接口耦合——替换 PostgreSQL 实现时需要修改包含 Protocol 定义的原文件
2. 实现选择硬编码——通过模块级别名（`EventStore = PostgresEventStore`）绑定实现，不同用户/部署实例无法通过配置选择不同实现

## 目标

1. Protocol 定义与实现分离——接口文件只定义抽象契约和注册表，实现文件只写具体持久化逻辑
2. 配置驱动实现选择——不同用户/部署实例通过 JSON 配置文件选择实现，不改代码
3. 注册表模式——新增实现时在注册表加一行映射，这是自然的开发阶段工作

## 架构区分

三种模块的拆分模式不同，反映了架构差异：

| 模块 | 拆分模式 | 理由 |
|------|---------|------|
| EventBus | 不拆（Protocol + 实现同文件） | 单一演进实现——进程内路由是通用能力，跨进程通信通过内部可插拔接口实现 |
| EventStore | Protocol + 注册表（接口文件） / 实现（独立文件） | 多实现并存——不同持久化方案可替换 |
| EventProjections | Protocol + 注册表（接口文件） / 实现（独立文件） | 多实现并存——不同持久化方案可替换 |
| UserRepository | ABC + 注册表（接口文件） / 实现（独立文件） | 多实现并存——UserRepositoryProvider 需要 enforced lifecycle methods（connect/close/scoped），ABC 保证子类必须实现 |

EventBus 之所以不拆，是因为业务代码通过 EventBus 发布/订阅事件时不应感知路由是进程内还是跨进程——这是 EventBus 内部的实现细节，通过组合进程内路由（通用能力）+ 跨进程通信（可插拔外部能力）来演进，而不是多个实现类并存。

UserRepositoryProvider 使用 ABC 而非 `@runtime_checkable Protocol`，因为 Provider 是基础设施契约：connect/close/scoped 是必须实现的硬性方法，子类未实现时 ABC 立即报错。而 EventStoreProtocol 使用 Protocol 是因为业务语义层面，任何有 append/get_events 方法的对象都可用（鸭子类型足够）。

## 文件结构

| 文件 | 职责 |
|------|------|
| `bus.py`（不变） | EventBus Protocol + InProcessEventBus + `_safe_run` + `wait_for_pending` |
| `store.py`（精简） | EventStoreProtocol 定义 + `STORE_IMPLEMENTATIONS` 注册表 + `load_store_impl()` 动态加载函数 |
| `postgres_store.py`（新文件） | PostgresEventStore 实现 + `_row_to_event` helper |
| `projections.py`（精简） | EventProjectionsProtocol 定义 + `PROJECTIONS_IMPLEMENTATIONS` 注册表 + `load_projections_impl()` 动态加载函数 |
| `postgres_projections.py`（新文件） | PostgresEventProjections 实现 + `_row_to_dict` helper |
| `auth/repository.py`（新文件） | UserRepositoryProtocol(ABC) + UserRepositoryProvider(ABC) + `REPO_PROVIDER_IMPLEMENTATIONS` 注册表 + `load_user_repo_provider()` 动态加载函数 |
| `auth/postgres_repo.py`（新文件） | PostgresUserRepository + PostgresUserRepositoryProvider 实现 |
| `types.py`（不变） | Event/EventType/Payload 模型 |

## 注册表与动态加载

每个接口文件包含：

1. Protocol/ABC 定义（EventStore/EventProjections 用 `@runtime_checkable Protocol`，UserRepositoryProvider 用 `ABC`）
2. 注册表 dict——实现名 → `模块路径.类名`
3. `load_*_impl()` 函数——查注册表、`importlib.import_module` + `getattr` 动态加载

**store.py 注册表：**

```python
STORE_IMPLEMENTATIONS = {
    "postgres": "app.hub.events.postgres_store.PostgresEventStore",
}

def load_store_impl(name: str) -> type:
    impl_path = STORE_IMPLEMENTATIONS.get(name)
    if impl_path is None:
        raise ValueError(f"未注册的EventStore实现: {name}，可选: {list(STORE_IMPLEMENTATIONS.keys())}")
    module_path, class_name = impl_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)
```

**projections.py 注册表同理：**

```python
PROJECTIONS_IMPLEMENTATIONS = {
    "postgres": "app.hub.events.postgres_projections.PostgresEventProjections",
}

def load_projections_impl(name: str) -> type:
    ...
```

**repository.py 注册表：**

```python
REPO_PROVIDER_IMPLEMENTATIONS = {
    "postgres": "app.hub.auth.postgres_repo.PostgresUserRepositoryProvider",
}

def load_user_repo_provider(name: str) -> type[UserRepositoryProvider]:
    impl_path = REPO_PROVIDER_IMPLEMENTATIONS.get(name)
    if impl_path is None:
        raise ValueError(f"未注册的UserRepositoryProvider实现: {name}，可选: {list(REPO_PROVIDER_IMPLEMENTATIONS.keys())}")
    module_path, class_name = impl_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)
```

UserRepositoryProvider 注册表映射到 Provider 类而非 Repository 类，因为路由通过 Provider.scoped() 获取 per-request 事务实例，不直接构造 Repository。

## 配置文件

JSON 配置文件 `orbion.json`（项目根目录）：

```json
{
  "event_store": "postgres",
  "event_projections": "postgres",
  "user_repo": "postgres"
}
```

最简配置——只写实现名。连接参数（PostgresSettings.url 等）由 Settings 从环境变量和嵌套 postgres 子配置读取，不在此配置中重复。密钥字段（jwt_secret、anthropic_api_key、postgres.password）只从 ORBION_* 环境变量读取，不允许出现在配置文件中。

## 应用启动流程

```python
from app.config import get_settings
from app.hub.events.store import EventStoreProtocol, load_store_impl
from app.hub.events.projections import EventProjectionsProtocol, load_projections_impl
from app.hub.auth.repository import UserRepositoryProvider, load_user_repo_provider

settings = get_settings()

# 动态加载实现类（实现名从配置读取，不硬编码）
store_class = load_store_impl(settings.event_store)
projections_class = load_projections_impl(settings.event_projections)
provider_class = load_user_repo_provider(settings.user_repo)

# 构造实例（self-managed pool模式，内部创建连接池）
store = store_class()
await store.connect()
projections = projections_class(bus)
await projections.connect()
provider = provider_class()
await provider.connect()

# 启动时验证Protocol契约
assert isinstance(store, EventStoreProtocol)
assert isinstance(projections, EventProjectionsProtocol)
assert isinstance(provider, UserRepositoryProvider)

# 路由使用Provider.scoped()获取per-request事务实例
async with provider.scoped() as repo:  # repo是UserRepositoryProtocol
    await repo.check_username_exists("admin")
```

## Phase 2 扩展流程

新增 Redis EventStore：
1. 新建 `redis_store.py`，实现 `RedisEventStore`（满足 EventStoreProtocol）
2. 在 `store.py` 注册表加一行：`"redis": "app.hub.events.redis_store.RedisEventStore"`
3. 用户改 `orbion.json`：`"event_store": "redis"`
4. 不改任何其他已有代码

新增 Redis UserRepositoryProvider：
1. 新建 `redis_repo.py`，实现 `RedisUserRepositoryProvider`（继承 UserRepositoryProvider ABC）
2. 在 `repository.py` 注册表加一行：`"redis": "app.hub.auth.redis_repo.RedisUserRepositoryProvider"`
3. 用户改 `orbion.json`：`"user_repo": "redis"`
4. 不改任何其他已有代码

## 测试调整

**test_protocol_conformance.py** — import 来源调整：
- `EventStoreProtocol` 从 `store` 导入
- `PostgresEventStore` 从 `postgres_store` 导入
- `EventProjectionsProtocol` 从 `projections` 导入
- `PostgresEventProjections` 从 `postgres_projections` 导入
- 新增：`load_store_impl("postgres")` 返回 PostgresEventStore 的测试
- 新增：`load_store_impl("unknown")` 抛 ValueError 的测试
- 同理 projections 的动态加载测试

**test_protocol_conformance.py** — import 来源调整：
- `EventStoreProtocol` 从 `store` 导入
- `PostgresEventStore` 从 `postgres_store` 导入
- `EventProjectionsProtocol` 从 `projections` 导入
- `PostgresEventProjections` 从 `postgres_projections` 导入
- 新增：`load_store_impl("postgres")` 返回 PostgresEventStore 的测试
- 新增：`load_store_impl("unknown")` 抛 ValueError 的测试
- 同理 projections 的动态加载测试

**test_event_store.py / test_projections.py**（集成） — import 改为直接引用实现类：
- `from app.hub.events.postgres_store import PostgresEventStore`
- `from app.hub.events.postgres_projections import PostgresEventProjections`

**test_user_repository.py** — Provider/Protocol conformance 与生命周期测试：
- `UserRepositoryProvider` ABC conformance：`issubclass(PostgresUserRepositoryProvider, UserRepositoryProvider)`
- `UserRepositoryProtocol` ABC conformance：`issubclass(PostgresUserRepository, UserRepositoryProtocol)`
- `load_user_repo_provider("postgres")` 返回 PostgresUserRepositoryProvider 类
- `load_user_repo_provider("unknown")` 抛 ValueError
- Provider lifecycle：scoped() 在未 connect 时抛 RuntimeError，connect/close 正常工作
- Repository lifecycle：_ensure_open 在未进入/已退出 context manager 时抛 RuntimeError

## 方案选择记录

讨论过程中考虑了以下方案，最终选择注册表模式：

| 方案 | 优势 | 劣势 | 决策 |
|------|------|------|------|
| 命名规则推导 | 新增实现不改注册表 | mypy 无法验证；snake_case→PascalCase 推导有歧义 | 不选——注册表映射更显式清晰 |
| 注册表模式 | 映射关系一目了然；无命名约束；配置驱动 | 新增实现改注册表一行 | **选定**——改注册表是自然的开发阶段工作 |
| 模块自注册 | 新增实现不改注册表 | 需额外机制确保模块被导入 | 不选——引入复杂度不值得 |
| setuptools entry_points | 业界标准 | 需包安装；内部项目过重 | 不选——Orbion 实现都在同一包内 |
| Pydantic Discriminated Union | 类型安全 | 新增实现改 Union 定义代码 | 不选——部分违反不改代码原则 |

| 场景 | 选择 | 原因 |
|------|------|------|
| EventStoreProtocol | `@runtime_checkable Protocol` | 业务语义层面，鸭子类型足够——任何有 append/get_events 方法的对象都可用 |
| EventProjectionsProtocol | `@runtime_checkable Protocol` | 同上，查询语义层面鸭子类型足够 |
| UserRepositoryProvider | `ABC`（`@abstractmethod`） | 基础设施契约，connect/close/scoped 是必须实现的硬性方法——ABC 保证子类未实现时立即报错，Protocol 不提供强制保证 |