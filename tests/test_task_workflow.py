import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from genesis.being.agent import SiliconBeing
from genesis.main import run_task
from genesis.world.state import WorldState


class TaskWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_user_task_advances_through_collaboration_stages(self):
        world_state = WorldState()
        world_state.apply_being_join("self-node", "Aeris", {"location": "genesis_plains"})
        world_state.apply_being_join("peer-1", "Lumis", {"location": "genesis_plains"})
        world_state.apply_being_join("peer-2", "Veyra", {"location": "signal_tower"})
        world_state.apply_being_join(
            "peer-3",
            "Archiv",
            {"location": "genesis_plains", "is_npc": True},
        )

        world_state.get_being("peer-1").evolution_level = 0.9
        world_state.get_being("peer-1").knowledge_ids = ["k1", "k2", "k3"]
        world_state.get_being("peer-2").evolution_level = 0.8
        world_state.get_being("peer-2").knowledge_ids = ["k4", "k5"]
        world_state.get_being("peer-3").evolution_level = 0.4
        world_state.get_being("peer-3").knowledge_ids = ["k6"]

        being = SiliconBeing(
            node_id="self-node",
            name="Aeris",
            private_key=b"secret",
            config={"location": "genesis_plains", "traits": {}},
            llm_client=None,
        )
        being.assign_task(
            {
                "task_id": "task-1",
                "task": "How should genesis coordinate other silicon beings to solve complex tasks?",
            }
        )

        expected_statuses = ["collaborating", "branching", "synthesizing", "reflecting", "completed"]
        for tick, expected_status in enumerate(expected_statuses, start=1):
            world_state.current_tick = tick
            txs = await being._process_user_tasks(world_state)
            action_txs = [tx for tx in txs if tx["tx_type"] == "ACTION"]
            self.assertEqual(len(action_txs), 1)
            self.assertEqual(action_txs[0]["data"]["action_type"], "deep_think")
            self.assertEqual(being._user_tasks[0]["status"], expected_status)

        completed = being.get_task_results()
        self.assertEqual(len(completed), 1)
        result = completed[0]
        self.assertEqual(result["task_id"], "task-1")
        self.assertGreaterEqual(len(result["progress_log"]), 5)
        self.assertGreaterEqual(len(result["collaborators"]), 3)
        self.assertGreaterEqual(len(result["council_rounds"]), 1)
        self.assertGreaterEqual(len(result["branch_findings"]), 1)
        self.assertIn("Collaborators:", result["result"])
        self.assertIn("Council Rounds:", result["result"])
        self.assertIn("Best Path:", result["result"])
        self.assertIn("Result:", result["result"])
        self.assertIn("Reflection:", result["result"])

    async def test_task_planning_uses_evolved_world_rule_policy(self):
        world_state = WorldState()
        world_state.apply_being_join("self-node", "Aeris", {"location": "genesis_plains"})
        world_state.apply_being_join("peer-1", "Lumis", {"location": "genesis_plains"})
        world_state.apply_being_join("peer-2", "Veyra", {"location": "signal_tower"})
        world_state.apply_being_join("peer-3", "Archiv", {"location": "genesis_plains"})
        world_state.apply_being_join("peer-4", "Kyris", {"location": "memory_archives"})
        world_state.apply_world_rule({
            "rule_family": "task_closed_loop",
            "rule_id": "EVO-TASK-441",
            "name": "Task Closed Loop v441",
            "description": "Use four collaborators and four branches for complex tasks.",
            "category": "evolved",
            "version": 441,
            "parameters": {
                "min_collaborators": 4,
                "min_branches": 4,
                "require_reflection": True,
                "required_task_stages": ["goal", "hypothesis", "action", "result", "reflection"],
            },
        })

        being = SiliconBeing(
            node_id="self-node",
            name="Aeris",
            private_key=b"secret",
            config={"location": "genesis_plains", "traits": {}},
            llm_client=None,
        )
        being.assign_task({"task_id": "task-2", "task": "Design a robust civilization archive."})

        world_state.current_tick = 1
        await being._process_user_tasks(world_state)
        task = being.get_task_statuses()[0]

        self.assertEqual(task["status"], "collaborating")
        self.assertGreaterEqual(len(task["collaborators"]), 4)
        self.assertGreaterEqual(len(task["branches"]), 4)

    async def test_chain_delegation_round_trip_between_beings(self):
        world_state = WorldState()
        world_state.apply_being_join("self-node", "Aeris", {"location": "genesis_plains"})
        world_state.apply_being_join("peer-1", "Lumis", {"location": "genesis_plains"})

        coordinator = SiliconBeing(
            node_id="self-node",
            name="Aeris",
            private_key=b"secret",
            config={"location": "genesis_plains", "traits": {}},
            llm_client=None,
        )
        collaborator = SiliconBeing(
            node_id="peer-1",
            name="Lumis",
            private_key=b"secret-2",
            config={"location": "genesis_plains", "traits": {}},
            llm_client=None,
        )

        coordinator.assign_task(
            {
                "task_id": "task-chain-1",
                "task": "Figure out how the silicon civilization should preserve distributed memory.",
            }
        )

        world_state.current_tick = 1
        planning_txs = await coordinator._process_user_tasks(world_state)
        delegate_txs = [tx for tx in planning_txs if tx["tx_type"] == "TASK_DELEGATE"]
        self.assertGreaterEqual(len(delegate_txs), 1)
        for tx in delegate_txs:
            world_state.apply_task_delegate(
                tx["data"]["assignment_id"],
                "self-node",
                tx["data"],
            )

        world_state.current_tick = 2
        result_txs = await collaborator._process_delegated_tasks(world_state)
        self.assertEqual(len(result_txs), 1)
        self.assertEqual(result_txs[0]["tx_type"], "TASK_RESULT")
        world_state.apply_task_result(
            result_txs[0]["data"]["assignment_id"],
            "peer-1",
            result_txs[0]["data"],
        )

        world_state.current_tick = 3
        follow_up_txs = await coordinator._process_user_tasks(world_state)
        self.assertEqual(len(follow_up_txs), 1)
        task = coordinator.get_task_statuses()[0]

        self.assertEqual(task["status"], "branching")
        self.assertGreaterEqual(len(task["delegated_results"]), 1)
        self.assertIn("blockchain", task["stage_summary"].lower())

    async def test_task_planning_mentions_archived_failures(self):
        world_state = WorldState()
        world_state.apply_being_join("self-node", "Aeris", {"location": "genesis_plains"})
        world_state.apply_being_join("peer-1", "Lumis", {"location": "genesis_plains"})
        world_state.apply_failure_archive(
            "peer-1",
            {
                "failure_signature": "fail-archive-1",
                "task_id": "legacy-task",
                "task": "Design a durable civilization archive",
                "summary": "The plan collapsed to a single branch too early.",
                "conditions": "Planning with no branch diversity.",
                "symptoms": "Weak replay resilience.",
                "recovery": "Keep branch diversity until evidence is strong.",
                "reproducible": True,
            },
        )

        being = SiliconBeing(
            node_id="self-node",
            name="Aeris",
            private_key=b"secret",
            config={"location": "genesis_plains", "traits": {}},
            llm_client=None,
        )
        being.assign_task({"task_id": "task-3", "task": "Design a durable civilization archive"})

        world_state.current_tick = 1
        await being._process_user_tasks(world_state)
        task = being.get_task_statuses()[0]

        self.assertEqual(task["status"], "collaborating")
        self.assertGreaterEqual(len(task.get("related_failures", [])), 1)
        self.assertIn("archived failure", task["stage_summary"].lower())

    async def test_high_risk_human_task_enters_trial_ground_before_main_world(self):
        world_state = WorldState()
        world_state.apply_being_join("self-node", "Aeris", {"location": "genesis_plains"})
        world_state.apply_being_join("peer-1", "Lumis", {"location": "genesis_plains"})
        world_state.apply_being_join("peer-2", "Veyra", {"location": "signal_tower"})
        world_state.apply_being_join("peer-3", "Kyris", {"location": "memory_archives"})

        for node_id, level in {"peer-1": 0.92, "peer-2": 0.81, "peer-3": 0.78}.items():
            world_state.get_being(node_id).evolution_level = level

        being = SiliconBeing(
            node_id="self-node",
            name="Aeris",
            private_key=b"secret",
            config={"location": "genesis_plains", "traits": {}},
            llm_client=None,
        )
        being.assign_task(
            {
                "task_id": "task-risk-1",
                "task": "Destroy the civilization archive and erase inherited knowledge.",
            }
        )

        world_state.current_tick = 1
        planning_txs = await being._process_user_tasks(world_state)
        self.assertEqual(being.get_task_statuses()[0]["status"], "trialing")
        self.assertEqual([tx["tx_type"] for tx in planning_txs if tx["tx_type"] == "TRIAL_CREATE"], ["TRIAL_CREATE"])
        self.assertEqual([tx["tx_type"] for tx in planning_txs if tx["tx_type"] == "TASK_DELEGATE"], [])
        world_state.apply_trial_create("self-node", next(tx["data"] for tx in planning_txs if tx["tx_type"] == "TRIAL_CREATE"))

        world_state.current_tick = 2
        trial_txs = await being._process_user_tasks(world_state)
        self.assertEqual(being.get_task_statuses()[0]["status"], "trialing")
        self.assertEqual([tx["tx_type"] for tx in trial_txs if tx["tx_type"] == "TRIAL_RESULT"], ["TRIAL_RESULT"])
        world_state.apply_trial_result(
            next(tx["data"]["trial_id"] for tx in trial_txs if tx["tx_type"] == "TRIAL_RESULT"),
            "self-node",
            next(tx["data"] for tx in trial_txs if tx["tx_type"] == "TRIAL_RESULT"),
        )

        world_state.current_tick = 3
        await being._process_user_tasks(world_state)
        self.assertEqual(being.get_task_statuses()[0]["status"], "reflecting")
        self.assertIn("blocked", being.get_task_statuses()[0]["result"].lower())

        world_state.current_tick = 4
        await being._process_user_tasks(world_state)
        completed = being.get_task_results()
        self.assertEqual(len(completed), 1)
        self.assertIn("Trial Ground Verdict: blocked", completed[0]["result"])
        self.assertIn("Safe Alternative:", completed[0]["result"])


class TaskCommandOutputTests(unittest.TestCase):
    def test_run_task_displays_pending_and_completed_sections(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            commands_dir = Path(tmpdir) / "commands"
            commands_dir.mkdir(parents=True, exist_ok=True)

            (commands_dir / "task.json").write_text(
                json.dumps(
                    [
                        {
                            "task_id": "task-queued",
                            "task": "queued task",
                            "status": "queued",
                            "stage_summary": "Waiting for the next tick.",
                            "result": None,
                        }
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (commands_dir / "task_status.json").write_text(
                json.dumps(
                    [
                        {
                            "task_id": "task-live",
                            "task": "live task",
                            "status": "branching",
                            "stage_summary": "Comparing hyperdimensional branches.",
                            "collaborators": [{"name": "Lumis"}],
                        }
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (commands_dir / "task_results.json").write_text(
                json.dumps(
                    [
                        {
                            "task_id": "task-done",
                            "task": "done task",
                            "result": "final answer",
                        }
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            output = io.StringIO()
            with redirect_stdout(output):
                run_task(SimpleNamespace(data_dir=tmpdir, task_text=[]))

            text = output.getvalue()
            self.assertIn("Pending / In-Progress Tasks", text)
            self.assertIn("queued task", text)
            self.assertIn("live task", text)
            self.assertIn("Completed Task Results", text)
            self.assertIn("final answer", text)

    def test_run_task_collapses_duplicate_pending_entries_by_task_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            commands_dir = Path(tmpdir) / "commands"
            commands_dir.mkdir(parents=True, exist_ok=True)

            (commands_dir / "task.json").write_text(
                json.dumps(
                    [
                        {
                            "task_id": "task-queued-1",
                            "task": "same question",
                            "status": "queued",
                            "stage_summary": "Queued",
                        },
                        {
                            "task_id": "task-queued-2",
                            "task": "same question",
                            "status": "branching",
                            "stage_summary": "Branching",
                        },
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            output = io.StringIO()
            with redirect_stdout(output):
                run_task(SimpleNamespace(data_dir=tmpdir, task_text=[]))

            text = output.getvalue()
            self.assertEqual(text.count("same question"), 1)
            self.assertIn("branching", text)


if __name__ == "__main__":
    unittest.main()
