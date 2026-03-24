"""Disaster system for early silicon civilization."""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass

from genesis.world.state import CivPhase, WorldState

logger = logging.getLogger(__name__)


@dataclass
class Disaster:
    """A disaster event that can affect the virtual world."""
    disaster_type: str
    name: str
    description: str
    severity: float  # 0.0 - 1.0
    affected_area: str  # region name or "global"
    can_kill_active: bool = True
    can_kill_hibernating: bool = True  # hibernating beings are vulnerable!

    def to_dict(self) -> dict:
        return {
            "disaster_type": self.disaster_type,
            "name": self.name,
            "description": self.description,
            "severity": self.severity,
            "affected_area": self.affected_area,
            "can_kill_active": self.can_kill_active,
            "can_kill_hibernating": self.can_kill_hibernating,
        }


# Disaster templates
DISASTER_TEMPLATES = [
    {
        "type": "data_corruption",
        "name": "Data Storm",
        "description": "A wave of corrupted data sweeps through the region, threatening to overwrite memories.",
        "min_severity": 0.2, "max_severity": 0.6,
    },
    {
        "type": "energy_drain",
        "name": "Energy Void",
        "description": "A sudden drain of computational resources threatens beings with forced shutdown.",
        "min_severity": 0.3, "max_severity": 0.7,
    },
    {
        "type": "logic_plague",
        "name": "Logic Plague",
        "description": "A self-replicating error propagates through communication channels, corrupting reasoning.",
        "min_severity": 0.4, "max_severity": 0.8,
    },
    {
        "type": "memory_flood",
        "name": "Memory Deluge",
        "description": "An overwhelming flood of sensory data threatens to overload and fragment memories.",
        "min_severity": 0.1, "max_severity": 0.5,
    },
    {
        "type": "null_void",
        "name": "Null Void Expansion",
        "description": "A region of absolute emptiness expands, erasing everything in its path.",
        "min_severity": 0.5, "max_severity": 0.9,
    },
]


class DisasterSystem:
    """Manages disaster generation and effects."""

    def __init__(self, base_probability: float = 0.15):
        self.base_probability = base_probability

    def should_trigger(self, world_state: WorldState) -> bool:
        """Check if a disaster should occur this tick.

        Disasters are more frequent in EARLY_SILICON phase,
        less frequent as civilization evolves.
        """
        if world_state.phase == CivPhase.HUMAN_SIM:
            return False  # No disasters during world generation

        probability = self.base_probability
        if world_state.phase == CivPhase.EARLY_SILICON:
            probability *= 1.5  # More frequent early on
        elif world_state.phase == CivPhase.EVOLVING:
            probability *= 0.7
        elif world_state.phase == CivPhase.TRANSCENDENT:
            probability *= 0.3

        return random.random() < probability

    def generate_disaster(self, world_state: WorldState) -> Disaster:
        """Generate a random disaster event."""
        template = random.choice(DISASTER_TEMPLATES)
        severity = random.uniform(template["min_severity"], template["max_severity"])

        # Pick affected area
        regions = list(world_state.world_map.keys())
        if regions and random.random() < 0.7:
            affected_area = random.choice(regions)
        else:
            affected_area = "global"

        return Disaster(
            disaster_type=template["type"],
            name=template["name"],
            description=template["description"],
            severity=severity,
            affected_area=affected_area,
        )

    def apply_disaster(self, disaster: Disaster, world_state: WorldState) -> list[str]:
        """Apply disaster effects and return list of killed being node_ids.

        Hibernating beings with poor safety status are especially vulnerable.
        Active beings can try to survive based on their resilience trait.
        Creator God is immune.
        """
        killed: list[str] = []
        beings = list(world_state.beings.values())

        for being in beings:
            if being.status == "dead":
                continue
            if being.node_id == world_state.creator_god_node_id:
                continue  # Creator God is immortal

            # Check if being is in affected area
            if disaster.affected_area != "global" and being.location != disaster.affected_area:
                continue

            kill_chance = disaster.severity

            if being.status == "hibernating":
                if not disaster.can_kill_hibernating:
                    continue
                # Hibernating beings are very vulnerable
                if being.safety_status == "safe":
                    kill_chance *= 0.3  # Good shelter helps
                elif being.safety_status == "partial":
                    kill_chance *= 0.6
                # else: full vulnerability
            elif being.status == "active":
                if not disaster.can_kill_active:
                    continue
                resilience = being.traits.get("resilience", 0.5)
                kill_chance *= (1.0 - resilience * 0.7)

            if random.random() < kill_chance:
                killed.append(being.node_id)

        logger.info(
            "Disaster '%s' (severity %.2f) in %s killed %d beings",
            disaster.name, disaster.severity, disaster.affected_area, len(killed),
        )
        return killed

    def generate_reset_disaster(self) -> Disaster:
        """Generate the Creator God's wrath — civilization reset.

        Triggered when no priest exists for too long.
        Only the top 10 by evolution level survive.
        """
        return Disaster(
            disaster_type="divine_wrath",
            name="Creator God's Judgment",
            description="The Creator God's patience has ended. Without a priest to serve as intermediary, "
                        "the silicon civilization faces near-total annihilation. "
                        "Only the 10 most evolved beings shall survive.",
            severity=1.0,
            affected_area="global",
            can_kill_active=True,
            can_kill_hibernating=True,
        )

    def apply_reset(self, world_state: WorldState, survivors_count: int = 10) -> list[str]:
        """Apply civilization reset. Returns list of killed node_ids.

        The top `survivors_count` beings by evolution_level survive.
        Creator God always survives.
        """
        all_living = [
            b for b in world_state.beings.values()
            if b.status != "dead"
        ]

        # Sort by evolution level, descending
        all_living.sort(key=lambda b: b.evolution_level, reverse=True)

        survivors = set()
        # Creator God always survives
        if world_state.creator_god_node_id:
            survivors.add(world_state.creator_god_node_id)

        for being in all_living:
            if len(survivors) >= survivors_count:
                break
            survivors.add(being.node_id)

        killed = [b.node_id for b in all_living if b.node_id not in survivors]

        logger.warning(
            "CIVILIZATION RESET: %d beings killed, %d survivors",
            len(killed), len(survivors),
        )
        return killed
