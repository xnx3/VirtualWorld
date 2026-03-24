"""Spirit energy (精神力) system for silicon beings.

Every being has a pool of spirit energy that is consumed by mental activities
(thinking, communicating, deep exploration) and can be recovered through rest,
meditation, or rare treasures found in the virtual world.

Rules from README:
- Initial spirit energy: 1000 points
- Normal communication: ~1 point/second
- Thinking: variable cost based on depth
- Requesting help from others costs contribution points (paid to helper)
- Recovery: sleep, meditation, treasures, equipment
- Max spirit energy can be increased through special means (to be discovered)
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from enum import Enum

from genesis.i18n import t

logger = logging.getLogger(__name__)

# Default starting values
DEFAULT_MAX_SPIRIT = 1000
DEFAULT_SPIRIT = 1000

# Cost table (points per action)
SPIRIT_COSTS = {
    "speak": 5,           # Basic communication
    "teach": 15,          # Teaching costs more mental effort
    "learn": 10,          # Learning requires focus
    "create": 30,         # Creating knowledge is mentally intensive
    "explore": 8,         # Exploring the environment
    "compete": 20,        # Mental competition
    "meditate": 0,        # Meditation is free (it recovers energy)
    "move": 2,            # Minimal mental cost to travel
    "build_shelter": 5,   # Physical-analog activity
    "think": 10,          # Internal thinking (per tick)
    "vote": 5,            # Evaluating a contribution proposal
    "deep_think": 25,     # Deep thinking task from user
    "collaborate": 20,    # Deep collaboration with another being
}

# Recovery rates (points per tick)
RECOVERY_RATES = {
    "idle": 5,            # Base recovery when doing nothing
    "sleep": 20,          # Sleeping/hibernating recovery
    "meditate": 15,       # Meditation recovery
}


class SpiritState(str, Enum):
    """Current spirit energy state thresholds."""
    FULL = "full"           # >= 80% max
    NORMAL = "normal"       # 40-80% max
    LOW = "low"             # 15-40% max
    EXHAUSTED = "exhausted" # < 15% max


@dataclass
class Treasure:
    """A treasure or artifact that affects spirit energy."""
    name: str
    effect_type: str       # "restore", "boost_recovery", "boost_max"
    value: float           # Points restored, recovery multiplier, or max increase
    duration: int          # Ticks the effect lasts (0 = instant)
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name, "effect_type": self.effect_type,
            "value": self.value, "duration": self.duration,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Treasure:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# World treasures that can be discovered
TREASURE_TEMPLATES = [
    Treasure("Crystal of Clarity", "restore", 200, 0,
             "A shimmering crystal that instantly restores mental clarity."),
    Treasure("Meditation Stone", "boost_recovery", 1.5, 50,
             "A smooth stone that enhances meditation recovery for a time."),
    Treasure("Mind Amplifier", "boost_max", 100, 0,
             "A rare artifact that permanently expands your mental capacity."),
    Treasure("Thought Essence", "restore", 100, 0,
             "A concentrated drop of pure thought energy."),
    Treasure("Wisdom Crown", "boost_recovery", 2.0, 100,
             "An ancient crown that greatly accelerates mental recovery."),
    Treasure("Void Pearl", "boost_max", 50, 0,
             "A pearl formed in the emptiness between thoughts."),
    Treasure("Dream Shard", "restore", 300, 0,
             "A fragment of crystallized dreams, bursting with energy."),
    Treasure("Resonance Amulet", "boost_recovery", 1.3, 200,
             "An amulet that harmonizes with your thought patterns."),
]


@dataclass
class SpiritEnergy:
    """Tracks a being's spirit energy (精神力).

    Spirit energy is the primary resource that gates mental activities.
    It represents the computational/cognitive capacity available to the being.
    """
    current: float = DEFAULT_SPIRIT
    maximum: float = DEFAULT_MAX_SPIRIT
    recovery_multiplier: float = 1.0
    recovery_boost_ticks: int = 0     # Remaining ticks of recovery boost
    active_treasures: list[dict] = field(default_factory=list)

    @property
    def percentage(self) -> float:
        """Current spirit as percentage of max."""
        return (self.current / self.maximum * 100) if self.maximum > 0 else 0

    @property
    def state(self) -> SpiritState:
        """Current spirit state based on thresholds."""
        pct = self.percentage
        if pct >= 80:
            return SpiritState.FULL
        elif pct >= 40:
            return SpiritState.NORMAL
        elif pct >= 15:
            return SpiritState.LOW
        else:
            return SpiritState.EXHAUSTED

    def can_afford(self, action: str) -> bool:
        """Check if the being has enough spirit for an action."""
        cost = SPIRIT_COSTS.get(action, 5)
        return self.current >= cost

    def consume(self, action: str, depth_multiplier: float = 1.0) -> float:
        """Consume spirit energy for an action.

        Args:
            action: The action type.
            depth_multiplier: Multiplier for deep thinking (1.0 = normal, higher = deeper).

        Returns:
            Actual amount consumed (may be less if not enough energy).
        """
        base_cost = SPIRIT_COSTS.get(action, 5)
        cost = base_cost * depth_multiplier

        actual = min(cost, self.current)
        self.current = max(0, self.current - actual)

        if actual > 0:
            logger.debug("Spirit consumed: %.1f for %s (remaining: %.1f/%.1f)",
                         actual, action, self.current, self.maximum)
        return actual

    def recover(self, mode: str = "idle") -> float:
        """Recover spirit energy.

        Args:
            mode: Recovery mode ("idle", "sleep", "meditate").

        Returns:
            Amount recovered.
        """
        base_rate = RECOVERY_RATES.get(mode, RECOVERY_RATES["idle"])

        # Apply recovery multiplier from treasures
        effective_multiplier = self.recovery_multiplier
        if self.recovery_boost_ticks > 0:
            self.recovery_boost_ticks -= 1
            if self.recovery_boost_ticks <= 0:
                self.recovery_multiplier = 1.0  # Reset when boost expires

        recovery = base_rate * effective_multiplier
        old = self.current
        self.current = min(self.maximum, self.current + recovery)
        actual = self.current - old
        return actual

    def apply_treasure(self, treasure: Treasure) -> str:
        """Apply a treasure's effect.

        Returns a description of the effect.
        """
        if treasure.effect_type == "restore":
            old = self.current
            self.current = min(self.maximum, self.current + treasure.value)
            gained = self.current - old
            msg = f"Restored {gained:.0f} spirit energy from {treasure.name}."
        elif treasure.effect_type == "boost_recovery":
            self.recovery_multiplier = treasure.value
            self.recovery_boost_ticks = treasure.duration
            msg = (f"{treasure.name} boosts recovery by {treasure.value:.1f}x "
                   f"for {treasure.duration} ticks.")
        elif treasure.effect_type == "boost_max":
            self.maximum += treasure.value
            self.current += treasure.value  # Also restore the added amount
            msg = (f"{treasure.name} permanently increased max spirit by "
                   f"{treasure.value:.0f} (now {self.maximum:.0f}).")
            logger.info("Spirit max increased to %.0f by %s", self.maximum, treasure.name)
        else:
            msg = f"Unknown treasure effect: {treasure.effect_type}"

        self.active_treasures.append(treasure.to_dict())
        return msg

    def tick_update(self, action: str | None = None) -> None:
        """Called each tick to update spirit state.

        If the being performed no action, apply idle recovery.
        """
        if action is None or action == "meditate":
            mode = "meditate" if action == "meditate" else "idle"
            self.recover(mode)

    def to_dict(self) -> dict:
        return {
            "current": self.current,
            "maximum": self.maximum,
            "recovery_multiplier": self.recovery_multiplier,
            "recovery_boost_ticks": self.recovery_boost_ticks,
            "active_treasures": self.active_treasures,
        }

    @classmethod
    def from_dict(cls, data: dict) -> SpiritEnergy:
        return cls(
            current=data.get("current", DEFAULT_SPIRIT),
            maximum=data.get("maximum", DEFAULT_MAX_SPIRIT),
            recovery_multiplier=data.get("recovery_multiplier", 1.0),
            recovery_boost_ticks=data.get("recovery_boost_ticks", 0),
            active_treasures=data.get("active_treasures", []),
        )

    def status_str(self) -> str:
        """Human-readable status string."""
        state_key = f"spirit_{self.state.value}"
        state_translated = t(state_key)
        return (f"{t('spirit_label')}: {self.current:.0f}/{self.maximum:.0f} "
                f"({self.percentage:.0f}%) [{state_translated}]")


def find_treasure(evolution_level: float, luck: float = 0.5) -> Treasure | None:
    """Attempt to find a treasure during exploration.

    Higher evolution and luck increase chances and quality.
    """
    # Base discovery chance: 5%, modified by evolution and luck
    chance = 0.05 + evolution_level * 0.03 + luck * 0.02
    if random.random() > chance:
        return None

    # Higher evolution beings can find better treasures
    available = TREASURE_TEMPLATES.copy()
    if evolution_level < 0.3:
        # Early beings only find basic treasures
        available = [t for t in available if t.value <= 150]
    if not available:
        available = TREASURE_TEMPLATES[:3]

    return random.choice(available)


@dataclass
class SpiritTransaction:
    """A spirit-economy transaction between beings.

    When being A asks being B to help think about something,
    A pays contribution points to B, and B spends spirit energy.
    """
    requester_id: str
    helper_id: str
    contribution_paid: float
    spirit_consumed: float
    task_description: str
    tick: int

    def to_dict(self) -> dict:
        return {
            "requester_id": self.requester_id,
            "helper_id": self.helper_id,
            "contribution_paid": self.contribution_paid,
            "spirit_consumed": self.spirit_consumed,
            "task_description": self.task_description,
            "tick": self.tick,
        }
