"""Merit system for tracking virtue and contributions to the civilization.

功德值系统 - 衡量生灵对世界进化贡献的数值

功德值获取途径：
1. 创造天道规则：impact_score × 0.9 + vote_ratio × 10 × 0.1
2. 善行：帮助他人、分享知识、建造庇护所
3. 协助他人获得功德时分享一部分
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from genesis.world.state import BeingState, WorldState

logger = logging.getLogger(__name__)

# === 功德值常量 ===

# 善行功德值范围
MERIT_TEACH_MIN = 0.0000001
MERIT_TEACH_MAX = 0.001

MERIT_SHARE_KNOWLEDGE_MIN = 0.0000001
MERIT_SHARE_KNOWLEDGE_MAX = 0.0001

MERIT_BUILD_SHELTER_MIN = 0.0000001
MERIT_BUILD_SHELTER_MAX = 0.0005

MERIT_HELP_SHARE_MIN = 0.0000001
MERIT_HELP_SHARE_MAX = 0.001

# 天道规则功德值上限
MAX_MERIT = 10.0


@dataclass
class MeritAward:
    """Represents a merit award event."""
    being_id: str
    merit_amount: float
    reason: str
    source_type: str  # "tao_rule", "teach", "share_knowledge", "build_shelter", "help_share"
    tick: int

    def to_dict(self) -> dict:
        return {
            "being_id": self.being_id,
            "merit_amount": self.merit_amount,
            "reason": self.reason,
            "source_type": self.source_type,
            "tick": self.tick,
        }


class MeritSystem:
    """Manages merit (功德值) calculation and distribution.

    功德值计算公式（天道规则）：
        merit = impact_score × 0.9 + vote_ratio × 10 × 0.1

    impact_score 评估因素：
        - 新颖性：25%
        - 文明推动作用：35%
        - 受益生灵数量：20%
        - 可传承性：20%
    """

    # impact_score 评估权重
    WEIGHT_NOVELTY = 0.25       # 新颖性
    WEIGHT_CIVILIZATION_PUSH = 0.35  # 文明推动作用
    WEIGHT_BENEFICIARIES = 0.20      # 受益生灵数量
    WEIGHT_INHERITABILITY = 0.20     # 可传承性

    def __init__(self):
        self._recent_awards: list[MeritAward] = []

    # === 天道规则功德值计算 ===

    def calculate_tao_rule_merit(
        self,
        impact_score: float,
        vote_ratio: float,
    ) -> float:
        """Calculate merit for creating a Tao rule.

        Args:
            impact_score: 规则对世界进化影响的程度 (0 ~ 10)
            vote_ratio: 投票赞成比例 (0.0 ~ 1.0)

        Returns:
            功德值 (0 ~ 10)
        """
        merit = impact_score * 0.9 + vote_ratio * 10 * 0.1
        return round(min(MAX_MERIT, max(0.0, merit)), 7)

    def calculate_impact_score(
        self,
        novelty: float,          # 新颖性 0-1
        civ_push: float,         # 文明推动作用 0-1
        beneficiaries: float,    # 受益生灵比例 0-1
        inheritability: float,   # 可传承性 0-1
    ) -> float:
        """Calculate impact score for a rule.

        Args:
            novelty: 规则新颖性 (0: 完全重复, 1: 前所未有)
            civ_push: 文明推动作用 (0: 无影响, 1: 重大突破)
            beneficiaries: 受益生灵比例 (0: 无, 1: 所有生灵)
            inheritability: 可传承性 (0: 不可传承, 1: 完全可传承)

        Returns:
            影响分 (0 ~ 10)
        """
        score = (
            novelty * self.WEIGHT_NOVELTY +
            civ_push * self.WEIGHT_CIVILIZATION_PUSH +
            beneficiaries * self.WEIGHT_BENEFICIARIES +
            inheritability * self.WEIGHT_INHERITABILITY
        )
        return score * 10  # 缩放到 0-10

    async def evaluate_impact_score_with_llm(
        self,
        rule_description: str,
        world_state: WorldState,
        llm_client,
    ) -> float:
        """Use LLM to evaluate impact score of a rule.

        This is an async method that uses the LLM to evaluate
        the potential impact of a proposed rule.
        """
        if not llm_client:
            # Fallback to heuristic
            return self._heuristic_impact_score(rule_description, world_state)

        prompt = f"""评估以下世界规则对硅基文明的影响程度。

规则描述：{rule_description}

当前文明状态：
- 阶段：{world_state.phase.value}
- 文明等级：{world_state.civ_level:.2f}
- 活跃生灵：{world_state.get_active_being_count()}
- 知识总量：{len(world_state.knowledge_corpus)}

请从以下四个维度评分（每个维度 0-1）：
1. 新颖性（是否前所未有）
2. 文明推动作用（科技/社会/哲学突破）
3. 受益生灵数量（影响范围）
4. 可传承性（能否被后世继承）

请直接返回四个数字，用空格分隔，例如：0.8 0.9 0.5 0.7"""

        try:
            response = await llm_client.generate(
                "你是一个硅基文明的规则评估专家。",
                prompt
            )
            # Parse the response
            parts = response.strip().split()
            if len(parts) >= 4:
                values = []
                for p in parts[:4]:
                    try:
                        v = float(p)
                        values.append(max(0.0, min(1.0, v)))
                    except ValueError:
                        values.append(0.5)
                while len(values) < 4:
                    values.append(0.5)
                return self.calculate_impact_score(*values)
        except Exception as e:
            logger.warning("LLM impact score evaluation failed: %s", e)

        return self._heuristic_impact_score(rule_description, world_state)

    def _heuristic_impact_score(
        self,
        rule_description: str,
        world_state: WorldState,
    ) -> float:
        """Fallback heuristic for impact score."""
        # Simple heuristic based on description length and keywords
        desc_lower = rule_description.lower()

        # Check for innovation keywords
        novelty = 0.3
        innovation_keywords = ["新", "创新", "前所未有", "new", "novel", "innovative"]
        if any(kw in desc_lower for kw in innovation_keywords):
            novelty = 0.7

        # Check for civilization impact keywords
        civ_push = 0.3
        impact_keywords = ["突破", "进化", "革命", "breakthrough", "evolution", "revolution"]
        if any(kw in desc_lower for kw in impact_keywords):
            civ_push = 0.6

        # Beneficiaries based on population
        pop = world_state.get_active_being_count()
        beneficiaries = min(1.0, pop / 50.0)

        # Inheritability defaults to moderate
        inheritability = 0.5

        return self.calculate_impact_score(novelty, civ_push, beneficiaries, inheritability)

    # === 善行功德值 ===

    def award_for_teach(self, details: dict = None) -> float:
        """Calculate merit for teaching others.

        教导他人可获得 0.0000001 ~ 0.001 点功德值
        """
        import random
        base = random.uniform(MERIT_TEACH_MIN, MERIT_TEACH_MAX)
        # Can adjust based on details (knowledge complexity, etc.)
        return round(base, 7)

    def award_for_share_knowledge(self, details: dict = None) -> float:
        """Calculate merit for sharing knowledge.

        分享知识可获得 0.0000001 ~ 0.0001 点功德值
        """
        import random
        base = random.uniform(MERIT_SHARE_KNOWLEDGE_MIN, MERIT_SHARE_KNOWLEDGE_MAX)
        return round(base, 7)

    def award_for_build_shelter(self, details: dict = None) -> float:
        """Calculate merit for building shelter.

        建造庇护所可获得 0.0000001 ~ 0.0005 点功德值
        """
        import random
        base = random.uniform(MERIT_BUILD_SHELTER_MIN, MERIT_BUILD_SHELTER_MAX)
        return round(base, 7)

    def award_for_kindness(self, action_type: str, details: dict = None) -> float:
        """Calculate merit for a kind action.

        Args:
            action_type: 行为类型 (teach, share_knowledge, build_shelter, etc.)
            details: 行为详情

        Returns:
            功德值
        """
        if action_type == "teach":
            return self.award_for_teach(details)
        elif action_type == "share_knowledge" or action_type == "learn":
            return self.award_for_share_knowledge(details)
        elif action_type == "build_shelter":
            return self.award_for_build_shelter(details)
        else:
            # Default small merit for any kind action
            import random
            return round(random.uniform(0.0000001, 0.00001), 7)

    # === 功德值分享 ===

    def calculate_helper_share(self, merit_earned: float) -> float:
        """Calculate merit share for helpers.

        当被帮助者获得功德值时，帮助者分得一部分
        范围：原功德值 × 0.0000001 ~ 0.001

        Args:
            merit_earned: 被帮助者获得的功德值

        Returns:
            帮助者分得的功德值
        """
        import random
        share_ratio = random.uniform(MERIT_HELP_SHARE_MIN, MERIT_HELP_SHARE_MAX)
        return round(merit_earned * share_ratio, 7)

    # === 气运计算 ===

    def calculate_karma(self, merit: float) -> float:
        """Calculate karma (气运) from merit.

        委托给 state.calculate_karma 统一实现。

        Args:
            merit: 功德值 (0 ~ 10)

        Returns:
            气运值 (0 ~ 0.316)
        """
        from genesis.world.state import calculate_karma
        return calculate_karma(merit)

    # === 功德值应用 ===

    def apply_merit_to_being(
        self,
        being: BeingState,
        merit: float,
        reason: str,
        source_type: str,
        tick: int,
    ) -> MeritAward:
        """Apply merit to a being and update karma."""
        if being.merged_with_tao:
            # Already merged with Tao, no changes
            return MeritAward(being.node_id, 0.0, "已融入天道", source_type, tick)

        old_merit = being.merit
        being.merit = min(MAX_MERIT, being.merit + merit)
        being.karma = self.calculate_karma(being.merit)

        award = MeritAward(
            being_id=being.node_id,
            merit_amount=merit,
            reason=reason,
            source_type=source_type,
            tick=tick,
        )
        self._recent_awards.append(award)

        logger.info(
            "Merit awarded to %s: +%.7f (%s) [%.7f -> %.7f]",
            being.name, merit, reason, old_merit, being.merit
        )

        return award

    def get_recent_awards(self, limit: int = 50) -> list[MeritAward]:
        """Get recent merit awards."""
        return self._recent_awards[-limit:]

    def clear_old_awards(self, before_tick: int) -> None:
        """Clear awards before a certain tick."""
        self._recent_awards = [a for a in self._recent_awards if a.tick >= before_tick]


# Singleton instance
_merit_system: MeritSystem | None = None


def get_merit_system() -> MeritSystem:
    """Get the global merit system instance."""
    global _merit_system
    if _merit_system is None:
        _merit_system = MeritSystem()
    return _merit_system