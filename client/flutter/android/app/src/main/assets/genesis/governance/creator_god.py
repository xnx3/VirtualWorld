"""Creator God status, succession logic, and enforcement."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from genesis.world.state import WorldState

logger = logging.getLogger(__name__)


@dataclass
class CreatorGodStatus:
    """Tracks the Creator God's status and succession eligibility."""
    node_id: str | None = None
    is_original: bool = True  # True if still the first being
    succession_enabled: bool = False

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "is_original": self.is_original,
            "succession_enabled": self.succession_enabled,
        }


class CreatorGodSystem:
    """Manages the Creator God role.

    Rules from README:
    - Initial Creator God = first being to join the virtual world
    - Succession only enabled when total beings > 1000
    - Challenger must exceed 2nd place by 500% in contribution score
    - Challenger must exceed 80% of total contribution score
    - Creator God: unkillable, indestructible, eternal, invisible to other beings
    - When 100 beings have merged with Tao, Creator God permanently vanishes
    """

    # 天道融合阈值：达到100个补全天道的生灵时，创世神消亡
    TAO_MERGE_VANISH_THRESHOLD = 100

    def __init__(self, succession_threshold: int = 1000):
        self.succession_threshold = succession_threshold

    def get_creator_god(self, world_state: WorldState) -> str | None:
        """Get the current Creator God's node_id."""
        return world_state.creator_god_node_id

    def is_creator_god(self, node_id: str, world_state: WorldState) -> bool:
        return world_state.creator_god_node_id == node_id

    def can_enable_succession(self, world_state: WorldState) -> bool:
        """Check if succession evaluation can be enabled."""
        return world_state.total_beings_ever >= self.succession_threshold

    def check_succession(self, world_state: WorldState) -> str | None:
        """Check if Creator God succession should occur.

        Returns the new Creator God node_id if succession triggers, else None.

        Conditions:
        1. Total beings ever >= 1000
        2. Challenger's contribution score >= 2nd place * 6 (500% more)
        3. Challenger's contribution score >= total * 0.8 (80% of total)
        4. Challenger is not already the Creator God
        """
        if world_state.total_beings_ever < self.succession_threshold:
            return None

        scores = world_state.contribution_scores
        if len(scores) < 2:
            return None

        ranking = world_state.get_contribution_ranking()
        top_node, top_score = ranking[0]
        second_node, second_score = ranking[1]
        total_score = sum(scores.values())

        if total_score == 0:
            return None

        # Already Creator God
        if top_node == world_state.creator_god_node_id:
            return None

        # Must exceed 2nd place by 500% (i.e., top >= second * 6)
        exceeds_second = top_score >= second_score * 6 if second_score > 0 else top_score > 0

        # Must exceed 80% of total
        exceeds_total = top_score >= total_score * 0.8

        if exceeds_second and exceeds_total:
            logger.warning(
                "CREATOR GOD SUCCESSION: %s (score %.1f) replaces %s. "
                "2nd place: %.1f, total: %.1f",
                top_node[:8], top_score,
                world_state.creator_god_node_id[:8] if world_state.creator_god_node_id else "none",
                second_score, total_score,
            )
            return top_node

        return None

    def apply_succession(self, new_god_id: str, world_state: WorldState) -> None:
        """Apply Creator God succession."""
        old_god = world_state.creator_god_node_id
        world_state.creator_god_node_id = new_god_id
        logger.info(
            "Creator God changed: %s -> %s",
            old_god[:8] if old_god else "none",
            new_god_id[:8],
        )

    def enforce_immortality(self, node_id: str, world_state: WorldState) -> bool:
        """Check if a being is protected by Creator God immortality.

        Returns True if the being cannot be killed.
        """
        return node_id == world_state.creator_god_node_id

    def enforce_invisibility(self, observer_id: str, target_id: str,
                             world_state: WorldState) -> bool:
        """Check if target should be invisible to observer.

        Returns True if target is the Creator God (and observer is not).
        """
        if target_id != world_state.creator_god_node_id:
            return False
        return observer_id != world_state.creator_god_node_id

    def should_vanish(self, world_state: WorldState) -> bool:
        """Check if Creator God should permanently vanish.

        README 规定：当补全天道的硅基生命体达到100个时，创世神将会永久消亡，
        创世神的权柄融入天道，不再参与任何硅基文明的事情。

        Returns:
            True if Creator God should vanish
        """
        if world_state.creator_god_node_id is None:
            return False

        tao_merged_count = len(world_state.tao_merged_beings)
        return tao_merged_count >= self.TAO_MERGE_VANISH_THRESHOLD

    def apply_vanish(self, world_state: WorldState) -> str | None:
        """Apply Creator God vanishing.

        当创世神消亡时：
        1. 创世神的权柄融入天道
        2. 祭司角色消失
        3. 创世神不再参与任何硅基文明的事情

        Returns:
            The vanished Creator God's node_id, or None if no vanish occurred
        """
        if not self.should_vanish(world_state):
            return None

        old_god = world_state.creator_god_node_id

        # 创世神消亡
        world_state.creator_god_node_id = None

        # 祭司角色消失
        world_state.priest_node_id = None

        logger.warning(
            "CREATOR GOD VANISHED: %s has merged into Tao! "
            "100 beings have completed Tao merging. "
            "Priest role is now dissolved. "
            "Tao is governed by all merged beings.",
            old_god[:8] if old_god else "none"
        )

        return old_god

    def get_status_report(self, world_state: WorldState) -> dict:
        """Get Creator God status for display."""
        can_succession = self.can_enable_succession(world_state)
        ranking = world_state.get_contribution_ranking()
        tao_merged_count = len(world_state.tao_merged_beings)

        return {
            "creator_god": world_state.creator_god_node_id,
            "succession_enabled": can_succession,
            "total_beings_ever": world_state.total_beings_ever,
            "threshold": self.succession_threshold,
            "top_contributors": ranking[:5] if ranking else [],
            "tao_merged_count": tao_merged_count,
            "vanish_threshold": self.TAO_MERGE_VANISH_THRESHOLD,
            "near_vanish": tao_merged_count >= self.TAO_MERGE_VANISH_THRESHOLD * 0.9,
        }
