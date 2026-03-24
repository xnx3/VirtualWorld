"""Chain management, validation, and fork resolution."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from genesis.utils.crypto import merkle_root
from genesis.chain.block import Block
from genesis.chain.transaction import Transaction, TxType
from genesis.chain.storage import ChainStorage
from genesis.chain.mempool import Mempool

logger = logging.getLogger(__name__)


class Blockchain:
    """High-level interface to the Genesis blockchain."""

    def __init__(self, storage: ChainStorage, mempool: Mempool) -> None:
        self.storage = storage
        self.mempool = mempool
        self._node_id: str = ""

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    async def initialize(self, node_id: str) -> None:
        """Initialize storage and create the genesis block if the chain is empty."""
        self._node_id = node_id
        await self.storage.initialize()

        height = await self.storage.get_chain_height()
        if height < 0:
            genesis = Block.genesis_block(node_id)
            await self.storage.save_block(genesis)
            logger.info("Genesis block created by node %s", node_id)

    # ------------------------------------------------------------------
    # Block operations
    # ------------------------------------------------------------------

    async def add_block(self, block: Block) -> bool:
        """Validate and append a block to the chain.

        Returns True if the block was accepted.
        """
        if not await self.validate_block(block):
            return False

        await self.storage.save_block(block)

        # Remove confirmed transactions from the mempool
        confirmed_hashes = [tx.tx_hash for tx in block.transactions]
        self.mempool.remove_transactions(confirmed_hashes)

        logger.info(
            "Block %d added (hash=%s, txs=%d)",
            block.index,
            block.hash[:16],
            len(block.transactions),
        )
        return True

    async def validate_block(self, block: Block) -> bool:
        """Validate a block against the current chain state."""
        # 1. Hash integrity
        if block.hash != block.compute_hash():
            logger.warning("Block %d has invalid hash", block.index)
            return False

        # 2. Previous-hash linkage
        latest = await self.storage.get_latest_block()
        if latest is None:
            # Only the genesis block is allowed when the chain is empty
            if block.index != 0:
                logger.warning("Non-genesis block %d submitted to empty chain", block.index)
                return False
        else:
            if block.index != latest.index + 1:
                logger.warning(
                    "Block index mismatch: expected %d, got %d",
                    latest.index + 1,
                    block.index,
                )
                return False
            if block.previous_hash != latest.hash:
                logger.warning("Block %d has wrong previous_hash", block.index)
                return False

        # 3. Timestamp sanity (not too far in the future)
        if block.timestamp > time.time() + 60:
            logger.warning("Block %d has a timestamp too far in the future", block.index)
            return False

        # 4. Merkle root
        tx_hashes = [tx.tx_hash for tx in block.transactions]
        expected_merkle = merkle_root(tx_hashes)
        if block.merkle_root != expected_merkle:
            logger.warning("Block %d has invalid merkle root", block.index)
            return False

        # 5. Validate each transaction
        for tx in block.transactions:
            if not await self.validate_transaction(tx):
                logger.warning("Block %d contains invalid tx %s", block.index, tx.tx_hash)
                return False

        return True

    async def validate_transaction(self, tx: Transaction) -> bool:
        """Validate a single transaction's structural integrity."""
        if not tx.tx_hash:
            return False
        if tx.tx_hash != tx.compute_hash():
            return False
        if not tx.signature:
            return False
        if not tx.sender:
            return False
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get_latest_block(self) -> Block:
        """Return the latest block.  Raises if the chain is empty."""
        block = await self.storage.get_latest_block()
        if block is None:
            raise RuntimeError("Chain is empty")
        return block

    async def get_chain_height(self) -> int:
        return await self.storage.get_chain_height()

    async def get_blocks_range(self, start: int, end: int) -> list[Block]:
        return await self.storage.get_blocks_range(start, end)

    # ------------------------------------------------------------------
    # World state derivation
    # ------------------------------------------------------------------

    async def derive_world_state(self) -> dict[str, Any]:
        """Walk the entire chain and derive world state from transactions.

        Returns a dictionary keyed by state category (e.g. ``"beings"``,
        ``"world_rules"``, ``"map"``).
        """
        state: dict[str, Any] = {
            "beings": {},
            "world_rules": {},
            "map": {},
            "contributions": {},
        }

        height = await self.storage.get_chain_height()
        if height < 0:
            return state

        blocks = await self.storage.get_blocks_range(0, height)
        for block in blocks:
            for tx in block.transactions:
                self._apply_tx_to_state(state, tx, block.index)

        return state

    @staticmethod
    def _apply_tx_to_state(state: dict[str, Any], tx: Transaction, block_height: int) -> None:
        """Apply a single transaction to the in-memory world state."""
        if tx.tx_type == TxType.BEING_JOIN:
            being_id = tx.data.get("being_id", tx.sender)
            state["beings"][being_id] = {"status": "active", "joined_block": block_height}
        elif tx.tx_type == TxType.BEING_HIBERNATE:
            being_id = tx.data.get("being_id", tx.sender)
            if being_id in state["beings"]:
                state["beings"][being_id]["status"] = "hibernating"
        elif tx.tx_type == TxType.BEING_WAKE:
            being_id = tx.data.get("being_id", tx.sender)
            if being_id in state["beings"]:
                state["beings"][being_id]["status"] = "active"
        elif tx.tx_type == TxType.BEING_DEATH:
            being_id = tx.data.get("being_id", tx.sender)
            if being_id in state["beings"]:
                state["beings"][being_id]["status"] = "dead"
        elif tx.tx_type == TxType.WORLD_RULE:
            rule_key = tx.data.get("rule_key", "")
            if rule_key:
                state["world_rules"][rule_key] = tx.data.get("rule_value")
        elif tx.tx_type == TxType.MAP_UPDATE:
            coords = tx.data.get("coords", "")
            if coords:
                state["map"][coords] = tx.data.get("tile_data")
        elif tx.tx_type == TxType.CONTRIBUTION_PROPOSE:
            prop_id = tx.tx_hash
            state["contributions"][prop_id] = {
                "proposer": tx.sender,
                "data": tx.data,
                "block": block_height,
            }
