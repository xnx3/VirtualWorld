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


class GenesisMismatchError(RuntimeError):
    """Raised when a peer belongs to a different blockchain genesis."""


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
        peers = sorted(
            self._peer_manager.get_active_peers(),
            key=lambda peer: peer.chain_height,
            reverse=True,
        )
        if not peers:
            logger.info("No peers available for sync")
            return False

        advanced = False
        best_compatible_height: int | None = None
        last_mismatch: GenesisMismatchError | None = None

        for peer in peers:
            try:
                compatible = await self._ensure_peer_compatible(
                    blockchain,
                    peer.node_id,
                    peer.chain_height,
                )
            except GenesisMismatchError as exc:
                last_mismatch = exc
                logger.warning("%s", exc)
                continue
            except (asyncio.TimeoutError, OSError) as exc:
                logger.warning(
                    "Failed to verify genesis compatibility with %s: %s",
                    peer.node_id[:16],
                    exc,
                )
                continue

            if not compatible:
                continue

            best_compatible_height = (
                peer.chain_height
                if best_compatible_height is None
                else max(best_compatible_height, peer.chain_height)
            )

            current_height = await blockchain.get_chain_height()
            if peer.chain_height <= current_height:
                continue

            logger.info(
                "Starting sync from height %d to %d (peer %s)",
                current_height,
                peer.chain_height,
                peer.node_id[:16],
            )

            if await self._sync_from_peer(blockchain, peer.node_id, peer.chain_height, current_height):
                advanced = True

            synced_height = await blockchain.get_chain_height()
            if synced_height >= peer.chain_height:
                break

        if best_compatible_height is None:
            if last_mismatch is not None:
                raise last_mismatch
            logger.info("No compatible peers available for sync")
            return False

        if advanced:
            logger.info(
                "Sync complete: chain advanced to height %d",
                await blockchain.get_chain_height(),
            )
        else:
            logger.info(
                "Chain is up to date (local=%d, best_peer=%d)",
                await blockchain.get_chain_height(),
                best_compatible_height,
            )
        return advanced

    async def _ensure_peer_compatible(
        self,
        blockchain: Any,
        peer_id: str,
        remote_height: int,
    ) -> bool:
        """Verify that a peer shares the same genesis block, resetting a local stub when safe."""
        if remote_height < 0:
            return False

        remote_blocks = await self.request_blocks(peer_id, 0, 0)
        if not remote_blocks:
            raise OSError(f"peer {peer_id[:16]} returned no genesis block")

        try:
            remote_genesis = Block.from_dict(remote_blocks[0])
        except Exception as exc:
            raise OSError(f"peer {peer_id[:16]} returned invalid genesis block") from exc

        local_height = await blockchain.get_chain_height()
        if local_height < 0:
            return True

        local_genesis = await blockchain.get_block(0)
        if local_genesis is None or local_genesis.hash == remote_genesis.hash:
            return True

        if await blockchain.has_only_genesis():
            logger.warning(
                "Resetting local genesis %s to adopt peer %s genesis %s",
                local_genesis.hash[:16],
                peer_id[:16],
                remote_genesis.hash[:16],
            )
            await blockchain.reset_to_empty()
            return True

        raise GenesisMismatchError(
            "Genesis mismatch with peer "
            f"{peer_id[:16]} (local={local_genesis.hash[:16]}, remote={remote_genesis.hash[:16]})"
        )

    async def _sync_from_peer(
        self,
        blockchain: Any,
        peer_id: str,
        remote_height: int,
        local_height: int,
    ) -> bool:
        """Synchronize missing blocks from one peer and report whether progress was made."""
        advanced = False
        current = local_height + 1

        while current <= remote_height:
            end = min(current + _BATCH_SIZE - 1, remote_height)
            try:
                blocks = await self.request_blocks(peer_id, current, end)
            except (asyncio.TimeoutError, OSError) as exc:
                logger.warning("Block request from %s failed at height %d: %s", peer_id[:16], current, exc)
                break

            if not blocks:
                logger.warning("Received empty block batch from %s at height %d", peer_id[:16], current)
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
                    return advanced

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
