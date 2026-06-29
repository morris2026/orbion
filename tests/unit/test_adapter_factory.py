"""AdapterFactory UT：AR-4.1–AR-4.5。

验证 LRU 淘汰 + close、api_key_hash 变更重建 + 旧 close、显式 invalidate 移除 + close、
TTL 过期重建、并发 5 次 get_or_create 单实例化。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid4

import pytest

from app.biz.agents.adapters.base import BaseAdapter
from app.biz.agents.adapters.factory import AdapterFactory, UserModelProtocol, _CacheEntry


@dataclass(init=False)
class FakeAdapter(BaseAdapter):
    """记录 close 调用次数的可控 Adapter。"""

    user_model: UserModelProtocol
    closed: int = 0

    def __init__(self, user_model: UserModelProtocol) -> None:
        super().__init__(model_name="fake")
        self.user_model = user_model
        self.closed = 0

    async def close(self) -> None:
        self.closed += 1


@dataclass
class FakeUserModel:
    """UserModelProtocol 鸭子类型实现。"""

    user_id: UUID
    model_id: str
    api_key_hash: str
    provider: str = "openai"
    model_name: str = "gpt-4o"
    base_url: str | None = None


class FakeAdapterFactory(AdapterFactory):
    """测试用 Factory：_build 返回 FakeAdapter，记录 build 次数。"""

    def __init__(self, max_cached: int = 3, ttl_seconds: int = 3600) -> None:
        super().__init__(max_cached=max_cached, ttl_seconds=ttl_seconds)
        self.build_count = 0

    async def _build(self, user_model: UserModelProtocol) -> BaseAdapter:
        self.build_count += 1
        return FakeAdapter(user_model=user_model)


def _user(model_id: str, api_key_hash: str = "h1", user_id: UUID | None = None) -> FakeUserModel:
    return FakeUserModel(
        user_id=user_id or uuid4(),
        model_id=model_id,
        api_key_hash=api_key_hash,
    )


async def test_lru_eviction_closes_oldest() -> None:
    # AR-4.1：max_cached=3，第 4 次创建淘汰 model1 并 close
    factory = FakeAdapterFactory(max_cached=3)
    u = uuid4()
    adapters: list[FakeAdapter] = [
        cast(FakeAdapter, await factory.get_or_create(_user("m1", user_id=u))),
        cast(FakeAdapter, await factory.get_or_create(_user("m2", user_id=u))),
        cast(FakeAdapter, await factory.get_or_create(_user("m3", user_id=u))),
    ]
    await factory.get_or_create(_user("m4", user_id=u))

    assert len(factory._cache) == 3
    assert (u, "m1") not in factory._cache
    assert (u, "m2") in factory._cache
    assert (u, "m3") in factory._cache
    assert (u, "m4") in factory._cache
    assert adapters[0].closed == 1
    assert all(a.closed == 0 for a in adapters[1:])


async def test_api_key_hash_change_rebuilds_and_closes_old() -> None:
    # AR-4.2：api_key_hash 变更 → 返回新实例，旧 close 被调用
    factory = FakeAdapterFactory()
    um1 = _user("m1", api_key_hash="h1")
    old = cast(FakeAdapter, await factory.get_or_create(um1))

    um2 = _user("m1", api_key_hash="h2", user_id=um1.user_id)
    new = cast(FakeAdapter, await factory.get_or_create(um2))

    assert new is not old
    assert old.closed == 1
    assert factory.build_count == 2


async def test_invalidate_removes_and_closes() -> None:
    # AR-4.3：invalidate 立即移除 + close，后续 get_or_create 创建新实例
    factory = FakeAdapterFactory()
    um = _user("m1")
    old = cast(FakeAdapter, await factory.get_or_create(um))

    await factory.invalidate(um.user_id, um.model_id)

    assert (um.user_id, um.model_id) not in factory._cache
    assert old.closed == 1

    new = cast(FakeAdapter, await factory.get_or_create(um))
    assert new is not old
    assert factory.build_count == 2


async def test_ttl_expiry_rebuilds() -> None:
    # AR-4.4：ttl_seconds=0 → 立即过期，第二次返回新实例
    factory = FakeAdapterFactory(ttl_seconds=0)
    um = _user("m1")
    old = cast(FakeAdapter, await factory.get_or_create(um))

    await asyncio.sleep(0.01)

    new = cast(FakeAdapter, await factory.get_or_create(um))
    assert new is not old
    entry = factory._cache[(um.user_id, um.model_id)]
    assert entry.expired() is True


async def test_concurrent_get_or_create_single_instantiation() -> None:
    # AR-4.5：5 次并发 get_or_create 同 user+model → 返回相同实例，_build 仅调用一次
    factory = FakeAdapterFactory()
    um = _user("m1")

    results = await asyncio.gather(*[factory.get_or_create(um) for _ in range(5)])

    assert all(r is results[0] for r in results)
    assert factory.build_count == 1


async def test_close_all_releases_every_adapter() -> None:
    # 边界：close_all 释放所有缓存
    factory = FakeAdapterFactory()
    u = uuid4()
    a1 = cast(FakeAdapter, await factory.get_or_create(_user("m1", user_id=u)))
    a2 = cast(FakeAdapter, await factory.get_or_create(_user("m2", user_id=u)))

    await factory.close_all()

    assert len(factory._cache) == 0
    assert a1.closed == 1
    assert a2.closed == 1


class _BuildFailOnceFactory(FakeAdapterFactory):
    """_build 第一次抛异常，第二次起正常返回。"""

    def __init__(self, max_cached: int = 3, ttl_seconds: int = 3600) -> None:
        super().__init__(max_cached=max_cached, ttl_seconds=ttl_seconds)
        self._should_fail = True

    async def _build(self, user_model: UserModelProtocol) -> BaseAdapter:
        self.build_count += 1
        if self._should_fail:
            self._should_fail = False
            raise RuntimeError("build boom")
        return FakeAdapter(user_model=user_model)


async def test_build_failure_leaves_cache_clean_and_retry_succeeds() -> None:
    # _build 抛异常时缓存中该 key 不存在；重试成功后正常返回且 build_count==2
    factory = _BuildFailOnceFactory()
    um = _user("m1")

    with pytest.raises(RuntimeError, match="build boom"):
        await factory.get_or_create(um)

    assert (um.user_id, um.model_id) not in factory._cache
    assert factory.build_count == 1

    adapter = cast(FakeAdapter, await factory.get_or_create(um))
    assert isinstance(adapter, FakeAdapter)
    assert (um.user_id, um.model_id) in factory._cache
    assert factory.build_count == 2


async def test_close_all_continues_on_adapter_close_exception() -> None:
    # close_all 中某 adapter.close() 抛异常不中断后续释放
    factory = FakeAdapterFactory()
    u = uuid4()

    class _BoomAdapter(FakeAdapter):
        async def close(self) -> None:
            raise RuntimeError("close boom")

    # 直接塞入缓存绕过 _build
    factory._cache[(u, "m1")] = _CacheEntry(
        adapter=_BoomAdapter(_user("m1", user_id=u)),
        api_key_hash="h1",
        ttl_seconds=3600,
    )
    a2 = _BoomAdapter(_user("m2", user_id=u))
    factory._cache[(u, "m2")] = _CacheEntry(
        adapter=a2,
        api_key_hash="h1",
        ttl_seconds=3600,
    )

    await factory.close_all()

    assert len(factory._cache) == 0
