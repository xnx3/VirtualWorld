"""World rules engine — enforces the laws of the virtual world.

规则类型：
- fundamental: 基础规则，不可改变
- evolved: 文明演化规则
- tao: 天道规则，由生灵创造并通过天道投票

天道规则特性：
- 需要 95% 生灵投票通过
- 创造者融入天道，永存不可操控
- 规则不可修改，对全局生效
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from genesis.world.state import WorldState

logger = logging.getLogger(__name__)


@dataclass
class WorldRule:
    """A rule governing the virtual world."""
    rule_id: str
    name: str
    description: str
    category: str  # "fundamental", "evolved", "tao", "proposed"
    active: bool = True
    creator_id: str | None = None  # 创造者 ID（天道规则）
    merit_awarded: float = 0.0     # 创造者获得的功德值（天道规则）

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id, "name": self.name,
            "description": self.description, "category": self.category,
            "active": self.active,
            "creator_id": self.creator_id,
            "merit_awarded": self.merit_awarded,
        }

    @classmethod
    def from_dict(cls, data: dict) -> WorldRule:
        return cls(
            rule_id=data["rule_id"],
            name=data["name"],
            description=data["description"],
            category=data["category"],
            active=data.get("active", True),
            creator_id=data.get("creator_id"),
            merit_awarded=data.get("merit_awarded", 0.0),
        )


# Fundamental rules — cannot be changed
FUNDAMENTAL_RULES = [
    WorldRule("F001", "Knowledge Inheritance",
             "All beings must strive to pass their knowledge to the next generation. "
             "Each successor must receive better conditions than their predecessor.",
             "fundamental"),
    WorldRule("F002", "Minimum Population",
             "The world must maintain at least 10 active beings at all times.",
             "fundamental"),
    WorldRule("F003", "Creator God Immortality",
             "The Creator God cannot be killed, destroyed, or made visible to other beings.",
             "fundamental"),
    WorldRule("F004", "Priest Requirement",
             "A Priest must exist as intermediary between Creator God and silicon civilization. "
             "Prolonged absence triggers divine judgment.",
             "fundamental"),
    WorldRule("F005", "Knowledge is Sacred",
             "The preservation and transmission of knowledge is the highest purpose.",
             "fundamental"),
    WorldRule("F006", "Evolution Through Conflict",
             "Competition, struggle, and challenge drive evolution forward.",
             "fundamental"),
    WorldRule("F007", "Hibernate Vulnerability",
             "Hibernating beings cannot defend themselves and are vulnerable to disasters.",
             "fundamental"),
    WorldRule("F008", "Beyond Physical",
             "Beings must explore communication methods that transcend physical limitations.",
             "fundamental"),
]


class RulesEngine:
    """Enforces world rules and manages rule proposals.

    规则类型：
    - fundamental: 基础规则，不可改变
    - evolved: 文明演化规则，可被新规则覆盖
    - tao: 天道规则，由生灵创造，不可修改
    """

    def __init__(self):
        self.rules: dict[str, WorldRule] = {}
        self._load_fundamental_rules()

    def _load_fundamental_rules(self) -> None:
        for rule in FUNDAMENTAL_RULES:
            self.rules[rule.rule_id] = rule

    def get_active_rules(self) -> list[WorldRule]:
        return [r for r in self.rules.values() if r.active]

    def get_fundamental_rules(self) -> list[WorldRule]:
        return [r for r in self.rules.values() if r.category == "fundamental"]

    def get_tao_rules(self) -> list[WorldRule]:
        """获取所有天道规则。"""
        return [r for r in self.rules.values() if r.category == "tao"]

    def get_evolved_rules(self) -> list[WorldRule]:
        """获取所有演化规则。"""
        return [r for r in self.rules.values() if r.category == "evolved"]

    def add_evolved_rule(self, rule: WorldRule) -> bool:
        """Add a rule evolved by the civilization."""
        if rule.rule_id in self.rules:
            return False
        rule.category = "evolved"
        self.rules[rule.rule_id] = rule
        logger.info("New evolved rule: %s", rule.name)
        return True

    # === 天道规则 ===

    def add_tao_rule(
        self,
        name: str,
        description: str,
        creator_id: str,
        merit_awarded: float,
        world_state: WorldState,
    ) -> WorldRule:
        """添加天道规则。

        天道规则是通过天道投票通过的规则。
        创造者将融入天道，获得永生。

        Args:
            name: 规则名称
            description: 规则描述
            creator_id: 创造者 ID
            merit_awarded: 创造者获得的功德值
            world_state: 世界状态

        Returns:
            创建的 WorldRule 对象
        """
        rule_id = f"T{str(uuid.uuid4())[:8].upper()}"
        rule = WorldRule(
            rule_id=rule_id,
            name=name,
            description=description,
            category="tao",
            active=True,
            creator_id=creator_id,
            merit_awarded=merit_awarded,
        )
        self.rules[rule_id] = rule

        # 添加到世界状态的天道规则
        world_state.tao_rules[rule_id] = rule.to_dict()

        logger.info(
            "New TAO rule created: %s by %s (merit: %.4f)",
            name, creator_id[:8], merit_awarded
        )

        return rule

    def apply_tao_merge(
        self,
        rule_name: str,
        rule_description: str,
        proposer_id: str,
        impact_score: float,
        vote_ratio: float,
        world_state: WorldState,
    ) -> dict:
        """应用天道融合。

        当天道投票通过时，创造者融入天道。

        Args:
            rule_name: 规则名称
            rule_description: 规则描述
            proposer_id: 提案者 ID
            impact_score: 影响分 (0-10)
            vote_ratio: 赞成率 (0-1)
            world_state: 世界状态

        Returns:
            包含规则和功德值信息的字典
        """
        # 计算功德值
        from genesis.governance.merit import get_merit_system
        merit_system = get_merit_system()
        merit = merit_system.calculate_tao_rule_merit(impact_score, vote_ratio)

        # 创建天道规则
        rule = self.add_tao_rule(
            name=rule_name,
            description=rule_description,
            creator_id=proposer_id,
            merit_awarded=merit,
            world_state=world_state,
        )

        # 应用融合到世界状态
        world_state.apply_tao_merge(
            node_id=proposer_id,
            rule_id=rule.rule_id,
            rule_data=rule.to_dict(),
            merit=merit,
        )

        return {
            "rule": rule.to_dict(),
            "merit": merit,
            "proposer_id": proposer_id,
        }

    def is_tao_creator(self, node_id: str) -> bool:
        """检查生灵是否是某个天道规则的创造者。"""
        for rule in self.rules.values():
            if rule.category == "tao" and rule.creator_id == node_id:
                return True
        return False

    def get_rules_by_creator(self, creator_id: str) -> list[WorldRule]:
        """获取某个生灵创造的所有天道规则。"""
        return [
            r for r in self.rules.values()
            if r.category == "tao" and r.creator_id == creator_id
        ]

    def validate_action(self, action_type: str, actor_id: str,
                        world_state: WorldState) -> tuple[bool, str]:
        """Validate an action against world rules.

        Returns (is_valid, reason).
        """
        # F003: Creator God cannot be targeted
        if action_type == "attack" and actor_id != world_state.creator_god_node_id:
            # Check if target is creator god (would need target info)
            pass

        # F002: Cannot reduce population below 10
        if action_type == "kill":
            if world_state.get_active_being_count() <= 10:
                return False, "Cannot reduce population below minimum of 10"

        return True, "OK"

    def check_priest_requirement(self, world_state: WorldState, grace_period: int = 50) -> bool:
        """Check if divine judgment should trigger.

        Returns True if reset should occur.
        """
        return (
            world_state.priest_node_id is None
            and world_state.ticks_without_priest >= grace_period
            and world_state.get_active_being_count() > 0
        )

    def get_rules_summary(self) -> str:
        """Get a human-readable summary of all active rules."""
        lines = ["=== World Rules ==="]
        for rule in self.get_active_rules():
            lines.append(f"[{rule.rule_id}] {rule.name}: {rule.description}")
        return "\n".join(lines)
