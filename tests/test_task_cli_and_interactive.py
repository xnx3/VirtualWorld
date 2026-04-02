import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from genesis.main import GenesisNode, enqueue_user_task


class TaskQueueHelperTests(unittest.TestCase):
    def test_enqueue_user_task_writes_command_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            record = enqueue_user_task(tmpdir, "count silicon beings")
            task_file = Path(tmpdir) / "commands" / "task.json"

            self.assertTrue(task_file.exists())
            queued = json.loads(task_file.read_text(encoding="utf-8"))
            self.assertEqual(len(queued), 1)
            self.assertEqual(queued[0]["task"], "count silicon beings")
            self.assertEqual(queued[0]["task_id"], record["task_id"])
            self.assertEqual(queued[0]["status"], "queued")


class InteractiveInputTests(unittest.TestCase):
    def test_accept_user_text_assigns_task_to_active_being(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            node = GenesisNode(tmpdir)
            assigned: list[str] = []
            node.being = SimpleNamespace(assign_task=lambda task: assigned.append(task))
            node._save_task_status = lambda: None

            result = node.accept_user_text("Please inspect active beings")

            self.assertEqual(result["type"], "task")
            self.assertFalse(result["buffered"])
            self.assertEqual(assigned, ["Please inspect active beings"])

    def test_accept_user_text_stop_sets_shutdown_flag(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            node = GenesisNode(tmpdir)

            result = node.accept_user_text("/stop")

            self.assertEqual(result["type"], "stop")
            self.assertTrue(node._shutdown)

    def test_accept_user_text_without_being_buffers_task(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            node = GenesisNode(tmpdir)

            result = node.accept_user_text("buffer this task")

            self.assertEqual(result["type"], "task")
            self.assertTrue(result["buffered"])
            task_file = Path(tmpdir) / "commands" / "task.json"
            queued = json.loads(task_file.read_text(encoding="utf-8"))
            self.assertEqual(queued[0]["task"], "buffer this task")


if __name__ == "__main__":
    unittest.main()
