"""MVP-6.1–MVP-6.4: Protocol接口抽象与注册表动态加载"""

import pytest

from app.biz.projects.read_repo import READ_IMPLEMENTATIONS, ProjectReadProtocol, load_project_read_impl
from app.biz.threads.read_repo import THREAD_READ_IMPLEMENTATIONS, ThreadReadProtocol, load_thread_read_impl
from app.hub.events.bus import InProcessEventBus
from app.hub.events.projections import (
    PROJECTIONS_IMPLEMENTATIONS,
    EventProjectionsProtocol,
    load_projections_impl,
)
from app.hub.events.store import (
    STORE_IMPLEMENTATIONS,
    EventStoreProtocol,
    load_store_impl,
)


@pytest.mark.parametrize("impl_name", list(STORE_IMPLEMENTATIONS.keys()))
def test_store_impl_satisfies_protocol(impl_name: str) -> None:
    """MVP-6.1: 注册表中所有EventStore实现继承EventStoreProtocol"""
    cls = load_store_impl(impl_name)
    store = cls()
    assert isinstance(store, EventStoreProtocol)


@pytest.mark.parametrize("impl_name", list(PROJECTIONS_IMPLEMENTATIONS.keys()))
def test_projections_impl_satisfies_protocol(impl_name: str) -> None:
    """MVP-6.2: 注册表中所有EventProjections实现继承EventProjectionsProtocol"""
    bus = InProcessEventBus()
    cls = load_projections_impl(impl_name)
    projections = cls(bus)
    assert isinstance(projections, EventProjectionsProtocol)


def test_load_unknown_store_raises_value_error() -> None:
    """MVP-6.3: load_store_impl对未注册实现名抛出ValueError"""
    with pytest.raises(ValueError, match="未注册的EventStore实现"):
        load_store_impl("unknown")


def test_load_unknown_projections_raises_value_error() -> None:
    """MVP-6.4: load_projections_impl对未注册实现名抛出ValueError"""
    with pytest.raises(ValueError, match="未注册的EventProjections实现"):
        load_projections_impl("unknown")


# -- 新增协议方法一致性测试 --


@pytest.mark.parametrize("impl_name", list(READ_IMPLEMENTATIONS.keys()))
def test_project_read_impl_satisfies_protocol(impl_name: str) -> None:
    """ProjectReadProtocol实现包含check_project_name_exists方法"""
    cls = load_project_read_impl(impl_name)
    assert issubclass(cls, ProjectReadProtocol)
    assert hasattr(cls, "check_project_name_exists")


@pytest.mark.parametrize("impl_name", list(THREAD_READ_IMPLEMENTATIONS.keys()))
def test_thread_read_impl_satisfies_protocol(impl_name: str) -> None:
    """ThreadReadProtocol实现包含check_thread_title_exists方法"""
    cls = load_thread_read_impl(impl_name)
    assert issubclass(cls, ThreadReadProtocol)
    assert hasattr(cls, "check_thread_title_exists")
