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


class ProofOfContribution:
    """Proof-of-Contribution consensus for Genesis.

    Rules
    -----
    - Block proposer is selected via weighted round-robin based on
      contribution scores.
    - Contribution votes use the median score, discarding outliers
      (>2 std dev from the median) and requiring 51 % participation.
    - Self-votes are rejected.
    - A node may create at most 1 contribution proposal per 10 blocks.
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

    # ------------------------------------------------------------------
    # Proposer selection
    # ------------------------------------------------------------------

    async def select_proposer(
        self,
        active_nodes: list[str],
        contribution_scores: dict[str, float],
    ) -> str:
        """Select the next block proposer using weighted round-robin.

        The algorithm sorts nodes deterministically, then uses the current
        chain height to pick a slot.  Each node occupies a number of
        consecutive slots proportional to its contribution score (minimum 1).
        """
        if not active_nodes:
            raise ValueError("No active nodes to select proposer from")

        sorted_nodes = sorted(active_nodes)
        height = await self.blockchain.get_chain_height()

        # Build the weighted slot list
        slots: list[str] = []
        for node in sorted_nodes:
            weight = max(1, int(contribution_scores.get(node, 1.0)))
            slots.extend([node] * weight)

        if not slots:
            # Fallback: simple round-robin
            return sorted_nodes[height % len(sorted_nodes)]

        return slots[height % len(slots)]

    def is_my_turn(
        self,
        active_nodes: list[str],
        contribution_scores: dict[str, float],
    ) -> bool:
        """Synchronous convenience check (uses the same logic but sync)."""
        if not active_nodes:
            return False

        sorted_nodes = sorted(active_nodes)

        # We need the chain height; use a quick sync estimate from the
        # storage layer.  For a fully async path, use select_proposer instead.
        # This method exists for lightweight polling.
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            # If we're inside an event loop, schedule as a task and return
            # False (callers should prefer the async path).
            return False
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
    ) -> float | None:
        """Tally contribution votes for a proposal.

        Returns the accepted score, or None if the vote is invalid
        (insufficient participation, etc.).

        Rules:
        - Self-votes are discarded.
        - Outliers (>2 std dev from median) are discarded.
        - At least 51 % of voters (after self-vote removal) must have
          voted for the result to be valid.
        """
        if not votes:
            return None

        # Determine the proposer of the original proposal
        # (look up in the chain)
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

        # Filter out self-votes and extract scores
        valid_votes: list[float] = []
        for vote in votes:
            if vote.tx_type != TxType.CONTRIBUTION_VOTE:
                continue
            if proposer is not None and vote.sender == proposer:
                continue  # self-votes rejected
            score = vote.data.get("score")
            if score is not None:
                valid_votes.append(float(score))

        if not valid_votes:
            return None

        # Require 51 % participation (relative to the supplied vote list
        # minus self-votes)
        total_eligible = len([v for v in votes if v.tx_type == TxType.CONTRIBUTION_VOTE and (proposer is None or v.sender != proposer)])
        if total_eligible == 0:
            return None

        participation = len(valid_votes) / total_eligible
        if participation < 0.51:
            return None

        # Compute median
        median = statistics.median(valid_votes)

        if len(valid_votes) < 3:
            # Not enough data points for std-dev filtering
            return median

        # Remove outliers (>2 std dev from median)
        try:
            stdev = statistics.stdev(valid_votes)
        except statistics.StatisticsError:
            return median

        if stdev == 0:
            return median

        filtered = [s for s in valid_votes if abs(s - median) <= 2 * stdev]
        if not filtered:
            return median

        return statistics.median(filtered)
