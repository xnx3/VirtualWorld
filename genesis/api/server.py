"""WebSocket服务端 - 实时事件推送

提供：
- 事件广播：tick更新、思考、行动、精神力变化等
- 远程控制：启动/停止、任务分配、配置修改
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Set, Optional, Callable

logger = logging.getLogger("genesis.api")

# 全局状态
_clients: Set = set()
_server: Optional[Any] = None
_loop: Optional[asyncio.AbstractEventLoop] = None
_on_command: Optional[Callable] = None


async def handle_client(websocket, path: str = ""):
    """处理WebSocket客户端连接"""
    _clients.add(websocket)
    client_addr = getattr(websocket, 'remote_address', 'unknown')
    logger.info("API client connected: %s", client_addr)

    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                await _handle_command(websocket, data)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON from client: %s", message[:100])
    except Exception as e:
        logger.debug("Client error: %s", e)
    finally:
        _clients.discard(websocket)
        logger.info("API client disconnected: %s", client_addr)


async def _handle_command(websocket, data: dict):
    """处理客户端命令"""
    cmd_type = data.get("type", "")

    if cmd_type == "ping":
        await websocket.send(json.dumps({"type": "pong"}))

    elif cmd_type == "task":
        # 分配任务给生命体
        task = data.get("task", "")
        if _on_command:
            result = await _on_command("task", {"task": task})
            await websocket.send(json.dumps({
                "type": "task_response",
                "success": result.get("success", True),
                "message": result.get("message", "")
            }))

    elif cmd_type == "stop":
        # 停止节点
        if _on_command:
            await _on_command("stop", {})

    elif cmd_type == "status":
        # 获取状态
        if _on_command:
            status = await _on_command("status", {})
            await websocket.send(json.dumps({
                "type": "status",
                "data": status
            }))

    else:
        logger.debug("Unknown command type: %s", cmd_type)


def broadcast_event(event_type: str, data: dict[str, Any]) -> None:
    """广播事件给所有连接的客户端

    Args:
        event_type: 事件类型 (tick, think, action, spirit, disaster等)
        data: 事件数据
    """
    if not _clients:
        return

    message = json.dumps({
        "type": event_type,
        "data": data
    }, ensure_ascii=False)

    # 在事件循环中调度发送
    for client in list(_clients):
        try:
            if _loop and not _loop.is_closed():
                asyncio.run_coroutine_threadsafe(
                    client.send(message),
                    _loop
                )
        except Exception as e:
            logger.debug("Broadcast error: %s", e)
            _clients.discard(client)


async def start_api_server(
    host: str = "127.0.0.1",
    port: int = 19842,
    on_command: Optional[Callable] = None
) -> None:
    """启动WebSocket API服务器

    Args:
        host: 监听地址
        port: 监听端口
        on_command: 命令回调函数
    """
    global _server, _loop, _on_command

    _loop = asyncio.get_running_loop()
    _on_command = on_command

    try:
        import websockets
        _server = await websockets.serve(
            handle_client,
            host,
            port,
            ping_interval=20,
            ping_timeout=10
        )
        logger.info("API server started on ws://%s:%d", host, port)
    except ImportError:
        logger.warning("websockets not installed, API server disabled")
        logger.warning("Install with: pip install websockets")


async def stop_api_server() -> None:
    """停止WebSocket API服务器"""
    global _server

    if _server:
        _server.close()
        await _server.wait_closed()
        logger.info("API server stopped")

    _clients.clear()