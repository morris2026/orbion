"""EventStoreProtocol定义与注册表"""

import importlib
from abc import ABC, abstractmethod

from app.hub.events.types import Event


class EventStoreProtocol(ABC):
    """事件持久化存储抽象接口"""

    @abstractmethod
    async def connect(self) -> None: ...
    @abstractmethod
    async def close(self) -> None: ...
    @abstractmethod
    async def append(self, event: Event) -> None: ...
    @abstractmethod
    async def get_events_by_correlation(self, correlation_id: str, limit: int = 100) -> list[Event]: ...
    @abstractmethod
    async def get_events_by_project(
        self, project_id: str, event_type: str | None = None, limit: int = 50
    ) -> list[Event]: ...


# 注册表：实现名 → 模块路径.类名
STORE_IMPLEMENTATIONS = {
    "postgres": "app.hub.events.postgres_store.PostgresEventStore",
}


def load_store_impl(name: str) -> type[EventStoreProtocol]:
    """按注册表动态加载EventStore实现类

    Args:
        name: 注册表中的实现名，如 "postgres"

    Returns:
        实现类（未实例化），保证为 EventStoreProtocol 的子类

    Raises:
        ValueError: 实现名未在注册表中注册，或加载的类未继承 EventStoreProtocol
    """
    impl_path = STORE_IMPLEMENTATIONS.get(name)
    if impl_path is None:
        raise ValueError(f"未注册的EventStore实现: {name}，可选: {list(STORE_IMPLEMENTATIONS.keys())}")
    module_path, class_name = impl_path.rsplit(".", 1)
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        raise ValueError(f"注册表引用的实现模块不存在: {module_path}") from e
    try:
        impl_cls = getattr(module, class_name)
    except AttributeError as e:
        raise ValueError(f"模块 {module_path} 中不存在类 {class_name}") from e
    if not isinstance(impl_cls, type) or not issubclass(impl_cls, EventStoreProtocol):
        raise ValueError(f"实现类 {class_name} 未继承 EventStoreProtocol")
    return impl_cls
