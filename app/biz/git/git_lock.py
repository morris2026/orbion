"""全局 git 锁 — 进程级 asyncio.Lock 串行化所有 git 操作

Why 全局锁：所有 worktree 共享同一 bare 仓库的 .git 目录（refs、objects、packed-refs），
git 自身会创建 .git/index.lock 文件锁，并发会损坏仓库。按 worktree 分锁复杂度高、
收益有限（git 操作毫秒级），统一全局串行化最简单可靠。

跨项目阻塞说明：本锁跨所有项目共享，单实例下高并发项目会互相阻塞。MVP 可接受
（单实例并发量低）；若出现锁竞争（orbion_git_lock_wait_seconds metric 持续 > 1s），
可改为按 repo_name 分锁。详见设计 §5.4。

多实例部署：asyncio.Lock 只在单进程内有效，多实例需改用 PostgreSQL advisory lock
等跨进程锁。MVP 不考虑多实例（§5.4.3）。
"""

from __future__ import annotations

import asyncio
import weakref

# 按 event loop 缓存的锁实例
# Why 按 loop 缓存：asyncio.Lock 绑定到首次 acquire 的 loop，跨 loop 使用会
# RuntimeError。生产单 loop 下退化为单例；测试 function-scope loop 各自独立，
# 既保证进程级语义（同一 loop 内全局串行），又兼容 pytest-asyncio 多 loop。
_locks_by_loop: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = weakref.WeakKeyDictionary()


def get_global_git_lock() -> asyncio.Lock:
    """获取当前 event loop 的全局 git 锁（同 loop 内单例）

    必须在 async 上下文中调用（需有 running loop）。
    """
    loop = asyncio.get_running_loop()
    lock = _locks_by_loop.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _locks_by_loop[loop] = lock
    return lock
