"""MVP-6.1–MVP-6.4: Protocol接口抽象与注册表动态加载"""

import pytest

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
