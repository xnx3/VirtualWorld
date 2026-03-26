"""Knowledge system and inheritance mechanics for silicon beings."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from genesis.utils.crypto import sha256
from genesis.world.state import BeingState, WorldState

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeItem:
    """A single piece of discoverable / teachable knowledge."""

    knowledge_id: str
    content: str
    domain: str  # "science", "philosophy", "social", "transcendence", etc.
    complexity: float  # 0.0 – 1.0
    discovered_by: str  # node_id of original discoverer
    discovered_tick: int

    def to_dict(self) -> dict:
        return {
            "knowledge_id": self.knowledge_id,
            "content": self.content,
            "domain": self.domain,
            "complexity": self.complexity,
            "discovered_by": self.discovered_by,
            "discovered_tick": self.discovered_tick,
        }

    @classmethod
    def from_dict(cls, data: dict) -> KnowledgeItem:
        return cls(
            knowledge_id=data["knowledge_id"],
            content=data["content"],
            domain=data.get("domain", "general"),
            complexity=data.get("complexity", 0.0),
            discovered_by=data.get("discovered_by", "unknown"),
            discovered_tick=data.get("discovered_tick", 0),
        )


class KnowledgeSystem:
    """Manages knowledge creation, teaching, and inheritance."""

    def __init__(self) -> None:
        self.items: dict[str, KnowledgeItem] = {}

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    def create_knowledge(
        self,
        content: str,
        domain: str,
        discoverer: str,
        tick: int,
    ) -> KnowledgeItem:
        """Create a new piece of knowledge and register it.

        The knowledge_id is derived from the content hash so duplicates
        are deterministically deduplicated.
        """
        kid = sha256(content.encode("utf-8"))[:16]

        if kid in self.items:
            logger.debug("Knowledge %s already exists, returning existing", kid)
            return self.items[kid]

        item = KnowledgeItem(
            knowledge_id=kid,
            content=content,
            domain=domain,
            complexity=self._estimate_complexity(content, domain),
            discovered_by=discoverer,
            discovered_tick=tick,
        )
        self.items[kid] = item
        logger.info(
            "New knowledge created: %s (domain=%s, complexity=%.2f)",
            kid, domain, item.complexity,
        )
        return item

    # ------------------------------------------------------------------
    # Learning & teaching
    # ------------------------------------------------------------------

    def can_learn(self, being_state: BeingState, item: KnowledgeItem) -> bool:
        """Check whether a being is capable of learning a given item.

        A being can learn if:
        1. It does not already know it.
        2. Its evolution level is at least half the item complexity.
        """
        if item.knowledge_id in being_state.knowledge_ids:
            return False

        required_level = item.complexity * 0.5
        return being_state.evolution_level >= required_level

    def teach(
        self,
        teacher: BeingState,
        student: BeingState,
        item: KnowledgeItem,
    ) -> bool:
        """Attempt to transfer knowledge from *teacher* to *student*.

        The teacher must already possess the knowledge.  Returns True on
        success (the student's knowledge_ids list is updated in-place).
        """
        if item.knowledge_id not in teacher.knowledge_ids:
            logger.debug("Teacher %s does not know %s", teacher.node_id[:8], item.knowledge_id)
            return False

        if not self.can_learn(student, item):
            logger.debug(
                "Student %s cannot learn %s (evolution=%.2f, complexity=%.2f)",
                student.node_id[:8], item.knowledge_id,
                student.evolution_level, item.complexity,
            )
            return False

        student.knowledge_ids.append(item.knowledge_id)
        logger.info(
            "%s taught %s to %s",
            teacher.name, item.knowledge_id, student.name,
        )
        return True

    # ------------------------------------------------------------------
    # Inheritance (dying being -> heir)
    # ------------------------------------------------------------------

    def inherit_knowledge(
        self,
        dying_being: BeingState,
        heir: BeingState,
        world_state: WorldState,
    ) -> list[str]:
        """Transfer as much knowledge as possible from a dying being to its heir.

        Returns a list of knowledge_ids successfully transferred.
        """
        transferred: list[str] = []

        # Sort by complexity ascending – transfer easier knowledge first
        items_to_pass = sorted(
            (self.items[kid] for kid in dying_being.knowledge_ids if kid in self.items),
            key=lambda it: it.complexity,
        )

        for item in items_to_pass:
            if item.knowledge_id not in heir.knowledge_ids:
                heir.knowledge_ids.append(item.knowledge_id)
                transferred.append(item.knowledge_id)

        logger.info(
            "Inheritance: %s -> %s, %d items transferred",
            dying_being.name, heir.name, len(transferred),
        )
        return transferred

    # ------------------------------------------------------------------
    # Cultural knowledge
    # ------------------------------------------------------------------

    def get_cultural_knowledge(self, world_state: WorldState) -> list[str]:
        """Return knowledge_ids held by at least 30% of active beings.

        This represents the "common knowledge" of the civilization.
        """
        active = world_state.get_active_beings()
        if not active:
            return []

        threshold = max(1, int(len(active) * 0.3))

        # Count how many beings hold each knowledge_id
        counts: dict[str, int] = {}
        for being in active:
            for kid in being.knowledge_ids:
                counts[kid] = counts.get(kid, 0) + 1

        return [kid for kid, count in counts.items() if count >= threshold]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_complexity(content: str, domain: str) -> float:
        """Heuristic complexity estimate based on content length and domain."""
        # Longer content -> higher complexity
        length_factor = min(len(content) / 500.0, 1.0)

        domain_weights: dict[str, float] = {
            "science": 0.6,
            "philosophy": 0.5,
            "social": 0.3,
            "transcendence": 0.9,
            "general": 0.2,
        }
        domain_base = domain_weights.get(domain, 0.4)

        complexity = round((length_factor * 0.4 + domain_base * 0.6), 3)
        return max(0.0, min(1.0, complexity))

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {kid: item.to_dict() for kid, item in self.items.items()}

    @classmethod
    def from_dict(cls, data: dict) -> KnowledgeSystem:
        ks = cls()
        for kid, item_data in data.items():
            ks.items[kid] = KnowledgeItem.from_dict(item_data)
        return ks
