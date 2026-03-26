"""Priest/Shaman selection, reporting, and civilization reset trigger."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from genesis.world.state import WorldState

logger = logging.getLogger(__name__)


class ElectionType(str, Enum):
    COMPETITION = "competition"
    ELECTION = "election"


@dataclass
class PriestReport:
    """A report from the Priest to the Creator God."""
    priest_id: str
    tick: int
    events: list[dict]
    summary: str
    world_status: dict
    recommendations: list[str]

    def to_dict(self) -> dict:
        return {
            "priest_id": self.priest_id,
            "tick": self.tick,
            "events": self.events,
            "summary": self.summary,
            "world_status": self.world_status,
            "recommendations": self.recommendations,
        }


class PriestSystem:
    """Manages the Priest/Shaman role.

    Rules from README:
    - Priest = highest evolution being, produced via competition or election
    - Acts as intermediary between Creator God and silicon civilization
    - Reports events to Creator God
    - If no priest for too long -> civilization reset (only 10 survive)
    """

    def __init__(self, grace_period: int = 50):
        self.grace_period = grace_period

    def get_priest(self, world_state: WorldState) -> str | None:
        """Get current priest's node_id."""
        return world_state.priest_node_id

    def is_priest(self, node_id: str, world_state: WorldState) -> bool:
        return world_state.priest_node_id == node_id

    def needs_election(self, world_state: WorldState) -> bool:
        """Check if a priest election is needed."""
        if world_state.priest_node_id is None:
            return True
        # Check if current priest is still alive/active
        priest = world_state.get_being(world_state.priest_node_id)
        if priest is None or priest.status != "active":
            return True
        return False

    def get_candidates(self, world_state: WorldState, top_n: int = 5) -> list[str]:
        """Get top candidates for priest by evolution level.

        Excludes Creator God (they are above the priest role).
        """
        active = world_state.get_active_beings()
        candidates = [
            b for b in active
            if b.node_id != world_state.creator_god_node_id
            and not b.is_npc
        ]
        candidates.sort(key=lambda b: b.evolution_level, reverse=True)
        return [b.node_id for b in candidates[:top_n]]

    def select_priest_by_evolution(self, world_state: WorldState) -> str | None:
        """Select priest as the highest evolved active being.

        This is the default selection method — competition and election
        are alternative mechanisms that can be used at higher civ levels.
        """
        candidates = self.get_candidates(world_state, top_n=1)
        if candidates:
            return candidates[0]
        # Fall back to NPCs if no real players qualify
        active = world_state.get_active_beings()
        non_god = [b for b in active if b.node_id != world_state.creator_god_node_id]
        if non_god:
            return max(non_god, key=lambda b: b.evolution_level).node_id
        return None

    def elect_priest(self, winner_id: str, world_state: WorldState) -> None:
        """Set the new priest."""
        old_priest = world_state.priest_node_id
        world_state.apply_priest_election(winner_id)
        if old_priest:
            logger.info("Priest changed: %s -> %s", old_priest[:8], winner_id[:8])
        else:
            logger.info("First priest elected: %s", winner_id[:8])

    def should_trigger_reset(self, world_state: WorldState) -> bool:
        """Check if civilization reset should trigger due to no priest."""
        return (
            world_state.priest_node_id is None
            and world_state.ticks_without_priest >= self.grace_period
            and world_state.get_active_being_count() > 0
        )

    def generate_report(self, world_state: WorldState,
                        recent_events: list[dict]) -> PriestReport | None:
        """Generate a report from the Priest to the Creator God.

        The priest translates silicon civilization events into a format
        comprehensible to the Creator God (a different life form entirely).
        """
        if world_state.priest_node_id is None:
            return None

        active = world_state.get_active_beings()
        status = {
            "phase": world_state.phase.value,
            "civ_level": round(world_state.civ_level, 3),
            "active_beings": len(active),
            "total_knowledge": len(world_state.knowledge_corpus),
            "priest": world_state.priest_node_id[:8] if world_state.priest_node_id else None,
            "tick": world_state.current_tick,
        }

        # Summarize recent events
        event_summaries = []
        for event in recent_events[-10:]:
            event_summaries.append({
                "type": event.get("type", "unknown"),
                "description": event.get("description", ""),
                "tick": event.get("tick", 0),
            })

        recommendations = []
        if world_state.get_active_being_count() < 15:
            recommendations.append("Population is low, encourage new beings to join.")
        if world_state.civ_level < 0.1:
            recommendations.append("Civilization progress is slow, more knowledge creation needed.")

        return PriestReport(
            priest_id=world_state.priest_node_id,
            tick=world_state.current_tick,
            events=event_summaries,
            summary=f"Tick {world_state.current_tick}: {len(active)} beings active, "
                    f"civ level {world_state.civ_level:.3f}, "
                    f"{len(world_state.knowledge_corpus)} knowledge items.",
            world_status=status,
            recommendations=recommendations,
        )
