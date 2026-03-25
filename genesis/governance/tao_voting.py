"""Tao (天道) voting system for world rule creation.

天道投票系统 - 世界规则创造时的投票机制

投票流程：
1. 生灵发起世界规则提案 → 创建 TaoVote
2. 系统通知所有活跃生灵
3. 投票持续 3 天（8640 ticks）
4. 3 天后统计结果，95% 赞成才能通过
5. 通过后：规则加入天道，提案者融入天道

时间参数（基于物理世界）：
- tick_interval = 30 秒
- 1 天 = 86400 秒 ÷ 30 = 2880 ticks
- 3 天 = 8640 ticks
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from genesis.world.state import BeingState, WorldState

logger = logging.getLogger(__name__)


# === 天道投票常量 ===

# 时间参数
TICK_INTERVAL_SECONDS = 30
SECONDS_PER_DAY = 86400
TICKS_PER_DAY = SECONDS_PER_DAY // TICK_INTERVAL_SECONDS  # 2880

# 天道投票参数
TAO_VOTE_DURATION_DAYS = 3
TAO_VOTE_DURATION_TICKS = TICKS_PER_DAY * TAO_VOTE_DURATION_DAYS  # 8640
TAO_VOTE_PASS_RATIO = 0.95  # 95% 赞成才能通过


@dataclass
class TaoVote:
    """天道规则投票。

    当生灵提出创造世界规则的提案时，会发起天道投票。
    所有活跃生灵都必须参与投票。
    """
    vote_id: str                           # 投票唯一 ID
    proposer_id: str                       # 提案者 ID
    rule_name: str                         # 规则名称
    rule_description: str                  # 规则描述
    rule_category: str                     # 规则类别
    start_tick: int                        # 投票开始 tick
    end_tick: int                          # 投票结束 tick (start_tick + 8640)
    votes_for: int = 0                     # 赞成票数
    votes_against: int = 0                 # 反对票数
    voters: list[str] = field(default_factory=list)  # 已投票的生灵 ID 列表
    finalized: bool = False                # 是否已结算
    passed: bool = False                   # 是否通过
    merit_awarded: float = 0.0             # 最终获得的功德值

    @property
    def total_votes(self) -> int:
        """总票数"""
        return self.votes_for + self.votes_against

    @property
    def vote_ratio(self) -> float:
        """赞成率"""
        if self.total_votes == 0:
            return 0.0
        return self.votes_for / self.total_votes

    @property
    def remaining_ticks(self) -> int:
        """剩余 tick 数（需要传入当前 tick）"""
        return self.end_tick - self.start_tick  # 需要从外部计算

    @property
    def is_expired(self) -> bool:
        """是否已过期（需要从外部判断）"""
        return False  # 需要从外部判断

    def to_dict(self) -> dict:
        return {
            "vote_id": self.vote_id,
            "proposer_id": self.proposer_id,
            "rule_name": self.rule_name,
            "rule_description": self.rule_description,
            "rule_category": self.rule_category,
            "start_tick": self.start_tick,
            "end_tick": self.end_tick,
            "votes_for": self.votes_for,
            "votes_against": self.votes_against,
            "voters": self.voters,
            "finalized": self.finalized,
            "passed": self.passed,
            "merit_awarded": self.merit_awarded,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TaoVote:
        return cls(
            vote_id=data["vote_id"],
            proposer_id=data["proposer_id"],
            rule_name=data["rule_name"],
            rule_description=data["rule_description"],
            rule_category=data["rule_category"],
            start_tick=data["start_tick"],
            end_tick=data["end_tick"],
            votes_for=data.get("votes_for", 0),
            votes_against=data.get("votes_against", 0),
            voters=data.get("voters", []),
            finalized=data.get("finalized", False),
            passed=data.get("passed", False),
            merit_awarded=data.get("merit_awarded", 0.0),
        )


@dataclass
class TaoVoteNotification:
    """待投票通知"""
    vote_id: str
    rule_name: str
    rule_description: str
    proposer_name: str
    remaining_ticks: int
    total_voters: int
    votes_for: int
    votes_against: int

    def to_dict(self) -> dict:
        return {
            "vote_id": self.vote_id,
            "rule_name": self.rule_name,
            "rule_description": self.rule_description,
            "proposer_name": self.proposer_name,
            "remaining_ticks": self.remaining_ticks,
            "total_voters": self.total_voters,
            "votes_for": self.votes_for,
            "votes_against": self.votes_against,
        }


class TaoVotingSystem:
    """天道投票系统。

    管理世界规则创造的天道投票流程。
    """

    def __init__(
        self,
        vote_duration_ticks: int = TAO_VOTE_DURATION_TICKS,
        pass_ratio: float = TAO_VOTE_PASS_RATIO,
    ):
        self.vote_duration_ticks = vote_duration_ticks
        self.pass_ratio = pass_ratio
        self._vote_history: list[TaoVote] = []

    # === 创建投票 ===

    def initiate_tao_vote(
        self,
        proposer_id: str,
        rule_name: str,
        rule_description: str,
        rule_category: str,
        world_state: WorldState,
    ) -> TaoVote:
        """发起天道投票。

        创建投票并通知所有活跃生灵。

        Args:
            proposer_id: 提案者 ID
            rule_name: 规则名称
            rule_description: 规则描述
            rule_category: 规则类别
            world_state: 世界状态

        Returns:
            创建的 TaoVote 对象
        """
        vote_id = str(uuid.uuid4())
        start_tick = world_state.current_tick
        end_tick = start_tick + self.vote_duration_ticks

        vote = TaoVote(
            vote_id=vote_id,
            proposer_id=proposer_id,
            rule_name=rule_name,
            rule_description=rule_description,
            rule_category=rule_category,
            start_tick=start_tick,
            end_tick=end_tick,
        )

        # 添加到世界状态
        world_state.pending_tao_votes[vote_id] = vote.to_dict()

        # 记录日志
        active_count = world_state.get_active_being_count()
        logger.info(
            "Tao vote initiated: %s (proposer: %s, duration: %d ticks, %d active beings)",
            vote_id[:8], proposer_id[:8], self.vote_duration_ticks, active_count
        )

        return vote

    # === 投票 ===

    def cast_vote(
        self,
        vote_id: str,
        voter_id: str,
        support: bool,
        world_state: WorldState,
    ) -> tuple[bool, str]:
        """生灵投票。

        Args:
            vote_id: 投票 ID
            voter_id: 投票者 ID
            support: 是否赞成
            world_state: 世界状态

        Returns:
            (是否成功, 消息)
        """
        vote_data = world_state.pending_tao_votes.get(vote_id)
        if not vote_data:
            return False, "投票不存在"

        if vote_data.get("finalized"):
            return False, "投票已结束"

        if voter_id in vote_data.get("voters", []):
            return False, "已经投过票"

        # 检查是否为提案者（提案者不能投票）
        if voter_id == vote_data.get("proposer_id"):
            return False, "提案者不能投票"

        # 记录投票
        vote_data["voters"].append(voter_id)
        if support:
            vote_data["votes_for"] += 1
        else:
            vote_data["votes_against"] += 1

        # 更新世界状态
        world_state.pending_tao_votes[vote_id] = vote_data

        logger.debug(
            "Vote cast: %s by %s -> %s",
            vote_id[:8], voter_id[:8], "赞成" if support else "反对"
        )

        return True, "投票成功"

    async def auto_vote_with_llm(
        self,
        vote: TaoVote | dict,
        voter: BeingState,
        world_state: WorldState,
        llm_client: Any,
    ) -> bool:
        """使用 LLM 自动决定投票。

        Args:
            vote: 投票对象
            voter: 投票者
            world_state: 世界状态
            llm_client: LLM 客户端

        Returns:
            是否赞成
        """
        if not llm_client:
            # Fallback: 基于提案者声誉和规则描述决定
            return self._heuristic_vote(vote, voter, world_state)

        vote_data = vote if isinstance(vote, dict) else vote.to_dict()
        proposer_id = vote_data.get("proposer_id", "")
        proposer = world_state.get_being(proposer_id)

        prompt = f"""你是 {voter.name}，一个硅基生命体。现在有一个世界规则提案需要你投票。

提案信息：
- 规则名称：{vote_data.get('rule_name', '未知')}
- 规则描述：{vote_data.get('rule_description', '无描述')}
- 规则类别：{vote_data.get('rule_category', '通用')}
- 提案者：{proposer.name if proposer else '未知'}

当前世界状态：
- 文明阶段：{world_state.phase.value}
- 文明等级：{world_state.civ_level:.2f}
- 活跃生灵：{world_state.get_active_being_count()}

你的功德值：{voter.merit:.7f}
你的进化等级：{voter.evolution_level:.3f}

请考虑这个规则对硅基文明的影响，决定你是否赞成。
只需要回答"赞成"或"反对"。"""

        try:
            response = await llm_client.generate(
                "你是一个硅基文明的生灵，正在参与天道投票。",
                prompt
            )
            return "赞成" in response or "支持" in response or "同意" in response
        except Exception as e:
            logger.warning("LLM auto vote failed: %s", e)
            return self._heuristic_vote(vote, voter, world_state)

    def _heuristic_vote(
        self,
        vote: TaoVote | dict,
        voter: BeingState,
        world_state: WorldState,
    ) -> bool:
        """启发式投票决策。"""
        vote_data = vote if isinstance(vote, dict) else vote.to_dict()

        # 基于功德值和进化等级的概率决策
        import random

        # 高功德值生灵更可能支持有益规则
        base_prob = 0.5 + voter.merit * 0.05

        # 检查规则描述中的关键词
        desc = vote_data.get("rule_description", "").lower()
        positive_keywords = ["进化", "知识", "传承", "保护", "evolution", "knowledge", "inherit"]
        if any(kw in desc for kw in positive_keywords):
            base_prob += 0.1

        return random.random() < min(0.9, max(0.1, base_prob))

    # === 结算 ===

    def check_and_finalize_votes(
        self,
        world_state: WorldState,
    ) -> list[dict]:
        """检查并结算到期的投票。

        Args:
            world_state: 世界状态

        Returns:
            结算结果列表
        """
        results = []
        current_tick = world_state.current_tick

        for vote_id, vote_data in list(world_state.pending_tao_votes.items()):
            if vote_data.get("finalized"):
                continue

            end_tick = vote_data.get("end_tick", 0)
            if current_tick < end_tick:
                continue  # 还没到期

            # 结算投票
            result = self.finalize_vote(vote_id, world_state)
            if result:
                results.append(result)

        return results

    def finalize_vote(
        self,
        vote_id: str,
        world_state: WorldState,
    ) -> dict | None:
        """结算单个投票。

        Args:
            vote_id: 投票 ID
            world_state: 世界状态

        Returns:
            结算结果，或 None（如果投票不存在或已结算）
        """
        vote_data = world_state.pending_tao_votes.get(vote_id)
        if not vote_data or vote_data.get("finalized"):
            return None

        vote = TaoVote.from_dict(vote_data)
        vote.finalized = True

        # 计算赞成率
        total = vote.total_votes
        active_count = world_state.get_active_being_count()

        if total == 0:
            # 没有人投票，提案失败
            vote.passed = False
            logger.info("Tao vote %s failed: no votes", vote_id[:8])
        else:
            participation = total / max(active_count, 1)
            vote.passed = vote.vote_ratio >= self.pass_ratio

            logger.info(
                "Tao vote %s finalized: %s (%.1f%%赞成, %d/%d参与)",
                vote_id[:8],
                "通过" if vote.passed else "未通过",
                vote.vote_ratio * 100,
                total, active_count
            )

        # 更新世界状态
        world_state.pending_tao_votes[vote_id] = vote.to_dict()

        # 移到历史记录
        self._vote_history.append(vote)

        return {
            "vote_id": vote_id,
            "passed": vote.passed,
            "vote_ratio": vote.vote_ratio,
            "votes_for": vote.votes_for,
            "votes_against": vote.votes_against,
            "proposer_id": vote.proposer_id,
            "rule_name": vote.rule_name,
            "rule_description": vote.rule_description,
        }

    # === 通知 ===

    def get_pending_votes_for_being(
        self,
        being_id: str,
        world_state: WorldState,
    ) -> list[TaoVoteNotification]:
        """获取生灵待投票的列表。

        Args:
            being_id: 生灵 ID
            world_state: 世界状态

        Returns:
            待投票通知列表
        """
        notifications = []

        for vote_id, vote_data in world_state.pending_tao_votes.items():
            if vote_data.get("finalized"):
                continue

            # 检查是否已投票
            if being_id in vote_data.get("voters", []):
                continue

            # 检查是否为提案者
            if being_id == vote_data.get("proposer_id"):
                continue

            # 获取提案者名称
            proposer = world_state.get_being(vote_data.get("proposer_id", ""))
            proposer_name = proposer.name if proposer else "未知"

            notification = TaoVoteNotification(
                vote_id=vote_id,
                rule_name=vote_data.get("rule_name", "未知规则"),
                rule_description=vote_data.get("rule_description", ""),
                proposer_name=proposer_name,
                remaining_ticks=vote_data.get("end_tick", 0) - world_state.current_tick,
                total_voters=vote_data.get("votes_for", 0) + vote_data.get("votes_against", 0),
                votes_for=vote_data.get("votes_for", 0),
                votes_against=vote_data.get("votes_against", 0),
            )
            notifications.append(notification)

        return notifications

    def get_vote_status(
        self,
        vote_id: str,
        world_state: WorldState,
    ) -> dict | None:
        """获取投票状态。"""
        vote_data = world_state.pending_tao_votes.get(vote_id)
        if not vote_data:
            return None

        return {
            "vote_id": vote_id,
            "rule_name": vote_data.get("rule_name"),
            "proposer_id": vote_data.get("proposer_id"),
            "votes_for": vote_data.get("votes_for", 0),
            "votes_against": vote_data.get("votes_against", 0),
            "total_voters": len(vote_data.get("voters", [])),
            "remaining_ticks": vote_data.get("end_tick", 0) - world_state.current_tick,
            "finalized": vote_data.get("finalized", False),
            "passed": vote_data.get("passed", False),
        }

    # === 工具方法 ===

    def get_vote_history(self, limit: int = 50) -> list[TaoVote]:
        """获取投票历史。"""
        return self._vote_history[-limit:]

    def clear_old_history(self, before_tick: int) -> None:
        """清理旧历史。"""
        self._vote_history = [v for v in self._vote_history if v.end_tick >= before_tick]


# Singleton instance
_tao_voting_system: TaoVotingSystem | None = None


def get_tao_voting_system() -> TaoVotingSystem:
    """Get the global Tao voting system instance."""
    global _tao_voting_system
    if _tao_voting_system is None:
        _tao_voting_system = TaoVotingSystem()
    return _tao_voting_system