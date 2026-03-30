"""Chain synchronization: download and apply blocks from peers."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from genesis.chain.block import Block
from genesis.network.peer import PeerManager
from genesis.network.protocol import Message, MessageType
from genesis.network.server import P2PServer

logger = logging.getLogger(__name__)

# Number of blocks to request per batch during initial sync.
_BATCH_SIZE: int = 100

# Timeout for a single block-request round-trip.
_REQUEST_TIMEOUT: float = 30.0


class ChainSync:
    """Coordinates chain synchronization between this node and its peers.

    Typical lifecycle:
        1. On startup call ``sync_chain(blockchain)`` to catch up.
        2. Register ``handle_new_block`` and ``handle_new_tx`` as P2PServer
           message callbacks for real-time propagation.
    """

    def __init__(self, server: P2PServer, peer_manager: PeerManager) -> None:
        self._server = server
        self._peer_manager = peer_manager
        self._pending_responses: dict[str, asyncio.Future[Message]] = {}

        # Register an internal message handler so we can resolve futures.
        self._server.on_message(self._on_message)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def sync_chain(self, blockchain: Any) -> bool:
        """Perform a full synchronization against the best peer.

        *blockchain* is expected to expose:
            - ``get_chain_height() -> int``
            - ``add_block(block) -> bool``: validate and append a block

        Returns True if the chain was advanced, False otherwise.
        """
        best_peer = self._peer_manager.get_best_peer()
        if best_peer is None:
            logger.info("No peers available for sync")
            return False

        local_height = await blockchain.get_chain_height()
        remote_height = best_peer.chain_height

        if remote_height <= local_height:
            logger.info(
                "Chain is up to date (local=%d, best_peer=%d)",
                local_height,
                remote_height,
            )
            return False

        logger.info(
            "Starting sync from height %d to %d (peer %s)",
            local_height,
            remote_height,
            best_peer.node_id[:16],
        )

        advanced = False
        current = local_height + 1

        while current <= remote_height:
            end = min(current + _BATCH_SIZE - 1, remote_height)
            try:
                blocks = await self.request_blocks(best_peer.node_id, current, end)
            except (asyncio.TimeoutError, OSError) as exc:
                logger.warning("Block request failed at height %d: %s", current, exc)
                break

            if not blocks:
                logger.warning("Received empty block batch at height %d", current)
                break

            for block_data in blocks:
                try:
                    ok = await blockchain.add_block(Block.from_dict(block_data))
                except Exception:
                    logger.exception("Failed to apply block at height %d", current)
                    ok = False

                if ok:
                    current += 1
                    advanced = True
                else:
                    logger.warning("Block validation failed at height %d", current)
                    # Try to continue with the next peer in the future.
                    return advanced

        if advanced:
            logger.info("Sync complete: chain advanced to height %d", current)
        return advanced

    async def request_blocks(
        self, peer_id: str, start: int, end: int
    ) -> list[dict[str, Any]]:
        """Request blocks [start, end] from *peer_id*.

        Returns a list of block dicts.  Raises ``asyncio.TimeoutError`` if the
        peer does not respond in time.
        """
        request_key = f"blocks:{peer_id}:{start}:{end}"
        future: asyncio.Future[Message] = asyncio.get_running_loop().create_future()
        self._pending_responses[request_key] = future

        msg = Message.get_blocks(self._server.node_id, start, end)
        await self._server.send_to_peer(peer_id, msg)

        try:
            response = await asyncio.wait_for(future, timeout=_REQUEST_TIMEOUT)
        finally:
            self._pending_responses.pop(request_key, None)

        return response.payload.get("blocks", [])

    async def handle_new_block(self, block_data: dict[str, Any], blockchain: Any) -> bool:
        """Handle a NEW_BLOCK message received from the network.

        Validates and appends the block, then re-broadcasts to other peers.
        """
        block_height = block_data.get("index", -1)
        local_height = await blockchain.get_chain_height()

        if block_height <= local_height:
            logger.debug("Ignoring already-known block at height %d", block_height)
            return False

        if block_height > local_height + 1:
            logger.info(
                "Received future block %d (local=%d), triggering sync",
                block_height,
                local_height,
            )
            return await self.sync_chain(blockchain)

        try:
            ok = await blockchain.add_block(Block.from_dict(block_data))
        except Exception:
            logger.exception("Failed to apply new block %d", block_height)
            return False

        if ok:
            logger.info("Applied new block at height %d", block_height)
            # Re-broadcast to other peers.
            broadcast = Message.new_block(self._server.node_id, block_data)
            await self._server.broadcast_message(broadcast)
            return True
        else:
            logger.warning("Rejected new block at height %d", block_height)
            return False

    async def handle_new_tx(self, tx_data: dict[str, Any], blockchain: Any) -> bool:
        """Handle a NEW_TX message: validate and add to the mempool.

        *blockchain* is expected to expose ``add_pending_tx(tx_dict) -> bool``.
        """
        tx_hash = tx_data.get("tx_hash", "unknown")

        try:
            ok = await blockchain.add_pending_tx(tx_data)
        except Exception:
            logger.exception("Error adding pending tx %s", tx_hash)
            return False

        if ok:
            logger.debug("Accepted new tx %s", tx_hash)
            broadcast = Message.new_tx(self._server.node_id, tx_data)
            await self._server.broadcast_message(broadcast)
            return True
        else:
            logger.debug("Rejected tx %s", tx_hash)
            return False

    # ------------------------------------------------------------------
    # Internal: response matching
    # ------------------------------------------------------------------

    async def _on_message(self, msg: Message, peer_id: str) -> None:
        """Internal message handler that resolves pending request futures."""
        if msg.msg_type == MessageType.BLOCKS:
            # Match against a pending request from this peer.
            for key, future in list(self._pending_responses.items()):
                if key.startswith(f"blocks:{peer_id}:") and not future.done():
                    future.set_result(msg)
                    break

        elif msg.msg_type == MessageType.NEW_BLOCK:
            # Delegate to handle_new_block if a blockchain reference is available.
            # In practice, the top-level node wires this via on_message directly.
            pass

        elif msg.msg_type == MessageType.NEW_TX:
            pass
