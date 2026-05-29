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

EventBus 之所以不拆，是因为业务代码通过 EventBus 发布/订阅事件时不应感知路由是进程内还是跨进程——这是 EventBus 内部的实现细节，通过组合进程内路由（通用能力）+ 跨进程通信（可插拔外部能力）来演进，而不是多个实现类并存。

## 文件结构

| 文件 | 职责 |
|------|------|
| `bus.py`（不变） | EventBus Protocol + InProcessEventBus + `_safe_run` + `wait_for_pending` |
| `store.py`（精简） | EventStoreProtocol 定义 + `STORE_IMPLEMENTATIONS` 注册表 + `load_store_impl()` 动态加载函数 |
| `postgres_store.py`（新文件） | PostgresEventStore 实现 + `_row_to_event` helper |
| `projections.py`（精简） | EventProjectionsProtocol 定义 + `PROJECTIONS_IMPLEMENTATIONS` 注册表 + `load_projections_impl()` 动态加载函数 |
| `postgres_projections.py`（新文件） | PostgresEventProjections 实现 + `_row_to_dict` helper |
| `types.py`（不变） | Event/EventType/Payload 模型 |

## 注册表与动态加载

每个接口文件包含：

1. Protocol 定义（`@runtime_checkable`）
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

## 配置文件

JSON 配置文件 `orbion.json`（项目根目录）：

```json
{
  "event_store": "postgres",
  "event_projections": "postgres"
}
```

最简配置——只写实现名。连接参数（postgres_url 等）由 Settings 从环境变量读取，不在此配置中重复。

## 应用启动流程

```python
import json
from app.hub.events.store import EventStoreProtocol, load_store_impl
from app.hub.events.projections import EventProjectionsProtocol, load_projections_impl

config = json.load(open("orbion.json"))

# 动态加载实现类
store_class = load_store_impl(config["event_store"])
projections_class = load_projections_impl(config["event_projections"])

# 构造实例
store = store_class(settings.postgres_url)
projections = projections_class(bus, settings.postgres_url)

# 启动时验证Protocol契约
assert isinstance(store, EventStoreProtocol)
assert isinstance(projections, EventProjectionsProtocol)
```

## Phase 2 扩展流程

新增 Redis EventStore：
1. 新建 `redis_store.py`，实现 `RedisEventStore`（满足 EventStoreProtocol）
2. 在 `store.py` 注册表加一行：`"redis": "app.hub.events.redis_store.RedisEventStore"`
3. 用户改 `orbion.json`：`"event_store": "redis"`
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

**test_event_store.py / test_projections.py**（集成） — import 改为直接引用实现类：
- `from app.hub.events.postgres_store import PostgresEventStore`
- `from app.hub.events.postgres_projections import PostgresEventProjections`

## 方案选择记录

讨论过程中考虑了以下方案，最终选择注册表模式：

| 方案 | 优势 | 劣势 | 决策 |
|------|------|------|------|
| 命名规则推导 | 新增实现不改注册表 | mypy 无法验证；snake_case→PascalCase 推导有歧义 | 不选——注册表映射更显式清晰 |
| 注册表模式 | 映射关系一目了然；无命名约束；配置驱动 | 新增实现改注册表一行 | **选定**——改注册表是自然的开发阶段工作 |
| 模块自注册 | 新增实现不改注册表 | 需额外机制确保模块被导入 | 不选——引入复杂度不值得 |
| setuptools entry_points | 业界标准 | 需包安装；内部项目过重 | 不选——Orbion 实现都在同一包内 |
| Pydantic Discriminated Union | 类型安全 | 新增实现改 Union 定义代码 | 不选——部分违反不改代码原则 |