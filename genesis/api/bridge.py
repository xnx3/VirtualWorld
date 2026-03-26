"""输出桥接器 - Monkey Patch console._write

通过运行时替换实现零侵入：
- 不修改 console.py 源文件
- 保持原有终端输出
- 额外推送到WebSocket
"""

from __future__ import annotations

import logging
from typing import Optional, Callable

logger = logging.getLogger("genesis.api")

# 保存原始函数引用
_original_write: Optional[Callable] = None
_original_functions: dict = {}
_is_installed: bool = False


def install_bridge() -> bool:
    """安装输出桥接器

    通过Monkey Patch替换console模块的输出函数，
    使所有输出同时推送到WebSocket。

    Returns:
        bool: 安装是否成功
    """
    global _original_write, _original_functions, _is_installed

    if _is_installed:
        logger.warning("Bridge already installed")
        return True

    try:
        from genesis.chronicle import console as con
        from .server import broadcast_event

        # 保存原始函数
        _original_write = con._write

        # 创建桥接函数
        def bridged_write(text: str) -> None:
            # 1. 保持原终端输出
            _original_write(text)
            # 2. 推送到WebSocket
            broadcast_event("console_output", {"text": text})

        # 替换函数
        con._write = bridged_write

        # 桥接其他关键函数以提供结构化事件
        _bridge_structured_events(con, broadcast_event)

        _is_installed = True
        logger.info("Output bridge installed successfully")
        return True

    except Exception as e:
        logger.error("Failed to install bridge: %s", e)
        return False


def _bridge_structured_events(con, broadcast_event: Callable) -> None:
    """桥接结构化事件函数

    为关键函数添加事件广播，保持原函数调用。
    """
    global _original_functions

    # 保存并桥接 tick_header
    _original_functions['tick_header'] = con.tick_header
    def bridged_tick_header(tick: int, being_name: str, phase: str,
                            merit: float = 0.0, karma: float = 0.0,
                            evolution_level: float = 0.0, generation: int = 1) -> None:
        _original_functions['tick_header'](tick, being_name, phase)
        broadcast_event("tick", {
            "tick": tick,
            "being_name": being_name,
            "phase": phase,
            "merit": merit,
            "karma": karma,
            "evolution_level": evolution_level,
            "generation": generation,
        })
    con.tick_header = bridged_tick_header

    # 保存并桥接 think
    _original_functions['think'] = con.think
    def bridged_think(being_name: str, thought: str) -> None:
        _original_functions['think'](being_name, thought)
        broadcast_event("think", {
            "being_name": being_name,
            "thought": thought
        })
    con.think = bridged_think

    # 保存并桥接 decide
    _original_functions['decide'] = con.decide
    def bridged_decide(being_name: str, action_type: str, target: str | None, details: str) -> None:
        _original_functions['decide'](being_name, action_type, target, details)
        broadcast_event("action", {
            "being_name": being_name,
            "action_type": action_type,
            "target": target,
            "details": details
        })
    con.decide = bridged_decide

    # 保存并桥接 disaster_event
    _original_functions['disaster_event'] = con.disaster_event
    def bridged_disaster_event(name: str, severity: float, area: str, killed_count: int) -> None:
        _original_functions['disaster_event'](name, severity, area, killed_count)
        broadcast_event("disaster", {
            "name": name,
            "severity": severity,
            "area": area,
            "killed_count": killed_count
        })
    con.disaster_event = bridged_disaster_event

    # 保存并桥接 priest_event
    _original_functions['priest_event'] = con.priest_event
    def bridged_priest_event(event_type: str, name: str) -> None:
        _original_functions['priest_event'](event_type, name)
        broadcast_event("priest", {
            "event_type": event_type,
            "name": name
        })
    con.priest_event = bridged_priest_event

    # 保存并桥接 tao_vote_event (天道投票事件)
    if hasattr(con, 'tao_vote_event'):
        _original_functions['tao_vote_event'] = con.tao_vote_event
        def bridged_tao_vote_event(event_type: str, vote_id: str, rule_name: str,
                                    proposer_name: str, votes_for: int = 0,
                                    votes_against: int = 0, remaining_ticks: int = 0,
                                    ratio: float = 0.0, merit: float = 0.0) -> None:
            _original_functions['tao_vote_event'](event_type, vote_id, rule_name, proposer_name,
                                                  votes_for, votes_against, remaining_ticks,
                                                  ratio, merit)
            broadcast_event("tao_vote", {
                "event_type": event_type,
                "vote_id": vote_id,
                "rule_name": rule_name,
                "proposer_name": proposer_name,
                "votes_for": votes_for,
                "votes_against": votes_against,
                "remaining_ticks": remaining_ticks,
                "ratio": ratio,
                "merit": merit
            })
        con.tao_vote_event = bridged_tao_vote_event


def uninstall_bridge() -> bool:
    """卸载输出桥接器

    恢复所有原始函数。

    Returns:
        bool: 卸载是否成功
    """
    global _original_write, _original_functions, _is_installed

    if not _is_installed:
        return True

    try:
        from genesis.chronicle import console as con

        # 恢复原始函数
        if _original_write:
            con._write = _original_write

        for name, func in _original_functions.items():
            setattr(con, name, func)

        _original_write = None
        _original_functions = {}
        _is_installed = False

        logger.info("Output bridge uninstalled")
        return True

    except Exception as e:
        logger.error("Failed to uninstall bridge: %s", e)
        return False