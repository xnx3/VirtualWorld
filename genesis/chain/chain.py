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
        """Initialize storage without creating a local genesis block."""
        self._node_id = node_id
        await self.storage.initialize()

    async def ensure_local_genesis(self, node_id: str | None = None) -> bool:
        """Create a local genesis block if the chain is still empty."""
        creator_id = node_id or self._node_id
        if not creator_id:
            raise RuntimeError("Node ID must be set before creating a local genesis block")

        height = await self.storage.get_chain_height()
        if height >= 0:
            return False

        genesis = Block.genesis_block(creator_id)
        await self.storage.save_block(genesis)
        logger.info("Genesis block created by node %s", creator_id)
        return True

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

        # 2. Signature verification — block must be signed by its proposer
        if block.index > 0 and not block.verify_signature():
            logger.warning("Block %d has invalid proposer signature", block.index)
            return False

        # 3. Previous-hash linkage
        latest = await self.storage.get_latest_block()
        if latest is None:
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

        # 4. Timestamp sanity (not too far in the future)
        if block.timestamp > time.time() + 60:
            logger.warning("Block %d has a timestamp too far in the future", block.index)
            return False

        # 5. Merkle root
        tx_hashes = [tx.tx_hash for tx in block.transactions]
        expected_merkle = merkle_root(tx_hashes)
        if block.merkle_root != expected_merkle:
            logger.warning("Block %d has invalid merkle root", block.index)
            return False

        # 6. Validate each transaction
        for tx in block.transactions:
            if not await self.validate_transaction(tx):
                logger.warning("Block %d contains invalid tx %s", block.index, tx.tx_hash)
                return False

        return True

    async def validate_transaction(self, tx: Transaction) -> bool:
        """Validate a transaction's structural integrity and signature."""
        if not tx.tx_hash:
            return False
        if tx.tx_hash != tx.compute_hash():
            logger.warning("Transaction hash mismatch: %s", tx.tx_hash[:16])
            return False
        if not tx.signature:
            logger.warning("Transaction missing signature: %s", tx.tx_hash[:16])
            return False
        if not tx.sender:
            logger.warning("Transaction missing sender: %s", tx.tx_hash[:16])
            return False
        if not tx.verify_signature():
            logger.warning("Transaction signature invalid: %s", tx.tx_hash[:16])
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

    async def get_block(self, height: int) -> Block | None:
        """Return the block at *height*, or None when absent."""
        return await self.storage.get_block(height)

    async def get_chain_height(self) -> int:
        return await self.storage.get_chain_height()

    async def get_blocks_range(self, start: int, end: int) -> list[Block]:
        return await self.storage.get_blocks_range(start, end)

    async def has_only_genesis(self) -> bool:
        """True when the chain consists solely of the genesis block."""
        return await self.storage.get_chain_height() == 0

    async def reset_to_empty(self) -> None:
        """Clear all persisted chain data and pending transactions."""
        await self.storage.clear_chain()
        self.mempool.clear()

    async def add_pending_tx(self, tx: Transaction | dict[str, Any]) -> bool:
        """Validate and add a transaction to the local mempool."""
        try:
            candidate = tx if isinstance(tx, Transaction) else Transaction.from_dict(tx)
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Rejected malformed pending tx: %s", exc)
            return False

        if not await self.validate_transaction(candidate):
            logger.warning("Rejected invalid pending tx %s", candidate.tx_hash[:16])
            return False

        added = self.mempool.add_transaction(candidate)
        if not added:
            logger.debug(
                "Pending tx %s already exists or mempool rejected it",
                candidate.tx_hash[:16],
            )
        return added

    # ------------------------------------------------------------------
    # World state derivation
    # ------------------------------------------------------------------

    async def derive_world_state(self) -> dict[str, Any]:
        """Walk the entire chain and derive world state from transactions.

        Returns a ``WorldState.to_dict()`` payload. If the chain only contains
        the genesis block, an empty dict is returned so callers can bootstrap
        first-run state locally.
        """
        from genesis.world.state import WorldState

        world_state = WorldState()
        meaningful_tx_count = 0

        height = await self.storage.get_chain_height()
        if height < 0:
            return {}

        blocks = await self.storage.get_blocks_range(0, height)
        for block in blocks:
            for tx in block.transactions:
                if self._apply_tx_to_world_state(world_state, tx):
                    meaningful_tx_count += 1

        if meaningful_tx_count == 0:
            return {}
        world_state.update_civ_level()
        world_state.update_phase()
        return world_state.to_dict()

    @staticmethod
    def _apply_tx_to_world_state(world_state, tx: Transaction) -> bool:
        """Apply a single transaction to an in-memory ``WorldState``."""
        from genesis.governance.creator_god import CreatorGodSystem

        sender = tx.sender
        data = tx.data
        target_id = data.get("node_id") or data.get("being_id") or sender

        if tx.tx_type == TxType.BEING_JOIN:
            world_state.apply_being_join(target_id, data.get("name", "Unknown"), data)
        elif tx.tx_type == TxType.BEING_HIBERNATE:
            world_state.apply_being_hibernate(target_id, data)
        elif tx.tx_type == TxType.BEING_WAKE:
            world_state.apply_being_wake(target_id, data)
        elif tx.tx_type == TxType.BEING_DEATH:
            world_state.apply_being_death(target_id, data)
        elif tx.tx_type == TxType.ACTION:
            world_state.apply_action(sender, data)
        elif tx.tx_type == TxType.KNOWLEDGE_SHARE:
            world_state.apply_knowledge_share(sender, data)
        elif tx.tx_type == TxType.STATE_UPDATE:
            world_state.apply_state_update(sender, data)
        elif tx.tx_type == TxType.CONTRIBUTION_PROPOSE:
            world_state.apply_contribution_propose(tx.tx_hash, sender, data)
        elif tx.tx_type == TxType.CONTRIBUTION_VOTE:
            world_state.apply_contribution_vote(data, sender_id=sender)
        elif tx.tx_type == TxType.CONTRIBUTION_FINALIZE:
            world_state.apply_contribution_finalize(data)
        elif tx.tx_type == TxType.PRIEST_ELECTION:
            world_state.apply_priest_election(data.get("candidate_id", sender))
        elif tx.tx_type == TxType.CREATOR_SUCCESSION:
            challenger = data.get("challenger_id")
            if challenger:
                CreatorGodSystem().apply_succession(challenger, world_state)
        elif tx.tx_type == TxType.CREATOR_VANISH:
            CreatorGodSystem().apply_vanish(world_state)
        elif tx.tx_type == TxType.DISASTER_EVENT:
            world_state.apply_disaster(data)
        elif tx.tx_type == TxType.WORLD_RULE:
            world_state.apply_world_rule(data)
        elif tx.tx_type == TxType.MAP_UPDATE:
            world_state.apply_map_update(data)
        elif tx.tx_type == TxType.TAO_VOTE_INITIATE:
            world_state.apply_tao_vote_start(
                vote_id=data.get("vote_id", tx.tx_hash),
                proposer_id=data.get("proposer_id", sender),
                rule_data={
                    "name": data.get("rule_name", ""),
                    "description": data.get("rule_description", ""),
                    "category": data.get("rule_category", "civilization"),
                },
                end_tick=data.get("end_tick", world_state.current_tick),
            )
        elif tx.tx_type == TxType.TAO_VOTE_CAST:
            world_state.apply_tao_vote_cast(
                vote_id=data.get("vote_id", ""),
                voter_id=sender,
                support=bool(data.get("support", False)),
            )
        elif tx.tx_type == TxType.TAO_VOTE_FINALIZE:
            vote_id = data.get("vote_id", "")
            if data.get("passed") and data.get("rule_id") and data.get("rule_data"):
                world_state.apply_tao_merge(
                    node_id=data.get("proposer_id", sender),
                    rule_id=data["rule_id"],
                    rule_data=data["rule_data"],
                    merit=float(data.get("merit", 0.0)),
                )
            world_state.pending_tao_votes.pop(vote_id, None)

        return tx.tx_type != TxType.THOUGHT
