"""ProjectReadProtocol + PostgresProjectRead 单元测试"""

import pytest

from app.biz.projects.read_repo import (
    READ_IMPLEMENTATIONS,
    ProjectReadProtocol,
    load_project_read_impl,
)


def test_postgres_read_satisfies_protocol() -> None:
    """PostgresProjectRead继承ProjectReadProtocol"""
    cls = load_project_read_impl("postgres")
    assert issubclass(cls, ProjectReadProtocol)


@pytest.mark.parametrize("impl_name", list(READ_IMPLEMENTATIONS.keys()))
def test_all_read_impls_satisfies_protocol(impl_name: str) -> None:
    """注册表中所有ProjectRead实现继承ProjectReadProtocol"""
    cls = load_project_read_impl(impl_name)
    assert issubclass(cls, ProjectReadProtocol)


def test_load_unknown_read_impl_raises_value_error() -> None:
    """load_project_read_impl对未注册实现名抛出ValueError"""
    with pytest.raises(ValueError, match="未注册的ProjectRead实现"):
        load_project_read_impl("unknown")


class TestPostgresProjectReadBoundary:
    """PostgresProjectRead边界条件测试"""

    @pytest.mark.asyncio
    async def test_methods_raise_before_connect(self) -> None:
        """未connect时调用读方法抛RuntimeError"""
        cls = load_project_read_impl("postgres")
        repo = cls()

        with pytest.raises(RuntimeError, match="未连接"):
            await repo.list_projects("user-1")

        with pytest.raises(RuntimeError, match="未连接"):
            await repo.get_project("proj-1", "user-1")

        with pytest.raises(RuntimeError, match="未连接"):
            await repo.get_member_roles("proj-1", "user-1")

        with pytest.raises(RuntimeError, match="未连接"):
            await repo.check_member_exists("proj-1", "user-1")

    @pytest.mark.asyncio
    async def test_methods_raise_after_close(self) -> None:
        """close后再调用读方法抛RuntimeError"""
        cls = load_project_read_impl("postgres")
        repo = cls()
        # close on never-connected repo is safe (pool is None)
        await repo.close()
        with pytest.raises(RuntimeError, match="未连接"):
            await repo.list_projects("user-1")
