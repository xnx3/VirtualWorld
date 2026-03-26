"""API数据模型

定义WebSocket消息格式和事件结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional
from enum import Enum


class EventType(str, Enum):
    """事件类型"""
    # 连接相关
    CONNECTED = "connected"
    PONG = "pong"

    # 实时事件
    CONSOLE_OUTPUT = "console_output"
    TICK = "tick"
    THINK = "think"
    ACTION = "action"
    DISASTER = "disaster"
    PRIEST = "priest"
    BIRTH = "birth"
    DEATH = "death"
    KNOWLEDGE = "knowledge"

    # 状态事件
    STATUS = "status"
    WORLD_STATE = "world_state"

    # 响应事件
    TASK_RESPONSE = "task_response"
    ERROR = "error"


@dataclass
class APIMessage:
    """API消息基类"""
    type: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        import json
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "APIMessage":
        import json
        data = json.loads(json_str)
        return cls(type=data.get("type", ""), data=data.get("data", {}))


@dataclass
class TickEvent:
    """Tick事件数据"""
    tick: int
    being_name: str
    phase: str


@dataclass
class ThinkEvent:
    """思考事件数据"""
    being_name: str
    thought: str


@dataclass
class ActionEvent:
    """行动事件数据"""
    being_name: str
    action_type: str
    target: Optional[str]
    details: str


@dataclass
class DisasterEvent:
    """灾害事件数据"""
    name: str
    severity: float
    area: str
    killed_count: int


@dataclass
class PriestEvent:
    """祭祀事件数据"""
    event_type: str  # elected, no_priest, reset
    name: str


@dataclass
class TaskCommand:
    """任务命令"""
    type: str = "task"
    task: str = ""


@dataclass
class StatusRequest:
    """状态请求"""
    type: str = "status"


@dataclass
class StopCommand:
    """停止命令"""
    type: str = "stop"