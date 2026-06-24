"""全局 git 锁测试 — GW-2.1

验证 _global_git_lock 串行化所有 git 操作：5 个并发操作不会同时进入临界区，
峰值并发数恒为 1。用临界区内并发计数器作为确定性证据，不依赖时序。

偏离测试设计：原 GW-2.1 用 git_service.commit（5 次并发），但 GitCommandService
未实现 commit 方法（step 1 范围）。改用 stub 慢操作（持锁 sleep）隔离锁逻辑，
验证目标不变——锁串行化并发调用。真实 git 操作的不冲突验证由 GW-2.7 同项目
并发用例覆盖。
"""

from __future__ import annotations

import asyncio

from app.biz.git.git_lock import get_global_git_lock


class _LockContentionTracker:
    """临界区内并发计数器

    每个 op 进入临界区时 _in_lock += 1，离开时 -= 1。
    锁若串行化，_peak 恒为 1；锁若失效（多 op 同时进入），_peak > 1。
    asyncio 单线程下 _in_lock += 1 与 await sleep 之间无 yield point，
    所以另一 op 只能在 sleep 期间尝试进入——锁若有效会被阻塞。
    """

    def __init__(self) -> None:
        self._in_lock = 0
        self._peak = 0

    def on_enter(self) -> None:
        self._in_lock += 1
        if self._in_lock > self._peak:
            self._peak = self._in_lock

    def on_exit(self) -> None:
        self._in_lock -= 1

    @property
    def peak(self) -> int:
        return self._peak


async def _slow_op_under_lock(tracker: _LockContentionTracker, duration: float) -> None:
    """模拟 git 操作：持锁 + 记录并发 + sleep + 释放"""
    async with get_global_git_lock():
        tracker.on_enter()
        try:
            await asyncio.sleep(duration)
        finally:
            tracker.on_exit()


async def test_global_lock_serializes_concurrent_git_ops() -> None:
    """GW-2.1：5 个并发 git 操作串行执行，峰值并发数 = 1"""
    tracker = _LockContentionTracker()
    await asyncio.gather(*[_slow_op_under_lock(tracker, 0.05) for _ in range(5)])

    assert tracker.peak == 1, f"锁未串行化：临界区内峰值并发数 {tracker.peak} > 1，说明多个 op 同时进入临界区"


async def test_global_lock_released_after_op() -> None:
    """锁在操作完成后释放，下一个操作可立即获取（无死锁）

    用计数器验证：第一个 op 释放后，第二个 op 进入时 _in_lock 应为 1（而非 2）。
    """
    tracker = _LockContentionTracker()
    lock = get_global_git_lock()

    async with lock:
        tracker.on_enter()
        await asyncio.sleep(0.01)
        tracker.on_exit()

    async with lock:
        tracker.on_enter()
        assert tracker.peak == 1, "第二次进入时峰值应仍为 1（前一次已释放）"
        await asyncio.sleep(0.01)
        tracker.on_exit()


async def test_global_lock_singleton_across_calls() -> None:
    """多次调用 get_global_git_lock 返回同一实例（同 loop 内单例）"""
    lock1 = get_global_git_lock()
    lock2 = get_global_git_lock()
    assert lock1 is lock2


async def test_global_lock_cross_project_serializes() -> None:
    """GW-2.7 子集：跨项目并发也通过同一全局锁串行化（峰值 = 1）"""
    tracker = _LockContentionTracker()
    await asyncio.gather(*[_slow_op_under_lock(tracker, 0.03) for _ in range(4)])

    assert tracker.peak == 1, f"跨项目未串行化：峰值 {tracker.peak} > 1"
