"""根conftest — 统一的function级全局状态清理兜底fixture"""

import pytest


@pytest.fixture(autouse=True, scope="function")
def _reset_global_state() -> None:
    """每个测试前后清理全局状态残留，消除随机化执行顺序时的状态泄漏
    Why: pytest-randomly随机化时，前一个测试的全局状态残留可能污染后续测试；
    统一的function级清理确保无论执行顺序如何，每个测试都从干净环境开始
    """
    # setup前：无操作（各子目录conftest已有具体的DB/app.state清理）
    yield
    # teardown后：清理模块级全局对象可能残留的属性
    from app.main import app

    for attr in (
        "event_store",
        "event_bus",
        "event_projections",
        "project_read",
        "project_service",
        "thread_read",
        "thread_service",
        "user_repo_provider",
        "sse_channel",
        "agent_runtime",
        "agent_scheduler",
        "agent_service",
    ):
        try:
            delattr(app.state, attr)
        except (AttributeError, KeyError):
            pass