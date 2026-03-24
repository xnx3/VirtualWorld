"""Placeholder for future sharding support."""

from __future__ import annotations


class ShardManager:
    """Placeholder for future sharding support.

    Will be activated when node count exceeds threshold.
    """

    def __init__(self) -> None:
        self.enabled: bool = False
        self.shard_id: int | None = None

    def should_enable(self, total_nodes: int) -> bool:
        """Return True when the network is large enough to benefit from sharding."""
        return total_nodes > 1000
