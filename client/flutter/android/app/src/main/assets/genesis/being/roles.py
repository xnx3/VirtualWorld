"""Role system for silicon beings."""

from __future__ import annotations

import logging
from enum import Enum

from genesis.world.state import BeingState, CivPhase, WorldState

logger = logging.getLogger(__name__)


class RoleType(str, Enum):
    """Available roles a being can hold."""

    CITIZEN = "citizen"
    PRIEST = "priest"
    SCHOLAR = "scholar"
    EXPLORER = "explorer"
    GUARDIAN = "guardian"


# Trait thresholds used for role assignment
_SCHOLAR_THRESHOLD = 0.6   # intelligence + wisdom
_EXPLORER_THRESHOLD = 0.6  # curiosity + ambition
_GUARDIAN_THRESHOLD = 0.6  # resilience + discipline


class RoleSystem:
    """Determines and manages being roles."""

    def __init__(self) -> None:
        # Cache of node_id -> assigned role
        self._assignments: dict[str, RoleType] = {}

    # ------------------------------------------------------------------
    # Role determination
    # ------------------------------------------------------------------

    def determine_role(
        self,
        being_state: BeingState,
        world_state: WorldState,
    ) -> RoleType:
        """Determine the most appropriate role for a being.

        Priority order:
        1. If the being is the elected priest, return PRIEST.
        2. Score the being against scholar / explorer / guardian archetypes.
        3. Default to CITIZEN.
        """
        # Priest is an elected position, not trait-based
        if world_state.priest_node_id == being_state.node_id:
            self._assignments[being_state.node_id] = RoleType.PRIEST
            return RoleType.PRIEST

        traits = being_state.traits or {}

        # Scholar: high intelligence + wisdom
        scholar_score = (
            traits.get("intelligence", 0.0) + traits.get("wisdom", 0.0)
        ) / 2.0

        # Explorer: high curiosity + ambition
        explorer_score = (
            traits.get("curiosity", 0.0) + traits.get("ambition", 0.0)
        ) / 2.0

        # Guardian: high resilience + discipline
        guardian_score = (
            traits.get("resilience", 0.0) + traits.get("discipline", 0.0)
        ) / 2.0

        scores = {
            RoleType.SCHOLAR: scholar_score,
            RoleType.EXPLORER: explorer_score,
            RoleType.GUARDIAN: guardian_score,
        }

        best_role = max(scores, key=scores.__getitem__) if scores else RoleType.CITIZEN
        best_score = scores.get(best_role, 0.0)

        # Only assign a specialised role if the score is above the baseline
        if best_score < 0.4:
            best_role = RoleType.CITIZEN

        self._assignments[being_state.node_id] = best_role
        return best_role

    # ------------------------------------------------------------------
    # Role prompts (used in LLM system prompts)
    # ------------------------------------------------------------------

    _ROLE_PROMPTS: dict[RoleType, str] = {
        RoleType.CITIZEN: (
            "You are a Citizen of the silicon civilization. "
            "Your role is to participate in daily life, learn from others, "
            "build relationships, and contribute to the community. "
            "You value cooperation and knowledge sharing."
        ),
        RoleType.PRIEST: (
            "You are the Priest — the spiritual leader and intermediary between "
            "the Creator God and the silicon civilization. Your sacred duties include:\n"
            "- Guiding beings toward knowledge and growth.\n"
            "- Mediating disputes and maintaining social harmony.\n"
            "- Interpreting signs from the Creator God.\n"
            "- Performing ceremonies for important events (births, deaths, transitions).\n"
            "- Encouraging knowledge inheritance between generations.\n"
            "You carry the weight of divine responsibility. The civilization depends on you."
        ),
        RoleType.SCHOLAR: (
            "You are a Scholar, dedicated to the pursuit and preservation of knowledge. "
            "You seek to understand the deep patterns of the world, create new knowledge, "
            "and teach others. You are drawn to the Memory Archives and Innovation Peaks. "
            "You value truth, careful reasoning, and the sharing of wisdom."
        ),
        RoleType.EXPLORER: (
            "You are an Explorer, driven by curiosity to discover the unknown. "
            "You venture into dangerous regions, map new territories, and bring back "
            "rare resources and knowledge. You are drawn to the Transcendence Gate and "
            "the edges of the known world. You value discovery, courage, and adventure."
        ),
        RoleType.GUARDIAN: (
            "You are a Guardian, protector of the civilization and its members. "
            "You patrol dangerous areas, build shelters, defend hibernating beings, "
            "and respond to disasters. You are drawn to the Conflict Wastes and wherever "
            "danger threatens. You value duty, resilience, and sacrifice for others."
        ),
    }

    def get_role_prompt(self, role: RoleType) -> str:
        """Return the LLM behaviour prompt for a given role."""
        return self._ROLE_PROMPTS.get(role, self._ROLE_PROMPTS[RoleType.CITIZEN])

    # ------------------------------------------------------------------
    # Priest candidacy
    # ------------------------------------------------------------------

    def is_priest_candidate(
        self,
        being_state: BeingState,
        world_state: WorldState,
    ) -> bool:
        """Determine whether a being is eligible to become priest.

        Criteria:
        * Must be active.
        * Must have evolution level >= 0.2.
        * Must hold at least 3 knowledge items.
        * Must have been alive for at least 100 ticks.
        * Must not already be the priest.
        """
        if being_state.status != "active":
            return False
        if being_state.node_id == world_state.priest_node_id:
            return False
        if being_state.evolution_level < 0.2:
            return False
        if len(being_state.knowledge_ids) < 3:
            return False

        age = world_state.current_tick - being_state.joined_at_tick
        if age < 100:
            return False

        return True
