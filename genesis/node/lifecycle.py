"""Node lifecycle management: start, stop, first-run detection.

``NodeLifecycle`` orchestrates the high-level startup and shutdown sequence
for a Genesis node, including identity creation and configuration
loading.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from genesis.node.config import VWConfig, load_config
from genesis.node.identity import NodeIdentity

logger = logging.getLogger(__name__)


class NodeLifecycle:
    """Manages the full lifecycle of a Genesis node.

    Attributes:
        data_dir:  Path to the node's persistent data directory.
        config:    Loaded :class:`VWConfig` (available after :meth:`start`).
        identity:  Node :class:`NodeIdentity` (available after :meth:`start`).
    """

    def __init__(self) -> None:
        self.data_dir: Path | None = None
        self.config: VWConfig | None = None
        self.identity: NodeIdentity | None = None
        self._running: bool = False
        self._stop_event: asyncio.Event = asyncio.Event()

    # -- public interface ----------------------------------------------------

    @property
    def running(self) -> bool:
        return self._running

    async def start(
        self,
        data_dir: str | Path,
        password: str | None = None,
    ) -> None:
        """Start the node.

        1. Ensure *data_dir* exists.
        2. Load (or create default) configuration.
        3. Generate or load the node identity.
        4. Log whether this is a first run or a rejoin.

        Parameters:
            data_dir: Filesystem path that holds config, identity, and state.
            password: Optional password to encrypt/decrypt the identity key.
        """
        if self._running:
            logger.warning("Node is already running")
            return

        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        first_run = is_first_run(self.data_dir)

        # Configuration
        self.config = load_config(self.data_dir)
        logger.info("Configuration loaded from %s", self.data_dir)

        # Identity
        self.identity = NodeIdentity.generate_or_load(self.data_dir, password=password)

        if first_run:
            logger.info(
                "First run -- generated new identity: %s", self.identity.node_id
            )
        else:
            logger.info(
                "Rejoining network with identity: %s", self.identity.node_id
            )

        self._running = True
        self._stop_event.clear()
        logger.info("Node started (tick_interval=%ds)", self.config.simulation.tick_interval)

    async def stop(self) -> None:
        """Gracefully hibernate the node.

        Signals any running subsystems (via the internal stop event) and
        performs cleanup.  Safe to call multiple times.
        """
        if not self._running:
            logger.debug("stop() called but node is not running")
            return

        logger.info("Initiating graceful hibernate ...")
        self._stop_event.set()
        self._running = False
        logger.info("Node hibernated successfully")

    async def wait_until_stopped(self) -> None:
        """Block until :meth:`stop` has been called."""
        await self._stop_event.wait()


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def is_first_run(data_dir: str | Path) -> bool:
    """Return ``True`` if *data_dir* has never been initialised.

    A directory is considered initialised if it contains an ``identity.key``
    file.
    """
    return not (Path(data_dir) / "identity.key").exists()
