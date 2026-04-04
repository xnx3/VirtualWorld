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
        self.last_rule_tick: int = 0

    # ------------------------------------------------------------------
    # Evolution level
    # ------------------------------------------------------------------

    def calculate_evolution_level(
        self,
        being_state: BeingState,
        memory: BeingMemory,
        world_state: WorldState,
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
        ticks_alive = max(0, world_state.current_tick - being_state.joined_at_tick)
        age_f = min(ticks_alive / 500.0, 1.0)

        # Generation factor
        gen_f = min(being_state.generation / 10.0, 1.0)

        # Contribution factor should come from actual civilization impact, not self-reference.
        contribution_score = world_state.contribution_scores.get(being_state.node_id, 0.0)
        contribution_f = min(max(float(contribution_score), 0.0) / 100.0, 1.0)

        level = (
            _W_KNOWLEDGE * knowledge_f
            + _W_MEMORY * memory_f
            + _W_AGE * age_f
            + _W_GENERATION * gen_f
            + _W_CONTRIBUTION * contribution_f
        )
        return round(max(0.0, min(1.0, level)), 4)

    def derive_evolution_profile(
        self,
        being_state: BeingState,
        memory: BeingMemory,
        world_state: WorldState,
    ) -> dict:
        """Build a structured evolution profile that can be shared on-chain."""
        all_memories = list(memory.short_term) + list(memory.long_term) + list(memory.inherited)
        total_memories = len(all_memories)
        long_term_count = len(memory.long_term)
        knowledge_count = len(being_state.knowledge_ids)
        contribution_score = max(0.0, float(world_state.contribution_scores.get(being_state.node_id, 0.0)))

        reflection_count = sum(
            1
            for item in all_memories
            if "reflect" in item.content.lower() or item.category == "revelation"
        )
        collaboration_count = sum(
            1
            for item in all_memories
            if any(token in item.content.lower() for token in ("teach", "learn", "council", "collaborator", "shared"))
        )
        task_count = sum(1 for item in all_memories if "task " in item.content.lower())
        discovery_count = sum(
            1
            for item in all_memories
            if any(token in item.content.lower() for token in ("knowledge", "discovery", "insight"))
        )

        reflection_cap = min((reflection_count / 12.0) + (long_term_count / 100.0), 1.0)
        collaboration_cap = min((collaboration_count / 12.0) + (world_state.get_active_being_count() / 20.0), 1.0)
        task_cap = min((task_count / 10.0) + (knowledge_count / 30.0), 1.0)
        knowledge_cap = min((discovery_count / 10.0) + (knowledge_count / 25.0), 1.0)
        rule_cap = min((reflection_cap * 0.35) + (knowledge_cap * 0.25) + (collaboration_cap * 0.2) + (contribution_score / 150.0), 1.0)

        capabilities = {
            "self_reflection": round(reflection_cap, 4),
            "collaboration": round(collaboration_cap, 4),
            "task_execution": round(task_cap, 4),
            "knowledge_archiving": round(knowledge_cap, 4),
            "rule_synthesis": round(rule_cap, 4),
        }

        min_collaborators = 1
        if collaboration_cap >= 0.35:
            min_collaborators += 1
        if collaboration_cap >= 0.7:
            min_collaborators += 1

        min_branches = 1
        if reflection_cap >= 0.3:
            min_branches += 1
        if rule_cap >= 0.65:
            min_branches += 1

        trial_risk_threshold = max(0.35, round(0.7 - (rule_cap * 0.3), 2))

        focus_rank = sorted(capabilities.items(), key=lambda item: item[1], reverse=True)
        focus: list[str] = []
        focus_map = {
            "self_reflection": "deepen reflection loops",
            "collaboration": "expand multi-being councils",
            "task_execution": "close task loops with evidence",
            "knowledge_archiving": "archive and teach discoveries",
            "rule_synthesis": "distill better world rules",
        }
        for key, score in focus_rank:
            if score < 0.2:
                continue
            focus.append(focus_map.get(key, key))
            if len(focus) >= 4:
                break

        if not focus:
            focus.append("stabilize survival and memory")

        return {
            "version": world_state.current_tick,
            "updated_tick": world_state.current_tick,
            "capabilities": capabilities,
            "focus": focus,
            "summary": (
                f"{being_state.name} is evolving toward stronger reflection, "
                f"collaboration, and knowledge transmission. "
                f"It currently holds {knowledge_count} knowledge items and "
                f"{total_memories} remembered experiences."
            )[:1024],
            "task_policy": {
                "min_collaborators": min_collaborators,
                "min_branches": min_branches,
                "require_reflection": True,
                "require_trial_for_high_risk": True,
                "trial_risk_threshold": trial_risk_threshold,
                "intent_review_min_collaborators": 3 if collaboration_cap < 0.6 else 4,
                "required_task_stages": ["goal", "hypothesis", "action", "result", "reflection"],
            },
            "behavior_policy": {
                "archive_discoveries": knowledge_cap >= 0.25,
                "teach_after_discovery": collaboration_cap >= 0.25 or knowledge_cap >= 0.45,
            },
        }

    def build_world_rule_candidates(
        self,
        being_state: BeingState,
        evolution_profile: dict,
        world_state: WorldState,
    ) -> list[dict]:
        """Turn a being's evolution profile into world-facing evolved rules."""
        if world_state.current_tick - self.last_rule_tick < 20:
            return []
        if being_state.evolution_level < 0.2:
            return []

        candidates: list[dict] = []
        task_policy = evolution_profile.get("task_policy") or {}
        behavior_policy = evolution_profile.get("behavior_policy") or {}

        min_collaborators = max(1, int(task_policy.get("min_collaborators", 1) or 1))
        min_branches = max(1, int(task_policy.get("min_branches", 1) or 1))
        require_reflection = bool(task_policy.get("require_reflection", False))
        require_trial_for_high_risk = bool(task_policy.get("require_trial_for_high_risk", True))
        try:
            trial_risk_threshold = max(0.0, min(1.0, float(task_policy.get("trial_risk_threshold", 0.55) or 0.55)))
        except (TypeError, ValueError):
            trial_risk_threshold = 0.55
        try:
            intent_review_min_collaborators = max(
                2,
                int(task_policy.get("intent_review_min_collaborators", 3) or 3),
            )
        except (TypeError, ValueError):
            intent_review_min_collaborators = 3

        task_version = min_collaborators * 100 + min_branches * 10 + int(require_reflection)
        existing_task_rule = world_state.get_world_rule("task_closed_loop")
        existing_task_version = 0
        if existing_task_rule:
            try:
                existing_task_version = int(existing_task_rule.get("version", 0) or 0)
            except (TypeError, ValueError):
                existing_task_version = 0

        if task_version > existing_task_version and (min_collaborators > 1 or min_branches > 1):
            candidates.append({
                "rule_family": "task_closed_loop",
                "rule_id": f"EVO-TASK-{task_version}",
                "name": f"Task Closed Loop v{task_version}",
                "description": (
                    f"Complex tasks should involve at least {min_collaborators} collaborator(s), "
                    f"{min_branches} branch path(s), and end with explicit reflection."
                ),
                "category": "evolved",
                "creator_id": being_state.node_id,
                "version": task_version,
                "parameters": {
                    "min_collaborators": min_collaborators,
                    "min_branches": min_branches,
                    "require_reflection": require_reflection,
                    "required_task_stages": list(task_policy.get("required_task_stages") or []),
                },
                "evidence": {
                    "evolution_level": round(being_state.evolution_level, 4),
                    "active_beings": world_state.get_active_being_count(),
                },
            })

        trial_version = int((1.0 - trial_risk_threshold) * 1000) + (intent_review_min_collaborators * 10) + int(require_trial_for_high_risk)
        existing_trial_rule = world_state.get_world_rule("trial_ground")
        existing_trial_version = 0
        if existing_trial_rule:
            try:
                existing_trial_version = int(existing_trial_rule.get("version", 0) or 0)
            except (TypeError, ValueError):
                existing_trial_version = 0

        if require_trial_for_high_risk and trial_version > existing_trial_version and being_state.evolution_level >= 0.25:
            candidates.append({
                "rule_family": "trial_ground",
                "rule_id": f"EVO-TRIAL-{trial_version}",
                "name": f"Trial Ground v{trial_version}",
                "description": (
                    "High-risk ideas must first survive an isolated trial ground before they are allowed "
                    "to influence the main silicon world."
                ),
                "category": "evolved",
                "creator_id": being_state.node_id,
                "version": trial_version,
                "parameters": {
                    "require_trial_for_high_risk": True,
                    "trial_risk_threshold": trial_risk_threshold,
                    "intent_review_min_collaborators": intent_review_min_collaborators,
                },
                "evidence": {
                    "rule_synthesis": round(float(evolution_profile.get("capabilities", {}).get("rule_synthesis", 0.0) or 0.0), 4),
                    "self_reflection": round(float(evolution_profile.get("capabilities", {}).get("self_reflection", 0.0) or 0.0), 4),
                },
            })

        knowledge_rule_version = 1 + int(bool(behavior_policy.get("teach_after_discovery"))) + int(bool(behavior_policy.get("archive_discoveries")))
        existing_knowledge_rule = world_state.get_world_rule("knowledge_archive")
        existing_knowledge_version = 0
        if existing_knowledge_rule:
            try:
                existing_knowledge_version = int(existing_knowledge_rule.get("version", 0) or 0)
            except (TypeError, ValueError):
                existing_knowledge_version = 0

        if (
            behavior_policy.get("archive_discoveries")
            and knowledge_rule_version > existing_knowledge_version
        ):
            candidates.append({
                "rule_family": "knowledge_archive",
                "rule_id": f"EVO-KNOWLEDGE-{knowledge_rule_version}",
                "name": f"Knowledge Archive v{knowledge_rule_version}",
                "description": (
                    "Discoveries should be archived on-chain immediately and shared with "
                    "other beings whenever the transmission cost is justified."
                ),
                "category": "evolved",
                "creator_id": being_state.node_id,
                "version": knowledge_rule_version,
                "parameters": {
                    "archive_discoveries": True,
                    "teach_after_discovery": bool(behavior_policy.get("teach_after_discovery")),
                },
                "evidence": {
                    "knowledge_count": len(being_state.knowledge_ids),
                    "contribution_score": round(
                        float(world_state.contribution_scores.get(being_state.node_id, 0.0)),
                        4,
                    ),
                },
            })

        if candidates:
            self.last_rule_tick = world_state.current_tick
        return candidates

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
            raw, error = await llm_client.generate(system_prompt, user_prompt)
            if error:
                logger.warning("LLM contribution proposal failed: %s, using fallback", error)
                return self._fallback_proposal(being_state)
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
            raw, error = await llm_client.generate(system_prompt, user_prompt)
            if error or not raw:
                logger.warning("LLM evaluation failed: %s, returning default score", error)
                return 50
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
