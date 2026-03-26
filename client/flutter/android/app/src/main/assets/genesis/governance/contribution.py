"""Evolution contribution scoring and consensus voting.

贡献系统 - 管理进化贡献评分和共识投票

当贡献类别为 "rule" 时，会触发天道投票流程：
1. 发起天道投票
2. 所有生灵投票（持续 3 天）
3. 95% 赞成则通过
4. 通过后创造者融入天道
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field

from genesis.world.state import WorldState

logger = logging.getLogger(__name__)


@dataclass
class ContributionProposal:
    """A proposal for an evolution contribution."""
    tx_hash: str
    proposer: str
    description: str
    category: str  # "rule", "ability", "species", "knowledge", "social_structure", "other"
    tick: int
    votes: list[ContributionVote] = field(default_factory=list)
    finalized: bool = False
    final_score: float | None = None

    def to_dict(self) -> dict:
        return {
            "tx_hash": self.tx_hash,
            "proposer": self.proposer,
            "description": self.description,
            "category": self.category,
            "tick": self.tick,
            "votes": [v.to_dict() for v in self.votes],
            "finalized": self.finalized,
            "final_score": self.final_score,
        }


@dataclass
class ContributionVote:
    """A vote on a contribution proposal."""
    voter_id: str
    score: int  # 0-100
    tick: int

    def to_dict(self) -> dict:
        return {"voter_id": self.voter_id, "score": self.score, "tick": self.tick}


class ContributionSystem:
    """Manages evolution contribution scoring and consensus voting.

    Rules from README:
    - Contribution is NOT measured by token consumption
    - Measured by actual evolution contribution (creating rules/abilities/species)
    - Contribution value determined by consensus of all blockchain nodes

    Implementation:
    - Each node's AI evaluates proposals and votes (0-100)
    - Median score after removing outliers (>2 std dev)
    - Require 51% of active nodes to vote
    - Max 1 proposal per 10 blocks per node
    - Cannot vote on own proposals
    """

    def __init__(self, vote_window: int = 5, min_voter_ratio: float = 0.51,
                 proposal_rate_limit: int = 10):
        self.vote_window = vote_window
        self.min_voter_ratio = min_voter_ratio
        self.proposal_rate_limit = proposal_rate_limit

    def can_propose(self, node_id: str, current_block: int,
                    world_state: WorldState) -> tuple[bool, str]:
        """Check if a node can submit a new proposal."""
        # Check rate limit: max 1 proposal per N blocks
        for tx_hash, proposal in world_state.pending_proposals.items():
            if (proposal["proposer"] == node_id and
                    current_block - proposal.get("block", 0) < self.proposal_rate_limit):
                return False, f"Rate limited: must wait {self.proposal_rate_limit} blocks between proposals"
        return True, "OK"

    def can_vote(self, voter_id: str, proposal: dict) -> tuple[bool, str]:
        """Check if a node can vote on a proposal."""
        # Cannot vote on own proposals
        if voter_id == proposal.get("proposer"):
            return False, "Cannot vote on own proposal"
        return True, "OK"

    def tally_votes(self, votes: list[dict], active_node_count: int) -> float | None:
        """Tally votes for a contribution proposal.

        Returns the final score, or None if insufficient votes.

        Process:
        1. Check minimum voter participation (51%)
        2. Remove outlier votes (>2 std dev from median)
        3. Take median of remaining votes
        """
        if not votes:
            return None

        # Check minimum participation
        voter_count = len(votes)
        if voter_count / max(active_node_count, 1) < self.min_voter_ratio:
            return None  # Insufficient participation

        scores = [v["score"] for v in votes]

        if len(scores) < 2:
            return float(scores[0]) if scores else None

        # Remove outliers (>2 std dev from median)
        median = statistics.median(scores)
        try:
            stdev = statistics.stdev(scores)
        except statistics.StatisticsError:
            stdev = 0

        if stdev > 0:
            filtered = [s for s in scores if abs(s - median) <= 2 * stdev]
        else:
            filtered = scores

        if not filtered:
            filtered = scores  # Fallback if all removed

        return statistics.median(filtered)

    def finalize_proposal(self, tx_hash: str, world_state: WorldState,
                          active_node_count: int) -> float | None:
        """Finalize a contribution proposal after voting window closes.

        Returns the final score or None if not enough votes.
        """
        votes = world_state.proposal_votes.get(tx_hash, [])
        score = self.tally_votes(votes, active_node_count)

        if score is not None:
            # Add to proposer's cumulative score
            proposal = world_state.pending_proposals.get(tx_hash, {})
            proposer = proposal.get("proposer")
            if proposer:
                current = world_state.contribution_scores.get(proposer, 0.0)
                world_state.contribution_scores[proposer] = current + score
                logger.info(
                    "Contribution finalized: %s by %s scored %.1f (total now %.1f)",
                    tx_hash[:8], proposer[:8], score,
                    world_state.contribution_scores[proposer],
                )

        # Remove from pending
        world_state.pending_proposals.pop(tx_hash, None)
        world_state.proposal_votes.pop(tx_hash, None)

        return score

    def get_ranking(self, world_state: WorldState) -> list[tuple[str, float]]:
        """Get contribution score ranking."""
        return world_state.get_contribution_ranking()

    # === 天道投票集成 ===

    def propose_rule_for_tao(
        self,
        proposer_id: str,
        rule_name: str,
        rule_description: str,
        world_state: WorldState,
    ) -> dict:
        """发起天道规则提案。

        当贡献类别为 "rule" 时，会触发天道投票。

        Args:
            proposer_id: 提案者 ID
            rule_name: 规则名称
            rule_description: 规则描述
            world_state: 世界状态

        Returns:
            包含投票信息的字典
        """
        from genesis.governance.tao_voting import get_tao_voting_system

        tao_system = get_tao_voting_system()
        vote = tao_system.initiate_tao_vote(
            proposer_id=proposer_id,
            rule_name=rule_name,
            rule_description=rule_description,
            rule_category="civilization",
            world_state=world_state,
        )

        logger.info(
            "Rule proposal %s submitted for TAO voting by %s",
            rule_name, proposer_id[:8]
        )

        return {
            "vote_id": vote.vote_id,
            "rule_name": rule_name,
            "end_tick": vote.end_tick,
            "status": "pending",
        }

    def process_contribution_for_tao(
        self,
        proposal: dict,
        world_state: WorldState,
    ) -> dict | None:
        """处理贡献提案，判断是否需要天道投票。

        Args:
            proposal: 提案数据
            world_state: 世界状态

        Returns:
            如果是规则提案，返回天道投票信息；否则返回 None
        """
        category = proposal.get("category", "other")

        if category == "rule":
            # 规则提案需要天道投票
            return self.propose_rule_for_tao(
                proposer_id=proposal.get("proposer", ""),
                rule_name=proposal.get("description", "新规则")[:50],
                rule_description=proposal.get("description", ""),
                world_state=world_state,
            )

        return None
