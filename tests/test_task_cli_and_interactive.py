import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from genesis.being.agent import SiliconBeing
from genesis.main import GenesisNode, enqueue_user_task
from genesis.network.peer import PeerInfo, PeerManager
from genesis.world.state import WorldState


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

    def test_enqueue_user_task_deduplicates_same_active_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            first = enqueue_user_task(tmpdir, "count silicon beings")
            second = enqueue_user_task(tmpdir, "  Count   silicon    beings ")
            task_file = Path(tmpdir) / "commands" / "task.json"
            queued = json.loads(task_file.read_text(encoding="utf-8"))

            self.assertEqual(first["task_id"], second["task_id"])
            self.assertTrue(second["deduplicated"])
            self.assertEqual(len(queued), 1)


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


class GenesisStartupGuardTests(unittest.TestCase):
    def test_first_run_requires_synced_civilization_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            node = GenesisNode(tmpdir)
            node.config = SimpleNamespace(network=SimpleNamespace(allow_local_bootstrap=False))
            node.world_state = WorldState()

            self.assertTrue(node._should_block_local_first_run(is_first_run=True))

    def test_first_run_allows_existing_synced_civilization(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            node = GenesisNode(tmpdir)
            node.config = SimpleNamespace(network=SimpleNamespace(allow_local_bootstrap=False))
            state = WorldState()
            state.apply_being_join("peer-1", "Lumis", {"p2p_address": "10.0.0.8", "p2p_port": 22333})
            node.world_state = state

            self.assertFalse(node._should_block_local_first_run(is_first_run=True))

    def test_first_run_can_explicitly_allow_local_bootstrap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            node = GenesisNode(tmpdir)
            node.config = SimpleNamespace(network=SimpleNamespace(allow_local_bootstrap=True))
            node.world_state = WorldState()

            self.assertFalse(node._should_block_local_first_run(is_first_run=True))

    def test_chain_seed_peers_skip_expired_on_chain_endpoint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            node = GenesisNode(tmpdir)
            node.identity = SimpleNamespace(node_id="self-node")
            state = WorldState()
            state.apply_being_join(
                "fresh-peer",
                "Lumis",
                {
                    "p2p_address": "10.0.0.8",
                    "p2p_port": 22333,
                    "p2p_updated_at": 1_000,
                    "p2p_ttl": 300,
                },
            )
            state.apply_being_join(
                "stale-peer",
                "Veyra",
                {
                    "p2p_address": "10.0.0.9",
                    "p2p_port": 22334,
                    "p2p_updated_at": 1_000,
                    "p2p_ttl": 60,
                },
            )
            node.world_state = state

            with patch("genesis.main.time.time", return_value=1_200):
                self.assertEqual(
                    node._get_chain_seed_peers(),
                    [("fresh-peer", "10.0.0.8", 22333)],
                )

    def test_known_peer_cache_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            node = GenesisNode(tmpdir)
            node.identity = SimpleNamespace(node_id="self-node")
            node.peer_manager = PeerManager()
            node.peer_manager.add_peer(PeerInfo("peer-1", "10.0.0.8", 22333, chain_height=7))

            node._save_known_peers()

            self.assertEqual(node._load_known_peers(), [("peer-1", "10.0.0.8", 22333)])


class BeingTaskDedupTests(unittest.TestCase):
    def test_silicon_being_ignores_duplicate_active_task_text(self):
        being = SiliconBeing(
            node_id="self-node",
            name="Aeris",
            private_key=b"secret",
            config={"location": "genesis_plains", "traits": {}},
            llm_client=None,
        )
        being.assign_task("How many active silicon beings are there?")
        being.assign_task("  how many ACTIVE silicon beings are there? ")

        self.assertEqual(len(being._user_tasks), 1)

    def test_existing_active_duplicates_are_collapsed(self):
        being = SiliconBeing(
            node_id="self-node",
            name="Aeris",
            private_key=b"secret",
            config={"location": "genesis_plains", "traits": {}},
            llm_client=None,
        )
        being._user_tasks = [
            {"task_id": "task-old", "task": "count active beings", "status": "queued", "created_at": 100},
            {"task_id": "task-new", "task": "Count   active beings", "status": "branching", "created_at": 101},
        ]

        being._deduplicate_active_tasks()

        self.assertEqual(len(being._user_tasks), 1)
        self.assertEqual(being._user_tasks[0]["task_id"], "task-new")


if __name__ == "__main__":
    unittest.main()
