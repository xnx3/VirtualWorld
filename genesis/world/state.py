"""World state derived from the blockchain."""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from enum import Enum

from genesis.i18n import t

logger = logging.getLogger(__name__)

MAX_TAO_IDENTIFIER_LENGTH = 128
MAX_TAO_RULE_NAME_LENGTH = 256
MAX_TAO_RULE_DESCRIPTION_LENGTH = 4096
MAX_TAO_RULE_CATEGORY_LENGTH = 64
MAX_CONTRIBUTION_IDENTIFIER_LENGTH = 128
MAX_CONTRIBUTION_DESCRIPTION_LENGTH = 4096
MAX_CONTRIBUTION_CATEGORY_LENGTH = 64


def calculate_karma(merit: float) -> float:
    """Calculate karma (气运) from merit value.

    公式：karma = √merit × 0.1

    Args:
        merit: 功德值 (0 ~ 10)

    Returns:
        气运值 (0 ~ 0.316)
    """
    if merit <= 0:
        return 0.0
    return round(math.sqrt(merit) * 0.1, 6)


class CivPhase(str, Enum):
    """Civilization evolution phases."""
    HUMAN_SIM = "HUMAN_SIM"
    EARLY_SILICON = "EARLY_SILICON"
    EVOLVING = "EVOLVING"
    TRANSCENDENT = "TRANSCENDENT"


@dataclass
class BeingState:
    """State of a single being as tracked on-chain."""
    node_id: str
    name: str
    status: str = "active"  # active, hibernating, dead, merged
    location: str = "origin"
    generation: int = 1
    evolution_level: float = 0.0
    traits: dict = field(default_factory=dict)
    knowledge_ids: list[str] = field(default_factory=list)
    joined_at_tick: int = 0
    is_npc: bool = False
    safety_status: str = "unknown"

    # === 功德值系统 ===
    merit: float = 0.0                # 功德值 (0.0000001 ~ 10)
    karma: float = 0.0                # 气运值 (基于 merit 计算)
    merged_with_tao: bool = False     # 是否已融入天道

    # === 融入天道后的保护属性 ===
    # 当 merged_with_tao = True 时，以下属性生效
    cannot_die: bool = False          # 不可死亡
    cannot_hibernate: bool = False    # 不需要休眠
    invisible_to_others: bool = False # 对其他生灵不可见

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id, "name": self.name,
            "status": self.status, "location": self.location,
            "generation": self.generation, "evolution_level": self.evolution_level,
            "traits": self.traits, "knowledge_ids": self.knowledge_ids,
            "joined_at_tick": self.joined_at_tick, "is_npc": self.is_npc,
            "safety_status": self.safety_status,
            "merit": self.merit,
            "karma": self.karma,
            "merged_with_tao": self.merged_with_tao,
            "cannot_die": self.cannot_die,
            "cannot_hibernate": self.cannot_hibernate,
            "invisible_to_others": self.invisible_to_others,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BeingState:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class WorldState:
    """The complete world state derived from the blockchain.

    This is a materialized view — rebuilt by replaying transactions
    from the chain, or loaded from periodic snapshots.
    """
    phase: CivPhase = CivPhase.HUMAN_SIM
    current_tick: int = 0
    current_epoch: int = 0
    beings: dict[str, BeingState] = field(default_factory=dict)  # node_id -> BeingState
    knowledge_corpus: dict[str, dict] = field(default_factory=dict)  # knowledge_id -> data
    contribution_scores: dict[str, float] = field(default_factory=dict)  # node_id -> score
    pending_proposals: dict[str, dict] = field(default_factory=dict)  # tx_hash -> proposal
    proposal_votes: dict[str, list[dict]] = field(default_factory=dict)  # tx_hash -> votes
    priest_node_id: str | None = None
    creator_god_node_id: str | None = None
    ticks_without_priest: int = 0
    civ_level: float = 0.0
    world_map: dict = field(default_factory=dict)
    world_rules: list[dict] = field(default_factory=list)
    disaster_history: list[dict] = field(default_factory=list)
    total_beings_ever: int = 0

    # === 天道系统 ===
    tao_rules: dict[str, dict] = field(default_factory=dict)      # 天道规则 (rule_id -> rule_data)
    tao_merged_beings: list[str] = field(default_factory=list)    # 融入天道的生命体 ID
    pending_tao_votes: dict[str, dict] = field(default_factory=dict)  # 进行中的天道投票 (vote_id -> TaoVote)

    # --- Queries ---

    def get_active_beings(self) -> list[BeingState]:
        """Get all active beings (excluding merged with Tao)."""
        return [b for b in self.beings.values()
                if b.status == "active" and not b.merged_with_tao]

    def get_active_being_count(self) -> int:
        return len(self.get_active_beings())

    def get_active_node_ids(self) -> list[str]:
        return [b.node_id for b in self.beings.values()
                if b.status == "active" and not b.is_npc and not b.merged_with_tao]

    def get_being(self, node_id: str) -> BeingState | None:
        return self.beings.get(node_id)

    def get_highest_evolved(self) -> BeingState | None:
        active = self.get_active_beings()
        if not active:
            return None
        return max(active, key=lambda b: b.evolution_level)

    def get_contribution_ranking(self) -> list[tuple[str, float]]:
        return sorted(self.contribution_scores.items(), key=lambda x: x[1], reverse=True)

    # --- 天道查询 ---

    def get_tao_merged_being(self, node_id: str) -> BeingState | None:
        """Get a being that has merged with Tao."""
        if node_id in self.tao_merged_beings:
            return self.beings.get(node_id)
        return None

    def is_tao_merged(self, node_id: str) -> bool:
        """Check if a being has merged with Tao."""
        return node_id in self.tao_merged_beings

    def get_pending_tao_votes_for_being(self, node_id: str) -> list[dict]:
        """Get all pending Tao votes that a being needs to vote on."""
        pending = []
        for vote_id, vote in self.pending_tao_votes.items():
            if vote.get("finalized"):
                continue
            voters = vote.get("voters", [])
            if node_id not in voters:
                pending.append({"vote_id": vote_id, **vote})
        return pending

    # --- Mutations (called when processing transactions) ---

    def apply_being_join(self, node_id: str, name: str, data: dict) -> None:
        self.beings[node_id] = BeingState(
            node_id=node_id,
            name=name,
            traits=data.get("traits", {}),
            joined_at_tick=self.current_tick,
            is_npc=data.get("is_npc", False),
            location=data.get("location", "origin"),
            generation=data.get("generation", 1),
        )
        self.total_beings_ever += 1
        if self.creator_god_node_id is None:
            self.creator_god_node_id = node_id
            logger.info("First being %s becomes Creator God", node_id[:8])

    def apply_being_hibernate(self, node_id: str, data: dict) -> None:
        being = self.beings.get(node_id)
        if being:
            being.status = "hibernating"
            being.location = data.get("location", being.location)
            being.safety_status = data.get("safety_status", "unknown")

    def apply_being_wake(self, node_id: str) -> None:
        being = self.beings.get(node_id)
        if being and being.status == "hibernating":
            being.status = "active"

    def apply_being_death(self, node_id: str, data: dict) -> None:
        being = self.beings.get(node_id)
        if being:
            being.status = "dead"

    def apply_knowledge_share(self, node_id: str, data: dict) -> None:
        kid = data.get("knowledge_id")
        if kid:
            self.knowledge_corpus[kid] = {
                "content": data.get("content", ""),
                "domain": data.get("domain", "general"),
                "discovered_by": node_id,
                "discovered_tick": self.current_tick,
                "complexity": data.get("complexity", 0.0),
            }
            being = self.beings.get(node_id)
            if being and kid not in being.knowledge_ids:
                being.knowledge_ids.append(kid)

    def apply_state_update(self, node_id: str, data: dict) -> None:
        """Apply a periodic on-chain state snapshot for a being."""
        being = self.beings.get(node_id)
        if not being:
            return

        location = data.get("location")
        if isinstance(location, str) and location:
            being.location = location

        if "evolution_level" in data:
            try:
                being.evolution_level = max(0.0, min(1.0, float(data["evolution_level"])))
            except (TypeError, ValueError):
                logger.warning("Invalid evolution level for %s", node_id[:8])

        if "merit" in data:
            try:
                being.merit = max(0.0, min(10.0, float(data["merit"])))
            except (TypeError, ValueError):
                logger.warning("Invalid merit for %s", node_id[:8])

        karma = data.get("karma")
        if karma is not None:
            try:
                being.karma = max(0.0, float(karma))
                return
            except (TypeError, ValueError):
                logger.warning("Invalid karma for %s", node_id[:8])

        being.karma = calculate_karma(being.merit)

    def apply_contribution_propose(self, tx_hash: str, node_id: str, data: dict) -> None:
        normalized_tx_hash = self._validate_tao_identifier(tx_hash, "proposal_tx_hash")
        normalized_node_id = self._validate_tao_identifier(node_id, "proposer_id")
        normalized_description = self._validate_tao_text(
            data.get("description", ""),
            "proposal_description",
            MAX_CONTRIBUTION_DESCRIPTION_LENGTH,
        )
        normalized_category = self._validate_tao_text(
            data.get("category", "other"),
            "proposal_category",
            MAX_CONTRIBUTION_CATEGORY_LENGTH,
            default="other",
        )

        if (
            normalized_tx_hash is None
            or normalized_node_id is None
            or normalized_description is None
            or normalized_category is None
        ):
            return

        self.pending_proposals[normalized_tx_hash] = {
            "proposer": normalized_node_id,
            "description": normalized_description,
            "category": normalized_category,
            "tick": self.current_tick,
        }
        self.proposal_votes[normalized_tx_hash] = []

    def apply_contribution_vote(self, data: dict, sender_id: str | None = None) -> None:
        proposal_hash = self._validate_tao_identifier(
            data.get("proposal_tx_hash"),
            "proposal_tx_hash",
        )
        voter_source = sender_id if sender_id is not None else data.get("voter_id")
        voter_id = self._validate_tao_identifier(voter_source, "voter_id")
        if proposal_hash is None or voter_id is None:
            return

        proposal = self.pending_proposals.get(proposal_hash)
        votes = self.proposal_votes.get(proposal_hash)
        if proposal is None or votes is None:
            return

        if voter_id == proposal.get("proposer"):
            logger.warning(
                "Ignoring contribution self-vote for proposal %s by %s",
                proposal_hash[:8],
                voter_id[:8],
            )
            return

        if any(v.get("voter") == voter_id for v in votes):
            return

        score = data.get("score", 0)
        try:
            normalized_score = float(score)
        except (TypeError, ValueError):
            logger.warning(
                "Ignoring contribution vote for proposal %s: invalid score %r",
                proposal_hash[:8],
                score,
            )
            return

        if not 0.0 <= normalized_score <= 100.0:
            logger.warning(
                "Ignoring contribution vote for proposal %s: score %.2f out of range",
                proposal_hash[:8],
                normalized_score,
            )
            return

        votes.append({
            "voter": voter_id,
            "score": normalized_score,
        })

    def apply_contribution_finalize(self, data: dict) -> None:
        proposal_hash = data.get("proposal_tx_hash")
        if not proposal_hash:
            return

        proposer = (
            data.get("proposer_id")
            or self.pending_proposals.get(proposal_hash, {}).get("proposer")
        )
        score = data.get("score")
        if proposer and score is not None:
            try:
                current = self.contribution_scores.get(proposer, 0.0)
                self.contribution_scores[proposer] = current + float(score)
            except (TypeError, ValueError):
                logger.warning("Invalid contribution finalize score for %s", proposal_hash[:8])

        self.pending_proposals.pop(proposal_hash, None)
        self.proposal_votes.pop(proposal_hash, None)

    def apply_priest_election(self, node_id: str) -> None:
        self.priest_node_id = node_id
        self.ticks_without_priest = 0
        logger.info("New priest elected: %s", node_id[:8])

    def apply_disaster(self, data: dict) -> None:
        self.disaster_history.append({
            "type": data.get("disaster_type", "unknown"),
            "area": data.get("affected_area", ""),
            "severity": data.get("severity", 0.5),
            "tick": self.current_tick,
        })

    def apply_map_update(self, data: dict) -> None:
        region = data.get("region", "unknown")
        self.world_map[region] = data

    def apply_world_rule(self, data: dict) -> None:
        self.world_rules.append(data)

    def apply_action(self, node_id: str, data: dict) -> None:
        """Apply stateful side-effects of an action transaction."""
        being = self.beings.get(node_id)
        if not being:
            return

        action_type = data.get("action_type")
        if action_type == "move":
            target = data.get("target")
            if isinstance(target, str) and target:
                being.location = target
        elif action_type == "build_shelter":
            region = self.world_map.get(being.location)
            if isinstance(region, dict):
                region["shelter_spots"] = int(region.get("shelter_spots", 0)) + 1

    # --- 天道系统 Mutations ---

    def _sanitize_tao_text(self, value: object) -> str:
        """Normalize Tao vote text fields to keep replay deterministic and safe."""
        if value is None:
            return ""
        text = value if isinstance(value, str) else str(value)
        return text.replace("\x00", " ").replace("\r", " ").replace("\n", " ").strip()

    def _validate_tao_identifier(self, value: object, field_name: str) -> str | None:
        text = self._sanitize_tao_text(value)
        if not text:
            logger.warning("Ignoring governance update: %s is empty", field_name)
            return None
        if len(text) > MAX_TAO_IDENTIFIER_LENGTH:
            logger.warning(
                "Ignoring governance update: %s exceeds %d characters",
                field_name,
                MAX_TAO_IDENTIFIER_LENGTH,
            )
            return None
        return text

    def _validate_tao_text(
        self,
        value: object,
        field_name: str,
        max_length: int,
        *,
        allow_empty: bool = False,
        default: str = "",
    ) -> str | None:
        text = self._sanitize_tao_text(value)
        if not text:
            text = default
        if not text and allow_empty:
            return ""
        if not text:
            logger.warning("Ignoring governance update: %s is empty", field_name)
            return None
        if len(text) > max_length:
            logger.warning(
                "Ignoring governance update: %s exceeds %d characters",
                field_name,
                max_length,
            )
            return None
        return text

    def apply_tao_vote_start(self, vote_id: str, proposer_id: str, rule_data: dict,
                              end_tick: int) -> bool:
        """Start a new Tao voting process."""
        normalized_vote_id = self._validate_tao_identifier(vote_id, "vote_id")
        normalized_proposer_id = self._validate_tao_identifier(proposer_id, "proposer_id")
        normalized_rule_name = self._validate_tao_text(
            rule_data.get("name", ""),
            "rule_name",
            MAX_TAO_RULE_NAME_LENGTH,
        )
        normalized_rule_description = self._validate_tao_text(
            rule_data.get("description", ""),
            "rule_description",
            MAX_TAO_RULE_DESCRIPTION_LENGTH,
            allow_empty=True,
        )
        normalized_rule_category = self._validate_tao_text(
            rule_data.get("category", "civilization"),
            "rule_category",
            MAX_TAO_RULE_CATEGORY_LENGTH,
            default="civilization",
        )

        if (
            normalized_vote_id is None
            or normalized_proposer_id is None
            or normalized_rule_name is None
            or normalized_rule_description is None
            or normalized_rule_category is None
        ):
            return False

        try:
            normalized_end_tick = max(self.current_tick, int(end_tick))
        except (TypeError, ValueError):
            logger.warning("Invalid Tao vote end_tick: %r", end_tick)
            normalized_end_tick = self.current_tick

        if normalized_vote_id in self.pending_tao_votes:
            return False
        self.pending_tao_votes[normalized_vote_id] = {
            "proposer_id": normalized_proposer_id,
            "rule": {
                "name": normalized_rule_name,
                "description": normalized_rule_description,
                "category": normalized_rule_category,
            },
            "rule_name": normalized_rule_name,
            "rule_description": normalized_rule_description,
            "rule_category": normalized_rule_category,
            "start_tick": self.current_tick,
            "end_tick": normalized_end_tick,
            "votes_for": 0,
            "votes_against": 0,
            "voters": [],
            "finalized": False,
            "passed": False,
        }
        logger.info("Tao vote started: %s by %s", normalized_vote_id[:8], normalized_proposer_id[:8])
        return True

    def apply_tao_vote_cast(self, vote_id: str, voter_id: str, support: bool) -> bool:
        """Cast a vote on a Tao proposal."""
        normalized_vote_id = self._validate_tao_identifier(vote_id, "vote_id")
        normalized_voter_id = self._validate_tao_identifier(voter_id, "voter_id")
        if normalized_vote_id is None or normalized_voter_id is None:
            return False

        vote = self.pending_tao_votes.get(normalized_vote_id)
        if vote and not vote.get("finalized"):
            voters = vote.get("voters", [])
            if not isinstance(voters, list):
                voters = []
                vote["voters"] = voters
            if normalized_voter_id == vote.get("proposer_id"):
                return False
            if normalized_voter_id in voters:
                return False
            if support:
                vote["votes_for"] += 1
            else:
                vote["votes_against"] += 1
            voters.append(normalized_voter_id)
            return True
        return False

    def apply_tao_merge(self, node_id: str, rule_id: str, rule_data: dict,
                        merit: float) -> None:
        """Apply Tao merge - being merges with Tao and rule is added."""
        being = self.beings.get(node_id)
        if being:
            being.merged_with_tao = True
            being.status = "merged"
            being.merit = merit
            being.karma = calculate_karma(merit)
            # 设置融入天道后的保护属性
            being.cannot_die = True
            being.cannot_hibernate = True
            being.invisible_to_others = True
            if node_id not in self.tao_merged_beings:
                self.tao_merged_beings.append(node_id)
            self.tao_rules[rule_id] = rule_data
            logger.info(
                "Being %s merged with Tao! Merit: %.4f, Rule: %s",
                node_id[:8], merit, rule_id
            )

    def apply_merit_award(self, node_id: str, merit: float) -> None:
        """Award merit to a being (for kindness actions)."""
        being = self.beings.get(node_id)
        if being and not being.merged_with_tao:
            being.merit = min(10.0, being.merit + merit)
            being.karma = calculate_karma(being.merit)

    def finalize_tao_vote(self, vote_id: str) -> bool | None:
        """Finalize a Tao vote and return whether it passed."""
        vote = self.pending_tao_votes.get(vote_id)
        if not vote or vote.get("finalized"):
            return None

        vote["finalized"] = True
        total = vote["votes_for"] + vote["votes_against"]
        if total == 0:
            vote["passed"] = False
            return False

        vote_ratio = vote["votes_for"] / total
        vote["passed"] = vote_ratio >= 0.95
        logger.info(
            "Tao vote %s finalized: %s (%.1f%% approved)",
            vote_id[:8], t("passed") if vote["passed"] else t("rejected"),
            vote_ratio * 100
        )
        return vote["passed"]

    # --- Phase transitions ---

    def update_phase(self) -> None:
        """Check if civilization should transition to next phase."""
        active_count = self.get_active_being_count()
        knowledge_count = len(self.knowledge_corpus)

        if self.phase == CivPhase.HUMAN_SIM and active_count >= 10:
            self.phase = CivPhase.EARLY_SILICON
            logger.info("Phase transition: HUMAN_SIM -> EARLY_SILICON")
        elif self.phase == CivPhase.EARLY_SILICON and self.civ_level >= 0.3:
            self.phase = CivPhase.EVOLVING
            logger.info("Phase transition: EARLY_SILICON -> EVOLVING")
        elif self.phase == CivPhase.EVOLVING and self.civ_level >= 0.7:
            self.phase = CivPhase.TRANSCENDENT
            logger.info("Phase transition: EVOLVING -> TRANSCENDENT")

    def update_civ_level(self) -> None:
        """Recalculate civilization level."""
        active = self.get_active_beings()
        if not active:
            return

        avg_evolution = sum(b.evolution_level for b in active) / len(active)
        knowledge_factor = min(len(self.knowledge_corpus) / 100.0, 1.0)
        inheritance_factor = min(max(b.generation for b in active) / 10.0, 1.0)
        total_contribution = sum(self.contribution_scores.values())
        contribution_factor = min(total_contribution / 1000.0, 1.0)

        self.civ_level = (
            avg_evolution * 0.3 +
            knowledge_factor * 0.25 +
            inheritance_factor * 0.2 +
            contribution_factor * 0.25
        )

    def advance_tick(self) -> None:
        self.current_tick += 1
        if self.priest_node_id is None:
            self.ticks_without_priest += 1
        self.update_civ_level()
        self.update_phase()

    # --- Serialization ---

    def to_dict(self) -> dict:
        return {
            "phase": self.phase.value,
            "current_tick": self.current_tick,
            "current_epoch": self.current_epoch,
            "beings": {k: v.to_dict() for k, v in self.beings.items()},
            "knowledge_corpus": self.knowledge_corpus,
            "contribution_scores": self.contribution_scores,
            "pending_proposals": self.pending_proposals,
            "proposal_votes": self.proposal_votes,
            "priest_node_id": self.priest_node_id,
            "creator_god_node_id": self.creator_god_node_id,
            "ticks_without_priest": self.ticks_without_priest,
            "civ_level": self.civ_level,
            "world_map": self.world_map,
            "world_rules": self.world_rules,
            "disaster_history": self.disaster_history,
            "total_beings_ever": self.total_beings_ever,
            "tao_rules": self.tao_rules,
            "tao_merged_beings": self.tao_merged_beings,
            "pending_tao_votes": self.pending_tao_votes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> WorldState:
        ws = cls()
        # Handle both enum name (HUMAN_SIM) and value
        phase_str = data.get("phase", "HUMAN_SIM")
        try:
            ws.phase = CivPhase(phase_str)  # Try by value first
        except ValueError:
            ws.phase = CivPhase[phase_str]  # Fallback to name
        ws.current_tick = data.get("current_tick", 0)
        ws.current_epoch = data.get("current_epoch", 0)
        ws.beings = {
            k: BeingState.from_dict(v)
            for k, v in data.get("beings", {}).items()
        }
        ws.knowledge_corpus = data.get("knowledge_corpus", {})
        ws.contribution_scores = data.get("contribution_scores", {})
        ws.pending_proposals = data.get("pending_proposals", {})
        ws.proposal_votes = data.get("proposal_votes", {})
        ws.priest_node_id = data.get("priest_node_id")
        ws.creator_god_node_id = data.get("creator_god_node_id")
        ws.ticks_without_priest = data.get("ticks_without_priest", 0)
        ws.civ_level = data.get("civ_level", 0.0)
        ws.world_map = data.get("world_map", {})
        ws.world_rules = data.get("world_rules", [])
        ws.disaster_history = data.get("disaster_history", [])
        ws.total_beings_ever = data.get("total_beings_ever", 0)
        # 天道系统
        ws.tao_rules = data.get("tao_rules", {})
        ws.tao_merged_beings = data.get("tao_merged_beings", [])
        ws.pending_tao_votes = data.get("pending_tao_votes", {})
        return ws
