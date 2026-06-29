"""AdapterFactory — 按 (user_id, model_id) 缓存 Adapter 实例（§6.7.3）。

设计参考 §6.7.3：
- LRU 淘汰：超过 max_cached 时关闭并移除最久未用的 adapter
- api_key_hash 校验：UserModel api_key 变更后重建（旧 adapter close）
- TTL 过期：超过 ttl_seconds 后下次 get_or_create 重建
- 显式 invalidate()：UserModel DELETE 场景立即移除 + close
- 并发单实例化：asyncio.Lock 保证同 (user_id, model_id) 并发 get_or_create 只 _build 一次
- close_all()：优雅停机释放所有缓存（SDK sessions + MCP server 子进程）

UserModelProtocol 鸭子类型接口避免循环依赖（不直接 import UserModel ORM 模型）。
_build 抽象方法由步骤 7 替换为按 provider 路由的创建逻辑。

默认 max_cached=64 / ttl_seconds=3600：设计文档示例用 200/1800，本实现针对 MVP 单实例
部署 + 用户量小的场景收窄 max_cached、放宽 TTL，减少重建频率。后续压测后可调。
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.biz.agents.adapters.base import AgentRuntimeAdapter

logger = logging.getLogger(__name__)


@runtime_checkable
class UserModelProtocol(Protocol):
    """UserModel 鸭子类型接口（避免 Adapter 层反向依赖 UserModel ORM 模型）。

    AdapterFactory 用 user_id / model_id / api_key_hash 做缓存键与失效判定；
    _build 子类访问 provider / model_name / base_url / api_key_enc 构造 Adapter。
    """

    user_id: UUID
    model_id: str
    api_key_hash: str
    provider: str
    model_name: str
    base_url: str | None
    api_key_enc: bytes


class _CacheEntry:
    """缓存条目：持有 adapter + 失效判定元数据。"""

    __slots__ = ("adapter", "api_key_hash", "ttl_seconds", "last_used", "created_at")

    def __init__(
        self,
        adapter: AgentRuntimeAdapter,
        api_key_hash: str,
        ttl_seconds: int,
    ) -> None:
        self.adapter = adapter
        self.api_key_hash = api_key_hash
        self.ttl_seconds = ttl_seconds
        self.last_used = time.monotonic()
        self.created_at = self.last_used

    def touch(self) -> None:
        self.last_used = time.monotonic()

    def expired(self) -> bool:
        """ttl_seconds=0 视为立即过期；负值视为永不过期。"""
        if self.ttl_seconds < 0:
            return False
        return (time.monotonic() - self.created_at) >= self.ttl_seconds


class AdapterFactory(ABC):
    """Adapter 实例缓存工厂（§6.7.3）。

    子类实现 _build(user_model) 按 provider 路由创建具体 Adapter。
    """

    def __init__(self, max_cached: int = 64, ttl_seconds: int = 3600) -> None:
        self._cache: OrderedDict[tuple[UUID, str], _CacheEntry] = OrderedDict()
        self._max_cached = max_cached
        self._ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()

    async def get_or_create(self, user_model: UserModelProtocol) -> AgentRuntimeAdapter:
        """获取或创建 Adapter 实例。

        命中缓存时校验 api_key_hash + TTL，失效则重建（旧 adapter close）。
        超过 max_cached 时 LRU 淘汰最旧条目并 close。
        _build 抛异常时缓存中该 key 不存在（旧条目已 evict、新条目未写入），状态干净。
        """
        key = (user_model.user_id, user_model.model_id)
        async with self._lock:
            entry = self._cache.get(key)
            if entry is not None:
                if entry.api_key_hash == user_model.api_key_hash and not entry.expired():
                    entry.touch()
                    self._cache.move_to_end(key)
                    return entry.adapter
                # api_key 变更或 TTL 过期 → 重建
                await self._evict(key)

            try:
                adapter = await self._build(user_model)
            except Exception:
                logger.exception(
                    "AdapterFactory._build failed user_id=%s model_id=%s",
                    user_model.user_id,
                    user_model.model_id,
                )
                raise
            self._cache[key] = _CacheEntry(
                adapter=adapter,
                api_key_hash=user_model.api_key_hash,
                ttl_seconds=self._ttl_seconds,
            )
            await self._enforce_capacity()
            return adapter

    async def invalidate(self, user_id: UUID, model_id: str) -> None:
        """显式移除缓存条目（UserModel DELETE 场景），close 旧 adapter。"""
        key = (user_id, model_id)
        async with self._lock:
            await self._evict(key)

    async def close_all(self) -> None:
        """优雅停机：释放所有缓存的 adapter（SDK sessions + MCP 子进程）。

        单个 adapter.close() 抛异常不中断后续释放，避免资源泄漏（步骤 19 优雅停机依赖）。
        """
        async with self._lock:
            keys = list(self._cache.keys())
            for key in keys:
                try:
                    await self._evict(key)
                except Exception:
                    logger.exception("AdapterFactory.close_all evict failed key=%s", key)

    @abstractmethod
    async def _build(self, user_model: UserModelProtocol) -> AgentRuntimeAdapter:
        """子类按 provider 路由创建具体 Adapter（步骤 7 替换）。"""
        ...

    async def _evict(self, key: tuple[UUID, str]) -> None:
        """移除并关闭指定条目（调用方持锁）。"""
        entry = self._cache.pop(key, None)
        if entry is not None:
            await entry.adapter.close()

    async def _enforce_capacity(self) -> None:
        """LRU 淘汰最旧条目直到不超过 max_cached（调用方持锁）。"""
        while len(self._cache) > self._max_cached:
            _key, entry = self._cache.popitem(last=False)
            await entry.adapter.close()
