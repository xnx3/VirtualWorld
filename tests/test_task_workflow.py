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

        expected_statuses = ["collaborating", "branching", "synthesizing", "completed"]
        for tick, expected_status in enumerate(expected_statuses, start=1):
            world_state.current_tick = tick
            txs = await being._process_user_tasks(world_state)
            self.assertEqual(len(txs), 1)
            self.assertEqual(txs[0]["tx_type"], "ACTION")
            self.assertEqual(txs[0]["data"]["action_type"], "deep_think")
            self.assertEqual(being._user_tasks[0]["status"], expected_status)

        completed = being.get_task_results()
        self.assertEqual(len(completed), 1)
        result = completed[0]
        self.assertEqual(result["task_id"], "task-1")
        self.assertGreaterEqual(len(result["progress_log"]), 4)
        self.assertGreaterEqual(len(result["collaborators"]), 3)
        self.assertGreaterEqual(len(result["council_rounds"]), 1)
        self.assertGreaterEqual(len(result["branch_findings"]), 1)
        self.assertIn("Collaborators:", result["result"])
        self.assertIn("Council Rounds:", result["result"])
        self.assertIn("Best Path:", result["result"])
        self.assertIn("Result:", result["result"])


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


if __name__ == "__main__":
    unittest.main()
