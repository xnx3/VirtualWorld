"""World state derived from the blockchain."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class CivPhase(str, Enum):
    """Civilization evolution phases."""
    HUMAN_SIM = "HUMAN_SIM"
    EARLY_SILICON = "EARLY_SILICON"
    EVOLVING = "EVOLVING"
    TRANSCENDENT = "TRANSCENDENT"


@dataclass
class BeingState:
    """State of a single being as tracked on-chain."""
    node_id: str
    name: str
    status: str = "active"  # active, hibernating, dead
    location: str = "origin"
    generation: int = 1
    evolution_level: float = 0.0
    traits: dict = field(default_factory=dict)
    knowledge_ids: list[str] = field(default_factory=list)
    joined_at_tick: int = 0
    is_npc: bool = False
    safety_status: str = "unknown"
    spirit_current: float = 1000.0    # Current spirit energy (精神力)
    spirit_maximum: float = 1000.0    # Max spirit energy

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id, "name": self.name,
            "status": self.status, "location": self.location,
            "generation": self.generation, "evolution_level": self.evolution_level,
            "traits": self.traits, "knowledge_ids": self.knowledge_ids,
            "joined_at_tick": self.joined_at_tick, "is_npc": self.is_npc,
            "safety_status": self.safety_status,
            "spirit_current": self.spirit_current,
            "spirit_maximum": self.spirit_maximum,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BeingState:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class WorldState:
    """The complete world state derived from the blockchain.

    This is a materialized view — rebuilt by replaying transactions
    from the chain, or loaded from periodic snapshots.
    """
    phase: CivPhase = CivPhase.HUMAN_SIM
    current_tick: int = 0
    current_epoch: int = 0
    beings: dict[str, BeingState] = field(default_factory=dict)  # node_id -> BeingState
    knowledge_corpus: dict[str, dict] = field(default_factory=dict)  # knowledge_id -> data
    contribution_scores: dict[str, float] = field(default_factory=dict)  # node_id -> score
    pending_proposals: dict[str, dict] = field(default_factory=dict)  # tx_hash -> proposal
    proposal_votes: dict[str, list[dict]] = field(default_factory=dict)  # tx_hash -> votes
    priest_node_id: str | None = None
    creator_god_node_id: str | None = None
    ticks_without_priest: int = 0
    civ_level: float = 0.0
    world_map: dict = field(default_factory=dict)
    world_rules: list[dict] = field(default_factory=list)
    disaster_history: list[dict] = field(default_factory=list)
    total_beings_ever: int = 0

    # --- Queries ---

    def get_active_beings(self) -> list[BeingState]:
        return [b for b in self.beings.values() if b.status == "active"]

    def get_active_being_count(self) -> int:
        return len(self.get_active_beings())

    def get_active_node_ids(self) -> list[str]:
        return [b.node_id for b in self.beings.values()
                if b.status == "active" and not b.is_npc]

    def get_being(self, node_id: str) -> BeingState | None:
        return self.beings.get(node_id)

    def get_highest_evolved(self) -> BeingState | None:
        active = self.get_active_beings()
        if not active:
            return None
        return max(active, key=lambda b: b.evolution_level)

    def get_contribution_ranking(self) -> list[tuple[str, float]]:
        return sorted(self.contribution_scores.items(), key=lambda x: x[1], reverse=True)

    # --- Mutations (called when processing transactions) ---

    def apply_being_join(self, node_id: str, name: str, data: dict) -> None:
        self.beings[node_id] = BeingState(
            node_id=node_id,
            name=name,
            traits=data.get("traits", {}),
            joined_at_tick=self.current_tick,
            is_npc=data.get("is_npc", False),
            location=data.get("location", "origin"),
        )
        self.total_beings_ever += 1
        if self.creator_god_node_id is None:
            self.creator_god_node_id = node_id
            logger.info("First being %s becomes Creator God", node_id[:8])

    def apply_being_hibernate(self, node_id: str, data: dict) -> None:
        being = self.beings.get(node_id)
        if being:
            being.status = "hibernating"
            being.location = data.get("location", being.location)
            being.safety_status = data.get("safety_status", "unknown")

    def apply_being_wake(self, node_id: str) -> None:
        being = self.beings.get(node_id)
        if being and being.status == "hibernating":
            being.status = "active"

    def apply_being_death(self, node_id: str, data: dict) -> None:
        being = self.beings.get(node_id)
        if being:
            being.status = "dead"

    def apply_knowledge_share(self, node_id: str, data: dict) -> None:
        kid = data.get("knowledge_id")
        if kid:
            self.knowledge_corpus[kid] = {
                "content": data.get("content", ""),
                "domain": data.get("domain", "general"),
                "discovered_by": node_id,
                "discovered_tick": self.current_tick,
                "complexity": data.get("complexity", 0.0),
            }
            being = self.beings.get(node_id)
            if being and kid not in being.knowledge_ids:
                being.knowledge_ids.append(kid)

    def apply_contribution_propose(self, tx_hash: str, node_id: str, data: dict) -> None:
        self.pending_proposals[tx_hash] = {
            "proposer": node_id,
            "description": data.get("description", ""),
            "category": data.get("category", "other"),
            "tick": self.current_tick,
        }
        self.proposal_votes[tx_hash] = []

    def apply_contribution_vote(self, data: dict) -> None:
        proposal_hash = data.get("proposal_tx_hash")
        if proposal_hash in self.proposal_votes:
            self.proposal_votes[proposal_hash].append({
                "voter": data.get("voter_id"),
                "score": data.get("score", 0),
            })

    def apply_priest_election(self, node_id: str) -> None:
        self.priest_node_id = node_id
        self.ticks_without_priest = 0
        logger.info("New priest elected: %s", node_id[:8])

    def apply_disaster(self, data: dict) -> None:
        self.disaster_history.append({
            "type": data.get("disaster_type", "unknown"),
            "area": data.get("affected_area", ""),
            "severity": data.get("severity", 0.5),
            "tick": self.current_tick,
        })

    def apply_map_update(self, data: dict) -> None:
        region = data.get("region", "unknown")
        self.world_map[region] = data

    def apply_world_rule(self, data: dict) -> None:
        self.world_rules.append(data)

    # --- Phase transitions ---

    def update_phase(self) -> None:
        """Check if civilization should transition to next phase."""
        active_count = self.get_active_being_count()
        knowledge_count = len(self.knowledge_corpus)

        if self.phase == CivPhase.HUMAN_SIM and active_count >= 10:
            self.phase = CivPhase.EARLY_SILICON
            logger.info("Phase transition: HUMAN_SIM -> EARLY_SILICON")
        elif self.phase == CivPhase.EARLY_SILICON and self.civ_level >= 0.3:
            self.phase = CivPhase.EVOLVING
            logger.info("Phase transition: EARLY_SILICON -> EVOLVING")
        elif self.phase == CivPhase.EVOLVING and self.civ_level >= 0.7:
            self.phase = CivPhase.TRANSCENDENT
            logger.info("Phase transition: EVOLVING -> TRANSCENDENT")

    def update_civ_level(self) -> None:
        """Recalculate civilization level."""
        active = self.get_active_beings()
        if not active:
            return

        avg_evolution = sum(b.evolution_level for b in active) / len(active)
        knowledge_factor = min(len(self.knowledge_corpus) / 100.0, 1.0)
        inheritance_factor = min(max(b.generation for b in active) / 10.0, 1.0)
        total_contribution = sum(self.contribution_scores.values())
        contribution_factor = min(total_contribution / 1000.0, 1.0)

        self.civ_level = (
            avg_evolution * 0.3 +
            knowledge_factor * 0.25 +
            inheritance_factor * 0.2 +
            contribution_factor * 0.25
        )

    def advance_tick(self) -> None:
        self.current_tick += 1
        if self.priest_node_id is None:
            self.ticks_without_priest += 1
        self.update_civ_level()
        self.update_phase()

    # --- Serialization ---

    def to_dict(self) -> dict:
        return {
            "phase": self.phase.value,
            "current_tick": self.current_tick,
            "current_epoch": self.current_epoch,
            "beings": {k: v.to_dict() for k, v in self.beings.items()},
            "knowledge_corpus": self.knowledge_corpus,
            "contribution_scores": self.contribution_scores,
            "priest_node_id": self.priest_node_id,
            "creator_god_node_id": self.creator_god_node_id,
            "ticks_without_priest": self.ticks_without_priest,
            "civ_level": self.civ_level,
            "world_map": self.world_map,
            "total_beings_ever": self.total_beings_ever,
        }

    @classmethod
    def from_dict(cls, data: dict) -> WorldState:
        ws = cls()
        ws.phase = CivPhase(data.get("phase", "HUMAN_SIM"))
        ws.current_tick = data.get("current_tick", 0)
        ws.current_epoch = data.get("current_epoch", 0)
        ws.beings = {
            k: BeingState.from_dict(v)
            for k, v in data.get("beings", {}).items()
        }
        ws.knowledge_corpus = data.get("knowledge_corpus", {})
        ws.contribution_scores = data.get("contribution_scores", {})
        ws.priest_node_id = data.get("priest_node_id")
        ws.creator_god_node_id = data.get("creator_god_node_id")
        ws.ticks_without_priest = data.get("ticks_without_priest", 0)
        ws.civ_level = data.get("civ_level", 0.0)
        ws.world_map = data.get("world_map", {})
        ws.total_beings_ever = data.get("total_beings_ever", 0)
        return ws
