"""UserRepositoryProtocol抽象接口与Provider注册表"""

import importlib
from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager
from datetime import datetime

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

    仅定义CRUD方法，事务生命周期由UserRepositoryProvider.scoped()管理。
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


class UserRepositoryProvider(ABC):
    """基础设施接口：连接池生命周期 + 每请求事务作用域工厂

    与EventStoreProtocol同一self-managed pool模式：
    - connect(): 创建连接池
    - close(): 关闭连接池
    - scoped(): 返回async context manager，yielding UserRepositoryProtocol

    使用模式：
        provider = PostgresUserRepositoryProvider()
        await provider.connect()
        async with provider.scoped() as repo:
            await repo.check_username_exists(...)
            await repo.create_user(...)
        await provider.close()
    """

    @abstractmethod
    async def connect(self) -> None: ...
    @abstractmethod
    async def close(self) -> None: ...
    @abstractmethod
    def scoped(self) -> AbstractAsyncContextManager[UserRepositoryProtocol]: ...


REPO_PROVIDER_IMPLEMENTATIONS = {
    "postgres": "app.hub.auth.postgres_repo.PostgresUserRepositoryProvider",
}


def load_user_repo_provider(name: str) -> type[UserRepositoryProvider]:
    """按注册表动态加载UserRepositoryProvider实现类

    Args:
        name: 注册表中的实现名，如 "postgres"

    Returns:
        Provider实现类（未实例化），保证为 UserRepositoryProvider 的子类

    Raises:
        ValueError: 实现名未在注册表中注册，或加载的类未继承 UserRepositoryProvider
    """
    impl_path = REPO_PROVIDER_IMPLEMENTATIONS.get(name)
    if impl_path is None:
        raise ValueError(
            f"未注册的UserRepositoryProvider实现: {name}，可选: {list(REPO_PROVIDER_IMPLEMENTATIONS.keys())}"
        )
    module_path, class_name = impl_path.rsplit(".", 1)
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        raise ValueError(f"注册表引用的实现模块不存在: {module_path}") from e
    try:
        impl_cls = getattr(module, class_name)
    except AttributeError as e:
        raise ValueError(f"模块 {module_path} 中不存在类 {class_name}") from e
    if not isinstance(impl_cls, type) or not issubclass(impl_cls, UserRepositoryProvider):
        raise ValueError(f"实现类 {class_name} 未继承 UserRepositoryProvider")
    return impl_cls
