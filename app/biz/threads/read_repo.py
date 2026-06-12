"""ThreadReadProtocol ABC + 注册表"""

import importlib
from abc import ABC, abstractmethod
from typing import Any


class ThreadReadProtocol(ABC):
    """线程读端抽象接口"""

    @abstractmethod
    async def connect(self) -> None: ...
    @abstractmethod
    async def close(self) -> None: ...
    @abstractmethod
    async def insert_thread(self, thread_id: str, project_id: str, title: str, type: str, created_by: str) -> None: ...
    @abstractmethod
    async def list_threads(self, project_id: str) -> list[dict[str, Any]]: ...
    @abstractmethod
    async def get_messages(
        self, thread_id: str, before: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]: ...
    @abstractmethod
    async def check_thread_in_project(self, thread_id: str, project_id: str) -> bool: ...
    @abstractmethod
    async def check_member_exists(self, project_id: str, user_id: str, member_type: str | None = None) -> bool: ...
    @abstractmethod
    async def check_thread_title_exists(self, project_id: str, title: str) -> bool: ...
    @abstractmethod
    async def get_thread_project_id(self, thread_id: str) -> str | None: ...
    @abstractmethod
    async def delete_thread(self, thread_id: str) -> bool: ...
    @abstractmethod
    async def get_default_thread_id(self, project_id: str) -> str | None: ...


# 注册表：实现名 → 模块路径.类名
THREAD_READ_IMPLEMENTATIONS = {
    "postgres": "app.biz.threads.postgres_read_repo.PostgresThreadRead",
}


def load_thread_read_impl(name: str) -> type[ThreadReadProtocol]:
    """按注册表动态加载ThreadRead实现类"""
    impl_path = THREAD_READ_IMPLEMENTATIONS.get(name)
    if impl_path is None:
        raise ValueError(f"未注册的ThreadRead实现: {name}，可选: {list(THREAD_READ_IMPLEMENTATIONS.keys())}")
    module_path, class_name = impl_path.rsplit(".", 1)
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        raise ValueError(f"注册表引用的实现模块不存在: {module_path}") from e
    try:
        impl_cls = getattr(module, class_name)
    except AttributeError as e:
        raise ValueError(f"模块 {module_path} 中不存在类 {class_name}") from e
    if not isinstance(impl_cls, type) or not issubclass(impl_cls, ThreadReadProtocol):
        raise ValueError(f"实现类 {class_name} 未继承 ThreadReadProtocol")
    return impl_cls
