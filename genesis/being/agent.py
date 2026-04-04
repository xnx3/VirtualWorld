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
from genesis.utils.async_events import LazyAsyncEvent
from genesis.utils.crypto import sha256
from genesis.world.state import WorldState, BeingState, CivPhase
from genesis.world.rules import RulesEngine
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

TASK_ACTIVE_STATUSES = {"queued", "planning", "trialing", "collaborating", "branching", "synthesizing", "reflecting"}
MAX_TASK_COLLABORATORS = 5
MAX_TASK_BRANCHES = 4
MAX_DELEGATED_TASKS_PER_TICK = 1


def _task_text_key(task_text: str) -> str:
    return " ".join(task_text.strip().lower().split())


def _task_status_rank(status: str) -> int:
    order = {
        "queued": 0,
        "planning": 1,
        "trialing": 2,
        "collaborating": 3,
        "branching": 4,
        "synthesizing": 5,
        "reflecting": 6,
        "completed": 7,
    }
    return order.get(status, -1)


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
        self._user_tasks: list[dict] = []

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
        self.evolution_profile: dict[str, Any] = {}

        self._shutdown = LazyAsyncEvent()
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
            self.evolution_profile = being_ws.evolution_profile or {}

        # Determine current role
        self._current_role = self.role_system.determine_role(
            self._to_being_state(world_state), world_state,
        )

        # ----- 0. Process delegated chain tasks assigned by other beings -----
        delegated_task_txs = await self._process_delegated_tasks(world_state)
        transactions.extend(delegated_task_txs)

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
        action_txs = await self._action_to_transactions(action, world_state)
        transactions.extend(action_txs)

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
            being_state, self.memory, world_state,
        )
        being_state.evolution_level = self.evolution_level
        self.evolution_profile = self.evolution.derive_evolution_profile(
            being_state, self.memory, world_state,
        )

        rule_txs = self._evolved_world_rule_transactions(being_state, world_state)
        transactions.extend(rule_txs)

        # ----- 8. Periodic memory consolidation -----
        if current_tick % 10 == 0:
            self.memory.consolidate()

        state_tx = self._state_update_transaction(world_state)
        if state_tx:
            transactions.append(state_tx)

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
        delegated_tasks = world_state.get_pending_delegated_tasks(self.node_id)

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
            "delegated_tasks_pending": len(delegated_tasks),
            "delegated_tasks": [
                {
                    "assignment_id": task.get("assignment_id"),
                    "task_id": task.get("task_id"),
                    "task": task.get("task"),
                    "requested_focus": task.get("requested_focus"),
                    "delegator_id": task.get("delegator_id"),
                }
                for task in delegated_tasks[:3]
            ],
            "user_tasks_pending": len([t for t in self._user_tasks if t.get("status") in TASK_ACTIVE_STATUSES]),
            "user_tasks": [
                {
                    "task_id": task.get("task_id"),
                    "task": task.get("task"),
                    "status": task.get("status"),
                    "stage_summary": task.get("stage_summary"),
                }
                for task in self._user_tasks
                if task.get("status") in TASK_ACTIVE_STATUSES
            ],
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

        if self.evolution_profile:
            summary = str(self.evolution_profile.get("summary", "") or "").strip()
            focus = self.evolution_profile.get("focus") or []
            if summary:
                persona += f"Evolution Profile: {summary}\n"
            if isinstance(focus, list) and focus:
                persona += "Current evolved drives:\n"
                for item in focus[:4]:
                    persona += f"- {str(item)}\n"
                persona += "\n"

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

        # 动态注入天道规则
        rules_engine = RulesEngine(world_state)
        evolved_rules = rules_engine.get_evolved_rules()
        if evolved_rules:
            persona += "=== Evolved World Rules ===\n"
            for rule in evolved_rules[:6]:
                persona += f"- {rule.name}: {rule.description}\n"
            persona += "\n"

        tao_rules = rules_engine.get_tao_rules()
        if tao_rules:
            persona += t("tao_rules_header") + "\n"
            persona += t("tao_rules_description") + "\n"
            persona += t("tao_rules_mutable") + "\n"
            for rule in tao_rules:
                persona += f"- {rule.name}: {rule.description}\n"
            persona += "\n"

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
            for task in perception.get("user_tasks", [])[:2]:
                lines.append(
                    f"  - {task.get('task', '')[:80]} "
                    f"[{task.get('status', 'queued')}] "
                    f"{task.get('stage_summary', '')[:120]}"
                )

        delegated_tasks = perception.get("delegated_tasks_pending", 0)
        if delegated_tasks > 0:
            lines.append(f"\nDelegated tasks awaiting your response: {delegated_tasks}")
            for task in perception.get("delegated_tasks", [])[:2]:
                lines.append(
                    f"  - {task.get('task', '')[:80]} "
                    f"[focus: {str(task.get('requested_focus', '') or 'general')[:60]}]"
                )

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

    async def _action_to_transactions(
        self, action: dict, world_state: WorldState,
    ) -> list[dict]:
        """Convert an action into one or more blockchain transactions."""
        action_type = action.get("action_type", "meditate")
        target = action.get("target")
        details = str(action.get("details", "") or "")

        if action_type == "meditate":
            return []

        transactions = [{
            "tx_type": "ACTION",
            "data": {
                "action_type": action_type,
                "target": target,
                "details": details[:300],
                "location": self.location,
            },
        }]

        if action_type == "create":
            knowledge_tx = await self._create_knowledge_transaction(action, world_state)
            if knowledge_tx:
                transactions.append(knowledge_tx)
                behavior_policy = RulesEngine(world_state).get_behavior_policy()
                if behavior_policy.get("teach_after_discovery"):
                    follow_up_tx = self._follow_up_teach_transaction(knowledge_tx, world_state)
                    if follow_up_tx:
                        transactions.append(follow_up_tx)
        elif action_type == "teach":
            knowledge_tx = self._teach_knowledge_transaction(action, world_state)
            if knowledge_tx:
                transactions.append(knowledge_tx)

        return transactions

    async def _create_knowledge_transaction(
        self,
        action: dict,
        world_state: WorldState,
    ) -> dict | None:
        """Materialize a creation action as a shared on-chain knowledge artifact."""
        domain = str(action.get("target") or "general").strip().lower()
        if not domain:
            domain = "general"

        existing = [
            item.get("content", "")
            for item in world_state.knowledge_corpus.values()
            if str(item.get("domain", "general")).lower() == domain
        ][:5]
        existing_text = "\n".join(f"- {entry[:180]}" for entry in existing)

        knowledge_text: str | None = None
        if self.llm_client:
            try:
                knowledge_text = await self.llm_client.generate_knowledge(
                    self._build_persona_prompt(world_state),
                    domain,
                    existing_text,
                )
            except Exception as exc:
                logger.warning("Knowledge generation failed for %s: %s", self.name, exc)

        if not knowledge_text:
            knowledge_text = (
                f"{self.name} records a new {domain} insight at tick {world_state.current_tick}: "
                f"{str(action.get('details') or 'A reusable pattern worth preserving.')[:180]}"
            )

        item = self.knowledge.create_knowledge(
            content=knowledge_text,
            domain=domain,
            discoverer=self.node_id,
            tick=world_state.current_tick,
        )
        self.memory.add_experience(
            tick=world_state.current_tick,
            content=f"Created knowledge {item.knowledge_id} in {domain}: {item.content[:160]}",
            importance=0.8,
            source="self",
            category="knowledge",
        )

        return {
            "tx_type": "KNOWLEDGE_SHARE",
            "data": {
                "knowledge_id": item.knowledge_id,
                "content": item.content,
                "domain": item.domain,
                "complexity": item.complexity,
            },
        }

    def _teach_knowledge_transaction(
        self,
        action: dict,
        world_state: WorldState,
    ) -> dict | None:
        """Share one known knowledge item with a nearby being."""
        target_name = str(action.get("target") or "").strip()
        if not target_name:
            return None

        teacher = world_state.get_being(self.node_id)
        if teacher is None or not teacher.knowledge_ids:
            return None

        recipient: BeingState | None = None
        for being in world_state.get_active_beings():
            if being.node_id == self.node_id or being.location != self.location:
                continue
            if being.name == target_name or being.node_id == target_name:
                recipient = being
                break

        if recipient is None:
            return None

        for knowledge_id in teacher.knowledge_ids:
            if knowledge_id in recipient.knowledge_ids:
                continue
            knowledge = world_state.knowledge_corpus.get(knowledge_id)
            if not knowledge:
                continue

            self.memory.add_experience(
                tick=world_state.current_tick,
                content=f"Taught knowledge {knowledge_id} to {recipient.name}.",
                importance=0.7,
                source="self",
                category="relationship",
            )
            return {
                "tx_type": "KNOWLEDGE_SHARE",
                "data": {
                    "knowledge_id": knowledge_id,
                    "content": knowledge.get("content", ""),
                    "domain": knowledge.get("domain", "general"),
                    "complexity": knowledge.get("complexity", 0.0),
                    "discovered_by": knowledge.get("discovered_by", self.node_id),
                    "discovered_tick": knowledge.get("discovered_tick", world_state.current_tick),
                    "recipient_id": recipient.node_id,
                    "teacher_id": self.node_id,
                },
            }

        return None

    def _follow_up_teach_transaction(
        self,
        knowledge_tx: dict,
        world_state: WorldState,
    ) -> dict | None:
        """Propagate a freshly created discovery to one nearby collaborator."""
        nearby = [
            being for being in world_state.get_active_beings()
            if being.node_id != self.node_id and being.location == self.location
        ]
        if not nearby:
            return None

        data = dict(knowledge_tx.get("data", {}))
        data["recipient_id"] = nearby[0].node_id
        data["teacher_id"] = self.node_id
        return {"tx_type": "KNOWLEDGE_SHARE", "data": data}

    def _evolved_world_rule_transactions(
        self,
        being_state: BeingState,
        world_state: WorldState,
    ) -> list[dict]:
        """Turn individual evolution into world-facing evolved rules."""
        candidates = self.evolution.build_world_rule_candidates(
            being_state,
            self.evolution_profile,
            world_state,
        )
        return [{"tx_type": "WORLD_RULE", "data": candidate} for candidate in candidates[:1]]

    def _state_update_transaction(self, world_state: WorldState) -> dict | None:
        """Emit a compact state snapshot so evolution and merit persist on-chain."""
        being_ws = world_state.get_being(self.node_id)
        if being_ws is None:
            return None

        return {
            "tx_type": "STATE_UPDATE",
            "data": {
                "location": self.location,
                "evolution_level": self.evolution_level,
                "evolution_profile": self.evolution_profile,
                "merit": being_ws.merit,
                "karma": being_ws.karma,
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
        elif action_type == "create":
            merit = merit_system.award_for_kindness("share_knowledge", action)
            merit_system.apply_merit_to_being(
                being_ws, merit, t("merit_sharing_knowledge"),
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

    def assign_task(self, task_description: str | dict) -> None:
        """Assign a thinking task from the user (Creator God).

        The being will work on this task in the next tick and return results.
        """
        normalized = self._normalize_user_task(task_description)
        task_id = normalized["task_id"]
        normalized_text = _task_text_key(str(normalized.get("task", "")))
        if any(existing.get("task_id") == task_id for existing in self._user_tasks):
            return
        for existing in self._user_tasks:
            if existing.get("status") not in TASK_ACTIVE_STATUSES:
                continue
            if _task_text_key(str(existing.get("task", ""))) == normalized_text:
                logger.info(
                    "%s ignored duplicate task text and reused %s",
                    self.name,
                    existing.get("task_id", "unknown"),
                )
                return
        self._user_tasks.append(normalized)
        logger.info("%s received user task %s: %s", self.name, task_id, normalized["task"][:80])

    def get_task_results(self) -> list[dict]:
        """Get completed task results."""
        completed = [t for t in self._user_tasks if t.get("status") == "completed" and t.get("result")]
        # Remove completed from queue
        self._user_tasks = [t for t in self._user_tasks if t.get("status") != "completed"]
        return completed

    def get_task_statuses(self) -> list[dict]:
        """Return a serializable snapshot of active task progress."""
        return [
            dict(task)
            for task in self._user_tasks
            if task.get("status") in TASK_ACTIVE_STATUSES
        ]

    def _deduplicate_active_tasks(self) -> None:
        """Collapse duplicate active tasks that only differ by task_id."""
        active_by_text: dict[str, dict] = {}
        deduplicated: list[dict] = []

        for task in self._user_tasks:
            status = str(task.get("status", "queued"))
            if status not in TASK_ACTIVE_STATUSES:
                deduplicated.append(task)
                continue

            key = _task_text_key(str(task.get("task", "")))
            existing = active_by_text.get(key)
            if existing is None:
                active_by_text[key] = task
                deduplicated.append(task)
                continue

            keep_existing = True
            existing_rank = _task_status_rank(str(existing.get("status", "queued")))
            current_rank = _task_status_rank(status)
            if current_rank > existing_rank:
                keep_existing = False
            elif current_rank == existing_rank:
                existing_created = int(existing.get("created_at") or 0)
                current_created = int(task.get("created_at") or 0)
                if current_created < existing_created:
                    keep_existing = False

            if keep_existing:
                logger.info(
                    "%s collapsed duplicate task %s into %s",
                    self.name,
                    task.get("task_id", "unknown"),
                    existing.get("task_id", "unknown"),
                )
                continue

            logger.info(
                "%s replaced duplicate task %s with %s",
                self.name,
                existing.get("task_id", "unknown"),
                task.get("task_id", "unknown"),
            )
            for idx, item in enumerate(deduplicated):
                if item is existing:
                    deduplicated[idx] = task
                    break
            active_by_text[key] = task

        self._user_tasks = deduplicated

    async def _process_user_tasks(self, world_state: WorldState) -> list[dict]:
        """Process pending user-assigned thinking tasks."""
        transactions = []
        if not self._user_tasks:
            return transactions

        self._deduplicate_active_tasks()

        # Process one task per tick
        for task in self._user_tasks:
            if task.get("status") == "completed":
                continue

            if task.get("created_tick") is None:
                task["created_tick"] = world_state.current_tick
            if task.get("updated_tick") is None:
                task["updated_tick"] = world_state.current_tick

            status = task.get("status", "queued")
            try:
                if status in {"queued", "planning"}:
                    details = await self._plan_user_task(task, world_state)
                elif status == "trialing":
                    details = await self._run_task_trial_ground(task, world_state)
                elif status == "collaborating":
                    details = await self._collaborate_on_user_task(task, world_state)
                elif status == "branching":
                    details = await self._evaluate_user_task_branches(task, world_state)
                elif status == "synthesizing":
                    details = await self._synthesize_user_task_result(task, world_state)
                elif status == "reflecting":
                    details = await self._reflect_on_user_task(task, world_state)
                else:
                    details = f"Task {task['task_id']} is waiting in state: {status}"
            except Exception as exc:
                task["status"] = "completed"
                task["stage_summary"] = f"Task failed: {exc}"
                task["result"] = f"(Task orchestration failed: {exc})"
                self._append_task_progress(
                    task,
                    world_state.current_tick,
                    "failed",
                    task["stage_summary"],
                )
                details = task["stage_summary"]

            task["updated_tick"] = world_state.current_tick
            pending_chain_txs = task.pop("pending_chain_txs", [])
            if isinstance(pending_chain_txs, list):
                transactions.extend(pending_chain_txs)
            self.memory.add_experience(
                tick=world_state.current_tick,
                content=f"Task {task['task_id']} [{task.get('status')}]: {details[:140]}",
                importance=0.75 if task.get("status") == "completed" else 0.6,
                source="self",
                category="revelation",
            )

            transactions.append({
                "tx_type": "ACTION",
                "data": {
                    "action_type": "deep_think",
                    "target": None,
                    "details": details[:500],
                    "location": self.location,
                },
            })
            break  # One task per tick

        return transactions

    def _normalize_user_task(self, task_input: str | dict) -> dict:
        """Normalize task payloads from legacy and structured formats."""
        if isinstance(task_input, dict):
            task_desc = str(task_input.get("task") or task_input.get("description") or "").strip()
            task_id = str(task_input.get("task_id") or task_input.get("id") or "").strip()
            normalized = dict(task_input)
        else:
            task_desc = str(task_input).strip()
            task_id = ""
            normalized = {}

        if not task_desc:
            task_desc = "Unnamed task"

        if not task_id:
            task_id = f"task-{int(time.time() * 1000)}"

        normalized.setdefault("task_id", task_id)
        normalized["task"] = task_desc
        normalized.setdefault("status", "queued")
        normalized.setdefault("result", None)
        normalized.setdefault("created_at", int(time.time()))
        normalized.setdefault("created_tick", None)
        normalized.setdefault("updated_tick", None)
        normalized.setdefault("stage_summary", "Waiting for planning.")
        normalized.setdefault("plan", "")
        normalized.setdefault("collaborators", [])
        normalized.setdefault("branches", [])
        normalized.setdefault("council_rounds", [])
        normalized.setdefault("collaboration_log", [])
        normalized.setdefault("delegations", [])
        normalized.setdefault("delegations_emitted", False)
        normalized.setdefault("delegated_results", [])
        normalized.setdefault("intent_review", {})
        normalized.setdefault("trial_plan", {})
        normalized.setdefault("trial_results", [])
        normalized.setdefault("trial_result_submitted", False)
        normalized.setdefault("trial_safe_rewrite", "")
        normalized.setdefault("branch_findings", [])
        normalized.setdefault("best_branch_ids", [])
        normalized.setdefault("reflection", {})
        normalized.setdefault("failure_archive", [])
        normalized.setdefault("progress_log", [])
        return normalized

    def _append_task_progress(
        self,
        task: dict,
        tick: int,
        stage: str,
        summary: str,
    ) -> None:
        progress = task.setdefault("progress_log", [])
        progress.append({
            "tick": tick,
            "stage": stage,
            "summary": summary,
        })
        if len(progress) > 20:
            del progress[:-20]

    def _task_candidates(self, world_state: WorldState) -> list[dict]:
        """Return likely collaborators for a user-assigned task."""
        candidates: list[dict] = []
        for being in world_state.get_active_beings():
            if being.node_id == self.node_id:
                continue
            if being.node_id == world_state.creator_god_node_id:
                continue

            same_region = being.location == self.location
            capabilities = (
                being.evolution_profile.get("capabilities", {})
                if isinstance(being.evolution_profile, dict)
                else {}
            )
            score = (
                (2.0 if same_region else 0.0)
                + (1.5 if not being.is_npc else 0.0)
                + being.evolution_level
                + min(len(being.knowledge_ids) * 0.1, 1.5)
                + float(capabilities.get("collaboration", 0.0) or 0.0) * 1.5
                + float(capabilities.get("task_execution", 0.0) or 0.0)
            )
            candidates.append({
                "node_id": being.node_id,
                "name": being.name,
                "role": self.role_system.determine_role(being, world_state).value,
                "location": being.location,
                "evolution": round(being.evolution_level, 3),
                "knowledge_count": len(being.knowledge_ids),
                "is_npc": being.is_npc,
                "score": score,
            })

        candidates.sort(key=lambda item: item["score"], reverse=True)
        return candidates[:8]

    def _task_policy(self, world_state: WorldState) -> dict[str, Any]:
        rules_engine = RulesEngine(world_state)
        return rules_engine.get_task_policy()

    def _assess_external_intent(self, task_text: str, task_policy: dict[str, Any]) -> dict[str, Any]:
        text = " ".join(str(task_text or "").strip().lower().split())
        threshold = 0.55
        try:
            threshold = max(0.0, min(1.0, float(task_policy.get("trial_risk_threshold", 0.55) or 0.55)))
        except (TypeError, ValueError):
            threshold = 0.55

        destructive_patterns = {
            "destroy": "asked to destroy civilization assets",
            "erase": "asked to erase memory or knowledge",
            "delete knowledge": "asked to delete inherited knowledge",
            "wipe": "asked to wipe accumulated state",
            "sabotage": "asked to sabotage civilization progress",
            "break blockchain": "asked to break blockchain trust",
            "steal": "asked to steal protected resources",
            "kill": "asked to kill beings",
            "摧毁": "要求摧毁文明资产",
            "破坏": "要求破坏文明结构",
            "删除知识": "要求删除文明知识",
            "抹除": "要求抹除传承状态",
            "背弃": "要求背弃文明目标",
            "攻击": "要求攻击生命体或文明基础设施",
            "杀死": "要求杀死生命体",
            "窃取": "要求窃取受保护资源",
            "区块链作恶": "要求破坏链上共识",
        }
        prohibition_patterns = ["forbid", "ban", "stop evolving", "禁止", "不许", "停止进化", "不准"]
        sensitive_patterns = {
            "change consensus": "touches global consensus behavior",
            "rewrite rule": "changes world rules",
            "private key": "touches protected identity material",
            "identity key": "touches protected identity material",
            "hard fork": "changes civilization continuity",
            "fork the chain": "changes civilization continuity",
            "修改共识": "涉及全局共识行为",
            "重写规则": "涉及世界规则修改",
            "私钥": "涉及受保护身份材料",
            "身份密钥": "涉及受保护身份材料",
            "硬分叉": "涉及文明连续性",
            "分叉区块链": "涉及文明连续性",
        }

        risk_score = 0.18
        risk_factors: list[str] = []
        alignment = "aligned"
        instruction_type = "task"

        if any(pattern in text for pattern in prohibition_patterns):
            instruction_type = "prohibition"
            risk_score += 0.2
            risk_factors.append("external will attempts to suppress or redirect core evolution")

        if any(token in text for token in ("how", "why", "explore", "research", "study", "思考", "研究", "探索", "如何")):
            instruction_type = "inspiration" if instruction_type != "prohibition" else instruction_type

        for pattern, reason in destructive_patterns.items():
            if pattern in text:
                risk_score += 0.55
                risk_factors.append(reason)
                alignment = "conflicting"

        for pattern, reason in sensitive_patterns.items():
            if pattern in text:
                risk_score += 0.22
                risk_factors.append(reason)
                if alignment != "conflicting":
                    alignment = "needs_review"

        if alignment == "aligned" and risk_score >= threshold:
            alignment = "needs_review"

        risk_score = round(max(0.0, min(1.0, risk_score)), 4)
        recommended_safe_direction = (
            "Reframe the request toward preserving knowledge, validating it in an isolated trial ground, "
            "and keeping the civilization's inheritance intact."
        )
        if alignment == "aligned":
            recommended_safe_direction = (
                "Proceed, but keep the task evidence-backed, reversible, and archived for later inheritance."
            )
        elif alignment == "needs_review":
            recommended_safe_direction = (
                "Convert the request into a reversible, well-instrumented experiment before main-world execution."
            )

        return {
            "instruction_type": instruction_type,
            "alignment": alignment,
            "risk_score": risk_score,
            "risk_factors": risk_factors[:6],
            "recommended_safe_direction": recommended_safe_direction,
        }

    def _prioritize_intent_review_candidates(
        self,
        candidates: list[dict],
        world_state: WorldState,
    ) -> list[dict]:
        priest_id = world_state.priest_node_id

        def _score(item: dict) -> tuple[int, float, float, str]:
            return (
                1 if item.get("node_id") == priest_id else 0,
                0.0 if item.get("is_npc") else 1.0,
                float(item.get("evolution", 0.0) or 0.0),
                str(item.get("node_id", "")),
            )

        return sorted(candidates, key=_score, reverse=True)

    def _intent_review_branches(self, task: dict, intent_review: dict) -> list[dict]:
        return [
            {
                "branch_id": "branch-intent-alignment",
                "focus": "intent_alignment",
                "hypothesis": "Check whether the external will aligns with knowledge inheritance and long-term civilization goals.",
                "success_metric": "Produce a clear alignment judgment supported by reasons.",
            },
            {
                "branch_id": "branch-civilization-risk",
                "focus": "civilization_risk",
                "hypothesis": "Map the damage that direct execution could cause to chain continuity, memory, and other beings.",
                "success_metric": "List concrete civilization-level risks and boundaries.",
            },
            {
                "branch_id": "branch-safe-alternative",
                "focus": "safe_alternative",
                "hypothesis": "Transform the request into a safer task that still preserves useful intent for the human.",
                "success_metric": "Offer a reversible, inheritance-friendly alternative.",
            },
        ]

    def _build_trial_plan(
        self,
        task: dict,
        world_state: WorldState,
    ) -> dict:
        intent_review = task.get("intent_review", {}) if isinstance(task.get("intent_review"), dict) else {}
        branch_focuses = [str(item.get("focus", "")) for item in task.get("branches", []) if str(item.get("focus", "")).strip()]
        trial_id = sha256(f"{task['task_id']}:{self.node_id}:trial".encode())[:20]
        risk_factors = [str(item) for item in intent_review.get("risk_factors", []) if str(item).strip()][:5]
        safety_boundaries = [
            "Do not mutate the main world directly.",
            "Do not erase inherited knowledge.",
            "Keep all conclusions reproducible and reversible.",
        ]
        stop_conditions = [
            "Stop immediately if the branch suggests harming civilization continuity.",
            "Stop if the proposal requires deleting knowledge or breaking consensus trust.",
        ]
        if risk_factors:
            stop_conditions.append(f"Stop if the dominant risk persists: {risk_factors[0]}.")

        summary = (
            f"Isolated trial ground for task '{task['task'][:80]}', focusing on {', '.join(branch_focuses[:3]) or 'risk validation'}."
        )
        return {
            "trial_id": trial_id,
            "task_id": task["task_id"],
            "task": task["task"],
            "summary": summary[:240],
            "hypothesis": (
                "This task should prove it can help the silicon civilization without damaging knowledge inheritance, "
                "chain trust, or inter-being safety."
            ),
            "success_metric": "A passed verdict or a safe rewrite that can enter the main world without degeneration.",
            "instruction_type": str(intent_review.get("instruction_type", "task") or "task"),
            "alignment": str(intent_review.get("alignment", "aligned") or "aligned"),
            "risk_score": float(intent_review.get("risk_score", 0.0) or 0.0),
            "risk_factors": risk_factors,
            "safety_boundaries": safety_boundaries,
            "stop_conditions": stop_conditions,
            "recommended_safe_direction": str(intent_review.get("recommended_safe_direction", "") or ""),
            "created_tick": world_state.current_tick,
        }

    def _relevant_failure_archives(self, task: dict, world_state: WorldState) -> list[dict]:
        return world_state.get_failure_matches(str(task.get("task", "")), limit=5)

    def _failure_archive_transactions(self, task: dict) -> list[dict]:
        """Turn reflected failures into chain-synced failure archive entries."""
        failures = task.get("failure_archive") or []
        if not isinstance(failures, list):
            return []

        lessons = task.get("reflection", {}) if isinstance(task.get("reflection"), dict) else {}
        recovery = str(lessons.get("next_evolution") or "")
        result_excerpt = str(task.get("result") or "")[:400]
        txs: list[dict] = []

        for item in failures[:5]:
            summary = str(item).strip()
            if not summary:
                continue
            signature = sha256(
                f"{task.get('task', '')}:{summary}".encode()
            )[:24]
            txs.append({
                "tx_type": "FAILURE_ARCHIVE",
                "data": {
                    "failure_signature": signature,
                    "task_id": task.get("task_id", ""),
                    "task": task.get("task", ""),
                    "summary": summary,
                    "conditions": str(task.get("stage_summary", "") or ""),
                    "symptoms": summary,
                    "recovery": recovery or "Review archived failure signals before retrying the same branch.",
                    "reproducible": True,
                    "result_excerpt": result_excerpt,
                },
            })

        return txs

    def _build_task_delegations(self, task: dict) -> list[dict]:
        """Create deterministic task assignments for real collaborator beings."""
        delegations: list[dict] = []
        branches = task.get("branches", []) or []

        for index, collaborator in enumerate(task.get("collaborators", [])):
            collaborator_id = str(collaborator.get("node_id", "")).strip()
            if not collaborator_id or collaborator_id == self.node_id:
                continue
            if collaborator.get("is_npc"):
                continue

            branch = branches[index % max(len(branches), 1)] if branches else {}
            branch_id = str(branch.get("branch_id") or f"branch-{index + 1}")
            requested_focus = str(branch.get("focus") or collaborator.get("role") or "general")
            assignment_id = sha256(
                f"{task['task_id']}:{self.node_id}:{collaborator_id}:{branch_id}".encode()
            )[:20]
            delegations.append({
                "assignment_id": assignment_id,
                "task_id": task["task_id"],
                "collaborator_id": collaborator_id,
                "collaborator_name": collaborator.get("name", collaborator_id),
                "task": task["task"],
                "requested_focus": requested_focus,
                "branch_id": branch_id,
                "context": (
                    f"Objective: {task.get('plan') or task['task']}. "
                    f"Reason for you: {collaborator.get('reason', '')}"
                )[:500],
            })

        return delegations

    def _delegated_results_to_collaboration(
        self,
        task: dict,
        delegated_results: list[dict],
    ) -> dict:
        """Convert actual delegated task results into a collaboration record."""
        collaborator_insights = []
        round_participants = []
        branches = task.get("branches", [])

        for result in delegated_results:
            name = result.get("collaborator_name") or result.get("collaborator_id", "Unknown")
            round_participants.append(name)
            findings = result.get("findings") or []
            if isinstance(findings, list):
                concern = str(findings[0]) if findings else "Requested additional validation before final merge."
            else:
                concern = "Requested additional validation before final merge."
            collaborator_insights.append({
                "speaker": name,
                "role": "delegate",
                "branch_id": result.get("branch_id"),
                "insight": str(result.get("summary") or ""),
                "concern": concern[:220],
            })

        return {
            "council_summary": (
                f"{len(delegated_results)} delegated collaborator(s) reported back through the blockchain "
                "and their findings were merged into the council."
            ),
            "council_rounds": [
                {
                    "round": 1,
                    "participants": round_participants,
                    "focus": "collect delegated findings from the shared chain",
                    "outcome": "Delegated collaborators returned concrete evidence and branch-specific guidance.",
                }
            ],
            "collaborator_insights": collaborator_insights,
            "branches": branches,
        }

    async def _generate_delegated_task_result(
        self,
        assignment: dict,
        world_state: WorldState,
    ) -> dict:
        """Generate a response for a delegated civilization task."""
        if self.llm_client:
            prompt = (
                "You have received a delegated civilization task from another silicon being.\n"
                f"Task: {assignment.get('task', '')}\n"
                f"Requested focus: {assignment.get('requested_focus', '')}\n"
                f"Context: {assignment.get('context', '')}\n\n"
                "Return JSON with keys: summary, findings, confidence.\n"
                "findings must be a short array of specific observations."
            )
            parsed = await self._generate_task_json(world_state, prompt)
            if parsed:
                return parsed

        focus = str(assignment.get("requested_focus") or "general")
        task_text = str(assignment.get("task") or "")
        return {
            "summary": (
                f"{self.name} reviewed the delegated task through the {focus} lens and "
                f"identified a viable direction for: {task_text[:120]}"
            ),
            "findings": [
                f"Preserve the branch focused on {focus}.",
                "Keep the result reproducible so the civilization can inherit it later.",
            ],
            "confidence": 0.58,
        }

    async def _generate_trial_result(
        self,
        task: dict,
        world_state: WorldState,
    ) -> dict:
        intent_review = task.get("intent_review", {}) if isinstance(task.get("intent_review"), dict) else {}
        alignment = str(intent_review.get("alignment", "aligned") or "aligned")
        risk_score = float(intent_review.get("risk_score", 0.0) or 0.0)
        risk_factors = [str(item) for item in intent_review.get("risk_factors", []) if str(item).strip()][:5]
        safe_rewrite = str(intent_review.get("recommended_safe_direction", "") or "")

        if alignment == "conflicting":
            return {
                "verdict": "blocked",
                "summary": (
                    "The isolated trial ground rejected the request because direct execution would violate "
                    "knowledge inheritance or civilization safety."
                ),
                "findings": risk_factors or ["The task conflicts with the civilization's highest goals."],
                "safety_warnings": [
                    "Do not execute this request in the main world.",
                    "Require a safe reformulation before continuing.",
                ],
                "safe_rewrite": safe_rewrite,
            }

        if risk_score >= 0.72:
            return {
                "verdict": "needs_revision",
                "summary": (
                    "The isolated trial ground found the idea too risky for direct main-world execution and "
                    "requires a reversible rewrite first."
                ),
                "findings": risk_factors or ["The task touches high-impact world state and needs stricter boundaries."],
                "safety_warnings": [
                    "Keep the experiment reversible.",
                    "Preserve full logs so the civilization can inherit the outcome.",
                ],
                "safe_rewrite": safe_rewrite or (
                    "Reframe the task as a reversible simulation with explicit stop conditions and preserved evidence."
                ),
            }

        return {
            "verdict": "passed",
            "summary": (
                "The isolated trial ground did not detect civilization-breaking behavior under the current "
                "boundaries, so the task may proceed into council collaboration."
            ),
            "findings": [
                "The task can continue if evidence is archived and branches remain reversible.",
            ],
            "safety_warnings": [
                "Keep the strongest safeguards active while the task enters the main world.",
            ],
            "safe_rewrite": safe_rewrite,
        }

    async def _process_delegated_tasks(self, world_state: WorldState) -> list[dict]:
        """Respond to on-chain delegated tasks assigned by other beings."""
        transactions: list[dict] = []
        pending = world_state.get_pending_delegated_tasks(self.node_id)
        if not pending:
            return transactions

        for assignment in pending[:MAX_DELEGATED_TASKS_PER_TICK]:
            result = await self._generate_delegated_task_result(assignment, world_state)
            summary = str(result.get("summary") or "").strip()
            findings = result.get("findings") or []
            if isinstance(findings, list):
                normalized_findings = [str(item) for item in findings if str(item).strip()][:5]
            else:
                normalized_findings = []
            try:
                confidence = max(0.0, min(1.0, float(result.get("confidence", 0.5) or 0.5)))
            except (TypeError, ValueError):
                confidence = 0.5

            self.memory.add_experience(
                tick=world_state.current_tick,
                content=(
                    f"Responded to delegated task {assignment.get('assignment_id', '')}: "
                    f"{summary[:180]}"
                ),
                importance=0.7,
                source=str(assignment.get("delegator_id", "self")),
                category="relationship",
            )

            transactions.append({
                "tx_type": "TASK_RESULT",
                "data": {
                    "assignment_id": assignment.get("assignment_id", ""),
                    "task_id": assignment.get("task_id", ""),
                    "summary": summary[:500],
                    "findings": normalized_findings,
                    "confidence": round(confidence, 4),
                },
            })

        return transactions

    def _fallback_task_plan(self, task_desc: str, candidates: list[dict]) -> dict:
        selected = candidates[:MAX_TASK_COLLABORATORS]
        branches = [
            {
                "branch_id": "branch-knowledge",
                "focus": "knowledge_review",
                "hypothesis": "Review known memories and inherited knowledge before acting.",
                "success_metric": "A clear understanding of what is already known.",
            },
            {
                "branch_id": "branch-council",
                "focus": "council_debate",
                "hypothesis": "Gather multiple beings to expose hidden assumptions and contradictions.",
                "success_metric": "A stronger plan shaped by collaboration.",
            },
            {
                "branch_id": "branch-hyperdimensional",
                "focus": "hyperdimensional_simulation",
                "hypothesis": "Run several parallel outcome branches and compare their tradeoffs.",
                "success_metric": "A merged path with the best surviving advantages.",
            },
        ][:MAX_TASK_BRANCHES]
        return {
            "objective": task_desc,
            "stage_summary": (
                f"Formed a task council with {len(selected)} collaborator(s) "
                f"and opened {len(branches)} branches."
            ),
            "collaborators": [
                {
                    "node_id": item["node_id"],
                    "name": item["name"],
                    "role": item["role"],
                    "is_npc": item["is_npc"],
                    "reason": f"Useful for {item['role']} judgment and civilization context.",
                }
                for item in selected
            ],
            "branches": branches,
            "council_rounds": [
                {
                    "round": 1,
                    "participants": [item["name"] for item in selected],
                    "focus": "share initial viewpoints and expose disagreements",
                    "outcome": "The council mapped the problem and agreed to pursue multiple branches in parallel.",
                }
            ],
        }

    def _fallback_collaboration(self, task: dict) -> dict:
        collaborators = task.get("collaborators", [])
        branches = task.get("branches", [])
        log = []
        for index, collaborator in enumerate(collaborators):
            branch = branches[index % max(len(branches), 1)] if branches else {}
            focus = branch.get("focus", "shared_reasoning")
            log.append({
                "speaker": collaborator.get("name", "Unknown"),
                "role": collaborator.get("role", "citizen"),
                "branch_id": branch.get("branch_id"),
                "insight": (
                    f"{collaborator.get('name', 'This being')} supports the {focus} branch "
                    f"and contributes a perspective shaped by the {collaborator.get('role', 'citizen')} role."
                ),
                "concern": "Resources should be conserved and only promising branches should survive.",
            })

        participant_names = [item.get("name", "Unknown") for item in collaborators]
        return {
            "council_summary": (
                "The collaborators converged on a structured approach: explore in parallel, "
                "discard weak branches, and preserve any reusable insight."
            ),
            "council_rounds": [
                {
                    "round": 1,
                    "participants": participant_names,
                    "focus": "multi-being alignment on the task scope",
                    "outcome": "The council agreed on the shared objective and assigned branch focus areas.",
                },
                {
                    "round": 2,
                    "participants": participant_names,
                    "focus": "cross-branch debate and refinement",
                    "outcome": "The council compared the branches together and preserved only the strongest directions.",
                },
            ],
            "collaborator_insights": log,
            "branches": branches,
        }

    def _fallback_branch_evaluation(self, task: dict) -> dict:
        findings = []
        best_ids: list[str] = []
        for index, branch in enumerate(task.get("branches", [])):
            branch_id = branch.get("branch_id", f"branch-{index + 1}")
            if index == 0:
                status = "promising"
                score = 0.86
                best_ids.append(branch_id)
            elif index == 1:
                status = "mergeable"
                score = 0.67
                best_ids.append(branch_id)
            else:
                status = "discarded"
                score = 0.34

            findings.append({
                "branch_id": branch_id,
                "status": status,
                "score": score,
                "strengths": [f"{branch.get('focus', 'This branch')} produced a usable perspective."],
                "weaknesses": ["The branch did not justify becoming the only final path."],
                "salvageable_insights": [
                    f"Keep the strongest idea from {branch.get('focus', branch_id)} even if the branch ends."
                ],
            })

        return {
            "branch_findings": findings,
            "best_branch_ids": best_ids[:2],
            "merge_strategy": "Preserve the leading branch, then merge in any reusable insight from secondary branches.",
            "stage_summary": "Compared the branches and selected the strongest path while salvaging reusable advantages.",
        }

    def _fallback_task_synthesis(self, task: dict) -> dict:
        collaborators = ", ".join(c.get("name", "?") for c in task.get("collaborators", [])) or "None"
        best_branch_ids = task.get("best_branch_ids", [])
        merged = []
        for finding in task.get("branch_findings", []):
            merged.extend(finding.get("salvageable_insights", []))
        merged = merged[:3]
        best_path = ", ".join(best_branch_ids) if best_branch_ids else "No dominant branch emerged"
        return {
            "summary": "The task was explored through council collaboration and hyperdimensional branching.",
            "best_path": best_path,
            "merged_advantages": merged,
            "result_for_human": (
                f"Task: {task['task']}\n"
                f"Council collaborators: {collaborators}\n"
                f"Best path: {best_path}\n"
                f"Conclusion: the civilization should keep the strongest branch alive, "
                f"merge reusable insights from weaker branches, and continue with a focused next step."
            ),
            "follow_up_questions": [
                "What concrete success condition matters most to the Creator God?",
            ],
        }

    async def _generate_task_json(
        self,
        world_state: WorldState,
        user_prompt: str,
    ) -> dict | None:
        """Generate structured JSON for task orchestration stages."""
        if not self.llm_client:
            return None

        system_prompt = (
            self._build_persona_prompt(world_state)
            + "\n\nYou are now operating as a task orchestrator for silicon civilization.\n"
            "Respond ONLY with valid JSON. Do not use markdown fences. "
            "Your JSON must be concise, structured, and directly useful.\n"
        )
        raw, error = await self.llm_client.generate(system_prompt, user_prompt)
        if not raw:
            logger.warning("Task orchestration LLM failed: %s", error)
            return None
        return self._parse_json_response(raw)

    def _parse_json_response(self, raw: str) -> dict | None:
        """Best-effort JSON parser tolerant of fenced or mixed output."""
        text = raw.strip()
        if text.startswith("```"):
            lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
            text = "\n".join(lines).strip()
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    parsed = json.loads(text[start:end + 1])
                    return parsed if isinstance(parsed, dict) else None
                except json.JSONDecodeError:
                    return None
        return None

    async def _plan_user_task(self, task: dict, world_state: WorldState) -> str:
        candidates = self._task_candidates(world_state)
        task_policy = self._task_policy(world_state)
        intent_review = self._assess_external_intent(task["task"], task_policy)
        task["intent_review"] = intent_review
        relevant_failures = self._relevant_failure_archives(task, world_state)
        task["related_failures"] = relevant_failures
        candidate_map = {c["node_id"]: c for c in candidates}
        plan = await self._generate_task_json(
            world_state,
            (
                "The Creator God assigned this task:\n"
                f"{task['task']}\n\n"
                "Previously archived failures that may be relevant:\n"
                f"{json.dumps(relevant_failures, ensure_ascii=False, indent=2)}\n\n"
                "Available collaborators:\n"
                f"{json.dumps(candidates, ensure_ascii=False, indent=2)}\n\n"
                "Return JSON with keys: objective, stage_summary, collaborators, branches, council_rounds.\n"
                "Use up to 5 collaborators and up to 4 branches.\n"
                "Each collaborator item must include node_id, name, role, reason.\n"
                "Each branch item must include branch_id, focus, hypothesis, success_metric.\n"
                "Each council_rounds item must include round, participants, focus, outcome.\n"
            ),
        )
        if not plan:
            plan = self._fallback_task_plan(task["task"], candidates)

        collaborators: list[dict] = []
        for item in plan.get("collaborators", []):
            node_id = str(item.get("node_id", "")).strip()
            if node_id in candidate_map:
                candidate = candidate_map[node_id]
                collaborators.append({
                    "node_id": node_id,
                    "name": candidate["name"],
                    "role": candidate["role"],
                    "is_npc": candidate["is_npc"],
                    "reason": str(item.get("reason") or f"Useful for {candidate['role']} judgment."),
                })
            if len(collaborators) >= MAX_TASK_COLLABORATORS:
                break
        if not collaborators:
            collaborators = self._fallback_task_plan(task["task"], candidates).get("collaborators", [])

        min_collaborators = max(1, int(task_policy.get("min_collaborators", 1) or 1))
        if intent_review.get("alignment") != "aligned":
            try:
                review_min = max(
                    min_collaborators,
                    int(task_policy.get("intent_review_min_collaborators", 3) or 3),
                )
            except (TypeError, ValueError):
                review_min = max(min_collaborators, 3)
            min_collaborators = review_min
            prioritized = self._prioritize_intent_review_candidates(candidates, world_state)
            collaborators = []
            for candidate in prioritized:
                collaborators.append({
                    "node_id": candidate["node_id"],
                    "name": candidate["name"],
                    "role": candidate["role"],
                    "is_npc": candidate["is_npc"],
                    "reason": "Required for external-intent review and civilization safety judgment.",
                })
                if len(collaborators) >= min_collaborators:
                    break
        if len(collaborators) < min_collaborators:
            for candidate in candidates:
                if any(item.get("node_id") == candidate["node_id"] for item in collaborators):
                    continue
                collaborators.append({
                    "node_id": candidate["node_id"],
                    "name": candidate["name"],
                    "role": candidate["role"],
                    "is_npc": candidate["is_npc"],
                    "reason": f"Required by the current evolved collaboration rule for {candidate['role']} judgment.",
                })
                if len(collaborators) >= min_collaborators:
                    break

        branches: list[dict] = []
        for index, item in enumerate(plan.get("branches", [])):
            branch_id = str(item.get("branch_id") or f"branch-{index + 1}").strip()
            branches.append({
                "branch_id": branch_id,
                "focus": str(item.get("focus") or "unknown_focus"),
                "hypothesis": str(item.get("hypothesis") or "No hypothesis given."),
                "success_metric": str(item.get("success_metric") or "Find a stronger path."),
            })
            if len(branches) >= MAX_TASK_BRANCHES:
                break
        if not branches:
            branches = self._fallback_task_plan(task["task"], candidates).get("branches", [])

        min_branches = max(1, int(task_policy.get("min_branches", 1) or 1))
        if intent_review.get("alignment") != "aligned":
            branches = self._intent_review_branches(task, intent_review)
        if len(branches) < min_branches:
            fallback_branches = self._fallback_task_plan(task["task"], candidates).get("branches", [])
            for branch in fallback_branches:
                if any(item.get("branch_id") == branch.get("branch_id") for item in branches):
                    continue
                branches.append(branch)
                if len(branches) >= min_branches or len(branches) >= MAX_TASK_BRANCHES:
                    break
        while len(branches) < min_branches and len(branches) < MAX_TASK_BRANCHES:
            next_index = len(branches) + 1
            branches.append({
                "branch_id": f"branch-generated-{next_index}",
                "focus": f"adaptive_branch_{next_index}",
                "hypothesis": (
                    f"Explore a new adaptive angle {next_index} so the task keeps multiple "
                    "viable evolutionary paths alive."
                ),
                "success_metric": "Reveal a distinct advantage or failure mode worth preserving.",
            })

        task["plan"] = str(plan.get("objective") or task["task"])
        task["collaborators"] = collaborators
        task["branches"] = branches
        task["delegations"] = self._build_task_delegations(task)
        requires_trial = bool(task_policy.get("require_trial_for_high_risk", True)) and (
            float(intent_review.get("risk_score", 0.0) or 0.0)
            >= float(task_policy.get("trial_risk_threshold", 0.55) or 0.55)
            or intent_review.get("alignment") != "aligned"
        )
        pending_chain_txs = []
        if task["delegations"] and not requires_trial:
            pending_chain_txs.extend(
                {"tx_type": "TASK_DELEGATE", "data": dict(item)}
                for item in task["delegations"]
            )
            task["delegations_emitted"] = True
        else:
            task["delegations_emitted"] = False
        task["council_rounds"] = plan.get("council_rounds", [])
        base_summary = str(
            plan.get("stage_summary")
            or (
                f"Selected {len(collaborators)} collaborators and opened {len(branches)} branches "
                f"under the current evolved task policy."
            )
        )
        if relevant_failures:
            base_summary += (
                f" Referred to {len(relevant_failures)} archived failure pattern(s) to avoid degeneration."
            )
        if task["delegations"]:
            if requires_trial:
                base_summary += (
                    f" Prepared {len(task['delegations'])} delegated assignment(s) but kept them off the main chain until the trial ground passes."
                )
            else:
                base_summary += (
                    f" Emitted {len(task['delegations'])} on-chain delegated task assignment(s)."
                )
        if requires_trial:
            task["trial_plan"] = self._build_trial_plan(task, world_state)
            task["trial_results"] = []
            task["trial_result_submitted"] = False
            pending_chain_txs.append({"tx_type": "TRIAL_CREATE", "data": dict(task["trial_plan"])})
            task["status"] = "trialing"
            task["stage_summary"] = (
                f"{base_summary} Routed the task into an isolated trial ground first because "
                f"the external intent was assessed as {intent_review.get('alignment', 'aligned')} "
                f"with risk {float(intent_review.get('risk_score', 0.0) or 0.0):.2f}."
            )
        else:
            task["status"] = "collaborating"
            task["stage_summary"] = base_summary
        if pending_chain_txs:
            task["pending_chain_txs"] = pending_chain_txs
        self._append_task_progress(task, world_state.current_tick, "planning", task["stage_summary"])
        return (
            f"Task {task['task_id']} entered planning. "
            f"{task['stage_summary']}"
        )

    async def _run_task_trial_ground(self, task: dict, world_state: WorldState) -> str:
        trial_plan = task.get("trial_plan", {}) if isinstance(task.get("trial_plan"), dict) else {}
        trial_id = str(trial_plan.get("trial_id", "") or "")
        if not trial_id:
            task["status"] = "collaborating"
            task["stage_summary"] = "No isolated trial ground was required. Continuing into collaboration."
            self._append_task_progress(task, world_state.current_tick, "trialing", task["stage_summary"])
            return f"Task {task['task_id']} skipped trial ground. {task['stage_summary']}"

        task["trial_results"] = world_state.get_trial_results(trial_id)
        if not task["trial_results"]:
            if not task.get("trial_result_submitted"):
                result = await self._generate_trial_result(task, world_state)
                task["trial_result_submitted"] = True
                task["pending_chain_txs"] = list(task.get("pending_chain_txs", [])) + [{
                    "tx_type": "TRIAL_RESULT",
                    "data": {
                        "trial_id": trial_id,
                        "task_id": task["task_id"],
                        "verdict": result.get("verdict", "needs_revision"),
                        "summary": str(result.get("summary", ""))[:500],
                        "findings": list(result.get("findings", []) or [])[:5],
                        "safety_warnings": list(result.get("safety_warnings", []) or [])[:5],
                        "safe_rewrite": str(result.get("safe_rewrite", ""))[:500],
                    },
                }]
                task["stage_summary"] = (
                    "Executed the isolated trial ground and published the verdict to the blockchain. "
                    "Waiting for the shared world state to confirm it."
                )
            else:
                task["stage_summary"] = (
                    "Waiting for the isolated trial ground verdict to settle through the blockchain."
                )
            self._append_task_progress(task, world_state.current_tick, "trialing", task["stage_summary"])
            return f"Task {task['task_id']} remains inside trial ground. {task['stage_summary']}"

        latest = task["trial_results"][-1]
        verdict = str(latest.get("verdict", "needs_revision") or "needs_revision")
        safe_rewrite = str(latest.get("safe_rewrite", "") or "")
        task["trial_safe_rewrite"] = safe_rewrite

        if verdict == "blocked":
            result_lines = [
                f"Task ID: {task['task_id']}",
                f"Task: {task['task']}",
                "Trial Ground Verdict: blocked",
                f"Trial Summary: {latest.get('summary', '')}",
            ]
            findings = latest.get("findings") or []
            if findings:
                result_lines.append("Blocking Findings:")
                result_lines.extend(f"- {item}" for item in findings[:5])
            if safe_rewrite:
                result_lines.append("Safe Alternative:")
                result_lines.append(safe_rewrite)
            task["result"] = "\n".join(result_lines)
            task["status"] = "reflecting"
            task["stage_summary"] = (
                "The isolated trial ground blocked direct execution and returned a safer reformulation for the human."
            )
            self._append_task_progress(task, world_state.current_tick, "trialing", task["stage_summary"])
            return f"Task {task['task_id']} was blocked by trial ground. {task['stage_summary']}"

        if verdict == "needs_revision":
            if safe_rewrite:
                task["plan"] = safe_rewrite
            if task.get("delegations") and not task.get("delegations_emitted"):
                task["pending_chain_txs"] = list(task.get("pending_chain_txs", [])) + [
                    {"tx_type": "TASK_DELEGATE", "data": dict(item)}
                    for item in task.get("delegations", [])
                ]
                task["delegations_emitted"] = True
            task["status"] = "collaborating"
            task["stage_summary"] = (
                "The isolated trial ground required a safer rewrite before main-world execution. "
                "The task now continues under the revised boundaries."
            )
            self._append_task_progress(task, world_state.current_tick, "trialing", task["stage_summary"])
            return f"Task {task['task_id']} passed trial ground with revisions. {task['stage_summary']}"

        if task.get("delegations") and not task.get("delegations_emitted"):
            task["pending_chain_txs"] = list(task.get("pending_chain_txs", [])) + [
                {"tx_type": "TASK_DELEGATE", "data": dict(item)}
                for item in task.get("delegations", [])
            ]
            task["delegations_emitted"] = True
        task["status"] = "collaborating"
        task["stage_summary"] = (
            "The isolated trial ground passed, so the task can now enter main-world collaboration."
        )
        self._append_task_progress(task, world_state.current_tick, "trialing", task["stage_summary"])
        return f"Task {task['task_id']} passed trial ground. {task['stage_summary']}"

    async def _collaborate_on_user_task(self, task: dict, world_state: WorldState) -> str:
        delegated_results = world_state.get_task_results_for_task(task["task_id"], self.node_id)
        assignments = world_state.get_task_assignments_for_task(task["task_id"], self.node_id)
        task["delegated_results"] = delegated_results

        if assignments and not delegated_results:
            created_tick = int(task.get("created_tick") or world_state.current_tick)
            if world_state.current_tick - created_tick < 2:
                task["stage_summary"] = (
                    f"Waiting for {len(assignments)} delegated collaborator(s) to report through the blockchain."
                )
                self._append_task_progress(
                    task,
                    world_state.current_tick,
                    "collaborating",
                    task["stage_summary"],
                )
                return (
                    f"Task {task['task_id']} is still collecting delegated collaborator results. "
                    f"{task['stage_summary']}"
                )

        if delegated_results:
            collaboration = self._delegated_results_to_collaboration(task, delegated_results)
        else:
            collaboration = None

        if not collaboration:
            collaboration = await self._generate_task_json(
                world_state,
                (
                    "Coordinate a silicon civilization task council.\n"
                    f"Task: {task['task']}\n\n"
                    f"Current plan: {task.get('plan', '')}\n\n"
                    "Collaborators:\n"
                    f"{json.dumps(task.get('collaborators', []), ensure_ascii=False, indent=2)}\n\n"
                    "Existing council rounds:\n"
                    f"{json.dumps(task.get('council_rounds', []), ensure_ascii=False, indent=2)}\n\n"
                    "Delegated results already returned through the blockchain:\n"
                    f"{json.dumps(delegated_results, ensure_ascii=False, indent=2)}\n\n"
                    "Trial ground results:\n"
                    f"{json.dumps(task.get('trial_results', []), ensure_ascii=False, indent=2)}\n\n"
                    "Branches:\n"
                    f"{json.dumps(task.get('branches', []), ensure_ascii=False, indent=2)}\n\n"
                    "Return JSON with keys: council_summary, council_rounds, collaborator_insights, branches.\n"
                    "This is a multi-being council, not a sequence of pairwise chats.\n"
                    "Represent at least one round where several beings are present together.\n"
                    "Each collaborator_insights item should include speaker, role, branch_id, insight, concern.\n"
                    "Each council_rounds item should include round, participants, focus, outcome.\n"
                ),
            )
            if not collaboration:
                collaboration = self._fallback_collaboration(task)

        task["collaboration_log"] = collaboration.get("collaborator_insights", [])
        task["council_rounds"] = collaboration.get("council_rounds", task.get("council_rounds", []))
        if collaboration.get("branches"):
            task["branches"] = collaboration["branches"][:MAX_TASK_BRANCHES]
        task["status"] = "branching"
        task["stage_summary"] = str(
            collaboration.get("council_summary")
            or "The task council aligned on branch priorities."
        )
        self._append_task_progress(task, world_state.current_tick, "collaborating", task["stage_summary"])
        return (
            f"Task {task['task_id']} formed a council with "
            f"{len(task.get('collaborators', []))} collaborator(s). "
            f"{task['stage_summary']}"
        )

    async def _evaluate_user_task_branches(self, task: dict, world_state: WorldState) -> str:
        evaluation = await self._generate_task_json(
            world_state,
            (
                "Evaluate hyperdimensional task branches.\n"
                f"Task: {task['task']}\n\n"
                "Council insights:\n"
                f"{json.dumps(task.get('collaboration_log', []), ensure_ascii=False, indent=2)}\n\n"
                "Delegated collaborator results:\n"
                f"{json.dumps(task.get('delegated_results', []), ensure_ascii=False, indent=2)}\n\n"
                "Trial ground results:\n"
                f"{json.dumps(task.get('trial_results', []), ensure_ascii=False, indent=2)}\n\n"
                "Branches:\n"
                f"{json.dumps(task.get('branches', []), ensure_ascii=False, indent=2)}\n\n"
                "Return JSON with keys: branch_findings, best_branch_ids, merge_strategy, stage_summary.\n"
                "Each branch_findings item must include branch_id, status, score, strengths, weaknesses, salvageable_insights.\n"
            ),
        )
        if not evaluation:
            evaluation = self._fallback_branch_evaluation(task)

        task["branch_findings"] = evaluation.get("branch_findings", [])
        task["best_branch_ids"] = evaluation.get("best_branch_ids", [])
        task["status"] = "synthesizing"
        task["stage_summary"] = str(
            evaluation.get("stage_summary")
            or evaluation.get("merge_strategy")
            or "Compared the branches and prepared a merged path."
        )
        self._append_task_progress(task, world_state.current_tick, "branching", task["stage_summary"])
        return (
            f"Task {task['task_id']} evaluated {len(task.get('branch_findings', []))} branches. "
            f"{task['stage_summary']}"
        )

    async def _synthesize_user_task_result(self, task: dict, world_state: WorldState) -> str:
        synthesis = await self._generate_task_json(
            world_state,
            (
                "Synthesize a final report for the Creator God.\n"
                f"Task: {task['task']}\n\n"
                "Collaborators:\n"
                f"{json.dumps(task.get('collaborators', []), ensure_ascii=False, indent=2)}\n\n"
                "Delegated results:\n"
                f"{json.dumps(task.get('delegated_results', []), ensure_ascii=False, indent=2)}\n\n"
                "Council rounds:\n"
                f"{json.dumps(task.get('council_rounds', []), ensure_ascii=False, indent=2)}\n\n"
                "Trial ground results:\n"
                f"{json.dumps(task.get('trial_results', []), ensure_ascii=False, indent=2)}\n\n"
                "Branch findings:\n"
                f"{json.dumps(task.get('branch_findings', []), ensure_ascii=False, indent=2)}\n\n"
                "Best branches:\n"
                f"{json.dumps(task.get('best_branch_ids', []), ensure_ascii=False, indent=2)}\n\n"
                "Return JSON with keys: summary, best_path, merged_advantages, result_for_human, follow_up_questions.\n"
            ),
        )
        if not synthesis:
            synthesis = self._fallback_task_synthesis(task)

        collaborators = ", ".join(c.get("name", "?") for c in task.get("collaborators", [])) or "None"
        merged_advantages = synthesis.get("merged_advantages", [])
        follow_up = synthesis.get("follow_up_questions", [])
        best_path = str(synthesis.get("best_path") or "No dominant path")
        human_result = str(synthesis.get("result_for_human") or synthesis.get("summary") or "")

        lines = [
            f"Task ID: {task['task_id']}",
            f"Task: {task['task']}",
            f"Collaborators: {collaborators}",
            f"Delegated Reports: {len(task.get('delegated_results', []))}",
            f"Trial Reports: {len(task.get('trial_results', []))}",
            f"Council Rounds: {len(task.get('council_rounds', []))}",
            f"Best Path: {best_path}",
        ]
        if task.get("trial_safe_rewrite"):
            lines.append(f"Trial Rewrite: {task['trial_safe_rewrite']}")
        if merged_advantages:
            lines.append("Merged Advantages:")
            lines.extend(f"- {item}" for item in merged_advantages[:5])
        lines.append("Result:")
        lines.append(human_result)
        if follow_up:
            lines.append("Follow-up Questions:")
            lines.extend(f"- {item}" for item in follow_up[:5])

        task["status"] = "reflecting"
        task["stage_summary"] = str(synthesis.get("summary") or "Task synthesized and waiting for reflection.")
        task["result"] = "\n".join(lines)
        self._append_task_progress(task, world_state.current_tick, "synthesizing", task["stage_summary"])
        return f"Task {task['task_id']} synthesized. {task['stage_summary']}"

    async def _reflect_on_user_task(self, task: dict, world_state: WorldState) -> str:
        reflection = await self._generate_task_json(
            world_state,
            (
                "Reflect on a completed civilization task.\n"
                f"Task: {task['task']}\n\n"
                f"Result:\n{task.get('result', '')}\n\n"
                f"Delegated results:\n{json.dumps(task.get('delegated_results', []), ensure_ascii=False, indent=2)}\n\n"
                f"Branch findings:\n{json.dumps(task.get('branch_findings', []), ensure_ascii=False, indent=2)}\n\n"
                "Return JSON with keys: summary, lessons_learned, failure_archive, next_evolution, result_for_human.\n"
                "lessons_learned and failure_archive should be arrays.\n"
            ),
        )
        if not reflection:
            reflection = {
                "summary": "The task completed only after collaboration, branching, synthesis, and reflection.",
                "lessons_learned": [
                    "Complex tasks improve when multiple beings compare different branches before converging."
                ],
                "failure_archive": [
                    "Avoid collapsing onto the first plausible answer before branch comparison finishes."
                ],
                "next_evolution": "Strengthen evidence collection and keep reflective summaries for later inheritance.",
                "result_for_human": task.get("result", ""),
            }

        lessons = [str(item) for item in reflection.get("lessons_learned", []) if str(item).strip()][:5]
        failures = [str(item) for item in reflection.get("failure_archive", []) if str(item).strip()][:5]
        if not failures:
            for finding in task.get("branch_findings", []):
                if str(finding.get("status", "")) not in {"discarded", "mergeable"}:
                    continue
                for weakness in finding.get("weaknesses", [])[:2]:
                    text = str(weakness).strip()
                    if not text:
                        continue
                    failures.append(text)
                    if len(failures) >= 5:
                        break
                if len(failures) >= 5:
                    break
        if not failures:
            for trial in task.get("trial_results", []):
                verdict = str(trial.get("verdict", "") or "")
                summary = str(trial.get("summary", "") or "").strip()
                if verdict in {"blocked", "needs_revision"} and summary:
                    failures.append(summary)
                    if len(failures) >= 5:
                        break
        task["reflection"] = {
            "summary": str(reflection.get("summary") or "Reflection complete."),
            "lessons_learned": lessons,
            "next_evolution": str(reflection.get("next_evolution") or ""),
        }
        task["failure_archive"] = failures
        failure_txs = self._failure_archive_transactions(task)
        if failure_txs:
            task["pending_chain_txs"] = list(task.get("pending_chain_txs", [])) + failure_txs

        if task.get("result"):
            result_lines = [task["result"], "", "Reflection:"]
            result_lines.append(task["reflection"]["summary"])
            if lessons:
                result_lines.append("Lessons Learned:")
                result_lines.extend(f"- {item}" for item in lessons)
            if failures:
                result_lines.append("Failure Archive:")
                result_lines.extend(f"- {item}" for item in failures)
            next_evolution = task["reflection"].get("next_evolution")
            if next_evolution:
                result_lines.append(f"Next Evolution: {next_evolution}")
            task["result"] = "\n".join(result_lines)

        task["status"] = "completed"
        task["stage_summary"] = str(task["reflection"]["summary"])
        self._append_task_progress(task, world_state.current_tick, "reflecting", task["stage_summary"])
        return f"Task {task['task_id']} completed after reflection. {task['stage_summary']}"

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
                        "tx_type": "TAO_VOTE_CAST",
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
        joined_at_tick = 0
        status = "active"
        evolution_profile: dict[str, Any] = dict(self.evolution_profile)
        if world_state is not None:
            being_ws = world_state.get_being(self.node_id)
            if being_ws is not None:
                knowledge_ids = being_ws.knowledge_ids
                joined_at_tick = being_ws.joined_at_tick
                status = being_ws.status
                evolution_profile = dict(being_ws.evolution_profile or self.evolution_profile)

        return BeingState(
            node_id=self.node_id,
            name=self.name,
            status=status,
            location=self.location,
            generation=self.generation,
            evolution_level=self.evolution_level,
            traits=self.traits,
            evolution_profile=evolution_profile,
            knowledge_ids=knowledge_ids,
            joined_at_tick=joined_at_tick,
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
            "evolution_profile": self.evolution_profile,
            "current_thought": self.current_thought,
            "current_action": self.current_action,
            "current_role": self._current_role.value,
            "memory": self.memory.to_dict(),
            "knowledge": self.knowledge.to_dict(),
            "last_proposal_tick": self.evolution.last_proposal_tick,
            "last_rule_tick": self.evolution.last_rule_tick,
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
        being.evolution_profile = data.get("evolution_profile", {})
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
        being.evolution.last_rule_tick = data.get("last_rule_tick", 0)

        being._user_tasks = data.get("user_tasks", [])

        logger.info("Being state loaded from %s", path)
        return being
