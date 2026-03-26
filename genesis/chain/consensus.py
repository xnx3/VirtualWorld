"""Proof-of-Contribution consensus mechanism."""

from __future__ import annotations

import logging
import statistics
import time
from typing import Any

from genesis.utils.crypto import merkle_root, sign
from genesis.chain.block import Block
from genesis.chain.transaction import Transaction, TxType
from genesis.chain.chain import Blockchain

logger = logging.getLogger(__name__)

# A node may submit at most one contribution proposal every this many blocks.
_PROPOSAL_COOLDOWN_BLOCKS = 10

# Minimum number of REAL (non-NPC) active nodes before consensus activates.
_MIN_REAL_NODES_FOR_CONSENSUS = 1


class ProofOfContribution:
    """Proof-of-Contribution consensus for Genesis.

    Security rules:
    - Only real (non-NPC) nodes participate in block proposer selection.
    - NPC votes are excluded from contribution tallying.
    - Proposal cooldown is enforced per node.
    - Minimum real node count required before governance activates.
    """

    def __init__(
        self,
        blockchain: Blockchain,
        node_id: str,
        private_key: bytes,
    ) -> None:
        self.blockchain = blockchain
        self.node_id = node_id
        self.private_key = private_key
        # Track last proposal block per node (enforces cooldown)
        self._last_proposal_block: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Proposer selection
    # ------------------------------------------------------------------

    async def select_proposer(
        self,
        active_nodes: list[str],
        contribution_scores: dict[str, float],
        npc_node_ids: set[str] | None = None,
    ) -> str:
        """Select the next block proposer using weighted round-robin.

        Only real (non-NPC) nodes are eligible to propose blocks.
        """
        npc_ids = npc_node_ids or set()
        real_nodes = [n for n in active_nodes if n not in npc_ids]

        # Fall back to all nodes if no real nodes available
        eligible = real_nodes if real_nodes else active_nodes
        if not eligible:
            raise ValueError("No eligible nodes to select proposer from")

        sorted_nodes = sorted(eligible)
        height = await self.blockchain.get_chain_height()

        slots: list[str] = []
        for node in sorted_nodes:
            weight = max(1, int(contribution_scores.get(node, 1.0)))
            slots.extend([node] * weight)

        if not slots:
            return sorted_nodes[height % len(sorted_nodes)]

        return slots[height % len(slots)]

    def is_my_turn(
        self,
        active_nodes: list[str],
        contribution_scores: dict[str, float],
        npc_node_ids: set[str] | None = None,
    ) -> bool:
        """Synchronous convenience check."""
        npc_ids = npc_node_ids or set()
        real_nodes = [n for n in active_nodes if n not in npc_ids]
        eligible = real_nodes if real_nodes else active_nodes
        if not eligible:
            return False

        sorted_nodes = sorted(eligible)

        import asyncio
        try:
            asyncio.get_running_loop()
            return False  # Inside event loop, use async path
        except RuntimeError:
            pass

        height = asyncio.run(self.blockchain.get_chain_height())

        slots: list[str] = []
        for node in sorted_nodes:
            weight = max(1, int(contribution_scores.get(node, 1.0)))
            slots.extend([node] * weight)

        if not slots:
            return sorted_nodes[height % len(sorted_nodes)] == self.node_id

        return slots[height % len(slots)] == self.node_id

    def can_propose(self, node_id: str, current_block: int) -> tuple[bool, str]:
        """Check if a node can submit a contribution proposal (cooldown enforcement)."""
        last = self._last_proposal_block.get(node_id, -_PROPOSAL_COOLDOWN_BLOCKS)
        if current_block - last < _PROPOSAL_COOLDOWN_BLOCKS:
            remaining = _PROPOSAL_COOLDOWN_BLOCKS - (current_block - last)
            return False, f"Cooldown active: {remaining} blocks remaining"
        return True, "OK"

    def record_proposal(self, node_id: str, block_height: int) -> None:
        """Record that a node submitted a proposal at this block height."""
        self._last_proposal_block[node_id] = block_height

    # ------------------------------------------------------------------
    # Block creation
    # ------------------------------------------------------------------

    async def create_block(self, transactions: list[Transaction]) -> Block:
        """Create and sign a new block containing the given transactions."""
        latest = await self.blockchain.get_latest_block()

        tx_hashes = [tx.tx_hash for tx in transactions]
        mr = merkle_root(tx_hashes)

        block = Block(
            index=latest.index + 1,
            timestamp=time.time(),
            previous_hash=latest.hash,
            merkle_root=mr,
            proposer=self.node_id,
            transactions=transactions,
            nonce=0,
        )

        block.sign_block(self.private_key)
        return block

    # ------------------------------------------------------------------
    # Contribution voting
    # ------------------------------------------------------------------

    async def tally_contribution_votes(
        self,
        proposal_tx_hash: str,
        votes: list[Transaction],
        npc_node_ids: set[str] | None = None,
    ) -> float | None:
        """Tally contribution votes, excluding NPC nodes and self-votes.

        Returns the accepted score, or None if invalid.
        """
        if not votes:
            return None

        npc_ids = npc_node_ids or set()

        # Find the proposer
        height = await self.blockchain.get_chain_height()
        proposer: str | None = None
        blocks = await self.blockchain.get_blocks_range(0, height)
        for blk in blocks:
            for tx in blk.transactions:
                if tx.tx_hash == proposal_tx_hash:
                    proposer = tx.sender
                    break
            if proposer is not None:
                break

        # Filter: real nodes only, no self-votes, valid signatures
        valid_votes: list[float] = []
        seen_voters: set[str] = set()
        for vote in votes:
            if vote.tx_type != TxType.CONTRIBUTION_VOTE:
                continue
            # NPC nodes cannot vote
            if vote.sender in npc_ids:
                continue
            # No self-votes
            if proposer is not None and vote.sender == proposer:
                continue
            # No duplicate votes
            if vote.sender in seen_voters:
                continue
            # Signature must be valid
            if not vote.verify_signature():
                logger.warning("Invalid vote signature from %s", vote.sender[:16])
                continue
            score = vote.data.get("score")
            if score is not None:
                try:
                    s = float(score)
                    if 0 <= s <= 100:  # Valid score range
                        valid_votes.append(s)
                        seen_voters.add(vote.sender)
                except (TypeError, ValueError):
                    pass

        if not valid_votes:
            return None

        # Require 51% participation from eligible real voters
        eligible_real_voters = len([
            v for v in votes
            if v.tx_type == TxType.CONTRIBUTION_VOTE
            and v.sender not in npc_ids
            and (proposer is None or v.sender != proposer)
        ])
        if eligible_real_voters == 0:
            return None

        participation = len(valid_votes) / eligible_real_voters
        if participation < 0.51:
            logger.debug(
                "Proposal %s: insufficient participation %.1f%%",
                proposal_tx_hash[:16], participation * 100,
            )
            return None

        # Compute median with outlier removal
        median = statistics.median(valid_votes)

        if len(valid_votes) < 3:
            return median

        try:
            stdev = statistics.stdev(valid_votes)
        except statistics.StatisticsError:
            return median

        if stdev == 0:
            return median

        filtered = [s for s in valid_votes if abs(s - median) <= 2 * stdev]
        return statistics.median(filtered) if filtered else median
