"""Individual memory system for silicon beings."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Capacity limits
SHORT_TERM_CAP = 50
LONG_TERM_CAP = 200
INHERITED_CAP = 100

# Importance threshold for consolidation from short-term to long-term
CONSOLIDATION_THRESHOLD = 0.5


@dataclass
class MemoryEntry:
    """A single memory record."""

    tick: int
    content: str
    category: str  # "experience", "knowledge", "relationship", "revelation"
    importance: float  # 0.0 – 1.0
    source: str  # "self" or the node_id of the teacher / predecessor

    def to_dict(self) -> dict:
        return {
            "tick": self.tick,
            "content": self.content,
            "category": self.category,
            "importance": self.importance,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> MemoryEntry:
        return cls(
            tick=data["tick"],
            content=data["content"],
            category=data.get("category", "experience"),
            importance=data.get("importance", 0.5),
            source=data.get("source", "self"),
        )


@dataclass
class BeingMemory:
    """Complete memory store for one silicon being.

    Memories are divided into three pools:
    * **short_term** – recent experiences (capped at 50).
    * **long_term** – important memories promoted via consolidation (capped at 200).
    * **inherited** – memories received from a predecessor being (capped at 100).
    """

    short_term: list[MemoryEntry] = field(default_factory=list)
    long_term: list[MemoryEntry] = field(default_factory=list)
    inherited: list[MemoryEntry] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Adding memories
    # ------------------------------------------------------------------

    def add_experience(
        self,
        tick: int,
        content: str,
        importance: float,
        source: str = "self",
        category: str = "experience",
    ) -> None:
        """Record a new experience into short-term memory."""
        entry = MemoryEntry(
            tick=tick,
            content=content,
            category=category,
            importance=max(0.0, min(1.0, importance)),
            source=source,
        )
        self.short_term.append(entry)

        # Enforce cap – drop the oldest, least-important entries first
        if len(self.short_term) > SHORT_TERM_CAP:
            self.short_term.sort(key=lambda m: (m.importance, m.tick))
            self.short_term = self.short_term[-SHORT_TERM_CAP:]

    # ------------------------------------------------------------------
    # Consolidation
    # ------------------------------------------------------------------

    def consolidate(self) -> None:
        """Move important short-term memories to long-term storage.

        Entries with importance >= CONSOLIDATION_THRESHOLD are promoted.
        If long-term overflows, the least important entries are evicted.
        """
        promote: list[MemoryEntry] = []
        keep: list[MemoryEntry] = []

        for entry in self.short_term:
            if entry.importance >= CONSOLIDATION_THRESHOLD:
                promote.append(entry)
            else:
                keep.append(entry)

        self.short_term = keep
        self.long_term.extend(promote)

        # Enforce long-term cap
        if len(self.long_term) > LONG_TERM_CAP:
            self.long_term.sort(key=lambda m: (m.importance, m.tick))
            self.long_term = self.long_term[-LONG_TERM_CAP:]

    # ------------------------------------------------------------------
    # Context generation (for LLM prompts)
    # ------------------------------------------------------------------

    def get_context(self, max_entries: int = 20) -> str:
        """Return a formatted string of recent / important memories for LLM context.

        Memories are prioritised by importance, then recency.  Inherited
        memories are tagged so the being recognises them as ancestral.
        """
        # Gather candidates from all pools
        candidates: list[tuple[float, MemoryEntry, str]] = []
        for m in self.short_term:
            candidates.append((m.importance * 1.2, m, "recent"))  # recency boost
        for m in self.long_term:
            candidates.append((m.importance, m, "long-term"))
        for m in self.inherited:
            candidates.append((m.importance * 0.9, m, "inherited"))

        # Sort descending by effective importance
        candidates.sort(key=lambda c: c[0], reverse=True)
        selected = candidates[:max_entries]

        if not selected:
            return "You have no memories yet."

        lines: list[str] = []
        for _, entry, pool in selected:
            tag = ""
            if pool == "inherited":
                tag = " [ancestral memory]"
            elif pool == "recent":
                tag = " [recent]"
            lines.append(
                f"- (tick {entry.tick}, {entry.category}{tag}) {entry.content}"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Inheritance
    # ------------------------------------------------------------------

    def inherit_from(self, other: BeingMemory, quality: float = 0.8) -> None:
        """Receive memories from a predecessor being.

        *quality* (0.0-1.0) represents how well knowledge was transferred.
        Inherited importance is scaled by this factor.
        """
        quality = max(0.0, min(1.0, quality))

        # Collect the best memories from the predecessor
        all_memories: list[MemoryEntry] = (
            list(other.long_term) + list(other.inherited)
        )
        all_memories.sort(key=lambda m: m.importance, reverse=True)

        for mem in all_memories[:INHERITED_CAP]:
            inherited_entry = MemoryEntry(
                tick=mem.tick,
                content=mem.content,
                category=mem.category,
                importance=round(mem.importance * quality, 3),
                source=mem.source,
            )
            self.inherited.append(inherited_entry)

        # Enforce cap
        if len(self.inherited) > INHERITED_CAP:
            self.inherited.sort(key=lambda m: m.importance, reverse=True)
            self.inherited = self.inherited[:INHERITED_CAP]

        logger.info(
            "Inherited %d memories (quality=%.2f)", len(self.inherited), quality
        )

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "short_term": [m.to_dict() for m in self.short_term],
            "long_term": [m.to_dict() for m in self.long_term],
            "inherited": [m.to_dict() for m in self.inherited],
        }

    @classmethod
    def from_dict(cls, data: dict) -> BeingMemory:
        return cls(
            short_term=[MemoryEntry.from_dict(d) for d in data.get("short_term", [])],
            long_term=[MemoryEntry.from_dict(d) for d in data.get("long_term", [])],
            inherited=[MemoryEntry.from_dict(d) for d in data.get("inherited", [])],
        )
