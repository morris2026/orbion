"""UserRepositoryProtocol抽象接口与注册表"""

import importlib
from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel


class UserRecord(BaseModel):
    """Repository返回的完整用户数据"""

    id: str
    username: str
    display_name: str
    # login端点需要password_hash做验证，repo返回完整DB行，不按端点裁剪字段
    password_hash: str
    status: str
    is_admin: bool = False


class PendingUserRecord(BaseModel):
    """Repository返回的待审批用户数据"""

    id: str
    username: str
    display_name: str
    status: str
    created_at: datetime


class UserRepositoryProtocol(ABC):
    """用户持久化抽象接口

    实现类同时为async context manager，每次使用创建新实例：
    async with repo:
        await repo.check_username_exists(...)
        await repo.create_user(...)
    正常退出 → commit；异常退出 → rollback
    """

    @abstractmethod
    async def has_active_users(self) -> bool: ...
    @abstractmethod
    async def check_username_exists(self, username: str) -> bool: ...
    @abstractmethod
    async def create_user(
        self,
        username: str,
        password_hash: str,
        display_name: str,
        user_status: str,
        is_admin: bool,
    ) -> UserRecord: ...
    @abstractmethod
    async def get_user_by_username(self, username: str) -> UserRecord | None: ...
    @abstractmethod
    async def get_user_by_id(self, user_id: str) -> UserRecord | None: ...
    @abstractmethod
    async def update_user_status(self, user_id: str, new_status: str) -> None: ...
    @abstractmethod
    async def list_pending_users(self) -> list[PendingUserRecord]: ...


class UserRepositoryFactory(Protocol):
    """工厂协议：接受pool参数，返回async context manager yielding UserRepositoryProtocol

    事务生命周期是实现细节（不在UserRepositoryProtocol中定义），
    但工厂协议确保mypy能验证 async with repo_cls(pool) as repo: 模式。
    """

    def __call__(self, pool: Any, /) -> AbstractAsyncContextManager[UserRepositoryProtocol]: ...  # noqa: ANN401


REPO_IMPLEMENTATIONS = {
    "postgres": "app.hub.auth.postgres_repo.PostgresUserRepository",
}


def load_user_repo_impl(name: str) -> type[UserRepositoryProtocol]:
    """按注册表动态加载UserRepository实现类

    Args:
        name: 注册表中的实现名，如 "postgres"

    Returns:
        实现类（未实例化），保证为 UserRepositoryProtocol 的子类

    Raises:
        ValueError: 实现名未在注册表中注册，或加载的类未继承 UserRepositoryProtocol
    """
    impl_path = REPO_IMPLEMENTATIONS.get(name)
    if impl_path is None:
        raise ValueError(f"未注册的UserRepository实现: {name}，可选: {list(REPO_IMPLEMENTATIONS.keys())}")
    module_path, class_name = impl_path.rsplit(".", 1)
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        raise ValueError(f"注册表引用的实现模块不存在: {module_path}") from e
    try:
        impl_cls = getattr(module, class_name)
    except AttributeError as e:
        raise ValueError(f"模块 {module_path} 中不存在类 {class_name}") from e
    if not isinstance(impl_cls, type) or not issubclass(impl_cls, UserRepositoryProtocol):
        raise ValueError(f"实现类 {class_name} 未继承 UserRepositoryProtocol")
    return impl_cls
