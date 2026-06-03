"""ChannelAdapter Protocol定义——Channel统一抽象接口"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ChannelAdapter(Protocol):
    """Channel插件抽象接口。

    SSEChannel和IMChannel都实现此接口。
    业务代码只依赖此接口，不依赖具体Channel实现。
    """

    async def send_event(self, project_id: str, event_type: str, payload: dict[str, Any]) -> None:
        """将Orbion事件推送到外部通道"""
        ...

    async def receive_event(self, external_event: dict[str, Any]) -> dict[str, Any]:
        """将外部通道事件翻译为Orbion事件payload"""
        ...
