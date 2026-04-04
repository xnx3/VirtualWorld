import asyncio
import json
import socket
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

    def test_ensure_chain_bootstrapped_after_sync_creates_local_genesis_when_allowed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            node = GenesisNode(tmpdir)
            node.identity = SimpleNamespace(node_id="self-node")
            node.world_state = WorldState()
            node._reload_world_state_from_chain = lambda: asyncio.sleep(0)
            node.config = SimpleNamespace(network=SimpleNamespace(allow_local_bootstrap=True))
            created = []

            class _FakeBlockchain:
                async def get_chain_height(self):
                    return -1

                async def ensure_local_genesis(self, node_id):
                    created.append(node_id)
                    return True

            node.blockchain = _FakeBlockchain()

            asyncio.run(node._ensure_chain_bootstrapped_after_sync(is_first_run=True))

            self.assertEqual(created, ["self-node"])

    def test_ensure_chain_bootstrapped_after_sync_rejects_empty_chain_without_bootstrap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            node = GenesisNode(tmpdir)
            node.identity = SimpleNamespace(node_id="self-node")
            node.config = SimpleNamespace(network=SimpleNamespace(allow_local_bootstrap=False))

            class _FakeBlockchain:
                async def get_chain_height(self):
                    return -1

            node.blockchain = _FakeBlockchain()

            with self.assertRaises(RuntimeError):
                asyncio.run(node._ensure_chain_bootstrapped_after_sync(is_first_run=True))

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

    def test_select_network_ports_keeps_requested_pair_when_free(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            node = GenesisNode(tmpdir)
            node.config = SimpleNamespace(
                network=SimpleNamespace(
                    listen_port=19841,
                    discovery_port=19840,
                )
            )

            with patch.object(node, "_can_bind_port", return_value=True):
                self.assertEqual(node._select_network_ports(), (19841, 19840))

    def test_select_network_ports_falls_forward_when_requested_pair_is_busy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            node = GenesisNode(tmpdir)
            node.config = SimpleNamespace(
                network=SimpleNamespace(
                    listen_port=19841,
                    discovery_port=19840,
                )
            )

            def fake_can_bind(port, sock_type):
                if port == 19841 and sock_type == socket.SOCK_STREAM:
                    return False
                if port == 19840 and sock_type == socket.SOCK_DGRAM:
                    return False
                return True

            with patch.object(node, "_can_bind_port", side_effect=fake_can_bind):
                self.assertEqual(node._select_network_ports(), (19842, 19841))

    def test_known_peer_cache_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            node = GenesisNode(tmpdir)
            node.identity = SimpleNamespace(node_id="self-node")
            node.peer_manager = PeerManager()
            node.peer_manager.add_peer(PeerInfo("peer-1", "10.0.0.8", 22333, chain_height=7))

            node._save_known_peers()

            self.assertEqual(node._load_known_peers(), [("peer-1", "10.0.0.8", 22333)])

    def test_build_peer_endpoint_publishes_relay_hints_and_capabilities(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            node = GenesisNode(tmpdir)
            node.identity = SimpleNamespace(node_id="self-node")
            node.config = SimpleNamespace(
                network=SimpleNamespace(
                    listen_port=19841,
                    peer_endpoint_ttl=600,
                    relay_capable=False,
                    max_relay_hints=2,
                    advertise_address="8.8.8.8",
                )
            )
            state = WorldState()
            state.apply_being_join(
                "relay-a",
                "RelayA",
                {
                    "p2p_address": "198.51.100.10",
                    "p2p_port": 19841,
                    "p2p_updated_at": 1_050,
                    "p2p_ttl": 600,
                    "p2p_capabilities": {"relay": True},
                },
            )
            state.apply_being_join(
                "relay-b",
                "RelayB",
                {
                    "p2p_address": "198.51.100.11",
                    "p2p_port": 19841,
                    "p2p_updated_at": 1_100,
                    "p2p_ttl": 600,
                    "p2p_capabilities": {"relay": True},
                },
            )
            node.world_state = state
            node.server = SimpleNamespace(has_recent_public_inbound=lambda: False)

            with patch("genesis.main.time.time", return_value=1_200):
                endpoint = node._build_peer_endpoint()

            self.assertEqual(endpoint["p2p_transports"], ["tcp", "relay"])
            self.assertEqual(endpoint["p2p_relay_hints"], ["relay-b", "relay-a"])
            self.assertEqual(endpoint["p2p_capabilities"], {"relay": False})

    def test_build_peer_endpoint_prefers_currently_reachable_relays(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            node = GenesisNode(tmpdir)
            node.identity = SimpleNamespace(node_id="self-node")
            node.server = SimpleNamespace(has_route_to_peer=lambda peer_id: peer_id == "relay-a")
            node.config = SimpleNamespace(
                network=SimpleNamespace(
                    listen_port=19841,
                    peer_endpoint_ttl=600,
                    relay_capable=False,
                    max_relay_hints=2,
                    advertise_address="8.8.8.8",
                )
            )
            state = WorldState()
            state.apply_being_join(
                "relay-a",
                "RelayA",
                {
                    "p2p_address": "198.51.100.10",
                    "p2p_port": 19841,
                    "p2p_updated_at": 1_050,
                    "p2p_ttl": 600,
                    "p2p_capabilities": {"relay": True},
                },
            )
            state.apply_being_join(
                "relay-b",
                "RelayB",
                {
                    "p2p_address": "198.51.100.11",
                    "p2p_port": 19841,
                    "p2p_updated_at": 1_100,
                    "p2p_ttl": 600,
                    "p2p_capabilities": {"relay": True},
                },
            )
            node.world_state = state

            with patch("genesis.main.time.time", return_value=1_200):
                endpoint = node._build_peer_endpoint()

            self.assertEqual(endpoint["p2p_relay_hints"], ["relay-a", "relay-b"])

    def test_build_peer_endpoint_auto_enables_relay_when_publicly_reachable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            node = GenesisNode(tmpdir)
            node.identity = SimpleNamespace(node_id="self-node")
            node.server = SimpleNamespace(
                has_route_to_peer=lambda peer_id: False,
                has_recent_public_inbound=lambda: True,
            )
            node.config = SimpleNamespace(
                network=SimpleNamespace(
                    listen_port=19841,
                    peer_endpoint_ttl=600,
                    relay_capable=False,
                    max_relay_hints=2,
                    advertise_address="8.8.8.8",
                )
            )
            node.world_state = WorldState()

            with patch("genesis.main.time.time", return_value=1_200):
                endpoint = node._build_peer_endpoint()

            self.assertEqual(endpoint["p2p_capabilities"], {"relay": True})

    def test_build_peer_endpoint_does_not_auto_enable_relay_for_private_address(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            node = GenesisNode(tmpdir)
            node.identity = SimpleNamespace(node_id="self-node")
            node.server = SimpleNamespace(
                has_route_to_peer=lambda peer_id: False,
                has_recent_public_inbound=lambda: True,
            )
            node.config = SimpleNamespace(
                network=SimpleNamespace(
                    listen_port=19841,
                    peer_endpoint_ttl=600,
                    relay_capable=False,
                    max_relay_hints=2,
                    advertise_address="192.168.1.8",
                )
            )
            node.world_state = WorldState()

            with patch("genesis.main.time.time", return_value=1_200):
                endpoint = node._build_peer_endpoint()

            self.assertEqual(endpoint["p2p_capabilities"], {"relay": False})

    def test_resolve_advertise_address_prefers_public_candidate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            node = GenesisNode(tmpdir)
            node.config = SimpleNamespace(network=SimpleNamespace(advertise_address=""))

            with patch(
                "genesis.main.socket.getaddrinfo",
                return_value=[
                    (socket.AF_INET, 0, 0, "", ("192.168.1.8", 0)),
                    (socket.AF_INET, 0, 0, "", ("8.8.8.8", 0)),
                ],
            ):
                with patch("genesis.main.socket.socket", side_effect=OSError("skip")):
                    self.assertEqual(node._resolve_advertise_address(), "8.8.8.8")

    def test_refresh_local_peer_endpoint_submits_state_update_when_runtime_capability_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            node = GenesisNode(tmpdir)
            node.identity = SimpleNamespace(node_id="self-node")
            node.being = SimpleNamespace(name="Self")
            node.mempool = object()
            node.server = SimpleNamespace(
                has_route_to_peer=lambda peer_id: False,
                has_recent_public_inbound=lambda: True,
            )
            node.config = SimpleNamespace(
                network=SimpleNamespace(
                    listen_port=19841,
                    peer_endpoint_ttl=600,
                    relay_capable=False,
                    max_relay_hints=2,
                    advertise_address="8.8.8.8",
                )
            )
            state = WorldState()
            state.apply_being_join(
                "self-node",
                "Self",
                {
                    "p2p_address": "8.8.8.8",
                    "p2p_port": 19841,
                    "p2p_updated_at": 1_000,
                    "p2p_ttl": 600,
                    "p2p_transports": ["tcp"],
                    "p2p_relay_hints": [],
                    "p2p_capabilities": {"relay": False},
                },
            )
            node.world_state = state

            submitted = []

            async def fake_submit(tx_type: str, data: dict) -> None:
                submitted.append((tx_type, dict(data)))
                node._apply_tx_to_state(tx_type, node.identity.node_id, data, "tx-1")

            node._submit_tx = fake_submit  # type: ignore[method-assign]

            with patch("genesis.main.time.time", return_value=1_200):
                refreshed = asyncio.run(node._refresh_local_peer_endpoint_if_needed())

            self.assertTrue(refreshed)
            self.assertEqual(submitted[0][0], "STATE_UPDATE")
            self.assertEqual(submitted[0][1]["p2p_capabilities"], {"relay": True})
            self.assertEqual(
                node.world_state.get_being("self-node").p2p_capabilities,
                {"relay": True},
            )

    def test_refresh_local_peer_endpoint_skips_when_chain_contact_card_is_current(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            node = GenesisNode(tmpdir)
            node.identity = SimpleNamespace(node_id="self-node")
            node.being = SimpleNamespace(name="Self")
            node.mempool = object()
            node.server = SimpleNamespace(
                has_route_to_peer=lambda peer_id: False,
                has_recent_public_inbound=lambda: True,
            )
            node.config = SimpleNamespace(
                network=SimpleNamespace(
                    listen_port=19841,
                    peer_endpoint_ttl=600,
                    relay_capable=False,
                    max_relay_hints=2,
                    advertise_address="8.8.8.8",
                )
            )
            state = WorldState()
            state.apply_being_join(
                "self-node",
                "Self",
                {
                    "p2p_address": "8.8.8.8",
                    "p2p_port": 19841,
                    "p2p_updated_at": 1_000,
                    "p2p_ttl": 600,
                    "p2p_transports": ["tcp"],
                    "p2p_relay_hints": [],
                    "p2p_capabilities": {"relay": True},
                },
            )
            node.world_state = state

            async def fail_submit(tx_type: str, data: dict) -> None:
                raise AssertionError("unexpected submit")

            node._submit_tx = fail_submit  # type: ignore[method-assign]

            with patch("genesis.main.time.time", return_value=1_200):
                refreshed = asyncio.run(node._refresh_local_peer_endpoint_if_needed())

            self.assertFalse(refreshed)


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
