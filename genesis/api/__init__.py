"""WebSocket API for Genesis - 零侵入核心代码

提供实时事件推送和远程控制接口。
"""

from .server import start_api_server, stop_api_server, broadcast_event
from .bridge import install_bridge, uninstall_bridge

__all__ = [
    "start_api_server",
    "stop_api_server",
    "broadcast_event",
    "install_bridge",
    "uninstall_bridge",
]