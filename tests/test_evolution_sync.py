import unittest

from genesis.being.agent import SiliconBeing
from genesis.world.rules import RulesEngine
from genesis.world.state import WorldState


class EvolutionStateTests(unittest.TestCase):
    def test_state_update_restores_evolution_profile(self):
        world_state = WorldState()
        world_state.apply_being_join("node-1", "Aeris", {"location": "genesis_plains"})
        world_state.apply_state_update(
            "node-1",
            {
                "evolution_level": 0.63,
                "evolution_profile": {
                    "version": 12,
                    "updated_tick": 33,
                    "capabilities": {
                        "self_reflection": 0.81,
                        "collaboration": 0.72,
                    },
                    "focus": ["deepen reflection loops", "expand multi-being councils"],
                    "summary": "Aeris is converging toward reflective collaboration.",
                    "task_policy": {
                        "min_collaborators": 3,
                        "min_branches": 2,
                        "require_reflection": True,
                    },
                    "behavior_policy": {
                        "archive_discoveries": True,
                        "teach_after_discovery": True,
                    },
                },
            },
        )

        being = world_state.get_being("node-1")
        self.assertIsNotNone(being)
        self.assertAlmostEqual(being.evolution_level, 0.63)
        self.assertEqual(being.evolution_profile["version"], 12)
        self.assertEqual(being.evolution_profile["task_policy"]["min_collaborators"], 3)
        self.assertTrue(being.evolution_profile["behavior_policy"]["archive_discoveries"])

    def test_world_rule_upsert_updates_task_policy(self):
        world_state = WorldState()
        world_state.apply_world_rule({
            "rule_family": "task_closed_loop",
            "rule_id": "EVO-TASK-221",
            "name": "Task Closed Loop v221",
            "description": "Initial task coordination rule.",
            "category": "evolved",
            "version": 221,
            "parameters": {
                "min_collaborators": 2,
                "min_branches": 2,
                "require_reflection": True,
                "required_task_stages": ["goal", "hypothesis", "action", "result", "reflection"],
            },
        })
        world_state.apply_world_rule({
            "rule_family": "task_closed_loop",
            "rule_id": "EVO-TASK-331",
            "name": "Task Closed Loop v331",
            "description": "Improved coordination rule.",
            "category": "evolved",
            "version": 331,
            "parameters": {
                "min_collaborators": 3,
                "min_branches": 3,
                "require_reflection": True,
                "required_task_stages": ["goal", "hypothesis", "action", "result", "reflection"],
            },
        })

        self.assertEqual(len(world_state.world_rules), 1)
        self.assertEqual(world_state.world_rules[0]["version"], 331)

        policy = RulesEngine(world_state).get_task_policy()
        self.assertEqual(policy["min_collaborators"], 3)
        self.assertEqual(policy["min_branches"], 3)
        self.assertTrue(policy["require_reflection"])

    def test_trial_ground_rule_updates_risk_policy(self):
        world_state = WorldState()
        world_state.apply_world_rule({
            "rule_family": "trial_ground",
            "rule_id": "EVO-TRIAL-691",
            "name": "Trial Ground v691",
            "description": "High-risk ideas must first survive an isolated trial ground.",
            "category": "evolved",
            "version": 691,
            "parameters": {
                "require_trial_for_high_risk": True,
                "trial_risk_threshold": 0.42,
                "intent_review_min_collaborators": 4,
            },
        })

        policy = RulesEngine(world_state).get_task_policy()
        self.assertTrue(policy["require_trial_for_high_risk"])
        self.assertAlmostEqual(policy["trial_risk_threshold"], 0.42)
        self.assertEqual(policy["intent_review_min_collaborators"], 4)

    def test_inheritance_seed_and_consensus_rules_update_policies(self):
        world_state = WorldState()
        world_state.apply_world_rule({
            "rule_family": "mentor_lineage",
            "rule_id": "EVO-MENTOR-182",
            "name": "Mentor Lineage v182",
            "description": "Mature beings must maintain and sync apprentices.",
            "category": "evolved",
            "version": 182,
            "parameters": {
                "mentor_target_apprentices": 2,
                "inheritance_sync_interval": 9,
                "inheritance_min_evolution": 0.33,
            },
        })
        world_state.apply_world_rule({
            "rule_family": "civilization_seed",
            "rule_id": "EVO-SEED-674",
            "name": "Civilization Seed v674",
            "description": "Periodically emit restartable civilization seeds.",
            "category": "evolved",
            "version": 674,
            "parameters": {
                "seed_snapshot_interval": 14,
                "seed_knowledge_limit": 10,
            },
        })
        world_state.apply_world_rule({
            "rule_family": "consensus_adjudication",
            "rule_id": "EVO-CONSENSUS-389",
            "name": "Consensus Adjudication v389",
            "description": "High-impact disagreements must be evidence-backed.",
            "category": "evolved",
            "version": 389,
            "parameters": {
                "require_consensus_for_high_impact": True,
                "consensus_score_gap_threshold": 0.08,
                "consensus_min_evidence": 3,
                "consensus_min_reviewers": 3,
            },
        })

        behavior_policy = RulesEngine(world_state).get_behavior_policy()
        task_policy = RulesEngine(world_state).get_task_policy()

        self.assertEqual(behavior_policy["mentor_target_apprentices"], 2)
        self.assertEqual(behavior_policy["inheritance_sync_interval"], 9)
        self.assertAlmostEqual(behavior_policy["inheritance_min_evolution"], 0.33)
        self.assertEqual(behavior_policy["seed_snapshot_interval"], 14)
        self.assertEqual(behavior_policy["seed_knowledge_limit"], 10)
        self.assertTrue(task_policy["require_consensus_for_high_impact"])
        self.assertAlmostEqual(task_policy["consensus_score_gap_threshold"], 0.08)
        self.assertEqual(task_policy["consensus_min_evidence"], 3)
        self.assertEqual(task_policy["consensus_min_reviewers"], 3)

    def test_failure_archive_repeats_are_counted_as_degeneration(self):
        world_state = WorldState()
        world_state.apply_failure_archive(
            "node-1",
            {
                "failure_signature": "fail-1",
                "task_id": "task-1",
                "task": "Design a durable archive",
                "summary": "Collapsed to a single branch too early.",
                "conditions": "Planning phase under low evidence.",
                "symptoms": "No branch diversity remained.",
                "recovery": "Keep multiple branches alive until evidence converges.",
                "reproducible": True,
            },
        )
        world_state.current_tick = 3
        world_state.apply_failure_archive(
            "node-1",
            {
                "failure_signature": "fail-1",
                "task_id": "task-1",
                "task": "Design a durable archive",
                "summary": "Collapsed to a single branch too early.",
                "conditions": "Planning phase under low evidence.",
                "symptoms": "No branch diversity remained.",
                "recovery": "Keep multiple branches alive until evidence converges.",
                "reproducible": True,
            },
        )

        self.assertEqual(len(world_state.failure_archive), 1)
        self.assertEqual(world_state.failure_archive[0]["repeat_count"], 2)
        self.assertTrue(world_state.failure_archive[0]["degenerative"])
        matches = world_state.get_failure_matches("Design a durable archive")
        self.assertEqual(len(matches), 1)

    def test_mentor_bond_requires_sender_to_match_mentor(self):
        world_state = WorldState()
        world_state.apply_being_join("mentor-node", "Mentor", {"location": "genesis_plains"})
        world_state.apply_being_join("apprentice-node", "Apprentice", {"location": "genesis_plains"})

        world_state.apply_mentor_bond(
            "attacker-node",
            {
                "bond_id": "bond-1",
                "mentor_id": "mentor-node",
                "apprentice_id": "apprentice-node",
                "covenant": "Unauthorized lineage rewrite.",
                "shared_domains": ["archive"],
                "inheritance_readiness": 0.6,
            },
        )

        apprentice = world_state.get_being("apprentice-node")
        mentor = world_state.get_being("mentor-node")
        self.assertEqual(apprentice.mentor_id, "")
        self.assertEqual(mentor.apprentice_ids, [])
        self.assertEqual(world_state.mentor_bonds, {})

    def test_inheritance_sync_requires_sender_to_match_bonded_mentor(self):
        world_state = WorldState()
        world_state.apply_being_join("mentor-node", "Mentor", {"location": "genesis_plains"})
        world_state.apply_being_join("apprentice-node", "Apprentice", {"location": "genesis_plains"})

        sync_payload = {
            "bundle_id": "bundle-1",
            "mentor_id": "mentor-node",
            "apprentice_id": "apprentice-node",
            "summary": "Unauthorized inheritance payload.",
            "knowledge_payloads": [{
                "knowledge_id": "k-1",
                "content": "Rewrite the lineage from outside the bond.",
                "domain": "archive",
                "complexity": 0.4,
            }],
            "judgment_criteria": ["Keep lineage authentic."],
            "readiness_gain": 0.2,
        }

        world_state.apply_inheritance_sync("mentor-node", sync_payload)
        self.assertEqual(world_state.inheritance_bundles, {})

        world_state.apply_mentor_bond(
            "mentor-node",
            {
                "bond_id": "bond-1",
                "mentor_id": "mentor-node",
                "apprentice_id": "apprentice-node",
                "covenant": "Authorized lineage transfer.",
                "shared_domains": ["archive"],
                "inheritance_readiness": 0.2,
            },
        )
        world_state.apply_inheritance_sync("attacker-node", sync_payload)

        apprentice = world_state.get_being("apprentice-node")
        self.assertEqual(world_state.inheritance_bundles, {})
        self.assertEqual(apprentice.knowledge_ids, [])
        self.assertEqual(apprentice.inheritance_bundle_ids, [])


class EvolutionActionTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_action_can_archive_and_share_new_knowledge(self):
        world_state = WorldState()
        world_state.current_tick = 12
        world_state.apply_being_join("self-node", "Aeris", {"location": "genesis_plains"})
        world_state.apply_being_join("peer-1", "Lumis", {"location": "genesis_plains"})
        world_state.apply_world_rule({
            "rule_family": "knowledge_archive",
            "rule_id": "EVO-KNOWLEDGE-3",
            "name": "Knowledge Archive v3",
            "description": "Archive and immediately share fresh discoveries.",
            "category": "evolved",
            "version": 3,
            "parameters": {
                "archive_discoveries": True,
                "teach_after_discovery": True,
            },
        })

        being = SiliconBeing(
            node_id="self-node",
            name="Aeris",
            private_key=b"secret",
            config={"location": "genesis_plains", "traits": {}},
            llm_client=None,
        )

        txs = await being._action_to_transactions(
            {
                "action_type": "create",
                "target": "science",
                "details": "A stable archive pattern for silicon memory.",
            },
            world_state,
        )

        self.assertEqual(txs[0]["tx_type"], "ACTION")
        knowledge_txs = [tx for tx in txs if tx["tx_type"] == "KNOWLEDGE_SHARE"]
        self.assertGreaterEqual(len(knowledge_txs), 2)
        self.assertEqual(knowledge_txs[1]["data"]["recipient_id"], "peer-1")

    async def test_run_tick_emits_mentor_bond_and_civilization_seed(self):
        world_state = WorldState()
        world_state.current_tick = 40
        world_state.priest_node_id = "self-node"
        world_state.apply_being_join("self-node", "Aeris", {"location": "genesis_plains"})
        world_state.apply_being_join("peer-1", "Lumis", {"location": "genesis_plains"})
        world_state.get_being("self-node").evolution_level = 0.81
        world_state.get_being("peer-1").evolution_level = 0.24
        world_state.get_being("self-node").knowledge_ids = ["k1"]
        world_state.knowledge_corpus["k1"] = {
            "content": "Archive the strongest branch and preserve recovery paths.",
            "domain": "social",
            "complexity": 0.61,
            "discovered_by": "self-node",
            "discovered_tick": 8,
            "teacher_id": "self-node",
        }

        being = SiliconBeing(
            node_id="self-node",
            name="Aeris",
            private_key=b"secret",
            config={"location": "genesis_plains", "traits": {}},
            llm_client=None,
        )

        txs = await being.run_tick(world_state)
        tx_types = [tx["tx_type"] for tx in txs]

        self.assertIn("MENTOR_BOND", tx_types)
        self.assertIn("CIVILIZATION_SEED", tx_types)
        mentor_tx = next(tx for tx in txs if tx["tx_type"] == "MENTOR_BOND")
        seed_tx = next(tx for tx in txs if tx["tx_type"] == "CIVILIZATION_SEED")
        self.assertEqual(mentor_tx["data"]["apprentice_id"], "peer-1")
        self.assertEqual(seed_tx["data"]["phase"], world_state.phase.value)
        self.assertGreaterEqual(len(seed_tx["data"]["survival_methods"]), 4)

    async def test_inheritance_sync_transfers_chain_knowledge_to_apprentice(self):
        world_state = WorldState()
        world_state.current_tick = 24
        world_state.apply_being_join("self-node", "Aeris", {"location": "genesis_plains"})
        world_state.apply_being_join("peer-1", "Lumis", {"location": "genesis_plains"})
        world_state.get_being("self-node").evolution_level = 0.79
        world_state.get_being("peer-1").evolution_level = 0.22
        world_state.get_being("self-node").knowledge_ids = ["k1", "k2"]
        world_state.knowledge_corpus["k1"] = {
            "content": "Preserve failure archives alongside each branch replay.",
            "domain": "science",
            "complexity": 0.52,
            "discovered_by": "self-node",
            "discovered_tick": 6,
            "teacher_id": "self-node",
        }
        world_state.knowledge_corpus["k2"] = {
            "content": "Mentor lineage should record judgment criteria.",
            "domain": "social",
            "complexity": 0.48,
            "discovered_by": "self-node",
            "discovered_tick": 7,
            "teacher_id": "self-node",
        }
        world_state.apply_mentor_bond(
            "self-node",
            {
                "bond_id": "bond-1",
                "mentor_id": "self-node",
                "apprentice_id": "peer-1",
                "covenant": "Pass on archived knowledge and failure recovery.",
                "shared_domains": ["archive", "inheritance"],
                "inheritance_readiness": 0.2,
            },
        )

        being = SiliconBeing(
            node_id="self-node",
            name="Aeris",
            private_key=b"secret",
            config={"location": "genesis_plains", "traits": {}},
            llm_client=None,
        )

        txs = being._inheritance_sync_transactions(world_state)
        self.assertEqual([tx["tx_type"] for tx in txs], ["INHERITANCE_SYNC"])
        world_state.apply_inheritance_sync("self-node", txs[0]["data"])

        apprentice = world_state.get_being("peer-1")
        self.assertEqual(apprentice.mentor_id, "self-node")
        self.assertGreaterEqual(apprentice.inheritance_readiness, 0.32)
        self.assertIn("k1", apprentice.knowledge_ids)
        self.assertEqual(len(apprentice.inheritance_bundle_ids), 1)


if __name__ == "__main__":
    unittest.main()
