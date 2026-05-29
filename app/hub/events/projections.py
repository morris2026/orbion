"""EventProjectionsProtocol定义与注册表"""

import importlib
from abc import ABC, abstractmethod
from typing import Any

from app.hub.events.bus import EventBus


class EventProjectionsProtocol(ABC):
    """CQRS读端投影抽象接口

    构造函数接受 EventBus 实例（用于订阅事件），配置参数从 get_settings() 自行获取。
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus

    @abstractmethod
    async def connect(self) -> None: ...
    @abstractmethod
    async def close(self) -> None: ...
    @abstractmethod
    async def get_thread_messages(self, thread_id: str) -> list[dict[str, Any]]: ...
    @abstractmethod
    async def get_execution_plans(
        self, project_id: str, thread_id: str | None = None, status: str | None = None
    ) -> list[dict[str, Any]]: ...
    @abstractmethod
    async def get_task_outputs(self, project_id: str, plan_id: str | None = None) -> list[dict[str, Any]]: ...
    @abstractmethod
    async def get_project_members(self, project_id: str) -> list[dict[str, Any]]: ...


# 注册表：实现名 → 模块路径.类名
PROJECTIONS_IMPLEMENTATIONS = {
    "postgres": "app.hub.events.postgres_projections.PostgresEventProjections",
}


def load_projections_impl(name: str) -> type[EventProjectionsProtocol]:
    """按注册表动态加载EventProjections实现类

    Args:
        name: 注册表中的实现名，如 "postgres"

    Returns:
        实现类（未实例化），保证为 EventProjectionsProtocol 的子类

    Raises:
        ValueError: 实现名未在注册表中注册，或加载的类未继承 EventProjectionsProtocol
    """
    impl_path = PROJECTIONS_IMPLEMENTATIONS.get(name)
    if impl_path is None:
        raise ValueError(f"未注册的EventProjections实现: {name}，可选: {list(PROJECTIONS_IMPLEMENTATIONS.keys())}")
    module_path, class_name = impl_path.rsplit(".", 1)
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        raise ValueError(f"注册表引用的实现模块不存在: {module_path}") from e
    try:
        impl_cls = getattr(module, class_name)
    except AttributeError as e:
        raise ValueError(f"模块 {module_path} 中不存在类 {class_name}") from e
    if not isinstance(impl_cls, type) or not issubclass(impl_cls, EventProjectionsProtocol):
        raise ValueError(f"实现类 {class_name} 未继承 EventProjectionsProtocol")
    return impl_cls
