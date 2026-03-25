"""Karma (气运) system for luck bonuses based on merit.

气运系统 - 基于功德值计算的概率加成

气运公式：karma = √merit × 0.1

气运效果：
- 探索发现宝物概率提升
- 灾害存活概率提升
- 知识获取量提升
- 竞争胜利概率提升
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass

from genesis.world.state import BeingState

logger = logging.getLogger(__name__)


@dataclass
class KarmaBonus:
    """Represents a karma bonus applied to an action."""
    being_id: str
    karma_value: float
    bonus_type: str  # "exploration", "disaster", "knowledge", "competition"
    original_chance: float
    modified_chance: float
    tick: int

    def to_dict(self) -> dict:
        return {
            "being_id": self.being_id,
            "karma_value": self.karma_value,
            "bonus_type": self.bonus_type,
            "original_chance": self.original_chance,
            "modified_chance": self.modified_chance,
            "tick": self.tick,
        }


class KarmaSystem:
    """Manages karma (气运) bonuses and applications.

    气运是基于功德值计算的概率加成，代表"好运"的加持。

    计算公式：karma = √merit × 0.1

    效果应用：
    - 探索：base_probability × (1 + karma)
    - 灾害：survival_rate × (1 + karma × 0.5)
    - 知识：knowledge_gain × (1 + karma)
    - 竞争：win_rate × (1 + karma × 0.3)
    """

    # 气运效果系数
    EXPLORATION_FACTOR = 1.0      # 探索加成系数
    DISASTER_FACTOR = 0.5         # 灾害存活加成系数
    KNOWLEDGE_FACTOR = 1.0        # 知识获取加成系数
    COMPETITION_FACTOR = 0.3      # 竞争加成系数

    def __init__(self):
        self._recent_bonuses: list[KarmaBonus] = []

    # === 基础计算 ===

    def get_karma(self, being: BeingState) -> float:
        """Get karma value for a being."""
        if being.merged_with_tao:
            return 0.0  # 已融入天道的生灵不再享受气运加成
        return being.karma

    def calculate_karma_from_merit(self, merit: float) -> float:
        """Calculate karma from merit value.

        委托给 state.calculate_karma 统一实现。

        公式：karma = √merit × 0.1
        """
        from genesis.world.state import calculate_karma
        return calculate_karma(merit)

    # === 探索加成 ===

    def apply_to_exploration(
        self,
        being: BeingState,
        base_probability: float,
        tick: int,
    ) -> tuple[float, KarmaBonus | None]:
        """Apply karma bonus to exploration treasure discovery.

        效果：概率 × (1 + karma)

        Args:
            being: 生灵状态
            base_probability: 基础发现概率 (0-1)
            tick: 当前 tick

        Returns:
            (修改后的概率, 加成记录)
        """
        karma = self.get_karma(being)
        if karma <= 0:
            return base_probability, None

        modified = base_probability * (1 + karma * self.EXPLORATION_FACTOR)
        modified = min(1.0, modified)  # 上限 100%

        bonus = KarmaBonus(
            being_id=being.node_id,
            karma_value=karma,
            bonus_type="exploration",
            original_chance=base_probability,
            modified_chance=modified,
            tick=tick,
        )
        self._recent_bonuses.append(bonus)

        logger.debug(
            "Karma exploration bonus for %s: %.2f%% -> %.2f%% (+%.1f%%)",
            being.name, base_probability * 100, modified * 100, karma * 100
        )

        return modified, bonus

    def roll_exploration_treasure(
        self,
        being: BeingState,
        base_probability: float,
        tick: int,
    ) -> tuple[bool, KarmaBonus | None]:
        """Roll for treasure discovery with karma bonus.

        Returns:
            (是否发现宝物, 加成记录)
        """
        modified_prob, bonus = self.apply_to_exploration(being, base_probability, tick)
        success = random.random() < modified_prob
        return success, bonus

    # === 灾害存活加成 ===

    def apply_to_disaster_survival(
        self,
        being: BeingState,
        base_survival_rate: float,
        disaster_severity: float,
        tick: int,
    ) -> tuple[float, KarmaBonus | None]:
        """Apply karma bonus to disaster survival.

        效果：存活率 × (1 + karma × 0.5)

        Args:
            being: 生灵状态
            base_survival_rate: 基础存活率 (0-1)
            disaster_severity: 灾害严重程度 (0-1)
            tick: 当前 tick

        Returns:
            (修改后的存活率, 加成记录)
        """
        karma = self.get_karma(being)
        if karma <= 0:
            return base_survival_rate, None

        # 灾害严重程度会降低气运效果
        effective_karma = karma * (1 - disaster_severity * 0.3)
        modified = base_survival_rate * (1 + effective_karma * self.DISASTER_FACTOR)
        modified = min(1.0, modified)

        bonus = KarmaBonus(
            being_id=being.node_id,
            karma_value=karma,
            bonus_type="disaster",
            original_chance=base_survival_rate,
            modified_chance=modified,
            tick=tick,
        )
        self._recent_bonuses.append(bonus)

        logger.debug(
            "Karma disaster survival bonus for %s: %.2f%% -> %.2f%%",
            being.name, base_survival_rate * 100, modified * 100
        )

        return modified, bonus

    def roll_disaster_survival(
        self,
        being: BeingState,
        base_survival_rate: float,
        disaster_severity: float,
        tick: int,
    ) -> tuple[bool, KarmaBonus | None]:
        """Roll for disaster survival with karma bonus.

        Returns:
            (是否存活, 加成记录)
        """
        modified_rate, bonus = self.apply_to_disaster_survival(
            being, base_survival_rate, disaster_severity, tick
        )
        survived = random.random() < modified_rate
        return survived, bonus

    # === 知识获取加成 ===

    def apply_to_knowledge_gain(
        self,
        being: BeingState,
        base_gain: float,
        tick: int,
    ) -> tuple[float, KarmaBonus | None]:
        """Apply karma bonus to knowledge gain.

        效果：获取量 × (1 + karma)

        Args:
            being: 生灵状态
            base_gain: 基础知识获取量
            tick: 当前 tick

        Returns:
            (修改后的获取量, 加成记录)
        """
        karma = self.get_karma(being)
        if karma <= 0:
            return base_gain, None

        modified = base_gain * (1 + karma * self.KNOWLEDGE_FACTOR)

        bonus = KarmaBonus(
            being_id=being.node_id,
            karma_value=karma,
            bonus_type="knowledge",
            original_chance=base_gain,
            modified_chance=modified,
            tick=tick,
        )
        self._recent_bonuses.append(bonus)

        logger.debug(
            "Karma knowledge bonus for %s: %.2f -> %.2f (+%.1f%%)",
            being.name, base_gain, modified, karma * 100
        )

        return modified, bonus

    # === 竞争加成 ===

    def apply_to_competition(
        self,
        being: BeingState,
        base_win_rate: float,
        opponent_karma: float | None = None,
        tick: int = 0,
    ) -> tuple[float, KarmaBonus | None]:
        """Apply karma bonus to competition win rate.

        效果：胜率 × (1 + karma × 0.3)

        如果对手也有气运，会进行对比调整。

        Args:
            being: 生灵状态
            base_win_rate: 基础胜率 (0-1)
            opponent_karma: 对手气运值 (可选)
            tick: 当前 tick

        Returns:
            (修改后的胜率, 加成记录)
        """
        karma = self.get_karma(being)
        if karma <= 0:
            return base_win_rate, None

        # 如果对手有气运，计算对比效果
        if opponent_karma is not None and opponent_karma > 0:
            karma_diff = karma - opponent_karma
            # 只有气运更高的一方才获得加成
            if karma_diff <= 0:
                return base_win_rate, None
            effective_karma = karma_diff * 0.5  # 差值效果减半
        else:
            effective_karma = karma

        modified = base_win_rate * (1 + effective_karma * self.COMPETITION_FACTOR)
        modified = min(0.95, modified)  # 上限 95%，保留失败可能

        bonus = KarmaBonus(
            being_id=being.node_id,
            karma_value=karma,
            bonus_type="competition",
            original_chance=base_win_rate,
            modified_chance=modified,
            tick=tick,
        )
        self._recent_bonuses.append(bonus)

        logger.debug(
            "Karma competition bonus for %s: %.2f%% -> %.2f%%",
            being.name, base_win_rate * 100, modified * 100
        )

        return modified, bonus

    def roll_competition(
        self,
        being: BeingState,
        base_win_rate: float,
        opponent: BeingState | None = None,
        tick: int = 0,
    ) -> tuple[bool, KarmaBonus | None]:
        """Roll for competition result with karma bonus.

        Returns:
            (是否胜利, 加成记录)
        """
        opponent_karma = None
        if opponent:
            opponent_karma = self.get_karma(opponent)

        modified_rate, bonus = self.apply_to_competition(
            being, base_win_rate, opponent_karma, tick
        )
        won = random.random() < modified_rate
        return won, bonus

    # === 工具方法 ===

    def get_recent_bonuses(self, limit: int = 50) -> list[KarmaBonus]:
        """Get recent karma bonuses."""
        return self._recent_bonuses[-limit:]

    def clear_old_bonuses(self, before_tick: int) -> None:
        """Clear bonuses before a certain tick."""
        self._recent_bonuses = [b for b in self._recent_bonuses if b.tick >= before_tick]

    def get_karma_description(self, being: BeingState) -> str:
        """Get a human-readable description of karma effects."""
        karma = self.get_karma(being)
        if karma <= 0:
            return "无气运加成"

        effects = []
        if karma > 0.05:
            effects.append(f"探索概率 +{karma * 100:.1f}%")
        if karma > 0.1:
            effects.append(f"灾害存活 +{karma * 50:.1f}%")
        if karma > 0.15:
            effects.append(f"知识获取 +{karma * 100:.1f}%")
        if karma > 0.2:
            effects.append(f"竞争胜率 +{karma * 30:.1f}%")

        if effects:
            return " | ".join(effects)
        return f"微弱气运 (+{karma * 100:.2f}%)"


# Singleton instance
_karma_system: KarmaSystem | None = None


def get_karma_system() -> KarmaSystem:
    """Get the global karma system instance."""
    global _karma_system
    if _karma_system is None:
        _karma_system = KarmaSystem()
    return _karma_system