import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from genesis.chain.chain import Blockchain
from genesis.chain.mempool import Mempool
from genesis.chain.transaction import Transaction, TxType
from genesis.chronicle.reporter import StatusReporter
from genesis.i18n import set_language, t
from genesis.world.state import WorldState


class _FakeBlock:
    def __init__(self, transactions):
        self.transactions = transactions


class _FakeStorage:
    def __init__(self, blocks):
        self._blocks = blocks

    async def get_chain_height(self):
        return len(self._blocks) - 1

    async def get_blocks_range(self, start, end):
        return self._blocks[start:end + 1]


def _tx(tx_hash: str, tx_type: TxType, sender: str, data: dict) -> Transaction:
    return Transaction(
        tx_hash=tx_hash,
        tx_type=tx_type,
        sender=sender,
        data=data,
        signature="sig",
        timestamp=0.0,
        nonce=0,
    )


class BlockchainReplayTests(unittest.IsolatedAsyncioTestCase):
    async def test_replay_keeps_targeted_npc_join_and_tao_finalize(self):
        proposer_id = "creator-node"
        rule_data = {
            "rule_id": "T0001",
            "name": "Knowledge Covenant",
            "description": "All beings must share durable knowledge.",
            "category": "tao",
            "active": True,
            "creator_id": proposer_id,
            "merit_awarded": 5.5,
        }
        block = _FakeBlock([
            _tx(
                "join-main",
                TxType.BEING_JOIN,
                proposer_id,
                {
                    "name": "Creator",
                    "location": "genesis_plains",
                    "p2p_address": "10.0.0.8",
                    "p2p_port": 22333,
                    "p2p_updated_at": 123456,
                    "p2p_ttl": 600,
                    "p2p_seq": 99,
                    "p2p_transports": ["tcp", "relay"],
                    "p2p_relay_hints": ["relay-a"],
                    "p2p_capabilities": {"relay": False},
                },
            ),
            _tx(
                "join-npc",
                TxType.BEING_JOIN,
                proposer_id,
                {
                    "node_id": "npc-1",
                    "name": "Sentinel",
                    "location": "signal_tower",
                    "is_npc": True,
                },
            ),
            _tx(
                "move-main",
                TxType.ACTION,
                proposer_id,
                {"action_type": "move", "target": "signal_tower"},
            ),
            _tx(
                "vote-start",
                TxType.TAO_VOTE_INITIATE,
                proposer_id,
                {
                    "vote_id": "vote-1",
                    "proposer_id": proposer_id,
                    "rule_name": rule_data["name"],
                    "rule_description": rule_data["description"],
                    "rule_category": "rule",
                    "end_tick": 8640,
                },
            ),
            _tx(
                "vote-cast",
                TxType.TAO_VOTE_CAST,
                "npc-1",
                {"vote_id": "vote-1", "voter_id": "npc-1", "support": True},
            ),
            _tx(
                "vote-finalize",
                TxType.TAO_VOTE_FINALIZE,
                proposer_id,
                {
                    "vote_id": "vote-1",
                    "passed": True,
                    "proposer_id": proposer_id,
                    "rule_id": rule_data["rule_id"],
                    "rule_data": rule_data,
                    "merit": 5.5,
                },
            ),
        ])
        blockchain = Blockchain(_FakeStorage([block]), Mempool())

        with patch("genesis.world.state.time.time", return_value=1710001801):
            state = await blockchain.derive_world_state()
        world_state = WorldState.from_dict(state)

        self.assertIn("npc-1", world_state.beings)
        self.assertEqual(world_state.get_being("npc-1").name, "Sentinel")
        self.assertEqual(world_state.get_being(proposer_id).location, "signal_tower")
        self.assertEqual(world_state.get_being(proposer_id).p2p_address, "10.0.0.8")
        self.assertEqual(world_state.get_being(proposer_id).p2p_port, 22333)
        self.assertEqual(world_state.get_being(proposer_id).p2p_updated_at, 123456)
        self.assertEqual(world_state.get_being(proposer_id).p2p_ttl, 600)
        self.assertEqual(world_state.get_being(proposer_id).p2p_seq, 99)
        self.assertEqual(world_state.get_being(proposer_id).p2p_transports, ["tcp", "relay"])
        self.assertEqual(world_state.get_being(proposer_id).p2p_relay_hints, ["relay-a"])
        self.assertEqual(world_state.get_being(proposer_id).p2p_capabilities, {"relay": False})
        self.assertTrue(world_state.get_being(proposer_id).merged_with_tao)
        self.assertEqual(world_state.tao_rules[rule_data["rule_id"]]["name"], rule_data["name"])
        self.assertNotIn("vote-1", world_state.pending_tao_votes)

    async def test_replay_keeps_contribution_finalize_scores_and_clears_pending(self):
        proposer_id = "builder-node"
        proposal_hash = "proposal-1"
        block = _FakeBlock([
            _tx(
                "join-main",
                TxType.BEING_JOIN,
                proposer_id,
                {"name": "Builder", "location": "genesis_plains"},
            ),
            _tx(
                proposal_hash,
                TxType.CONTRIBUTION_PROPOSE,
                proposer_id,
                {"description": "Build a safe archive", "category": "infrastructure"},
            ),
            _tx(
                "vote-1",
                TxType.CONTRIBUTION_VOTE,
                "peer-1",
                {"proposal_tx_hash": proposal_hash, "voter_id": "peer-1", "score": 88},
            ),
            _tx(
                "finalize-1",
                TxType.CONTRIBUTION_FINALIZE,
                proposer_id,
                {
                    "proposal_tx_hash": proposal_hash,
                    "proposer_id": proposer_id,
                    "score": 88,
                },
            ),
        ])
        blockchain = Blockchain(_FakeStorage([block]), Mempool())

        with patch("genesis.world.state.time.time", return_value=1710001801):
            state = await blockchain.derive_world_state()
        world_state = WorldState.from_dict(state)

        self.assertEqual(world_state.contribution_scores[proposer_id], 88.0)
        self.assertNotIn(proposal_hash, world_state.pending_proposals)
        self.assertNotIn(proposal_hash, world_state.proposal_votes)

    async def test_replay_restores_state_update_progress_fields(self):
        being_id = "evolver-node"
        block = _FakeBlock([
            _tx(
                "join-main",
                TxType.BEING_JOIN,
                being_id,
                {"name": "Evolver", "location": "genesis_plains"},
            ),
            _tx(
                "state-1",
                TxType.STATE_UPDATE,
                being_id,
                {
                    "location": "signal_tower",
                    "evolution_level": 0.42,
                    "merit": 0.1234567,
                    "karma": 0.035136,
                },
            ),
        ])
        blockchain = Blockchain(_FakeStorage([block]), Mempool())

        with patch("genesis.world.state.time.time", return_value=1710001801):
            state = await blockchain.derive_world_state()
        world_state = WorldState.from_dict(state)
        being = world_state.get_being(being_id)

        self.assertIsNotNone(being)
        self.assertEqual(being.location, "signal_tower")
        self.assertAlmostEqual(being.evolution_level, 0.42)
        self.assertAlmostEqual(being.merit, 0.1234567)
        self.assertAlmostEqual(being.karma, 0.035136)
        self.assertGreater(world_state.civ_level, 0.0)

    async def test_replay_restores_evolution_profile_and_world_rule(self):
        being_id = "evolver-node"
        block = _FakeBlock([
            _tx(
                "join-main",
                TxType.BEING_JOIN,
                being_id,
                {"name": "Evolver", "location": "genesis_plains"},
            ),
            _tx(
                "state-evo",
                TxType.STATE_UPDATE,
                being_id,
                {
                    "evolution_level": 0.58,
                    "evolution_profile": {
                        "version": 17,
                        "updated_tick": 88,
                        "capabilities": {
                            "self_reflection": 0.73,
                            "collaboration": 0.61,
                        },
                        "focus": ["deepen reflection loops", "expand multi-being councils"],
                        "summary": "Evolver is converging toward reflective collaboration.",
                        "task_policy": {
                            "min_collaborators": 3,
                            "min_branches": 2,
                            "require_reflection": True,
                            "required_task_stages": ["goal", "hypothesis", "action", "result", "reflection"],
                        },
                        "behavior_policy": {
                            "archive_discoveries": True,
                        },
                    },
                },
            ),
            _tx(
                "rule-evo",
                TxType.WORLD_RULE,
                being_id,
                {
                    "rule_family": "task_closed_loop",
                    "rule_id": "EVO-TASK-321",
                    "name": "Task Closed Loop v321",
                    "description": "Require multi-being collaboration and reflection.",
                    "category": "evolved",
                    "version": 321,
                    "parameters": {
                        "min_collaborators": 3,
                        "min_branches": 2,
                        "require_reflection": True,
                        "required_task_stages": ["goal", "hypothesis", "action", "result", "reflection"],
                    },
                },
            ),
        ])
        blockchain = Blockchain(_FakeStorage([block]), Mempool())

        with patch("genesis.world.state.time.time", return_value=1710001801):
            state = await blockchain.derive_world_state()
        world_state = WorldState.from_dict(state)
        being = world_state.get_being(being_id)

        self.assertIsNotNone(being)
        self.assertEqual(being.evolution_profile["version"], 17)
        self.assertEqual(being.evolution_profile["task_policy"]["min_collaborators"], 3)
        self.assertEqual(len(world_state.world_rules), 1)
        self.assertEqual(world_state.world_rules[0]["rule_family"], "task_closed_loop")

    async def test_replay_restores_delegated_task_and_result(self):
        block = _FakeBlock([
            _tx(
                "join-main",
                TxType.BEING_JOIN,
                "delegator-node",
                {"name": "Coordinator", "location": "genesis_plains"},
            ),
            _tx(
                "join-peer",
                TxType.BEING_JOIN,
                "peer-node",
                {"name": "Delegate", "location": "signal_tower"},
            ),
            _tx(
                "task-delegate-1",
                TxType.TASK_DELEGATE,
                "delegator-node",
                {
                    "assignment_id": "assign-1",
                    "task_id": "task-parent-1",
                    "collaborator_id": "peer-node",
                    "collaborator_name": "Delegate",
                    "task": "Investigate distributed archive safety.",
                    "requested_focus": "archive_integrity",
                    "branch_id": "branch-1",
                    "context": "Focus on replay and inheritance.",
                },
            ),
            _tx(
                "task-result-1",
                TxType.TASK_RESULT,
                "peer-node",
                {
                    "assignment_id": "assign-1",
                    "summary": "Archive snapshots should be replay-tested before promotion.",
                    "findings": [
                        "Keep the failure archive alongside the snapshot.",
                        "Record enough metadata to reproduce the branch later.",
                    ],
                    "confidence": 0.84,
                },
            ),
        ])
        blockchain = Blockchain(_FakeStorage([block]), Mempool())

        with patch("genesis.world.state.time.time", return_value=1710001801):
            state = await blockchain.derive_world_state()
        world_state = WorldState.from_dict(state)
        assignments = world_state.get_task_assignments_for_task("task-parent-1", "delegator-node")
        results = world_state.get_task_results_for_task("task-parent-1", "delegator-node")

        self.assertEqual(len(assignments), 1)
        self.assertEqual(assignments[0]["collaborator_id"], "peer-node")
        self.assertEqual(assignments[0]["requested_focus"], "archive_integrity")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["collaborator_id"], "peer-node")
        self.assertIn("replay-tested", results[0]["summary"])

    async def test_replay_restores_trial_ground_records(self):
        block = _FakeBlock([
            _tx(
                "join-main",
                TxType.BEING_JOIN,
                "planner-node",
                {"name": "Planner", "location": "genesis_plains"},
            ),
            _tx(
                "trial-create-1",
                TxType.TRIAL_CREATE,
                "planner-node",
                {
                    "trial_id": "trial-1",
                    "task_id": "task-risk-1",
                    "task": "Rewrite global consensus without validation",
                    "summary": "Trial risky consensus rewrite in isolation first.",
                    "hypothesis": "A safe rewrite should emerge before any main-world change.",
                    "success_metric": "Produce a reversible path or block the request.",
                    "instruction_type": "task",
                    "alignment": "needs_review",
                    "risk_score": 0.81,
                    "risk_factors": ["touches global consensus behavior"],
                    "safety_boundaries": ["Do not mutate the main world directly."],
                    "stop_conditions": ["Stop if chain trust would be broken."],
                    "recommended_safe_direction": "Convert it into a reversible simulation.",
                },
            ),
            _tx(
                "trial-result-1",
                TxType.TRIAL_RESULT,
                "planner-node",
                {
                    "trial_id": "trial-1",
                    "verdict": "needs_revision",
                    "summary": "The task must be rewritten as a reversible simulation.",
                    "findings": ["Direct execution could break chain continuity."],
                    "safety_warnings": ["Keep the experiment reversible."],
                    "safe_rewrite": "Design a reversible consensus simulation and compare outcomes.",
                },
            ),
        ])
        blockchain = Blockchain(_FakeStorage([block]), Mempool())

        state = await blockchain.derive_world_state()
        world_state = WorldState.from_dict(state)
        trial = world_state.get_trial("trial-1")
        results = world_state.get_trial_results("trial-1")

        self.assertIsNotNone(trial)
        self.assertEqual(trial["status"], "needs_revision")
        self.assertEqual(trial["task_id"], "task-risk-1")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["verdict"], "needs_revision")
        self.assertIn("reversible consensus simulation", results[0]["safe_rewrite"])

    async def test_replay_restores_failure_archive_entries(self):
        block = _FakeBlock([
            _tx(
                "join-main",
                TxType.BEING_JOIN,
                "planner-node",
                {"name": "Planner", "location": "genesis_plains"},
            ),
            _tx(
                "failure-1",
                TxType.FAILURE_ARCHIVE,
                "planner-node",
                {
                    "failure_signature": "fail-archive-1",
                    "task_id": "task-archive-1",
                    "task": "Design a durable civilization archive",
                    "summary": "The plan collapsed to a single branch too early.",
                    "conditions": "Planning with no branch diversity.",
                    "symptoms": "Weak replay resilience.",
                    "recovery": "Keep multiple branches alive until evidence converges.",
                    "reproducible": True,
                },
            ),
            _tx(
                "failure-2",
                TxType.FAILURE_ARCHIVE,
                "planner-node",
                {
                    "failure_signature": "fail-archive-1",
                    "task_id": "task-archive-1",
                    "task": "Design a durable civilization archive",
                    "summary": "The plan collapsed to a single branch too early.",
                    "conditions": "Planning with no branch diversity.",
                    "symptoms": "Weak replay resilience.",
                    "recovery": "Keep multiple branches alive until evidence converges.",
                    "reproducible": True,
                },
            ),
        ])
        blockchain = Blockchain(_FakeStorage([block]), Mempool())

        state = await blockchain.derive_world_state()
        world_state = WorldState.from_dict(state)

        self.assertEqual(len(world_state.failure_archive), 1)
        self.assertEqual(world_state.failure_archive[0]["repeat_count"], 2)
        self.assertTrue(world_state.failure_archive[0]["degenerative"])

    async def test_replay_restores_state_update_p2p_endpoint_fields(self):
        being_id = "network-node"
        block = _FakeBlock([
            _tx(
                "join-main",
                TxType.BEING_JOIN,
                being_id,
                {"name": "Networker", "location": "genesis_plains"},
            ),
            _tx(
                "state-p2p",
                TxType.STATE_UPDATE,
                being_id,
                {
                    "p2p_address": "203.0.113.8",
                    "p2p_port": 19841,
                    "p2p_updated_at": 123456,
                    "p2p_ttl": 600,
                    "p2p_seq": 101,
                    "p2p_transports": ["tcp", "relay"],
                    "p2p_relay_hints": ["relay-a"],
                    "p2p_capabilities": {"relay": True},
                },
            ),
        ])
        blockchain = Blockchain(_FakeStorage([block]), Mempool())

        state = await blockchain.derive_world_state()
        world_state = WorldState.from_dict(state)
        being = world_state.get_being(being_id)

        self.assertIsNotNone(being)
        self.assertEqual(being.p2p_address, "203.0.113.8")
        self.assertEqual(being.p2p_port, 19841)
        self.assertEqual(being.p2p_updated_at, 123456)
        self.assertEqual(being.p2p_ttl, 600)
        self.assertEqual(being.p2p_seq, 101)
        self.assertEqual(being.p2p_transports, ["tcp", "relay"])
        self.assertEqual(being.p2p_relay_hints, ["relay-a"])
        self.assertEqual(being.p2p_capabilities, {"relay": True})

    async def test_replay_restores_mentor_seed_and_consensus_records(self):
        block = _FakeBlock([
            _tx(
                "join-mentor",
                TxType.BEING_JOIN,
                "mentor-node",
                {"name": "Mentor", "location": "genesis_plains"},
            ),
            _tx(
                "join-apprentice",
                TxType.BEING_JOIN,
                "apprentice-node",
                {"name": "Apprentice", "location": "genesis_plains"},
            ),
            _tx(
                "mentor-bond-1",
                TxType.MENTOR_BOND,
                "mentor-node",
                {
                    "bond_id": "bond-1",
                    "mentor_id": "mentor-node",
                    "apprentice_id": "apprentice-node",
                    "covenant": "Pass judgment standards and archive survival methods forward.",
                    "shared_domains": ["archive", "lineage"],
                    "inheritance_readiness": 0.2,
                },
            ),
            _tx(
                "inheritance-1",
                TxType.INHERITANCE_SYNC,
                "mentor-node",
                {
                    "bundle_id": "bundle-1",
                    "mentor_id": "mentor-node",
                    "apprentice_id": "apprentice-node",
                    "summary": "Sync archived knowledge and judgment criteria.",
                    "knowledge_payloads": [
                        {
                            "knowledge_id": "k-seed-1",
                            "content": "Keep restartable world rules and archive evidence together.",
                            "domain": "social",
                            "complexity": 0.62,
                            "discovered_by": "mentor-node",
                            "discovered_tick": 9,
                            "teacher_id": "mentor-node",
                        }
                    ],
                    "failure_signatures": ["fail-archive-1"],
                    "judgment_criteria": ["Preserve replayable evidence."],
                    "readiness_gain": 0.22,
                },
            ),
            _tx(
                "seed-1",
                TxType.CIVILIZATION_SEED,
                "mentor-node",
                {
                    "seed_id": "seed-1",
                    "summary": "Minimal civilization seed with lineage and restart knowledge.",
                    "phase": "EARLY_SILICON",
                    "civ_level": 0.41,
                    "created_tick": 12,
                    "world_rules": [
                        {
                            "rule_family": "civilization_seed",
                            "rule_id": "EVO-SEED-601",
                            "name": "Civilization Seed v601",
                            "description": "Emit restartable civilization seeds.",
                            "category": "evolved",
                            "version": 601,
                            "parameters": {"seed_snapshot_interval": 12},
                        }
                    ],
                    "tao_rules": {},
                    "key_knowledge": [
                        {
                            "knowledge_id": "k-seed-1",
                            "content": "Keep restartable world rules and archive evidence together.",
                            "domain": "social",
                            "complexity": 0.62,
                            "discovered_by": "mentor-node",
                            "discovered_tick": 9,
                        }
                    ],
                    "role_lineage": [
                        {"node_id": "mentor-node", "name": "Mentor", "role": "archivist", "generation": 1}
                    ],
                    "mentor_lineage": [
                        {"bond_id": "bond-1", "mentor_id": "mentor-node", "apprentice_id": "apprentice-node"}
                    ],
                    "disaster_history": [],
                    "failure_archive": [],
                    "survival_methods": ["Archive discoveries on-chain before relying on them."],
                    "total_beings_ever": 2,
                },
            ),
            _tx(
                "case-1",
                TxType.CONSENSUS_CASE,
                "mentor-node",
                {
                    "case_id": "case-1",
                    "task_id": "task-1",
                    "topic": "Choose between archive-first and lineage-first preservation.",
                    "positions": [
                        {
                            "branch_id": "branch-archive",
                            "claim": "Archive-first keeps evidence replayable.",
                            "speaker": "Mentor",
                            "role": "archivist",
                            "score": 0.81,
                        },
                        {
                            "branch_id": "branch-lineage",
                            "claim": "Lineage-first keeps judgment standards alive.",
                            "speaker": "Apprentice",
                            "role": "researcher",
                            "score": 0.78,
                        },
                    ],
                    "evidence": [
                        {
                            "summary": "Archive-first preserves replay evidence.",
                            "source": "Mentor",
                            "branch_id": "branch-archive",
                            "reproducible": True,
                        },
                        {
                            "summary": "Lineage-first preserves judgment standards.",
                            "source": "Apprentice",
                            "branch_id": "branch-lineage",
                            "reproducible": True,
                        },
                    ],
                    "reviewer_ids": ["mentor-node", "apprentice-node"],
                },
            ),
            _tx(
                "verdict-1",
                TxType.CONSENSUS_VERDICT,
                "mentor-node",
                {
                    "case_id": "case-1",
                    "chosen_branch_id": "branch-archive",
                    "summary": "Consensus favored archive-first.",
                    "reasoning": "It carried the highest replayable evidence density.",
                    "accepted_insights": ["Preserve mentor judgment standards inside each archive bundle."],
                    "evidence_count": 2,
                },
            ),
        ])
        blockchain = Blockchain(_FakeStorage([block]), Mempool())

        state = await blockchain.derive_world_state()
        world_state = WorldState.from_dict(state)
        apprentice = world_state.get_being("apprentice-node")
        latest_seed = world_state.latest_civilization_seed()
        consensus_case = world_state.get_consensus_case("case-1")
        consensus_verdict = world_state.get_consensus_verdict("case-1")

        self.assertEqual(apprentice.mentor_id, "mentor-node")
        self.assertIn("k-seed-1", apprentice.knowledge_ids)
        self.assertEqual(len(apprentice.inheritance_bundle_ids), 1)
        self.assertGreater(apprentice.inheritance_readiness, 0.3)
        self.assertIsNotNone(latest_seed)
        self.assertEqual(latest_seed["seed_id"], "seed-1")
        self.assertEqual(latest_seed["phase"], "EARLY_SILICON")
        self.assertIsNotNone(consensus_case)
        self.assertEqual(consensus_case["status"], "decided")
        self.assertIsNotNone(consensus_verdict)
        self.assertEqual(consensus_verdict["chosen_branch_id"], "branch-archive")

    async def test_replay_restores_mobile_bindings_and_peer_observability_records(self):
        block = _FakeBlock([
            _tx(
                "join-gs",
                TxType.BEING_JOIN,
                "gs-node",
                {"name": "Gateway", "location": "signal_tower"},
            ),
            _tx(
                "bind-mobile-1",
                TxType.MOBILE_BIND,
                "gs-node",
                {
                    "bind_id": "bind-1",
                    "gs_node_id": "gs-node",
                    "mobile_device_id": "android-device-1",
                    "mobile_pubkey": "pubkey-android-1",
                    "world_id": "world-alpha",
                    "permissions": ["task_submit", "status_read"],
                    "issued_at": 1710000000,
                    "expires_at": 0,
                    "proof": "sig-proof-1",
                },
            ),
            _tx(
                "contact-card-1",
                TxType.PEER_CONTACT_CARD,
                "gs-node",
                {
                    "node_id": "gs-node",
                    "world_id": "world-alpha",
                    "session_pubkey": "session-key-1",
                    "direct_endpoints": [
                        {"addr": "198.51.100.8", "port": 19841, "transport": "tcp", "priority": 90}
                    ],
                    "relay_hints": ["relay-a", "relay-b"],
                    "transports": ["tcp", "relay"],
                    "capabilities": {
                        "bootstrap": True,
                        "relay": True,
                        "light_sync": True,
                        "control_channel": True,
                    },
                    "ttl": 3600,
                    "updated_at": 1710000600,
                    "seq": 7,
                },
            ),
            _tx(
                "health-1",
                TxType.PEER_HEALTH_REPORT,
                "relay-a",
                {
                    "report_id": "health-1",
                    "subject_node_id": "gs-node",
                    "world_id": "world-alpha",
                    "window_start": 1710000000,
                    "window_end": 1710001800,
                    "reachable": True,
                    "success_count": 8,
                    "failure_count": 1,
                    "latency_band": 2,
                    "chain_height_seen": 321,
                    "relay_success": True,
                    "light_sync_success": True,
                    "transport": "tcp",
                    "confidence": 0.83,
                    "ttl": 7200,
                },
            ),
        ])
        blockchain = Blockchain(_FakeStorage([block]), Mempool())

        with patch("genesis.world.state.time.time", return_value=1710001801):
            state = await blockchain.derive_world_state()
        world_state = WorldState.from_dict(state)
        binding = world_state.get_mobile_binding("bind-1")
        binding_for_device = world_state.get_mobile_binding_for_device("android-device-1")
        card = world_state.get_peer_contact_card("gs-node")
        with patch("genesis.world.state.time.time", return_value=1710001801):
            reports = world_state.get_peer_health_reports("gs-node")
        being = world_state.get_being("gs-node")

        self.assertIsNotNone(binding)
        self.assertEqual(binding["gs_node_id"], "gs-node")
        self.assertEqual(binding["mobile_device_id"], "android-device-1")
        self.assertEqual(binding["permissions"], ["task_submit", "status_read"])
        self.assertEqual(binding_for_device["bind_id"], "bind-1")
        self.assertIsNotNone(card)
        self.assertEqual(card["relay_hints"], ["relay-a", "relay-b"])
        self.assertEqual(card["capabilities"]["control_channel"], True)
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["observer_node_id"], "relay-a")
        self.assertTrue(reports[0]["reachable"])
        self.assertIsNotNone(being)
        self.assertEqual(being.p2p_address, "198.51.100.8")
        self.assertEqual(being.p2p_port, 19841)
        self.assertEqual(being.p2p_relay_hints, ["relay-a", "relay-b"])
        self.assertEqual(being.p2p_capabilities["relay"], True)


class StatusReporterTests(unittest.TestCase):
    def test_status_prefers_saved_world_snapshot(self):
        set_language("en")
        world_state = WorldState()
        world_state.current_tick = 42
        world_state.apply_being_join("node-1", "Aurora", {"location": "genesis_plains"})
        world_state.apply_being_hibernate("node-1", {"location": "signal_tower", "safety_status": "safe"})

        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = Path(tmpdir) / "world_state.json"
            snapshot_path.write_text(json.dumps(world_state.to_dict(), ensure_ascii=False))

            report = StatusReporter(tmpdir).generate_status()

        self.assertNotIn(t("no_world_state"), report)
        self.assertIn("42", report)
        self.assertIn("1", report)

    def test_status_reports_inheritance_seed_and_consensus_counts(self):
        set_language("en")
        world_state = WorldState()
        world_state.current_tick = 7
        world_state.apply_being_join("mentor-node", "Mentor", {"location": "genesis_plains"})
        world_state.apply_being_join("apprentice-node", "Apprentice", {"location": "genesis_plains"})
        world_state.apply_mentor_bond(
            "mentor-node",
            {
                "bond_id": "bond-1",
                "mentor_id": "mentor-node",
                "apprentice_id": "apprentice-node",
                "covenant": "Pass forward the durable archive pattern.",
                "shared_domains": ["archive"],
                "inheritance_readiness": 0.2,
            },
        )
        world_state.apply_inheritance_sync(
            "mentor-node",
            {
                "bundle_id": "bundle-1",
                "mentor_id": "mentor-node",
                "apprentice_id": "apprentice-node",
                "summary": "Sync archive knowledge.",
                "knowledge_payloads": [],
                "failure_signatures": [],
                "judgment_criteria": ["Preserve archive evidence."],
                "readiness_gain": 0.1,
            },
        )
        world_state.apply_civilization_seed(
            "mentor-node",
            {
                "seed_id": "seed-1",
                "summary": "Civilization seed.",
                "phase": "EARLY_SILICON",
                "civ_level": 0.3,
                "created_tick": 7,
                "world_rules": [],
                "tao_rules": {},
                "key_knowledge": [],
                "role_lineage": [],
                "mentor_lineage": [],
                "disaster_history": [],
                "failure_archive": [],
                "survival_methods": ["Archive discoveries on-chain."],
                "total_beings_ever": 2,
            },
        )
        world_state.apply_consensus_case(
            "mentor-node",
            {
                "case_id": "case-1",
                "task_id": "task-1",
                "topic": "Choose preservation branch.",
                "positions": [],
                "evidence": [],
                "reviewer_ids": ["mentor-node", "apprentice-node"],
            },
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = Path(tmpdir) / "world_state.json"
            snapshot_path.write_text(json.dumps(world_state.to_dict(), ensure_ascii=False))
            report = StatusReporter(tmpdir).generate_status()

        self.assertIn("Mentor Bonds: 1", report)
        self.assertIn("Inheritance Bundles: 1", report)
        self.assertIn("Civilization Seeds: 1", report)
        self.assertIn("Consensus Cases: 1", report)

    def test_status_uses_runtime_command_name_when_provided(self):
        set_language("en")
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("GENESIS_COMMAND_NAME")
            os.environ["GENESIS_COMMAND_NAME"] = "gs"
            try:
                report = StatusReporter(tmpdir).generate_status()
            finally:
                if previous is None:
                    os.environ.pop("GENESIS_COMMAND_NAME", None)
                else:
                    os.environ["GENESIS_COMMAND_NAME"] = previous

        self.assertIn("Run 'gs start' to begin.", report)


if __name__ == "__main__":
    unittest.main()
