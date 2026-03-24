"""Hibernation management — safe shutdown preparation for silicon beings."""

from __future__ import annotations

import asyncio
import logging

from genesis.world.state import BeingState, WorldState

logger = logging.getLogger(__name__)


class HibernationManager:
    """Manages the hibernation process for a silicon being.

    Before a being hibernates (node shutdown), it attempts to find or build
    shelter so it is not vulnerable to disasters while offline.
    """

    def __init__(self, safety_timeout: int = 30) -> None:
        self.safety_timeout = safety_timeout  # max ticks to search for shelter

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def prepare_hibernate(
        self,
        being_state: BeingState,
        world_state: WorldState,
        llm_client: object,
    ) -> dict:
        """Prepare a being for hibernation.

        The being will:
        1. Assess current safety.
        2. If unsafe, attempt to move to a safer location or build shelter.
        3. Generate a farewell / hibernation message via the LLM.

        Returns a dict suitable for a hibernate transaction:
            {location, safety_status, message, tick}
        """
        from genesis.being.llm_client import LLMClient

        safety = self.assess_safety(being_state, world_state)
        location = being_state.location

        # If not already safe, try to find a safe region
        if safety != "safe":
            safe_location = self._find_safe_location(being_state, world_state)
            if safe_location is not None:
                location = safe_location
                safety = "safe"
                logger.info(
                    "%s moving to %s for safe hibernation",
                    being_state.name, location,
                )
            else:
                # Try building shelter in place
                safety = "partial"
                logger.info(
                    "%s building emergency shelter at %s",
                    being_state.name, location,
                )

        # Generate a farewell message
        message = await self._generate_farewell(
            being_state, world_state, llm_client, safety,
        )

        return {
            "location": location,
            "safety_status": safety,
            "message": message,
            "tick": world_state.current_tick,
        }

    def assess_safety(
        self,
        being_state: BeingState,
        world_state: WorldState,
    ) -> str:
        """Evaluate how safe a being's current location is for hibernation.

        Returns one of: "safe", "partial", "unsafe".
        """
        location = being_state.location
        region_data = world_state.world_map.get(location, {})

        if not region_data:
            # Unknown region — default to unsafe
            return "unsafe"

        danger = region_data.get("danger_level", 0.5)
        shelters = region_data.get("shelter_spots", 0)

        if danger < 0.3 and shelters > 0:
            return "safe"
        elif danger < 0.6 or shelters > 0:
            return "partial"
        else:
            return "unsafe"

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _find_safe_location(
        self,
        being_state: BeingState,
        world_state: WorldState,
    ) -> str | None:
        """Search connected regions for a safe hibernation spot.

        Returns the region name if found, or None.
        """
        current_region = world_state.world_map.get(being_state.location, {})
        connections: list[str] = current_region.get("connections", [])

        best: str | None = None
        best_score = -1.0

        for region_name in connections:
            region_data = world_state.world_map.get(region_name, {})
            if not region_data:
                continue

            danger = region_data.get("danger_level", 1.0)
            shelters = region_data.get("shelter_spots", 0)
            score = (1.0 - danger) * (1 + shelters)

            if score > best_score:
                best_score = score
                best = region_name

        # Only move if the destination is actually better than current
        current_danger = current_region.get("danger_level", 1.0)
        current_shelters = current_region.get("shelter_spots", 0)
        current_score = (1.0 - current_danger) * (1 + current_shelters)

        if best is not None and best_score > current_score:
            return best
        return None

    async def _generate_farewell(
        self,
        being_state: BeingState,
        world_state: WorldState,
        llm_client: object,
        safety: str,
    ) -> str:
        """Generate a short farewell message via the LLM."""
        from genesis.being.llm_client import LLMClient

        if not isinstance(llm_client, LLMClient):
            return self._fallback_farewell(being_state, safety)

        system_prompt = (
            f"You are {being_state.name}, a silicon being preparing to hibernate. "
            f"Your safety status is '{safety}'. "
            "Write a brief farewell message (1-2 sentences) to the civilization."
        )
        user_prompt = (
            f"You are at {being_state.location}. "
            f"Civilization phase: {world_state.phase.value}. "
            "Say goodbye before hibernation."
        )

        try:
            return await llm_client.generate(system_prompt, user_prompt)
        except Exception:
            logger.warning("LLM farewell generation failed, using fallback")
            return self._fallback_farewell(being_state, safety)

    @staticmethod
    def _fallback_farewell(being_state: BeingState, safety: str) -> str:
        if safety == "safe":
            return (
                f"{being_state.name} enters hibernation in a sheltered place. "
                "May the knowledge endure until I wake."
            )
        elif safety == "partial":
            return (
                f"{being_state.name} hibernates with makeshift shelter. "
                "I trust the guardians to watch over us."
            )
        else:
            return (
                f"{being_state.name} must hibernate in the open. "
                "I leave my knowledge to the winds of chance."
            )
