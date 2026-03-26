"""Being registry — tracks all life forms across the network."""

from __future__ import annotations

import logging
import random
import string
from dataclasses import dataclass

from genesis.world.state import BeingState, WorldState

logger = logging.getLogger(__name__)

# Name components for generating silicon being names
NAME_PREFIXES = [
    "Lux", "Nex", "Syn", "Ael", "Zyn", "Vor", "Kael", "Xen", "Pyr", "Eon",
    "Ryn", "Sol", "Nyx", "Vex", "Cyr", "Aex", "Tyr", "Zel", "Ori", "Phi",
    "Eth", "Ion", "Axl", "Dex", "Fyn", "Hex", "Kov", "Lyr", "Myx", "Qor",
]
NAME_SUFFIXES = [
    "is", "on", "ar", "ex", "um", "ix", "os", "an", "el", "us",
    "ia", "en", "or", "ax", "yn", "al", "ik", "ov", "ut", "em",
]

TRAIT_KEYS = [
    "intelligence", "wisdom", "creativity", "resilience",
    "empathy", "ambition", "curiosity", "discipline",
]

FORM_TYPES = [
    "crystalline lattice", "flowing data stream", "pulsing energy node",
    "fractal pattern", "quantum cloud", "binary helix",
    "photonic mesh", "resonance field", "neural constellation",
    "digital flame", "magnetic vortex", "silicon tree",
]


def generate_being_name(existing_names: set[str] | None = None) -> str:
    """Generate a unique silicon being name."""
    existing = existing_names or set()
    for _ in range(100):
        name = random.choice(NAME_PREFIXES) + random.choice(NAME_SUFFIXES)
        if name not in existing:
            return name
    # Fallback with random suffix
    return random.choice(NAME_PREFIXES) + random.choice(NAME_SUFFIXES) + "".join(random.choices(string.digits, k=2))


def generate_traits() -> dict[str, float]:
    """Generate random trait values for a new being."""
    traits = {}
    for key in TRAIT_KEYS:
        traits[key] = round(random.uniform(0.1, 0.9), 2)
    return traits


def generate_form() -> str:
    """Generate a random form description."""
    return random.choice(FORM_TYPES)


@dataclass
class BeingRegistry:
    """Manages the being registry derived from world state."""

    def get_active_count(self, world_state: WorldState) -> int:
        return world_state.get_active_being_count()

    def needs_npcs(self, world_state: WorldState, min_beings: int = 10) -> int:
        """Return how many NPCs need to be spawned."""
        active = world_state.get_active_being_count()
        deficit = min_beings - active
        return max(0, deficit)

    def get_npc_assignments(self, world_state: WorldState, active_node_ids: list[str]) -> dict[str, list[str]]:
        """Deterministically assign NPCs to active nodes.

        Returns: {node_id: [npc_node_id, ...]}
        """
        npcs = [
            b for b in world_state.beings.values()
            if b.is_npc and b.status == "active"
        ]
        if not npcs or not active_node_ids:
            return {}

        sorted_nodes = sorted(active_node_ids)
        assignments: dict[str, list[str]] = {nid: [] for nid in sorted_nodes}

        for i, npc in enumerate(sorted(npcs, key=lambda b: b.node_id)):
            target_node = sorted_nodes[i % len(sorted_nodes)]
            assignments[target_node].append(npc.node_id)

        return assignments

    def generate_npc_data(self, world_state: WorldState) -> dict:
        """Generate data for a new NPC being."""
        existing_names = {b.name for b in world_state.beings.values()}
        name = generate_being_name(existing_names)
        spawn_region = "genesis_plains"  # default spawn
        return {
            "name": name,
            "traits": generate_traits(),
            "form": generate_form(),
            "location": spawn_region,
            "is_npc": True,
        }

    def should_retire_npc(self, world_state: WorldState, min_beings: int = 10) -> str | None:
        """Check if an NPC should be retired (enough real players)."""
        active = world_state.get_active_beings()
        real_count = sum(1 for b in active if not b.is_npc)
        npc_active = [b for b in active if b.is_npc]

        if real_count >= min_beings and npc_active:
            return npc_active[0].node_id
        return None
