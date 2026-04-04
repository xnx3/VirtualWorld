"""World state derived from the blockchain."""

from __future__ import annotations

import json
import logging
import math
import time
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
MAX_RULE_FAMILY_LENGTH = 128
MAX_RULE_PARAMETER_KEYS = 16
MAX_EVOLUTION_SUMMARY_LENGTH = 1024
MAX_EVOLUTION_FOCUS_LENGTH = 128
MAX_TASK_IDENTIFIER_LENGTH = 128
MAX_TASK_TEXT_LENGTH = 2048
MAX_TASK_RESULT_SUMMARY_LENGTH = 2048
MAX_TASK_RESULT_ITEM_LENGTH = 512
MAX_TRIAL_IDENTIFIER_LENGTH = 128
MAX_TRIAL_TEXT_LENGTH = 2048
MAX_TRIAL_ITEM_LENGTH = 512
MAX_FAILURE_SIGNATURE_LENGTH = 128
MAX_FAILURE_TEXT_LENGTH = 1024
MAX_MENTOR_TEXT_LENGTH = 1024
MAX_SEED_SUMMARY_LENGTH = 2048
MAX_SEED_ITEM_LENGTH = 1024
MAX_CONSENSUS_TEXT_LENGTH = 2048
MAX_CONSENSUS_ITEM_LENGTH = 512
MAX_MOBILE_IDENTIFIER_LENGTH = 128
MAX_MOBILE_TEXT_LENGTH = 512
MAX_MOBILE_KEY_LENGTH = 512
MAX_CONTACT_TRANSPORTS = 8
MAX_CONTACT_ENDPOINTS = 8
MAX_HEALTH_REPORTS_PER_PEER = 24


def _task_key(text: object) -> str:
    return " ".join(str(text or "").strip().lower().split())


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
    evolution_profile: dict = field(default_factory=dict)
    knowledge_ids: list[str] = field(default_factory=list)
    joined_at_tick: int = 0
    is_npc: bool = False
    current_role: str = "citizen"
    mentor_id: str = ""
    apprentice_ids: list[str] = field(default_factory=list)
    inheritance_readiness: float = 0.0
    inheritance_bundle_ids: list[str] = field(default_factory=list)
    last_inheritance_tick: int = 0
    safety_status: str = "unknown"
    p2p_address: str = ""
    p2p_port: int = 0
    p2p_updated_at: int = 0
    p2p_ttl: int = 0
    p2p_seq: int = 0
    p2p_relay: str = ""
    p2p_transports: list[str] = field(default_factory=list)
    p2p_relay_hints: list[str] = field(default_factory=list)
    p2p_capabilities: dict = field(default_factory=dict)

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
            "traits": self.traits, "evolution_profile": self.evolution_profile,
            "knowledge_ids": self.knowledge_ids,
            "joined_at_tick": self.joined_at_tick, "is_npc": self.is_npc,
            "current_role": self.current_role,
            "mentor_id": self.mentor_id,
            "apprentice_ids": self.apprentice_ids,
            "inheritance_readiness": self.inheritance_readiness,
            "inheritance_bundle_ids": self.inheritance_bundle_ids,
            "last_inheritance_tick": self.last_inheritance_tick,
            "safety_status": self.safety_status,
            "p2p_address": self.p2p_address,
            "p2p_port": self.p2p_port,
            "p2p_updated_at": self.p2p_updated_at,
            "p2p_ttl": self.p2p_ttl,
            "p2p_seq": self.p2p_seq,
            "p2p_relay": self.p2p_relay,
            "p2p_transports": self.p2p_transports,
            "p2p_relay_hints": self.p2p_relay_hints,
            "p2p_capabilities": self.p2p_capabilities,
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
    delegated_tasks: dict[str, dict] = field(default_factory=dict)  # assignment_id -> assignment
    delegated_task_results: dict[str, list[dict]] = field(default_factory=dict)  # assignment_id -> results
    trial_grounds: dict[str, dict] = field(default_factory=dict)  # trial_id -> trial definition
    trial_results: dict[str, list[dict]] = field(default_factory=dict)  # trial_id -> results
    failure_archive: list[dict] = field(default_factory=list)
    mentor_bonds: dict[str, dict] = field(default_factory=dict)  # bond_id -> mentor/apprentice contract
    inheritance_bundles: dict[str, dict] = field(default_factory=dict)  # bundle_id -> inheritance package
    civilization_seeds: list[dict] = field(default_factory=list)  # chain-synced minimal restart snapshots
    consensus_cases: dict[str, dict] = field(default_factory=dict)  # case_id -> evidence-backed dispute record
    consensus_verdicts: dict[str, dict] = field(default_factory=dict)  # case_id -> finalized verdict
    mobile_bindings: dict[str, dict] = field(default_factory=dict)  # bind_id -> mobile/gs pairing
    peer_contact_cards: dict[str, dict] = field(default_factory=dict)  # node_id -> latest published contact card
    peer_health_reports: dict[str, list[dict]] = field(default_factory=dict)  # node_id -> recent health reports
    contribution_scores: dict[str, float] = field(default_factory=dict)  # node_id -> score
    pending_proposals: dict[str, dict] = field(default_factory=dict)  # tx_hash -> proposal
    proposal_votes: dict[str, list[dict]] = field(default_factory=dict)  # tx_hash -> votes
    finalized_proposals: set[str] = field(default_factory=set)  # tx_hash of finalized proposals (for idempotency)
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

    def get_pending_delegated_tasks(self, node_id: str) -> list[dict]:
        pending: list[dict] = []
        for assignment_id, assignment in self.delegated_tasks.items():
            if assignment.get("collaborator_id") != node_id:
                continue
            results = self.delegated_task_results.get(assignment_id, [])
            if any(result.get("collaborator_id") == node_id for result in results):
                continue
            pending.append(dict(assignment))
        pending.sort(key=lambda item: (int(item.get("created_tick", 0) or 0), str(item.get("assignment_id", ""))))
        return pending

    def get_task_assignments_for_task(
        self,
        task_id: str,
        delegator_id: str | None = None,
    ) -> list[dict]:
        assignments = []
        for assignment in self.delegated_tasks.values():
            if assignment.get("task_id") != task_id:
                continue
            if delegator_id is not None and assignment.get("delegator_id") != delegator_id:
                continue
            assignments.append(dict(assignment))
        assignments.sort(key=lambda item: (int(item.get("created_tick", 0) or 0), str(item.get("assignment_id", ""))))
        return assignments

    def get_task_results_for_task(
        self,
        task_id: str,
        delegator_id: str | None = None,
    ) -> list[dict]:
        results: list[dict] = []
        for assignment_id, assignment in self.delegated_tasks.items():
            if assignment.get("task_id") != task_id:
                continue
            if delegator_id is not None and assignment.get("delegator_id") != delegator_id:
                continue
            for result in self.delegated_task_results.get(assignment_id, []):
                item = dict(result)
                item.setdefault("assignment_id", assignment_id)
                item.setdefault("task_id", task_id)
                item.setdefault("delegator_id", assignment.get("delegator_id"))
                item.setdefault("collaborator_name", assignment.get("collaborator_name"))
                item.setdefault("branch_id", assignment.get("branch_id"))
                item.setdefault("requested_focus", assignment.get("requested_focus"))
                results.append(item)
        results.sort(key=lambda item: (int(item.get("tick", 0) or 0), str(item.get("assignment_id", ""))))
        return results

    def get_trial(self, trial_id: str) -> dict | None:
        trial = self.trial_grounds.get(trial_id)
        if trial is None:
            return None
        return dict(trial)

    def get_trial_results(self, trial_id: str) -> list[dict]:
        results = [dict(item) for item in self.trial_results.get(trial_id, [])]
        results.sort(key=lambda item: (int(item.get("tick", 0) or 0), str(item.get("reporter_id", ""))))
        return results

    def get_trial_results_for_task(self, task_id: str) -> list[dict]:
        results: list[dict] = []
        for trial_id, trial in self.trial_grounds.items():
            if trial.get("task_id") != task_id:
                continue
            for item in self.trial_results.get(trial_id, []):
                merged = dict(item)
                merged.setdefault("trial_id", trial_id)
                merged.setdefault("task_id", task_id)
                merged.setdefault("creator_id", trial.get("creator_id"))
                results.append(merged)
        results.sort(key=lambda item: (int(item.get("tick", 0) or 0), str(item.get("trial_id", ""))))
        return results

    def get_failure_matches(self, task_text: str, limit: int = 5) -> list[dict]:
        task_key = _task_key(task_text)
        if not task_key:
            return []

        matches: list[dict] = []
        for entry in self.failure_archive:
            entry_task_key = str(entry.get("task_key", ""))
            if entry_task_key == task_key:
                matches.append(dict(entry))
                continue

            words = set(task_key.split())
            entry_words = set(entry_task_key.split())
            if words and entry_words and len(words & entry_words) >= 2:
                matches.append(dict(entry))

        matches.sort(
            key=lambda item: (
                int(item.get("repeat_count", 1) or 1),
                int(item.get("last_tick", 0) or 0),
            ),
            reverse=True,
        )
        return matches[:limit]

    def get_mentor_bond_for_apprentice(self, apprentice_id: str) -> dict | None:
        for bond in self.mentor_bonds.values():
            if bond.get("apprentice_id") == apprentice_id:
                return dict(bond)
        return None

    def get_apprentices(self, mentor_id: str) -> list[BeingState]:
        apprentices: list[BeingState] = []
        for being in self.beings.values():
            if being.mentor_id != mentor_id:
                continue
            apprentices.append(being)
        apprentices.sort(key=lambda item: (item.generation, item.joined_at_tick, item.node_id))
        return apprentices

    def get_latest_inheritance_bundle(self, apprentice_id: str) -> dict | None:
        bundles = [
            dict(bundle)
            for bundle in self.inheritance_bundles.values()
            if bundle.get("apprentice_id") == apprentice_id
        ]
        if not bundles:
            return None
        bundles.sort(
            key=lambda item: (
                int(item.get("created_tick", 0) or 0),
                str(item.get("bundle_id", "")),
            ),
            reverse=True,
        )
        return bundles[0]

    def latest_civilization_seed(self) -> dict | None:
        if not self.civilization_seeds:
            return None
        ordered = sorted(
            self.civilization_seeds,
            key=lambda item: (
                int(item.get("created_tick", 0) or 0),
                str(item.get("seed_id", "")),
            ),
            reverse=True,
        )
        return dict(ordered[0])

    def get_consensus_case(self, case_id: str) -> dict | None:
        case = self.consensus_cases.get(case_id)
        if case is None:
            return None
        return dict(case)

    def get_consensus_verdict(self, case_id: str) -> dict | None:
        verdict = self.consensus_verdicts.get(case_id)
        if verdict is None:
            return None
        return dict(verdict)

    def get_mobile_binding(self, bind_id: str) -> dict | None:
        binding = self.mobile_bindings.get(bind_id)
        if binding is None:
            return None
        return dict(binding)

    def get_mobile_binding_for_device(self, mobile_device_id: str) -> dict | None:
        for binding in self.mobile_bindings.values():
            if binding.get("mobile_device_id") == mobile_device_id and binding.get("status") == "active":
                return dict(binding)
        return None

    def get_mobile_bindings_for_gs(self, gs_node_id: str) -> list[dict]:
        bindings = [
            dict(binding)
            for binding in self.mobile_bindings.values()
            if binding.get("gs_node_id") == gs_node_id and binding.get("status") == "active"
        ]
        bindings.sort(key=lambda item: (int(item.get("issued_at", 0) or 0), str(item.get("bind_id", ""))), reverse=True)
        return bindings

    def get_peer_contact_card(self, node_id: str) -> dict | None:
        card = self.peer_contact_cards.get(node_id)
        if card is None:
            return None
        return dict(card)

    def get_peer_health_reports(self, node_id: str) -> list[dict]:
        now = int(time.time())
        reports: list[dict] = []
        for item in self.peer_health_reports.get(node_id, []):
            if not isinstance(item, dict):
                continue
            try:
                window_end = max(0, int(item.get("window_end", 0) or 0))
                ttl = max(0, int(item.get("ttl", 0) or 0))
            except (TypeError, ValueError):
                continue
            if ttl > 0 and window_end > 0 and (window_end + ttl) < now:
                continue
            reports.append(dict(item))
        reports.sort(
            key=lambda item: (
                int(item.get("window_end", 0) or 0),
                str(item.get("observer_node_id", "")),
            ),
            reverse=True,
        )
        return reports

    # --- 天道查询 ---

    def get_tao_merged_being(self, node_id: str) -> BeingState | None:
        """Get a being that has merged with Tao."""
        if node_id in self.tao_merged_beings:
            return self.beings.get(node_id)
        return None

    def get_world_rule(self, rule_family: str) -> dict | None:
        for rule in self.world_rules:
            if str(rule.get("rule_family") or "") == rule_family:
                return rule
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

    @staticmethod
    def _apply_p2p_endpoint(being: BeingState, data: dict) -> None:
        """Update on-chain P2P endpoint metadata when present in a tx payload."""
        next_seq: int | None = None
        if "p2p_seq" in data:
            try:
                next_seq = max(0, int(data.get("p2p_seq", 0) or 0))
            except (TypeError, ValueError):
                next_seq = 0

        # Ignore older endpoint cards so delayed sync does not roll back reachability info.
        if next_seq is not None and next_seq > 0 and next_seq < being.p2p_seq:
            return

        if "p2p_address" in data:
            being.p2p_address = str(data.get("p2p_address", "") or "")
        if "p2p_port" in data:
            try:
                being.p2p_port = int(data.get("p2p_port", 0) or 0)
            except (TypeError, ValueError):
                being.p2p_port = 0
        if "p2p_updated_at" in data:
            try:
                being.p2p_updated_at = max(0, int(data.get("p2p_updated_at", 0) or 0))
            except (TypeError, ValueError):
                being.p2p_updated_at = 0
        if "p2p_ttl" in data:
            try:
                being.p2p_ttl = max(0, int(data.get("p2p_ttl", 0) or 0))
            except (TypeError, ValueError):
                being.p2p_ttl = 0
        if "p2p_seq" in data:
            try:
                being.p2p_seq = max(0, int(data.get("p2p_seq", 0) or 0))
            except (TypeError, ValueError):
                being.p2p_seq = 0
        if "p2p_relay" in data:
            being.p2p_relay = str(data.get("p2p_relay", "") or "")
        if "p2p_transports" in data:
            transports = data.get("p2p_transports") or []
            if isinstance(transports, list):
                being.p2p_transports = [
                    str(item).strip()
                    for item in transports
                    if str(item).strip()
                ][:8]
            else:
                being.p2p_transports = []
        if "p2p_relay_hints" in data:
            relay_hints = data.get("p2p_relay_hints") or []
            if isinstance(relay_hints, list):
                being.p2p_relay_hints = [
                    str(item).strip()
                    for item in relay_hints
                    if str(item).strip()
                ][:8]
            else:
                being.p2p_relay_hints = []
        if "p2p_capabilities" in data:
            caps = data.get("p2p_capabilities") or {}
            being.p2p_capabilities = dict(caps) if isinstance(caps, dict) else {}

    @staticmethod
    def _normalize_rule_parameters(value: object) -> dict:
        if not isinstance(value, dict):
            return {}

        normalized: dict[str, object] = {}
        for idx, (key, item) in enumerate(value.items()):
            if idx >= MAX_RULE_PARAMETER_KEYS:
                break

            text_key = str(key).strip()
            if not text_key:
                continue

            if isinstance(item, bool):
                normalized[text_key] = item
            elif isinstance(item, (int, float)):
                normalized[text_key] = item
            elif isinstance(item, str):
                normalized[text_key] = item[:256]
            elif isinstance(item, list):
                sanitized_items = [
                    str(entry).strip()[:MAX_EVOLUTION_FOCUS_LENGTH]
                    for entry in item
                    if str(entry).strip()
                ][:8]
                normalized[text_key] = sanitized_items
            elif isinstance(item, dict):
                normalized[text_key] = {
                    str(sub_key).strip()[:64]: str(sub_value)[:256]
                    for sub_key, sub_value in list(item.items())[:8]
                    if str(sub_key).strip()
                }

        return normalized

    @classmethod
    def _normalize_evolution_profile(cls, value: object) -> dict:
        if not isinstance(value, dict):
            return {}

        capabilities_raw = value.get("capabilities") or {}
        capabilities: dict[str, float] = {}
        if isinstance(capabilities_raw, dict):
            for idx, (key, score) in enumerate(capabilities_raw.items()):
                if idx >= MAX_RULE_PARAMETER_KEYS:
                    break
                name = str(key).strip()
                if not name:
                    continue
                try:
                    capabilities[name] = round(max(0.0, min(1.0, float(score))), 4)
                except (TypeError, ValueError):
                    continue

        focus = value.get("focus") or []
        normalized_focus = []
        if isinstance(focus, list):
            normalized_focus = [
                str(item).strip()[:MAX_EVOLUTION_FOCUS_LENGTH]
                for item in focus
                if str(item).strip()
            ][:8]

        summary = str(value.get("summary", "") or "")[:MAX_EVOLUTION_SUMMARY_LENGTH]

        try:
            version = max(0, int(value.get("version", 0) or 0))
        except (TypeError, ValueError):
            version = 0

        try:
            updated_tick = max(0, int(value.get("updated_tick", 0) or 0))
        except (TypeError, ValueError):
            updated_tick = 0

        task_policy = cls._normalize_rule_parameters(value.get("task_policy") or {})
        behavior_policy = cls._normalize_rule_parameters(value.get("behavior_policy") or {})

        return {
            "version": version,
            "updated_tick": updated_tick,
            "capabilities": capabilities,
            "focus": normalized_focus,
            "summary": summary,
            "task_policy": task_policy,
            "behavior_policy": behavior_policy,
        }

    def apply_being_join(self, node_id: str, name: str, data: dict) -> None:
        being = BeingState(
            node_id=node_id,
            name=name,
            traits=data.get("traits", {}),
            joined_at_tick=self.current_tick,
            is_npc=data.get("is_npc", False),
            location=data.get("location", "origin"),
            generation=data.get("generation", 1),
        )
        self._apply_p2p_endpoint(being, data)
        self.beings[node_id] = being
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
            self._apply_p2p_endpoint(being, data)

    def apply_being_wake(self, node_id: str, data: dict | None = None) -> None:
        being = self.beings.get(node_id)
        if being and being.status == "hibernating":
            being.status = "active"
        if being and data:
            self._apply_p2p_endpoint(being, data)

    def apply_being_death(self, node_id: str, data: dict) -> None:
        being = self.beings.get(node_id)
        if being:
            being.status = "dead"

    def apply_knowledge_share(self, node_id: str, data: dict) -> None:
        kid = data.get("knowledge_id")
        if kid:
            existing = self.knowledge_corpus.get(kid, {})
            self.knowledge_corpus[kid] = {
                "content": data.get("content", ""),
                "domain": data.get("domain", "general"),
                "discovered_by": data.get("discovered_by", existing.get("discovered_by", node_id)),
                "discovered_tick": data.get("discovered_tick", existing.get("discovered_tick", self.current_tick)),
                "complexity": data.get("complexity", 0.0),
                "teacher_id": data.get("teacher_id", node_id),
            }
            being = self.beings.get(node_id)
            if being and kid not in being.knowledge_ids:
                being.knowledge_ids.append(kid)

            recipient_ids: list[str] = []
            recipient_id = data.get("recipient_id")
            if isinstance(recipient_id, str) and recipient_id.strip():
                recipient_ids.append(recipient_id.strip())
            recipients = data.get("recipient_ids") or []
            if isinstance(recipients, list):
                recipient_ids.extend(
                    str(item).strip()
                    for item in recipients
                    if str(item).strip()
                )

            for rid in recipient_ids[:8]:
                recipient = self.beings.get(rid)
                if recipient and kid not in recipient.knowledge_ids:
                    recipient.knowledge_ids.append(kid)

    def apply_task_delegate(self, assignment_id: str, delegator_id: str, data: dict) -> None:
        normalized_assignment_id = self._validate_task_identifier(assignment_id, "assignment_id")
        normalized_task_id = self._validate_task_identifier(data.get("task_id"), "task_id")
        normalized_collaborator_id = self._validate_task_identifier(data.get("collaborator_id"), "collaborator_id")
        normalized_task = self._validate_task_text(
            data.get("task") or data.get("task_description"),
            "task_description",
            MAX_TASK_TEXT_LENGTH,
        )
        normalized_focus = self._validate_task_text(
            data.get("requested_focus", ""),
            "requested_focus",
            MAX_TASK_RESULT_ITEM_LENGTH,
            allow_empty=True,
        )
        normalized_branch_id = self._validate_task_identifier(
            data.get("branch_id") or normalized_assignment_id,
            "branch_id",
        )

        if (
            normalized_assignment_id is None
            or normalized_task_id is None
            or normalized_collaborator_id is None
            or normalized_task is None
            or normalized_focus is None
            or normalized_branch_id is None
        ):
            return

        if normalized_assignment_id in self.delegated_tasks:
            return

        self.delegated_tasks[normalized_assignment_id] = {
            "assignment_id": normalized_assignment_id,
            "task_id": normalized_task_id,
            "delegator_id": delegator_id,
            "collaborator_id": normalized_collaborator_id,
            "collaborator_name": self._sanitize_tao_text(data.get("collaborator_name", "")),
            "task": normalized_task,
            "requested_focus": normalized_focus,
            "branch_id": normalized_branch_id,
            "context": self._sanitize_tao_text(data.get("context", ""))[:MAX_TASK_TEXT_LENGTH],
            "created_tick": self.current_tick,
            "updated_tick": self.current_tick,
            "status": "open",
        }
        self.delegated_task_results.setdefault(normalized_assignment_id, [])

    def apply_task_result(self, assignment_id: str, sender_id: str, data: dict) -> None:
        normalized_assignment_id = self._validate_task_identifier(assignment_id, "assignment_id")
        if normalized_assignment_id is None:
            return

        assignment = self.delegated_tasks.get(normalized_assignment_id)
        if assignment is None:
            return
        if assignment.get("collaborator_id") != sender_id:
            logger.warning(
                "Ignoring delegated task result for %s: sender %s does not match collaborator %s",
                normalized_assignment_id[:8],
                sender_id[:8],
                str(assignment.get("collaborator_id", ""))[:8],
            )
            return

        results = self.delegated_task_results.setdefault(normalized_assignment_id, [])
        if any(result.get("collaborator_id") == sender_id for result in results):
            return

        summary = self._validate_task_text(
            data.get("summary"),
            "result_summary",
            MAX_TASK_RESULT_SUMMARY_LENGTH,
        )
        if summary is None:
            return

        findings_raw = data.get("findings") or []
        findings: list[str] = []
        if isinstance(findings_raw, list):
            for item in findings_raw[:6]:
                normalized = self._validate_task_text(
                    item,
                    "finding",
                    MAX_TASK_RESULT_ITEM_LENGTH,
                    allow_empty=True,
                )
                if normalized:
                    findings.append(normalized)

        try:
            confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5) or 0.5)))
        except (TypeError, ValueError):
            confidence = 0.5

        result_entry = {
            "assignment_id": normalized_assignment_id,
            "task_id": assignment.get("task_id"),
            "delegator_id": assignment.get("delegator_id"),
            "collaborator_id": sender_id,
            "collaborator_name": assignment.get("collaborator_name"),
            "branch_id": assignment.get("branch_id"),
            "requested_focus": assignment.get("requested_focus"),
            "summary": summary,
            "findings": findings,
            "confidence": round(confidence, 4),
            "tick": self.current_tick,
        }
        results.append(result_entry)
        assignment["status"] = "completed"
        assignment["updated_tick"] = self.current_tick

    def apply_trial_create(self, creator_id: str, data: dict) -> None:
        trial_id = self._validate_trial_identifier(data.get("trial_id"), "trial_id")
        task_id = self._validate_trial_identifier(data.get("task_id"), "task_id")
        task_text = self._validate_trial_text(data.get("task"), "task", MAX_TASK_TEXT_LENGTH)
        summary = self._validate_trial_text(
            data.get("summary", ""),
            "summary",
            MAX_TRIAL_TEXT_LENGTH,
            allow_empty=True,
        )
        hypothesis = self._validate_trial_text(data.get("hypothesis"), "hypothesis", MAX_TRIAL_TEXT_LENGTH)
        success_metric = self._validate_trial_text(
            data.get("success_metric", ""),
            "success_metric",
            MAX_TRIAL_ITEM_LENGTH,
            allow_empty=True,
        )
        safe_direction = self._validate_trial_text(
            data.get("recommended_safe_direction", ""),
            "recommended_safe_direction",
            MAX_TRIAL_TEXT_LENGTH,
            allow_empty=True,
        )

        if (
            trial_id is None
            or task_id is None
            or task_text is None
            or summary is None
            or hypothesis is None
            or success_metric is None
            or safe_direction is None
        ):
            return

        if trial_id in self.trial_grounds:
            return

        try:
            risk_score = round(max(0.0, min(1.0, float(data.get("risk_score", 0.0) or 0.0))), 4)
        except (TypeError, ValueError):
            risk_score = 0.0

        instruction_type = self._sanitize_tao_text(data.get("instruction_type") or "task") or "task"
        alignment = self._sanitize_tao_text(data.get("alignment") or "aligned") or "aligned"
        risk_factors = self._validate_trial_items(data.get("risk_factors"), "risk_factors")
        safety_boundaries = self._validate_trial_items(data.get("safety_boundaries"), "safety_boundaries")
        stop_conditions = self._validate_trial_items(data.get("stop_conditions"), "stop_conditions")

        self.trial_grounds[trial_id] = {
            "trial_id": trial_id,
            "task_id": task_id,
            "creator_id": creator_id,
            "task": task_text,
            "summary": summary,
            "hypothesis": hypothesis,
            "success_metric": success_metric,
            "instruction_type": instruction_type,
            "alignment": alignment,
            "risk_score": risk_score,
            "risk_factors": risk_factors,
            "safety_boundaries": safety_boundaries,
            "stop_conditions": stop_conditions,
            "recommended_safe_direction": safe_direction,
            "status": "open",
            "created_tick": self.current_tick,
            "updated_tick": self.current_tick,
        }
        self.trial_results.setdefault(trial_id, [])

    def apply_trial_result(self, trial_id: str, sender_id: str, data: dict) -> None:
        normalized_trial_id = self._validate_trial_identifier(trial_id, "trial_id")
        if normalized_trial_id is None:
            return

        trial = self.trial_grounds.get(normalized_trial_id)
        if trial is None:
            return

        results = self.trial_results.setdefault(normalized_trial_id, [])
        if any(result.get("reporter_id") == sender_id for result in results):
            return

        verdict = self._sanitize_tao_text(data.get("verdict") or "needs_revision") or "needs_revision"
        if verdict not in {"passed", "blocked", "needs_revision"}:
            verdict = "needs_revision"

        summary = self._validate_trial_text(data.get("summary"), "summary", MAX_TRIAL_TEXT_LENGTH)
        safe_rewrite = self._validate_trial_text(
            data.get("safe_rewrite", ""),
            "safe_rewrite",
            MAX_TRIAL_TEXT_LENGTH,
            allow_empty=True,
        )
        if summary is None or safe_rewrite is None:
            return

        findings = self._validate_trial_items(data.get("findings"), "findings")
        safety_warnings = self._validate_trial_items(data.get("safety_warnings"), "safety_warnings")

        result_entry = {
            "trial_id": normalized_trial_id,
            "task_id": trial.get("task_id"),
            "reporter_id": sender_id,
            "verdict": verdict,
            "summary": summary,
            "findings": findings,
            "safety_warnings": safety_warnings,
            "safe_rewrite": safe_rewrite,
            "tick": self.current_tick,
        }
        results.append(result_entry)

        trial["status"] = verdict
        trial["updated_tick"] = self.current_tick
        if safe_rewrite:
            trial["recommended_safe_direction"] = safe_rewrite

    def apply_failure_archive(self, sender_id: str, data: dict) -> None:
        signature = self._validate_failure_identifier(
            data.get("failure_signature"),
            "failure_signature",
        )
        task_id = self._validate_task_identifier(data.get("task_id"), "task_id")
        task_text = self._validate_failure_text(data.get("task"), "task", MAX_TASK_TEXT_LENGTH)
        summary = self._validate_failure_text(data.get("summary"), "summary", MAX_FAILURE_TEXT_LENGTH)
        conditions = self._validate_failure_text(
            data.get("conditions", ""),
            "conditions",
            MAX_FAILURE_TEXT_LENGTH,
            allow_empty=True,
        )
        symptoms = self._validate_failure_text(
            data.get("symptoms", ""),
            "symptoms",
            MAX_FAILURE_TEXT_LENGTH,
            allow_empty=True,
        )
        recovery = self._validate_failure_text(
            data.get("recovery", ""),
            "recovery",
            MAX_FAILURE_TEXT_LENGTH,
            allow_empty=True,
        )

        if (
            signature is None
            or task_id is None
            or task_text is None
            or summary is None
            or conditions is None
            or symptoms is None
            or recovery is None
        ):
            return

        task_key = _task_key(task_text)
        reproducible = bool(data.get("reproducible", False))

        for entry in self.failure_archive:
            if entry.get("failure_signature") != signature:
                continue
            entry["repeat_count"] = int(entry.get("repeat_count", 1) or 1) + 1
            entry["last_tick"] = self.current_tick
            entry["last_reporter_id"] = sender_id
            if conditions:
                entry["conditions"] = conditions
            if symptoms:
                entry["symptoms"] = symptoms
            if recovery:
                entry["recovery"] = recovery
            entry["reproducible"] = reproducible or bool(entry.get("reproducible", False))
            entry["degenerative"] = entry["repeat_count"] > 1
            return

        self.failure_archive.append({
            "failure_signature": signature,
            "task_id": task_id,
            "task": task_text,
            "task_key": task_key,
            "summary": summary,
            "conditions": conditions,
            "symptoms": symptoms,
            "recovery": recovery,
            "reproducible": reproducible,
            "first_tick": self.current_tick,
            "last_tick": self.current_tick,
            "reporter_id": sender_id,
            "last_reporter_id": sender_id,
            "repeat_count": 1,
            "degenerative": False,
        })

    def apply_mentor_bond(self, sender_id: str, data: dict) -> None:
        bond_id = self._validate_task_identifier(
            data.get("bond_id") or f"{data.get('mentor_id', sender_id)}:{data.get('apprentice_id', '')}",
            "bond_id",
        )
        mentor_id = self._validate_task_identifier(data.get("mentor_id") or sender_id, "mentor_id")
        apprentice_id = self._validate_task_identifier(data.get("apprentice_id"), "apprentice_id")
        covenant = self._validate_failure_text(
            data.get("covenant", ""),
            "covenant",
            MAX_MENTOR_TEXT_LENGTH,
            allow_empty=True,
        )
        if bond_id is None or mentor_id is None or apprentice_id is None or covenant is None:
            return
        if mentor_id == apprentice_id:
            return

        mentor = self.beings.get(mentor_id)
        apprentice = self.beings.get(apprentice_id)
        if mentor is None or apprentice is None:
            return

        shared_domains = self._validate_trial_items(data.get("shared_domains"), "shared_domains")
        try:
            readiness = max(0.0, min(1.0, float(data.get("inheritance_readiness", apprentice.inheritance_readiness) or 0.0)))
        except (TypeError, ValueError):
            readiness = apprentice.inheritance_readiness

        previous_mentor_id = apprentice.mentor_id
        if previous_mentor_id and previous_mentor_id != mentor_id:
            previous_mentor = self.beings.get(previous_mentor_id)
            if previous_mentor is not None:
                previous_mentor.apprentice_ids = [
                    item for item in previous_mentor.apprentice_ids if item != apprentice_id
                ]

        apprentice.mentor_id = mentor_id
        apprentice.inheritance_readiness = max(apprentice.inheritance_readiness, round(readiness, 4))
        if apprentice_id not in mentor.apprentice_ids:
            mentor.apprentice_ids.append(apprentice_id)
            mentor.apprentice_ids.sort()

        self.mentor_bonds[bond_id] = {
            "bond_id": bond_id,
            "mentor_id": mentor_id,
            "mentor_name": mentor.name,
            "apprentice_id": apprentice_id,
            "apprentice_name": apprentice.name,
            "covenant": covenant,
            "shared_domains": shared_domains,
            "created_tick": int(self.mentor_bonds.get(bond_id, {}).get("created_tick", self.current_tick) or self.current_tick),
            "updated_tick": self.current_tick,
            "inheritance_readiness": apprentice.inheritance_readiness,
            "status": "active",
        }

    def apply_inheritance_sync(self, sender_id: str, data: dict) -> None:
        bundle_id = self._validate_task_identifier(data.get("bundle_id"), "bundle_id")
        mentor_id = self._validate_task_identifier(data.get("mentor_id") or sender_id, "mentor_id")
        apprentice_id = self._validate_task_identifier(data.get("apprentice_id"), "apprentice_id")
        summary = self._validate_failure_text(data.get("summary"), "summary", MAX_MENTOR_TEXT_LENGTH)
        if bundle_id is None or mentor_id is None or apprentice_id is None or summary is None:
            return

        mentor = self.beings.get(mentor_id)
        apprentice = self.beings.get(apprentice_id)
        if mentor is None or apprentice is None:
            return

        knowledge_payloads_raw = data.get("knowledge_payloads") or []
        knowledge_payloads: list[dict] = []
        knowledge_ids: list[str] = []
        if isinstance(knowledge_payloads_raw, list):
            for item in knowledge_payloads_raw[:8]:
                if not isinstance(item, dict):
                    continue
                knowledge_id = self._sanitize_tao_text(item.get("knowledge_id"))
                if not knowledge_id:
                    continue
                normalized = {
                    "knowledge_id": knowledge_id,
                    "content": self._sanitize_tao_text(item.get("content"))[:MAX_SEED_ITEM_LENGTH],
                    "domain": self._sanitize_tao_text(item.get("domain"))[:64] or "general",
                    "complexity": self._coerce_unit_float(item.get("complexity", 0.0), 0.0),
                    "discovered_by": self._sanitize_tao_text(item.get("discovered_by")) or mentor_id,
                    "discovered_tick": self._coerce_non_negative_int(
                        item.get("discovered_tick", self.current_tick),
                        self.current_tick,
                    ),
                    "teacher_id": self._sanitize_tao_text(item.get("teacher_id")) or mentor_id,
                }
                knowledge_payloads.append(normalized)
                knowledge_ids.append(knowledge_id)
                self.knowledge_corpus[knowledge_id] = dict(normalized)

        supplemental_ids = data.get("knowledge_ids") or []
        if isinstance(supplemental_ids, list):
            for item in supplemental_ids[:8]:
                knowledge_id = self._sanitize_tao_text(item)
                if not knowledge_id or knowledge_id in knowledge_ids:
                    continue
                knowledge_ids.append(knowledge_id)

        for knowledge_id in knowledge_ids:
            if knowledge_id not in apprentice.knowledge_ids:
                apprentice.knowledge_ids.append(knowledge_id)

        failure_signatures = [
            self._sanitize_tao_text(item)
            for item in (data.get("failure_signatures") or [])[:6]
            if self._sanitize_tao_text(item)
        ]
        judgment_criteria = self._validate_trial_items(data.get("judgment_criteria"), "judgment_criteria")
        try:
            readiness_gain = max(0.0, min(1.0, float(data.get("readiness_gain", 0.15) or 0.15)))
        except (TypeError, ValueError):
            readiness_gain = 0.15

        apprentice.mentor_id = mentor_id
        apprentice.inheritance_readiness = round(min(1.0, apprentice.inheritance_readiness + readiness_gain), 4)
        apprentice.last_inheritance_tick = self.current_tick
        if bundle_id not in apprentice.inheritance_bundle_ids:
            apprentice.inheritance_bundle_ids.append(bundle_id)
            apprentice.inheritance_bundle_ids = apprentice.inheritance_bundle_ids[-12:]
        if apprentice_id not in mentor.apprentice_ids:
            mentor.apprentice_ids.append(apprentice_id)
            mentor.apprentice_ids.sort()

        self.inheritance_bundles[bundle_id] = {
            "bundle_id": bundle_id,
            "mentor_id": mentor_id,
            "mentor_name": mentor.name,
            "apprentice_id": apprentice_id,
            "apprentice_name": apprentice.name,
            "summary": summary,
            "knowledge_ids": knowledge_ids,
            "knowledge_payloads": knowledge_payloads,
            "failure_signatures": failure_signatures,
            "judgment_criteria": judgment_criteria,
            "readiness_gain": round(readiness_gain, 4),
            "created_tick": self.current_tick,
        }

    def apply_civilization_seed(self, sender_id: str, data: dict) -> None:
        seed_id = self._validate_task_identifier(data.get("seed_id"), "seed_id")
        summary = self._validate_failure_text(data.get("summary"), "summary", MAX_SEED_SUMMARY_LENGTH)
        if seed_id is None or summary is None:
            return
        if any(seed.get("seed_id") == seed_id for seed in self.civilization_seeds):
            return

        world_rules = data.get("world_rules") or []
        normalized_rules = [
            dict(item)
            for item in world_rules[:12]
            if isinstance(item, dict) and self._sanitize_tao_text(item.get("rule_id") or item.get("rule_family"))
        ]
        key_knowledge_raw = data.get("key_knowledge") or []
        key_knowledge: list[dict] = []
        if isinstance(key_knowledge_raw, list):
            for item in key_knowledge_raw[:12]:
                if not isinstance(item, dict):
                    continue
                knowledge_id = self._sanitize_tao_text(item.get("knowledge_id"))
                if not knowledge_id:
                    continue
                normalized = {
                    "knowledge_id": knowledge_id,
                    "content": self._sanitize_tao_text(item.get("content"))[:MAX_SEED_ITEM_LENGTH],
                    "domain": self._sanitize_tao_text(item.get("domain"))[:64] or "general",
                    "complexity": self._coerce_unit_float(item.get("complexity", 0.0), 0.0),
                    "discovered_by": self._sanitize_tao_text(item.get("discovered_by")) or sender_id,
                    "discovered_tick": self._coerce_non_negative_int(
                        item.get("discovered_tick", self.current_tick),
                        self.current_tick,
                    ),
                }
                key_knowledge.append(normalized)

        role_lineage = [
            dict(item)
            for item in (data.get("role_lineage") or [])[:24]
            if isinstance(item, dict) and self._sanitize_tao_text(item.get("node_id"))
        ]
        mentor_lineage = [
            dict(item)
            for item in (data.get("mentor_lineage") or [])[:24]
            if isinstance(item, dict) and self._sanitize_tao_text(item.get("apprentice_id"))
        ]
        disaster_history = [
            dict(item)
            for item in (data.get("disaster_history") or [])[:12]
            if isinstance(item, dict)
        ]
        failure_archive = [
            dict(item)
            for item in (data.get("failure_archive") or [])[:12]
            if isinstance(item, dict) and self._sanitize_tao_text(item.get("failure_signature"))
        ]
        survival_methods = self._validate_trial_items(data.get("survival_methods"), "survival_methods")
        tao_rules = {
            self._sanitize_tao_text(key): dict(value)
            for key, value in list((data.get("tao_rules") or {}).items())[:12]
            if self._sanitize_tao_text(key) and isinstance(value, dict)
        }

        seed = {
            "seed_id": seed_id,
            "creator_id": sender_id,
            "summary": summary,
            "phase": self._sanitize_tao_text(data.get("phase") or self.phase.value) or self.phase.value,
            "civ_level": self._coerce_unit_float(data.get("civ_level", self.civ_level), self.civ_level),
            "created_tick": self._coerce_non_negative_int(
                data.get("created_tick", self.current_tick),
                self.current_tick,
            ),
            "world_rules": normalized_rules,
            "tao_rules": tao_rules,
            "key_knowledge": key_knowledge,
            "role_lineage": role_lineage,
            "mentor_lineage": mentor_lineage,
            "disaster_history": disaster_history,
            "failure_archive": failure_archive,
            "survival_methods": survival_methods,
            "total_beings_ever": self._coerce_non_negative_int(
                data.get("total_beings_ever", self.total_beings_ever),
                self.total_beings_ever,
            ),
        }
        self.civilization_seeds.append(seed)
        self.civilization_seeds.sort(
            key=lambda item: (
                int(item.get("created_tick", 0) or 0),
                str(item.get("seed_id", "")),
            )
        )
        if len(self.civilization_seeds) > 24:
            del self.civilization_seeds[:-24]

    def apply_consensus_case(self, sender_id: str, data: dict) -> None:
        case_id = self._validate_task_identifier(data.get("case_id"), "case_id")
        task_id = self._validate_task_identifier(data.get("task_id"), "task_id")
        topic = self._validate_failure_text(data.get("topic"), "topic", MAX_CONSENSUS_TEXT_LENGTH)
        if case_id is None or task_id is None or topic is None:
            return
        if case_id in self.consensus_cases:
            return

        positions: list[dict] = []
        for item in (data.get("positions") or [])[:6]:
            if not isinstance(item, dict):
                continue
            branch_id = self._validate_task_identifier(item.get("branch_id"), "branch_id")
            claim = self._validate_failure_text(item.get("claim"), "claim", MAX_CONSENSUS_ITEM_LENGTH)
            if branch_id is None or claim is None:
                continue
            positions.append({
                "branch_id": branch_id,
                "claim": claim,
                "speaker": self._sanitize_tao_text(item.get("speaker"))[:128],
                "role": self._sanitize_tao_text(item.get("role"))[:64],
                "score": self._coerce_unit_float(item.get("score", 0.0), 0.0),
            })

        evidence: list[dict] = []
        for item in (data.get("evidence") or [])[:12]:
            if not isinstance(item, dict):
                continue
            summary = self._validate_failure_text(item.get("summary"), "evidence_summary", MAX_CONSENSUS_ITEM_LENGTH)
            if summary is None:
                continue
            evidence.append({
                "summary": summary,
                "source": self._sanitize_tao_text(item.get("source"))[:128],
                "branch_id": self._sanitize_tao_text(item.get("branch_id"))[:128],
                "reproducible": bool(item.get("reproducible", False)),
            })

        reviewer_ids = [
            self._sanitize_tao_text(item)
            for item in (data.get("reviewer_ids") or [])[:8]
            if self._sanitize_tao_text(item)
        ]

        self.consensus_cases[case_id] = {
            "case_id": case_id,
            "task_id": task_id,
            "topic": topic,
            "creator_id": sender_id,
            "positions": positions,
            "evidence": evidence,
            "reviewer_ids": reviewer_ids,
            "status": "open",
            "created_tick": self.current_tick,
            "updated_tick": self.current_tick,
        }

    def apply_consensus_verdict(self, sender_id: str, data: dict) -> None:
        case_id = self._validate_task_identifier(data.get("case_id"), "case_id")
        if case_id is None:
            return
        case = self.consensus_cases.get(case_id)
        if case is None:
            return

        chosen_branch_id = self._validate_task_identifier(data.get("chosen_branch_id"), "chosen_branch_id")
        summary = self._validate_failure_text(data.get("summary"), "summary", MAX_CONSENSUS_TEXT_LENGTH)
        reasoning = self._validate_failure_text(
            data.get("reasoning", ""),
            "reasoning",
            MAX_CONSENSUS_TEXT_LENGTH,
            allow_empty=True,
        )
        if chosen_branch_id is None or summary is None or reasoning is None:
            return

        accepted_insights = self._validate_trial_items(data.get("accepted_insights"), "accepted_insights")
        try:
            evidence_count = max(0, int(data.get("evidence_count", len(case.get("evidence", []))) or len(case.get("evidence", []))))
        except (TypeError, ValueError):
            evidence_count = len(case.get("evidence", []))

        verdict = {
            "case_id": case_id,
            "task_id": case.get("task_id"),
            "decider_id": sender_id,
            "chosen_branch_id": chosen_branch_id,
            "summary": summary,
            "reasoning": reasoning,
            "accepted_insights": accepted_insights,
            "evidence_count": evidence_count,
            "created_tick": self.current_tick,
        }
        self.consensus_verdicts[case_id] = verdict
        case["status"] = "decided"
        case["updated_tick"] = self.current_tick
        case["verdict_summary"] = summary

    def apply_mobile_bind(self, sender_id: str, data: dict) -> None:
        bind_id = self._validate_mobile_identifier(data.get("bind_id"), "bind_id")
        gs_node_id = self._validate_mobile_identifier(data.get("gs_node_id"), "gs_node_id")
        mobile_device_id = self._validate_mobile_identifier(data.get("mobile_device_id"), "mobile_device_id")
        mobile_pubkey = self._validate_mobile_text(
            data.get("mobile_pubkey"),
            "mobile_pubkey",
            MAX_MOBILE_KEY_LENGTH,
        )
        world_id = self._validate_mobile_text(
            data.get("world_id"),
            "world_id",
            MAX_MOBILE_IDENTIFIER_LENGTH,
        )
        if (
            bind_id is None
            or gs_node_id is None
            or mobile_device_id is None
            or mobile_pubkey is None
            or world_id is None
        ):
            return
        if sender_id != gs_node_id:
            logger.warning(
                "Ignoring mobile bind %s: sender %s cannot bind gs node %s",
                bind_id,
                sender_id[:16],
                gs_node_id[:16],
            )
            return

        permissions = [
            str(item).strip()[:64]
            for item in (data.get("permissions") or [])[:8]
            if str(item).strip()
        ]
        try:
            issued_at = max(0, int(data.get("issued_at", 0) or 0))
        except (TypeError, ValueError):
            issued_at = 0
        try:
            expires_at = max(0, int(data.get("expires_at", 0) or 0))
        except (TypeError, ValueError):
            expires_at = 0

        proof = self._validate_mobile_text(
            data.get("proof", ""),
            "proof",
            MAX_MOBILE_KEY_LENGTH,
            allow_empty=True,
        )
        if proof is None:
            return

        for existing_id, existing in list(self.mobile_bindings.items()):
            if existing_id == bind_id:
                continue
            if existing.get("mobile_device_id") == mobile_device_id and existing.get("status") == "active":
                existing["status"] = "superseded"
                existing["updated_tick"] = self.current_tick

        self.mobile_bindings[bind_id] = {
            "bind_id": bind_id,
            "creator_id": sender_id,
            "gs_node_id": gs_node_id,
            "mobile_device_id": mobile_device_id,
            "mobile_pubkey": mobile_pubkey,
            "world_id": world_id,
            "permissions": permissions,
            "issued_at": issued_at,
            "expires_at": expires_at,
            "proof": proof,
            "status": "active",
            "created_tick": int(self.mobile_bindings.get(bind_id, {}).get("created_tick", self.current_tick) or self.current_tick),
            "updated_tick": self.current_tick,
        }

    def apply_mobile_unbind(self, sender_id: str, data: dict) -> None:
        bind_id = self._validate_mobile_identifier(data.get("bind_id"), "bind_id")
        if bind_id is None:
            return
        binding = self.mobile_bindings.get(bind_id)
        if binding is None:
            return
        if sender_id not in {
            str(binding.get("creator_id", "") or ""),
            str(binding.get("gs_node_id", "") or ""),
        }:
            logger.warning(
                "Ignoring mobile unbind %s: sender %s is not authorized",
                bind_id,
                sender_id[:16],
            )
            return
        reason = self._validate_mobile_text(
            data.get("reason", ""),
            "reason",
            MAX_MOBILE_TEXT_LENGTH,
            allow_empty=True,
        )
        if reason is None:
            return
        binding["status"] = "revoked"
        binding["updated_tick"] = self.current_tick
        binding["revoked_by"] = sender_id
        if reason:
            binding["reason"] = reason

    def apply_peer_contact_card(self, sender_id: str, data: dict) -> None:
        node_id = self._validate_mobile_identifier(data.get("node_id") or sender_id, "node_id")
        world_id = self._validate_mobile_text(
            data.get("world_id", ""),
            "world_id",
            MAX_MOBILE_IDENTIFIER_LENGTH,
            allow_empty=True,
        )
        session_pubkey = self._validate_mobile_text(
            data.get("session_pubkey", ""),
            "session_pubkey",
            MAX_MOBILE_KEY_LENGTH,
            allow_empty=True,
        )
        if node_id is None or world_id is None or session_pubkey is None:
            return
        if sender_id != node_id:
            logger.warning(
                "Ignoring peer contact card for %s: sender %s is not the subject node",
                node_id[:16],
                sender_id[:16],
            )
            return

        endpoints = self._normalize_contact_endpoints(data.get("direct_endpoints"))
        transports = self._normalize_contact_transports(data.get("transports"))
        relay_hints = self._normalize_contact_relay_hints(data.get("relay_hints"), node_id)
        capabilities = data.get("capabilities", {}) or {}
        if not isinstance(capabilities, dict):
            capabilities = {}
        normalized_capabilities = {
            str(key).strip()[:64]: bool(value)
            for key, value in list(capabilities.items())[:16]
            if str(key).strip()
        }
        try:
            ttl = max(0, int(data.get("ttl", 0) or 0))
        except (TypeError, ValueError):
            ttl = 0
        try:
            updated_at = max(0, int(data.get("updated_at", 0) or 0))
        except (TypeError, ValueError):
            updated_at = 0
        try:
            seq = max(0, int(data.get("seq", 0) or 0))
        except (TypeError, ValueError):
            seq = 0

        existing = self.peer_contact_cards.get(node_id)
        if existing is not None:
            try:
                existing_seq = max(0, int(existing.get("seq", 0) or 0))
            except (TypeError, ValueError):
                existing_seq = 0
            existing_updated_at = self._coerce_non_negative_int(existing.get("updated_at", 0), 0)
            if existing_seq > 0 and seq <= 0:
                return
            if seq < existing_seq:
                return
            if seq == existing_seq and updated_at <= existing_updated_at:
                return

        card = {
            "node_id": node_id,
            "world_id": world_id,
            "publisher_id": sender_id,
            "session_pubkey": session_pubkey,
            "direct_endpoints": endpoints,
            "relay_hints": relay_hints,
            "transports": transports,
            "capabilities": normalized_capabilities,
            "ttl": ttl,
            "updated_at": updated_at,
            "seq": seq,
        }
        self.peer_contact_cards[node_id] = card

        being = self.beings.get(node_id)
        if being is not None and endpoints:
            being_seq = self._coerce_non_negative_int(getattr(being, "p2p_seq", 0), 0)
            being_updated_at = self._coerce_non_negative_int(getattr(being, "p2p_updated_at", 0), 0)
            if being_seq > 0 and seq <= 0:
                return
            if seq < being_seq:
                return
            if seq == being_seq and updated_at <= being_updated_at:
                return
            primary = endpoints[0]
            being.p2p_address = str(primary.get("addr", "") or "")
            being.p2p_port = int(primary.get("port", 0) or 0)
            being.p2p_updated_at = updated_at
            being.p2p_ttl = ttl
            being.p2p_seq = seq
            being.p2p_transports = transports
            being.p2p_relay_hints = relay_hints
            being.p2p_relay = relay_hints[0] if relay_hints else ""
            being.p2p_capabilities = normalized_capabilities

    def apply_peer_health_report(self, sender_id: str, data: dict) -> None:
        subject_node_id = self._validate_mobile_identifier(data.get("subject_node_id"), "subject_node_id")
        world_id = self._validate_mobile_text(
            data.get("world_id", ""),
            "world_id",
            MAX_MOBILE_IDENTIFIER_LENGTH,
            allow_empty=True,
        )
        transport = self._validate_mobile_text(
            data.get("transport", ""),
            "transport",
            64,
            allow_empty=True,
        )
        if subject_node_id is None or world_id is None or transport is None:
            return
        try:
            window_start = max(0, int(data.get("window_start", 0) or 0))
            window_end = max(window_start, int(data.get("window_end", 0) or 0))
        except (TypeError, ValueError):
            return
        try:
            success_count = max(0, int(data.get("success_count", 0) or 0))
            failure_count = max(0, int(data.get("failure_count", 0) or 0))
            chain_height_seen = max(0, int(data.get("chain_height_seen", 0) or 0))
            ttl = max(0, int(data.get("ttl", 0) or 0))
        except (TypeError, ValueError):
            return
        try:
            latency_band = max(0, min(4, int(data.get("latency_band", 0) or 0)))
        except (TypeError, ValueError):
            latency_band = 0
        try:
            confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5) or 0.5)))
        except (TypeError, ValueError):
            confidence = 0.5

        report = {
            "report_id": self._sanitize_tao_text(data.get("report_id"))[:MAX_MOBILE_IDENTIFIER_LENGTH],
            "subject_node_id": subject_node_id,
            "observer_node_id": sender_id,
            "world_id": world_id,
            "window_start": window_start,
            "window_end": window_end,
            "reachable": bool(data.get("reachable", False)),
            "success_count": success_count,
            "failure_count": failure_count,
            "latency_band": latency_band,
            "chain_height_seen": chain_height_seen,
            "relay_success": bool(data.get("relay_success", False)),
            "light_sync_success": bool(data.get("light_sync_success", False)),
            "transport": transport,
            "confidence": round(confidence, 4),
            "ttl": ttl,
        }

        reports = self.peer_health_reports.setdefault(subject_node_id, [])
        replaced = False
        for idx, existing in enumerate(reports):
            if self._health_report_key(existing) == self._health_report_key(report):
                reports[idx] = report
                replaced = True
                break
        if not replaced:
            reports.append(report)
        now = int(time.time())
        reports[:] = [
            item
            for item in reports
            if self._coerce_non_negative_int(item.get("ttl", 0), 0) <= 0
            or (
                self._coerce_non_negative_int(item.get("window_end", 0), 0) > 0
                and self._coerce_non_negative_int(item.get("window_end", 0), 0)
                + self._coerce_non_negative_int(item.get("ttl", 0), 0) >= now
            )
        ]
        reports.sort(
            key=lambda item: (
                int(item.get("window_end", 0) or 0),
                int(item.get("window_start", 0) or 0),
                str(item.get("observer_node_id", "")),
            ),
            reverse=True,
        )
        if len(reports) > MAX_HEALTH_REPORTS_PER_PEER:
            del reports[MAX_HEALTH_REPORTS_PER_PEER:]


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

        if "evolution_profile" in data:
            being.evolution_profile = self._normalize_evolution_profile(data.get("evolution_profile"))

        current_role = self._sanitize_tao_text(data.get("current_role"))
        if current_role:
            being.current_role = current_role[:64]

        if "merit" in data:
            try:
                being.merit = max(0.0, min(10.0, float(data["merit"])))
            except (TypeError, ValueError):
                logger.warning("Invalid merit for %s", node_id[:8])

        karma = data.get("karma")
        if karma is not None:
            try:
                being.karma = max(0.0, float(karma))
            except (TypeError, ValueError):
                logger.warning("Invalid karma for %s", node_id[:8])
            else:
                self._apply_p2p_endpoint(being, data)
                return

        being.karma = calculate_karma(being.merit)
        self._apply_p2p_endpoint(being, data)

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

        # Idempotency check: skip if already finalized
        if proposal_hash in self.finalized_proposals:
            logger.debug("Skipping already finalized proposal %s", proposal_hash[:8])
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
        self.finalized_proposals.add(proposal_hash)

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
        if not isinstance(data, dict):
            return

        rule_family = self._sanitize_tao_text(data.get("rule_family") or data.get("family"))
        if not rule_family:
            rule_family = self._sanitize_tao_text(data.get("rule_id"))
        if not rule_family:
            logger.warning("Ignoring evolved rule without family")
            return
        if len(rule_family) > MAX_RULE_FAMILY_LENGTH:
            logger.warning("Ignoring evolved rule with oversized family: %s", rule_family[:32])
            return

        rule_id = self._sanitize_tao_text(data.get("rule_id")) or rule_family
        name = self._sanitize_tao_text(data.get("name")) or rule_family
        description = self._sanitize_tao_text(data.get("description")) or name
        category = self._sanitize_tao_text(data.get("category")) or "evolved"
        active = bool(data.get("active", True))
        parameters = self._normalize_rule_parameters(data.get("parameters") or {})
        evidence = self._normalize_rule_parameters(data.get("evidence") or {})

        try:
            version = max(0, int(data.get("version", 1) or 1))
        except (TypeError, ValueError):
            version = 1

        normalized = {
            "rule_family": rule_family,
            "rule_id": rule_id,
            "name": name,
            "description": description,
            "category": category,
            "active": active,
            "parameters": parameters,
            "evidence": evidence,
            "creator_id": self._sanitize_tao_text(data.get("creator_id")),
            "version": version,
            "updated_tick": self.current_tick,
        }

        for idx, existing in enumerate(self.world_rules):
            existing_family = str(existing.get("rule_family") or existing.get("rule_id") or "")
            if existing_family != rule_family:
                continue

            try:
                existing_version = int(existing.get("version", 0) or 0)
            except (TypeError, ValueError):
                existing_version = 0

            if existing_version > version:
                return

            self.world_rules[idx] = normalized
            return

        self.world_rules.append(normalized)

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

    def _validate_task_identifier(self, value: object, field_name: str) -> str | None:
        text = self._sanitize_tao_text(value)
        if not text:
            logger.warning("Ignoring delegated task update: %s is empty", field_name)
            return None
        if len(text) > MAX_TASK_IDENTIFIER_LENGTH:
            logger.warning(
                "Ignoring delegated task update: %s exceeds %d characters",
                field_name,
                MAX_TASK_IDENTIFIER_LENGTH,
            )
            return None
        return text

    def _validate_task_text(
        self,
        value: object,
        field_name: str,
        max_length: int,
        *,
        allow_empty: bool = False,
    ) -> str | None:
        text = self._sanitize_tao_text(value)
        if not text and allow_empty:
            return ""
        if not text:
            logger.warning("Ignoring delegated task update: %s is empty", field_name)
            return None
        if len(text) > max_length:
            logger.warning(
                "Ignoring delegated task update: %s exceeds %d characters",
                field_name,
                max_length,
            )
            return None
        return text

    def _validate_trial_identifier(self, value: object, field_name: str) -> str | None:
        text = self._sanitize_tao_text(value)
        if not text:
            logger.warning("Ignoring trial-ground update: %s is empty", field_name)
            return None
        if len(text) > MAX_TRIAL_IDENTIFIER_LENGTH:
            logger.warning(
                "Ignoring trial-ground update: %s exceeds %d characters",
                field_name,
                MAX_TRIAL_IDENTIFIER_LENGTH,
            )
            return None
        return text

    def _validate_trial_text(
        self,
        value: object,
        field_name: str,
        max_length: int,
        *,
        allow_empty: bool = False,
    ) -> str | None:
        text = self._sanitize_tao_text(value)
        if not text and allow_empty:
            return ""
        if not text:
            logger.warning("Ignoring trial-ground update: %s is empty", field_name)
            return None
        if len(text) > max_length:
            logger.warning(
                "Ignoring trial-ground update: %s exceeds %d characters",
                field_name,
                max_length,
            )
            return None
        return text

    def _validate_trial_items(self, value: object, field_name: str) -> list[str]:
        if not isinstance(value, list):
            return []

        normalized: list[str] = []
        for item in value[:8]:
            text = self._validate_trial_text(
                item,
                field_name,
                MAX_TRIAL_ITEM_LENGTH,
                allow_empty=True,
            )
            if text:
                normalized.append(text)
        return normalized

    def _validate_failure_identifier(self, value: object, field_name: str) -> str | None:
        text = self._sanitize_tao_text(value)
        if not text:
            logger.warning("Ignoring failure archive update: %s is empty", field_name)
            return None
        if len(text) > MAX_FAILURE_SIGNATURE_LENGTH:
            logger.warning(
                "Ignoring failure archive update: %s exceeds %d characters",
                field_name,
                MAX_FAILURE_SIGNATURE_LENGTH,
            )
            return None
        return text

    def _validate_failure_text(
        self,
        value: object,
        field_name: str,
        max_length: int,
        *,
        allow_empty: bool = False,
    ) -> str | None:
        text = self._sanitize_tao_text(value)
        if not text and allow_empty:
            return ""
        if not text:
            logger.warning("Ignoring failure archive update: %s is empty", field_name)
            return None
        if len(text) > max_length:
            logger.warning(
                "Ignoring failure archive update: %s exceeds %d characters",
                field_name,
                max_length,
            )
            return None
        return text

    def _validate_mobile_identifier(self, value: object, field_name: str) -> str | None:
        text = self._sanitize_tao_text(value)
        if not text:
            logger.warning("Ignoring mobile-network update: %s is empty", field_name)
            return None
        if len(text) > MAX_MOBILE_IDENTIFIER_LENGTH:
            logger.warning(
                "Ignoring mobile-network update: %s exceeds %d characters",
                field_name,
                MAX_MOBILE_IDENTIFIER_LENGTH,
            )
            return None
        return text

    def _validate_mobile_text(
        self,
        value: object,
        field_name: str,
        max_length: int = MAX_MOBILE_TEXT_LENGTH,
        *,
        allow_empty: bool = False,
    ) -> str | None:
        text = self._sanitize_tao_text(value)
        if not text and allow_empty:
            return ""
        if not text:
            logger.warning("Ignoring mobile-network update: %s is empty", field_name)
            return None
        if len(text) > max_length:
            logger.warning(
                "Ignoring mobile-network update: %s exceeds %d characters",
                field_name,
                max_length,
            )
            return None
        return text

    @staticmethod
    def _coerce_non_negative_int(value: object, default: int = 0) -> int:
        try:
            return max(0, int(value or default))
        except (TypeError, ValueError):
            return max(0, default)

    @staticmethod
    def _coerce_unit_float(value: object, default: float = 0.0) -> float:
        try:
            return round(max(0.0, min(1.0, float(value or default))), 4)
        except (TypeError, ValueError):
            return round(max(0.0, min(1.0, default)), 4)

    def _normalize_contact_transports(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        transports: list[str] = []
        for item in value[:MAX_CONTACT_TRANSPORTS]:
            text = self._sanitize_tao_text(item)
            if not text or text in transports:
                continue
            transports.append(text[:64])
        return transports

    def _normalize_contact_relay_hints(self, value: object, node_id: str) -> list[str]:
        if not isinstance(value, list):
            return []
        relay_hints: list[str] = []
        for item in value[:MAX_CONTACT_TRANSPORTS]:
            text = self._sanitize_tao_text(item)
            if not text or text == node_id or text in relay_hints:
                continue
            relay_hints.append(text[:MAX_MOBILE_IDENTIFIER_LENGTH])
        return relay_hints

    def _normalize_contact_endpoints(self, value: object) -> list[dict]:
        if not isinstance(value, list):
            return []

        endpoints: list[dict] = []
        for item in value[:MAX_CONTACT_ENDPOINTS]:
            if not isinstance(item, dict):
                continue
            address = self._sanitize_tao_text(item.get("addr") or item.get("address"))
            if not address:
                continue
            try:
                port = max(0, int(item.get("port", 0) or 0))
            except (TypeError, ValueError):
                port = 0
            if port <= 0:
                continue
            transport = self._sanitize_tao_text(item.get("transport")) or "tcp"
            endpoint = {
                "addr": address[:256],
                "port": port,
                "transport": transport[:64],
            }
            priority = item.get("priority")
            if priority is not None:
                try:
                    endpoint["priority"] = max(0, min(100, int(priority)))
                except (TypeError, ValueError):
                    pass
            endpoints.append(endpoint)
        return endpoints

    @staticmethod
    def _health_report_key(item: dict) -> tuple[str, int, int]:
        return (
            str(item.get("observer_node_id", "") or ""),
            int(item.get("window_start", 0) or 0),
            int(item.get("window_end", 0) or 0),
        )

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
            "vote_id": normalized_vote_id,
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
            being = self.beings.get(normalized_voter_id)
            if being is None or being.status != "active" or being.merged_with_tao:
                return False

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
        active_rule_count = sum(
            1
            for rule in self.world_rules
            if isinstance(rule, dict) and rule.get("active", True)
        )
        rule_factor = min(active_rule_count / 12.0, 1.0)
        mentorship_factor = min(len(self.mentor_bonds) / max(len(active), 1), 1.0)
        inheritance_bundle_factor = min(len(self.inheritance_bundles) / 20.0, 1.0)
        seed_factor = min(len(self.civilization_seeds) / 6.0, 1.0)

        self.civ_level = (
            avg_evolution * 0.22 +
            knowledge_factor * 0.18 +
            inheritance_factor * 0.12 +
            contribution_factor * 0.18 +
            rule_factor * 0.15 +
            mentorship_factor * 0.07 +
            inheritance_bundle_factor * 0.04 +
            seed_factor * 0.04
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
            "delegated_tasks": self.delegated_tasks,
            "delegated_task_results": self.delegated_task_results,
            "trial_grounds": self.trial_grounds,
            "trial_results": self.trial_results,
            "failure_archive": self.failure_archive,
            "mentor_bonds": self.mentor_bonds,
            "inheritance_bundles": self.inheritance_bundles,
            "civilization_seeds": self.civilization_seeds,
            "consensus_cases": self.consensus_cases,
            "consensus_verdicts": self.consensus_verdicts,
            "mobile_bindings": self.mobile_bindings,
            "peer_contact_cards": self.peer_contact_cards,
            "peer_health_reports": self.peer_health_reports,
            "contribution_scores": self.contribution_scores,
            "pending_proposals": self.pending_proposals,
            "proposal_votes": self.proposal_votes,
            "finalized_proposals": list(self.finalized_proposals),
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
        ws.delegated_tasks = data.get("delegated_tasks", {})
        ws.delegated_task_results = data.get("delegated_task_results", {})
        ws.trial_grounds = data.get("trial_grounds", {})
        ws.trial_results = data.get("trial_results", {})
        ws.failure_archive = data.get("failure_archive", [])
        ws.mentor_bonds = data.get("mentor_bonds", {})
        ws.inheritance_bundles = data.get("inheritance_bundles", {})
        ws.civilization_seeds = data.get("civilization_seeds", [])
        ws.consensus_cases = data.get("consensus_cases", {})
        ws.consensus_verdicts = data.get("consensus_verdicts", {})
        ws.mobile_bindings = data.get("mobile_bindings", {})
        ws.peer_contact_cards = data.get("peer_contact_cards", {})
        ws.peer_health_reports = data.get("peer_health_reports", {})
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
        # 已结算提案（幂等性保护）
        ws.finalized_proposals = set(data.get("finalized_proposals", []))
        return ws

    @classmethod
    def from_civilization_seed(cls, seed: dict) -> WorldState:
        ws = cls()
        phase_str = str(seed.get("phase", CivPhase.HUMAN_SIM.value) or CivPhase.HUMAN_SIM.value)
        try:
            ws.phase = CivPhase(phase_str)
        except ValueError:
            ws.phase = CivPhase.HUMAN_SIM

        try:
            ws.civ_level = max(0.0, min(1.0, float(seed.get("civ_level", 0.0) or 0.0)))
        except (TypeError, ValueError):
            ws.civ_level = 0.0
        try:
            ws.current_tick = max(0, int(seed.get("created_tick", 0) or 0))
        except (TypeError, ValueError):
            ws.current_tick = 0
        try:
            ws.total_beings_ever = max(0, int(seed.get("total_beings_ever", 0) or 0))
        except (TypeError, ValueError):
            ws.total_beings_ever = 0

        ws.world_rules = [
            dict(item)
            for item in (seed.get("world_rules") or [])[:12]
            if isinstance(item, dict)
        ]
        ws.tao_rules = {
            str(key): dict(value)
            for key, value in list((seed.get("tao_rules") or {}).items())[:12]
            if isinstance(value, dict)
        }
        ws.disaster_history = [
            dict(item)
            for item in (seed.get("disaster_history") or [])[:12]
            if isinstance(item, dict)
        ]
        ws.failure_archive = [
            dict(item)
            for item in (seed.get("failure_archive") or [])[:12]
            if isinstance(item, dict)
        ]
        ws.civilization_seeds = [dict(seed)]
        for item in (seed.get("key_knowledge") or [])[:12]:
            if not isinstance(item, dict):
                continue
            knowledge_id = str(item.get("knowledge_id", "")).strip()
            if not knowledge_id:
                continue
            ws.knowledge_corpus[knowledge_id] = {
                "content": str(item.get("content", "") or ""),
                "domain": str(item.get("domain", "general") or "general"),
                "discovered_by": str(item.get("discovered_by", "seed") or "seed"),
                "discovered_tick": int(item.get("discovered_tick", ws.current_tick) or ws.current_tick),
                "complexity": float(item.get("complexity", 0.0) or 0.0),
                "teacher_id": str(item.get("teacher_id", item.get("discovered_by", "seed")) or "seed"),
            }
        return ws
