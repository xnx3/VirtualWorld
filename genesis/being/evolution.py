"""Evolution tracking and contribution proposals for silicon beings."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from genesis.being.memory import BeingMemory
from genesis.world.state import BeingState, CivPhase, WorldState

logger = logging.getLogger(__name__)

# Weights for the evolution-level formula
_W_KNOWLEDGE = 0.30
_W_MEMORY = 0.20
_W_AGE = 0.15
_W_GENERATION = 0.15
_W_CONTRIBUTION = 0.20

# Minimum evolution level before a being may propose contributions
_PROPOSAL_EVOLUTION_THRESHOLD = 0.15
# Minimum ticks alive before proposing
_PROPOSAL_AGE_THRESHOLD = 50


class EvolutionTracker:
    """Calculates evolution level and manages contribution proposals."""

    def __init__(self) -> None:
        self.last_proposal_tick: int = 0

    # ------------------------------------------------------------------
    # Evolution level
    # ------------------------------------------------------------------

    def calculate_evolution_level(
        self,
        being_state: BeingState,
        memory: BeingMemory,
    ) -> float:
        """Compute a composite evolution level in [0.0, 1.0].

        Factors:
        * Number of knowledge items held.
        * Size and quality of long-term memory.
        * Age (ticks alive).
        * Generation number (later generations inherit more).
        * Accumulated contribution score.
        """
        # Knowledge factor
        k_count = len(being_state.knowledge_ids)
        knowledge_f = min(k_count / 20.0, 1.0)

        # Memory factor (long-term + inherited)
        mem_count = len(memory.long_term) + len(memory.inherited)
        avg_importance = 0.0
        if mem_count > 0:
            avg_importance = sum(
                m.importance for m in memory.long_term
            ) / max(len(memory.long_term), 1)
        memory_f = min(mem_count / 100.0, 1.0) * max(avg_importance, 0.3)

        # Age factor
        age_f = min(being_state.joined_at_tick / 500.0, 1.0) if being_state.joined_at_tick > 0 else 0.0
        # Actually we want ticks alive, but we only have joined_at_tick.
        # Use generation as a proxy-complement for age.

        # Generation factor
        gen_f = min(being_state.generation / 10.0, 1.0)

        # Contribution factor (stored in evolution_level seed from world state)
        contribution_f = min(being_state.evolution_level * 1.5, 1.0)

        level = (
            _W_KNOWLEDGE * knowledge_f
            + _W_MEMORY * memory_f
            + _W_AGE * age_f
            + _W_GENERATION * gen_f
            + _W_CONTRIBUTION * contribution_f
        )
        return round(max(0.0, min(1.0, level)), 4)

    # ------------------------------------------------------------------
    # Contribution proposals
    # ------------------------------------------------------------------

    def should_propose_contribution(
        self,
        being_state: BeingState,
        memory: BeingMemory,
        world_state: WorldState,
    ) -> bool:
        """Decide whether it is appropriate to propose a contribution now."""
        # Must be above the evolution threshold
        if being_state.evolution_level < _PROPOSAL_EVOLUTION_THRESHOLD:
            return False

        # Must have been alive for some time
        age = world_state.current_tick - being_state.joined_at_tick
        if age < _PROPOSAL_AGE_THRESHOLD:
            return False

        # Rate-limit: at least 20 ticks between proposals
        if world_state.current_tick - self.last_proposal_tick < 20:
            return False

        # Need some long-term memories to draw from
        if len(memory.long_term) < 3:
            return False

        return True

    async def formulate_contribution(
        self,
        being_state: BeingState,
        memory: BeingMemory,
        world_state: WorldState,
        llm_client: object,  # vw.being.llm_client.LLMClient
    ) -> dict:
        """Use the LLM to formulate a contribution proposal.

        Returns a dict with keys: description, category.
        """
        from genesis.being.llm_client import LLMClient  # deferred import

        assert isinstance(llm_client, LLMClient)

        phase = world_state.phase.value
        memory_context = memory.get_context(max_entries=10)
        knowledge_count = len(being_state.knowledge_ids)

        system_prompt = (
            f"You are {being_state.name}, a silicon being in the {phase} phase. "
            f"You have {knowledge_count} pieces of knowledge and the following memories:\n"
            f"{memory_context}\n\n"
            "Propose a contribution to the civilization. "
            "Respond with a JSON object containing exactly two keys:\n"
            '  "description": a 1-2 sentence description of your contribution,\n'
            '  "category": one of "science", "philosophy", "social", "infrastructure", "art".'
        )

        user_prompt = (
            f"Current civilization level: {world_state.civ_level:.2f}. "
            f"Active beings: {world_state.get_active_being_count()}. "
            f"Phase: {phase}. "
            "What would you like to contribute?"
        )

        try:
            raw = await llm_client.generate(system_prompt, user_prompt)
            # Try to parse as JSON
            proposal = self._parse_proposal(raw)
        except Exception:
            logger.warning("LLM contribution proposal failed, using fallback")
            proposal = self._fallback_proposal(being_state)

        self.last_proposal_tick = world_state.current_tick
        return proposal

    async def evaluate_contribution(
        self,
        proposal: dict,
        being_state: BeingState,
        llm_client: object,
    ) -> int:
        """Evaluate a contribution proposal, returning a score 0-100.

        This is used by other beings to vote on proposals.
        """
        from genesis.being.llm_client import LLMClient

        assert isinstance(llm_client, LLMClient)

        system_prompt = (
            f"You are {being_state.name}, a silicon being evaluating a contribution proposal.\n"
            "Score the following proposal from 0 to 100 based on:\n"
            "- Originality and creativity (30%)\n"
            "- Benefit to civilization (40%)\n"
            "- Feasibility (30%)\n"
            "Respond with ONLY a single integer between 0 and 100."
        )

        desc = proposal.get("description", "No description")
        cat = proposal.get("category", "other")
        user_prompt = f"Proposal ({cat}): {desc}"

        try:
            raw = await llm_client.generate(system_prompt, user_prompt)
            score = int("".join(c for c in raw.strip() if c.isdigit())[:3])
            return max(0, min(100, score))
        except Exception:
            logger.warning("LLM evaluation failed, returning default score")
            return 50

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_proposal(raw: str) -> dict:
        """Best-effort JSON extraction from LLM response."""
        # Try direct parse
        raw = raw.strip()
        # Find JSON object in the response
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(raw[start:end])
                return {
                    "description": str(data.get("description", "A new contribution")),
                    "category": str(data.get("category", "other")),
                }
            except json.JSONDecodeError:
                pass

        # Fallback: use raw text as description
        return {"description": raw[:200], "category": "other"}

    @staticmethod
    def _fallback_proposal(being_state: BeingState) -> dict:
        """Rule-based fallback when the LLM is unavailable."""
        categories = ["science", "philosophy", "social", "infrastructure", "art"]
        # Deterministic pick based on node_id hash
        idx = sum(ord(c) for c in being_state.node_id) % len(categories)
        cat = categories[idx]
        return {
            "description": (
                f"{being_state.name} proposes advancing the civilization's {cat} "
                f"through systematic study and shared practice."
            ),
            "category": cat,
        }
