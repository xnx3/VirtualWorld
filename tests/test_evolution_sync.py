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


if __name__ == "__main__":
    unittest.main()
