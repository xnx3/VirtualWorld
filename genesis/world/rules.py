"""World rules engine — enforces the laws of the virtual world."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from genesis.world.state import WorldState

logger = logging.getLogger(__name__)


@dataclass
class WorldRule:
    """A rule governing the virtual world."""
    rule_id: str
    name: str
    description: str
    category: str  # "fundamental", "evolved", "proposed"
    active: bool = True

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id, "name": self.name,
            "description": self.description, "category": self.category,
            "active": self.active,
        }


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
    """Enforces world rules and manages rule proposals."""

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

    def add_evolved_rule(self, rule: WorldRule) -> bool:
        """Add a rule evolved by the civilization."""
        if rule.rule_id in self.rules:
            return False
        rule.category = "evolved"
        self.rules[rule.rule_id] = rule
        logger.info("New evolved rule: %s", rule.name)
        return True

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
