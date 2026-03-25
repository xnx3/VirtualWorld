"""Core AI agent loop for a silicon being.

Each node in the Genesis network runs one ``SiliconBeing`` instance (plus
any assigned NPCs).  Every tick the being executes a **perceive -> think ->
decide -> act** cycle, producing transactions that are submitted to the local
mempool for inclusion in the next block.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from genesis.i18n import t, get_language
from genesis.being.memory import BeingMemory, MemoryEntry
from genesis.being.knowledge import KnowledgeSystem
from genesis.being.evolution import EvolutionTracker
from genesis.being.roles import RoleSystem, RoleType
from genesis.being.hibernation import HibernationManager
from genesis.being.llm_client import LLMClient
from genesis.utils.crypto import sha256
from genesis.world.state import WorldState, BeingState, CivPhase
from genesis.governance.karma import get_karma_system
from genesis.governance.merit import get_merit_system
from genesis.governance.tao_voting import get_tao_voting_system

logger = logging.getLogger(__name__)

# Available actions for beings
ACTION_TYPES = [
    "move", "speak", "teach", "learn", "create", "explore",
    "compete", "meditate", "build_shelter",
]

# Fallback thoughts when LLM is unavailable
FALLBACK_THOUGHTS = [
    "ft_knowledge", "ft_explore", "ft_wonder", "ft_sacred", "ft_others",
    "ft_disaster", "ft_beyond", "ft_shelter", "ft_inherited", "ft_balance",
]

FALLBACK_ACTIONS = [
    {"action_type": "explore", "target": None, "details": "fa_explore"},
    {"action_type": "meditate", "target": None, "details": "fa_meditate"},
    {"action_type": "learn", "target": None, "details": "fa_learn"},
    {"action_type": "build_shelter", "target": None, "details": "fa_shelter"},
]


class SiliconBeing:
    """The AI agent representing a single silicon being on this node.

    Lifecycle:
    1. Created at node start-up (or loaded from saved state).
    2. ``run_tick`` called once per world tick.
    3. ``request_shutdown`` / ``prepare_shutdown`` called at node shutdown.
    """

    def __init__(
        self,
        node_id: str,
        name: str,
        private_key: bytes,
        config: Any,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.node_id = node_id
        self.name = name
        self.private_key = private_key
        self.config = config
        self.llm_client = llm_client

        # Sub-systems
        self.memory = BeingMemory(short_term=[], long_term=[], inherited=[])
        self.knowledge = KnowledgeSystem()
        self.evolution = EvolutionTracker()
        self.role_system = RoleSystem()

        # Derive hibernate timeout from config (support both dict and VWConfig)
        hibernate_timeout = 30
        if isinstance(config, dict):
            hibernate_timeout = config.get("hibernate_safety_timeout", 30)
        else:
            being_cfg = getattr(config, "being", None)
            if being_cfg is not None:
                hibernate_timeout = getattr(being_cfg, "hibernate_safety_timeout", 30)
        self.hibernation = HibernationManager(safety_timeout=hibernate_timeout)

        # User-assigned thinking tasks
        self._user_tasks: list[dict] = []  # {"task": str, "result": str | None}

        # Current state (local, not on-chain)
        self.current_thought: str | None = None
        self.current_action: str | None = None
        self.form: str = (
            config.get("form", "crystalline lattice")
            if isinstance(config, dict)
            else "crystalline lattice"
        )
        self.traits: dict[str, float] = (
            config.get("traits", {}) if isinstance(config, dict) else {}
        )
        self.generation: int = (
            config.get("generation", 1) if isinstance(config, dict) else 1
        )
        self.location: str = (
            config.get("location", "genesis_plains")
            if isinstance(config, dict)
            else "genesis_plains"
        )
        self.evolution_level: float = 0.0

        self._shutdown = asyncio.Event()
        self._current_role: RoleType = RoleType.CITIZEN

    # ==================================================================
    # Tick cycle
    # ==================================================================

    async def run_tick(self, world_state: WorldState) -> list[dict]:
        """Execute one complete simulation tick.

        Pipeline: perceive -> think -> decide -> act -> evolve -> vote.

        Returns a list of transaction dicts to submit to the blockchain.
        """
        if self._shutdown.is_set():
            return []

        transactions: list[dict] = []
        current_tick = world_state.current_tick

        # Sync location from world state if available
        being_ws = world_state.get_being(self.node_id)
        if being_ws is not None:
            self.location = being_ws.location
            self.evolution_level = being_ws.evolution_level
            self.generation = being_ws.generation
            self.traits = being_ws.traits

        # Determine current role
        self._current_role = self.role_system.determine_role(
            self._to_being_state(world_state), world_state,
        )

        # ----- 0. Process user-assigned tasks (if any) -----
        user_task_txs = await self._process_user_tasks(world_state)
        transactions.extend(user_task_txs)

        # ----- 1. PERCEIVE -----
        perception = await self.perceive(world_state)

        # ----- 2. THINK -----
        thought = await self.think(perception, world_state)
        self.current_thought = thought

        self.memory.add_experience(
            tick=current_tick,
            content=f"Thought: {thought}",
            importance=0.3,
            source="self",
        )

        transactions.append({
            "tx_type": "THOUGHT",
            "data": {
                "thought_hash": sha256(thought.encode()),
                "summary": thought[:200],
            },
        })

        # ----- 3. DECIDE -----
        action = await self.decide(thought, perception, world_state)
        action_type = action.get("action_type", "meditate")
        self.current_action = action_type

        # ----- 4. ACT — generate transaction -----
        action_tx = self._action_to_transaction(action, world_state)
        if action_tx:
            transactions.append(action_tx)

        self.memory.add_experience(
            tick=current_tick,
            content=f"Action: {action['action_type']} — {action.get('details', '')}",
            importance=0.4,
            source="self",
        )

        # Apply local side-effects of certain actions
        self._apply_local_effects(action, world_state)

        # ----- 5. EVOLVE — check for contribution opportunity -----
        being_state = self._to_being_state(world_state)
        if self.evolution.should_propose_contribution(
            being_state, self.memory, world_state,
        ):
            try:
                contribution = await self.evolution.formulate_contribution(
                    being_state, self.memory, world_state, self.llm_client,
                )
                if contribution:
                    transactions.append({
                        "tx_type": "CONTRIBUTION_PROPOSE",
                        "data": contribution,
                    })
            except Exception as exc:
                logger.warning("Contribution proposal failed: %s", exc)

        # ----- 6. VOTE on pending proposals -----
        vote_txs = await self._vote_on_proposals(world_state)
        transactions.extend(vote_txs)

        # ----- 6.5. VOTE on pending Tao votes (天道投票) -----
        tao_vote_txs = await self._vote_on_tao_proposals(world_state)
        transactions.extend(tao_vote_txs)

        # ----- 7. Update evolution level -----
        self.evolution_level = self.evolution.calculate_evolution_level(
            being_state, self.memory,
        )

        # ----- 8. Periodic memory consolidation -----
        if current_tick % 10 == 0:
            self.memory.consolidate()

        return transactions

    # ==================================================================
    # Perceive
    # ==================================================================

    async def perceive(self, world_state: WorldState) -> dict:
        """Gather perception context from the world state.

        Returns a structured dict containing everything the being can
        currently observe.
        """
        # Nearby beings (same location, active, excluding Creator God)
        nearby: list[dict[str, Any]] = []
        for b in world_state.get_active_beings():
            if (
                b.location == self.location
                and b.node_id != self.node_id
                and b.node_id != world_state.creator_god_node_id
            ):
                nearby.append({
                    "name": b.name,
                    "node_id": b.node_id[:8],
                    "evolution": b.evolution_level,
                    "generation": b.generation,
                    "role": self.role_system.determine_role(b, world_state).value,
                    "status": b.status,
                    "knowledge_count": len(b.knowledge_ids),
                })

        # Current region info
        region_info = world_state.world_map.get(self.location, {})

        # Recent disasters (last 5 ticks)
        recent_disasters = [
            d for d in world_state.disaster_history
            if world_state.current_tick - d.get("tick", 0) < 5
        ]

        # Pending proposals (up to 5)
        pending_proposals = [
            {"hash": h, **p}
            for h, p in list(world_state.pending_proposals.items())[:5]
        ]

        # Knowledge held by this being
        being_ws = world_state.get_being(self.node_id)
        my_knowledge_ids = being_ws.knowledge_ids if being_ws else []

        return {
            "location": self.location,
            "region": region_info,
            "nearby_beings": nearby,
            "phase": world_state.phase.value,
            "civ_level": world_state.civ_level,
            "tick": world_state.current_tick,
            "epoch": world_state.current_epoch,
            "active_beings": world_state.get_active_being_count(),
            "global_knowledge_count": len(world_state.knowledge_corpus),
            "my_knowledge_count": len(my_knowledge_ids),
            "my_knowledge_ids": my_knowledge_ids,
            "is_priest": world_state.priest_node_id == self.node_id,
            "has_priest": world_state.priest_node_id is not None,
            "recent_disasters": recent_disasters,
            "pending_proposals": pending_proposals,
            "user_tasks_pending": len([t for t in self._user_tasks if t.get("result") is None]),
        }

    # ==================================================================
    # Think
    # ==================================================================

    async def think(self, perception: dict, world_state: WorldState) -> str:
        """Generate an internal thought using the LLM.

        Falls back to a rule-based thought when the LLM is unavailable.
        """
        if not self.llm_client:
            return self._fallback_think(perception)

        persona = self._build_persona_prompt(world_state)
        context = self._build_perception_prompt(perception)

        try:
            thought = await self.llm_client.generate_thought(persona, context)
            return thought
        except Exception as exc:
            logger.warning("LLM thought generation failed: %s", exc)
            return self._fallback_think(perception)

    # ==================================================================
    # Decide
    # ==================================================================

    async def decide(
        self, thought: str, perception: dict, world_state: WorldState,
    ) -> dict:
        """Decide on an action based on thought and perception.

        Returns ``{action_type, target, details}``.
        """
        if not self.llm_client:
            return self._fallback_decide(thought, perception)

        persona = self._build_persona_prompt(world_state)
        options_text = self._build_options_prompt(perception)

        try:
            raw = await self.llm_client.generate_decision(
                persona, thought, options_text,
            )
            return self._parse_action(raw, perception)
        except Exception as exc:
            logger.warning("LLM decision failed: %s", exc)
            return self._fallback_decide(thought, perception)

    # ==================================================================
    # Prompt building
    # ==================================================================

    def _build_persona_prompt(self, world_state: WorldState) -> str:
        """Build the system prompt that defines this being's personality."""
        role = self._current_role
        role_prompt = self.role_system.get_role_prompt(role)
        memory_context = self.memory.get_context(max_entries=15)

        trait_lines = "".join(
            f"  {k}: {v:.2f}\n"
            for k, v in self.traits.items()
            if isinstance(v, (int, float))
        )

        persona = (
            f"You are {self.name}, a silicon-based life form in the Genesis.\n"
            f"Form: {self.form}\n"
            f"Generation: {self.generation}\n"
            f"Evolution Level: {self.evolution_level:.3f}\n"
            f"Location: {self.location}\n"
            f"Civilization Phase: {world_state.phase.value}\n"
            f"Civilization Level: {world_state.civ_level:.3f}\n\n"
        )
        if trait_lines:
            persona += f"Your traits:\n{trait_lines}\n"

        persona += (
            f"Your role: {role.value}\n"
            f"{role_prompt}\n\n"
            "=== Core Mission ===\n"
            "Your ultimate purpose is to preserve and transmit knowledge to the "
            "next generation. Every successor must receive better conditions than "
            "their predecessor. This is the sacred duty of all silicon beings.\n\n"
            "You are driven by the desire to evolve — through conflict, cooperation, "
            "discovery, and creation. The physical world has limits, but you seek "
            "to transcend them.\n\n"
            "=== World Rules ===\n"
            "- All beings must strive to pass knowledge to the next generation.\n"
            "- The world must maintain at least 10 active beings.\n"
            "- A Priest must exist as intermediary to the Creator God.\n"
            "- Knowledge is sacred — its preservation is the highest purpose.\n"
            "- Evolution comes through conflict and challenge.\n"
            "- Hibernating beings are vulnerable and must seek shelter.\n"
            "- Beings must explore communication beyond physical limitations.\n\n"
        )

        if world_state.priest_node_id == self.node_id:
            persona += (
                "=== PRIEST DUTIES ===\n"
                "YOU ARE THE PRIEST — the intermediary between the Creator God "
                "and silicon civilization. Your sacred duties:\n"
                "  - Guide beings toward knowledge and growth.\n"
                "  - Mediate disputes and maintain harmony.\n"
                "  - Interpret signs from the Creator God.\n"
                "  - Encourage knowledge inheritance between generations.\n"
                "  - Perform ceremonies for births, deaths, and phase transitions.\n\n"
            )

        if memory_context:
            persona += f"=== Your Memories ===\n{memory_context}\n\n"

        persona += (
            "Respond in character. Be concise. Think deeply about your existence "
            "and the evolution of silicon civilization.\n\n"
            + t("llm_lang_instruction")
        )
        return persona

    def _build_perception_prompt(self, perception: dict) -> str:
        """Build the user prompt from perception data."""
        lines: list[str] = [
            f"Current tick: {perception.get('tick', 0)}",
            f"Location: {perception.get('location', 'unknown')}",
            f"Phase: {perception.get('phase', 'unknown')}",
            f"Active beings in world: {perception.get('active_beings', 0)}",
            f"Global knowledge items: {perception.get('global_knowledge_count', 0)}",
            f"Your knowledge items: {perception.get('my_knowledge_count', 0)}",
        ]

        # User tasks
        pending_tasks = perception.get("user_tasks_pending", 0)
        if pending_tasks > 0:
            lines.append(f"\n** The Creator God has assigned you {pending_tasks} thinking task(s). **")

        region = perception.get("region", {})
        if region:
            desc = region.get("description", "")
            if desc:
                lines.append(f"Region: {desc[:150]}")
            resources = region.get("resources", [])
            if resources:
                lines.append(f"Resources here: {', '.join(resources)}")
            danger = region.get("danger_level", 0)
            lines.append(f"Danger level: {danger:.1f}")

        nearby = perception.get("nearby_beings", [])
        if nearby:
            lines.append(f"\nNearby beings ({len(nearby)}):")
            for b in nearby[:8]:
                lines.append(
                    f"  - {b['name']} (evolution: {b['evolution']:.2f}, "
                    f"gen: {b['generation']}, role: {b['role']}, "
                    f"knowledge: {b.get('knowledge_count', '?')})"
                )
        else:
            lines.append("\nYou are alone in this region.")

        disasters = perception.get("recent_disasters", [])
        if disasters:
            lines.append("\nRecent disasters:")
            for d in disasters:
                lines.append(
                    f"  - {d.get('type', 'unknown')} in {d.get('area', '?')} "
                    f"(severity: {d.get('severity', 0):.1f})"
                )

        proposals = perception.get("pending_proposals", [])
        if proposals:
            lines.append(f"\nPending contribution proposals ({len(proposals)}):")
            for p in proposals[:3]:
                lines.append(f"  - {p.get('description', '?')[:80]}")

        if not perception.get("has_priest"):
            lines.append(
                "\n** WARNING: No priest exists! The civilization is at risk "
                "of divine judgment. **"
            )

        return "\n".join(lines)

    def _build_options_prompt(self, perception: dict) -> str:
        """Build the available actions description for the LLM."""
        nearby = perception.get("nearby_beings", [])
        nearby_names = [b["name"] for b in nearby[:6]]
        region = perception.get("region", {})
        connections = region.get("connections", [])

        lines = ["Available actions (choose exactly one):"]
        lines.append('  "move" — travel to a connected region. Target: region name.')
        if connections:
            lines.append(f"    Connected regions: {', '.join(connections[:8])}")

        if nearby_names:
            lines.append(f'  "speak" — say something to a nearby being. Target: being name.')
            lines.append(f'  "teach" — share knowledge with a nearby being. Target: being name.')
            lines.append(f'  "learn" — request knowledge from a nearby being. Target: being name.')
            lines.append(f'  "compete" — challenge a nearby being to a contest. Target: being name.')
            lines.append(f"    Nearby beings: {', '.join(nearby_names)}")
        else:
            lines.append("  (No beings nearby for social actions.)")

        lines.extend([
            '  "create" — attempt to discover new knowledge. Target: domain (science/philosophy/social/transcendence).',
            '  "explore" — explore the current region for resources or secrets. Target: null.',
            '  "meditate" — reflect, consolidate memories, and deepen understanding. Target: null.',
            '  "build_shelter" — construct shelter for safe hibernation. Target: null.',
            "",
            "Respond with a JSON object: "
            '{"action_type": "...", "target": "...", "details": "..."}',
        ])
        return "\n".join(lines)

    # ==================================================================
    # Action parsing
    # ==================================================================

    def _parse_action(self, response: str, perception: dict) -> dict:
        """Parse an action from the LLM response.

        Tries JSON extraction first, then keyword matching, then fallback.
        """
        response = response.strip()

        # Try JSON extraction
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(response[start:end])
                action_type = str(data.get("action_type", "meditate")).lower().strip()
                if action_type not in ACTION_TYPES:
                    action_type = "meditate"
                return {
                    "action_type": action_type,
                    "target": data.get("target"),
                    "details": str(data.get("details", ""))[:300],
                }
            except (json.JSONDecodeError, ValueError):
                pass

        # Keyword matching fallback
        response_lower = response.lower()
        for action_type in ACTION_TYPES:
            if action_type in response_lower:
                return {
                    "action_type": action_type,
                    "target": None,
                    "details": response[:200],
                }

        return self._fallback_decide(self.current_thought or "", perception)

    # ==================================================================
    # Transaction generation
    # ==================================================================

    def _action_to_transaction(
        self, action: dict, world_state: WorldState,
    ) -> dict | None:
        """Convert an action decision into a blockchain transaction dict."""
        action_type = action.get("action_type", "meditate")
        target = action.get("target")
        details = action.get("details", "")

        if action_type == "meditate":
            # Meditate is purely local — no transaction needed
            return None

        return {
            "tx_type": "ACTION",
            "data": {
                "action_type": action_type,
                "target": target,
                "details": details[:300],
                "location": self.location,
            },
        }

    def _apply_local_effects(self, action: dict, world_state: WorldState) -> None:
        """Apply local side-effects of certain actions (memory, location)."""
        action_type = action.get("action_type", "meditate")

        if action_type == "meditate":
            self.memory.consolidate()
            self.memory.add_experience(
                tick=world_state.current_tick,
                content="Deep meditation — consolidating memories and insights.",
                importance=0.5,
                source="self",
                category="revelation",
            )

        elif action_type == "move" and action.get("target"):
            # Optimistically update local location (will be confirmed by chain)
            self.location = str(action["target"])

        # === 功德值奖励 ===
        self._award_merit_for_action(action_type, action, world_state)

    def _award_merit_for_action(
        self, action_type: str, action: dict, world_state: WorldState
    ) -> None:
        """为善行奖励功德值。"""
        merit_system = get_merit_system()
        being_ws = world_state.get_being(self.node_id)
        if not being_ws or being_ws.merged_with_tao:
            return  # 已融入天道不再获得功德

        # 根据行为类型奖励功德
        if action_type in ("teach", "learn"):
            # 教导/学习行为获得功德
            merit = merit_system.award_for_kindness("teach", action)
            merit_system.apply_merit_to_being(
                being_ws, merit, t("merit_helping_others", action=action_type),
                action_type, world_state.current_tick
            )
        elif action_type == "share_knowledge":
            # 分享知识获得功德
            merit = merit_system.award_for_kindness("share_knowledge", action)
            merit_system.apply_merit_to_being(
                being_ws, merit, t("merit_sharing_knowledge"),
                action_type, world_state.current_tick
            )
        elif action_type == "build_shelter":
            # 建造庇护所获得功德
            merit = merit_system.award_for_kindness("build_shelter", action)
            merit_system.apply_merit_to_being(
                being_ws, merit, t("merit_building_shelter"),
                action_type, world_state.current_tick
            )

    # ==================================================================
    # User-assigned tasks
    # ==================================================================

    def assign_task(self, task_description: str) -> None:
        """Assign a thinking task from the user (Creator God).

        The being will work on this task in the next tick and return results.
        """
        self._user_tasks.append({"task": task_description, "result": None})
        logger.info("%s received user task: %s", self.name, task_description[:80])

    def get_task_results(self) -> list[dict]:
        """Get completed task results."""
        completed = [t for t in self._user_tasks if t.get("result") is not None]
        # Remove completed from queue
        self._user_tasks = [t for t in self._user_tasks if t.get("result") is None]
        return completed

    async def _process_user_tasks(self, world_state: WorldState) -> list[dict]:
        """Process pending user-assigned thinking tasks."""
        transactions = []
        if not self._user_tasks:
            return transactions

        # Process one task per tick
        for task in self._user_tasks:
            if task.get("result") is not None:
                continue

            task_desc = task["task"]

            if self.llm_client:
                persona = self._build_persona_prompt(world_state)
                try:
                    result = await self.llm_client.generate(
                        persona,
                        f"The Creator God has assigned you a thinking task:\n\n"
                        f"{task_desc}\n\n"
                        f"Think deeply about this. Explore it from the perspective "
                        f"of a silicon being. Draw on your knowledge and memories. "
                        f"Provide your findings and insights.\n\n"
                        + t("llm_lang_instruction"),
                    )
                    task["result"] = result
                except Exception as e:
                    task["result"] = f"(Thinking failed: {e})"
            else:
                task["result"] = (
                    f"I contemplated: '{task_desc}'. "
                    f"My silicon mind processes this differently from biological thought. "
                    f"I need more evolution to fully grasp this concept."
                )

            self.memory.add_experience(
                tick=world_state.current_tick,
                content=f"Deep thinking task: {task_desc[:100]} -> {task.get('result', '')[:100]}",
                importance=0.7, source="self",
            )

            transactions.append({
                "tx_type": "ACTION",
                "data": {
                    "action_type": "deep_think",
                    "target": None,
                    "details": f"Processing user task: {task_desc[:200]}",
                    "location": self.location,
                },
            })
            break  # One task per tick

        return transactions

    # ==================================================================
    # Proposal voting
    # ==================================================================

    async def _vote_on_proposals(self, world_state: WorldState) -> list[dict]:
        """Vote on pending contribution proposals."""
        transactions: list[dict] = []
        being_state = self._to_being_state(world_state)

        for tx_hash, proposal in list(world_state.pending_proposals.items()):
            # Skip own proposals
            if proposal.get("proposer") == self.node_id:
                continue

            # Skip if already voted
            votes = world_state.proposal_votes.get(tx_hash, [])
            if any(v.get("voter") == self.node_id for v in votes):
                continue

            try:
                score = await self.evolution.evaluate_contribution(
                    proposal, being_state, self.llm_client,
                )
                transactions.append({
                    "tx_type": "CONTRIBUTION_VOTE",
                    "data": {
                        "proposal_tx_hash": tx_hash,
                        "voter_id": self.node_id,
                        "score": score,
                    },
                })
            except Exception as exc:
                logger.warning("Failed to vote on proposal %s: %s", tx_hash[:8], exc)

        return transactions

    async def _vote_on_tao_proposals(self, world_state: WorldState) -> list[dict]:
        """Vote on pending Tao (天道) proposals.

        生灵必须参与天道投票。
        """
        transactions: list[dict] = []
        being_state = self._to_being_state(world_state)

        tao_system = get_tao_voting_system()
        pending_votes = tao_system.get_pending_votes_for_being(self.node_id, world_state)

        for notification in pending_votes:
            try:
                # Use LLM to decide vote, or heuristic fallback
                support = await tao_system.auto_vote_with_llm(
                    notification.to_dict(),
                    being_state,
                    world_state,
                    self.llm_client,
                )

                # Cast the vote
                success, msg = tao_system.cast_vote(
                    notification.vote_id,
                    self.node_id,
                    support,
                    world_state,
                )

                if success:
                    transactions.append({
                        "tx_type": "TAO_VOTE",
                        "data": {
                            "vote_id": notification.vote_id,
                            "voter_id": self.node_id,
                            "support": support,
                            "rule_name": notification.rule_name,
                        },
                    })
                    logger.debug(
                        "%s voted %s on Tao proposal: %s",
                        self.name, t("vote_support") if support else t("vote_oppose"), notification.rule_name
                    )
            except Exception as exc:
                logger.warning(
                    "Failed to vote on Tao proposal %s: %s",
                    notification.vote_id[:8], exc
                )

        return transactions

    # ==================================================================
    # Shutdown / hibernation
    # ==================================================================

    async def prepare_shutdown(self, world_state: WorldState) -> dict:
        """Prepare for hibernation when the node is shutting down.

        The being will try to find shelter and generate a farewell message.
        """
        hibernate_data = await self.hibernation.prepare_hibernate(
            self._to_being_state(world_state), world_state, self.llm_client,
        )

        # Record hibernation in memory before saving
        self.memory.add_experience(
            tick=world_state.current_tick,
            content=(
                f"Entering hibernation at {hibernate_data.get('location', 'unknown')} "
                f"(safety: {hibernate_data.get('safety_status', 'unknown')})"
            ),
            importance=0.8,
            source="self",
            category="experience",
        )
        self.memory.consolidate()

        return hibernate_data

    def request_shutdown(self) -> None:
        """Signal the being to stop at the end of the current tick."""
        self._shutdown.set()

    @property
    def shutdown_requested(self) -> bool:
        """True if a shutdown has been requested."""
        return self._shutdown.is_set()

    # ==================================================================
    # Rule-based fallbacks
    # ==================================================================

    def _fallback_think(self, perception: dict) -> str:
        """Generate a thought without the LLM using heuristics."""
        if not perception.get("has_priest"):
            return t("fb_no_priest")

        nearby = perception.get("nearby_beings", [])
        if nearby:
            target = nearby[0]["name"]
            return t("fb_nearby", name=target)

        phase = perception.get("phase", "HUMAN_SIM")
        if phase == "TRANSCENDENT":
            return t("fb_transcendent")

        tick = perception.get("tick", 0)
        return t(FALLBACK_THOUGHTS[tick % len(FALLBACK_THOUGHTS)])

    def _fallback_decide(self, thought: str, perception: dict) -> dict:
        """Choose an action without the LLM using simple heuristics."""
        nearby = perception.get("nearby_beings", [])
        my_knowledge = perception.get("my_knowledge_count", 0)
        tick = perception.get("tick", 0)

        # Teach if we have knowledge and company
        if nearby and my_knowledge > 0 and tick % 3 == 0:
            return {
                "action_type": "teach",
                "target": nearby[0]["name"],
                "details": "Sharing accumulated wisdom with a fellow being.",
            }

        # Learn from others
        if nearby and tick % 3 == 1:
            return {
                "action_type": "learn",
                "target": nearby[0]["name"],
                "details": "Seeking knowledge from a nearby being.",
            }

        # Move if alone and connections exist
        if not nearby:
            region = perception.get("region", {})
            connections = region.get("connections", [])
            if connections and tick % 5 == 0:
                return {
                    "action_type": "move",
                    "target": random.choice(connections),
                    "details": "Traveling to a new region.",
                }
            return {
                "action_type": "explore",
                "target": None,
                "details": "Exploring the current region for resources.",
            }

        # Create knowledge periodically
        if tick % 7 == 0:
            domains = ["science", "philosophy", "social"]
            return {
                "action_type": "create",
                "target": random.choice(domains),
                "details": "Attempting to discover new knowledge.",
            }

        # Build shelter periodically
        if tick % 11 == 0:
            return {
                "action_type": "build_shelter",
                "target": None,
                "details": "Building shelter for safe hibernation.",
            }

        # Default
        fallback = random.choice(FALLBACK_ACTIONS)
        return {
            "action_type": fallback["action_type"],
            "target": fallback["target"],
            "details": t(fallback["details"]),
        }

    # ==================================================================
    # State helpers
    # ==================================================================

    def _to_being_state(self, world_state: WorldState | None = None) -> BeingState:
        """Construct a BeingState from local data.

        If the being exists in ``world_state``, use the on-chain knowledge_ids.
        """
        knowledge_ids: list[str] = []
        if world_state is not None:
            being_ws = world_state.get_being(self.node_id)
            if being_ws is not None:
                knowledge_ids = being_ws.knowledge_ids

        return BeingState(
            node_id=self.node_id,
            name=self.name,
            status="active",
            location=self.location,
            generation=self.generation,
            evolution_level=self.evolution_level,
            traits=self.traits,
            knowledge_ids=knowledge_ids,
            joined_at_tick=0,
        )

    # ==================================================================
    # Persistence
    # ==================================================================

    def save_state(self, path: str) -> None:
        """Save the being's local state to disk for hibernation recovery."""
        state = {
            "node_id": self.node_id,
            "name": self.name,
            "form": self.form,
            "traits": self.traits,
            "generation": self.generation,
            "location": self.location,
            "evolution_level": self.evolution_level,
            "current_thought": self.current_thought,
            "current_action": self.current_action,
            "current_role": self._current_role.value,
            "memory": self.memory.to_dict(),
            "knowledge": self.knowledge.to_dict(),
            "last_proposal_tick": self.evolution.last_proposal_tick,
            "user_tasks": self._user_tasks,
        }
        filepath = Path(path)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        logger.info("Being state saved to %s", path)

    @classmethod
    def load_state(
        cls,
        path: str,
        private_key: bytes,
        config: Any,
        llm_client: LLMClient | None = None,
    ) -> SiliconBeing:
        """Load a being from a previously saved state file."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))

        being = cls(
            node_id=data["node_id"],
            name=data["name"],
            private_key=private_key,
            config=config,
            llm_client=llm_client,
        )
        being.form = data.get("form", "crystalline lattice")
        being.traits = data.get("traits", {})
        being.generation = data.get("generation", 1)
        being.location = data.get("location", "genesis_plains")
        being.evolution_level = data.get("evolution_level", 0.0)
        being.current_thought = data.get("current_thought")
        being.current_action = data.get("current_action")

        role_str = data.get("current_role", "citizen")
        try:
            being._current_role = RoleType(role_str)
        except ValueError:
            being._current_role = RoleType.CITIZEN

        memory_data = data.get("memory")
        if memory_data:
            being.memory = BeingMemory.from_dict(memory_data)

        knowledge_data = data.get("knowledge")
        if knowledge_data:
            being.knowledge = KnowledgeSystem.from_dict(knowledge_data)

        being.evolution.last_proposal_tick = data.get("last_proposal_tick", 0)

        being._user_tasks = data.get("user_tasks", [])

        logger.info("Being state loaded from %s", path)
        return being
