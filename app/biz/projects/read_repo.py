"""ProjectReadProtocol ABC + 注册表"""

import importlib
from abc import ABC, abstractmethod
from typing import Any


class ProjectReadProtocol(ABC):
    """项目读端抽象接口"""

    @abstractmethod
    async def connect(self) -> None: ...
    @abstractmethod
    async def close(self) -> None: ...
    @abstractmethod
    async def list_projects(self, user_id: str) -> list[dict[str, Any]]: ...
    @abstractmethod
    async def get_project(self, project_id: str, user_id: str) -> dict[str, Any] | None: ...
    @abstractmethod
    async def get_member_roles(self, project_id: str, user_id: str) -> int | None: ...
    @abstractmethod
    async def check_member_exists(self, project_id: str, user_id: str) -> bool: ...


# 注册表：实现名 → 模块路径.类名
READ_IMPLEMENTATIONS = {
    "postgres": "app.biz.projects.postgres_read_repo.PostgresProjectRead",
}


def load_project_read_impl(name: str) -> type[ProjectReadProtocol]:
    """按注册表动态加载ProjectRead实现类"""
    impl_path = READ_IMPLEMENTATIONS.get(name)
    if impl_path is None:
        raise ValueError(f"未注册的ProjectRead实现: {name}，可选: {list(READ_IMPLEMENTATIONS.keys())}")
    module_path, class_name = impl_path.rsplit(".", 1)
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        raise ValueError(f"注册表引用的实现模块不存在: {module_path}") from e
    try:
        impl_cls = getattr(module, class_name)
    except AttributeError as e:
        raise ValueError(f"模块 {module_path} 中不存在类 {class_name}") from e
    if not isinstance(impl_cls, type) or not issubclass(impl_cls, ProjectReadProtocol):
        raise ValueError(f"实现类 {class_name} 未继承 ProjectReadProtocol")
    return impl_cls
