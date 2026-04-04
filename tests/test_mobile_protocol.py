import json
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from genesis.chain.chain import Blockchain
from genesis.chain.transaction import Transaction, TxType
from genesis.main import GenesisNode
from genesis.mobile.contact_card import build_peer_contact_card
from genesis.mobile.pairing_qr import build_pairing_payload, build_pairing_qr_text
from genesis.mobile.peer_snapshot import build_snapshot_peers
from genesis.node.identity import NodeIdentity
from genesis.world.state import WorldState


class WorldStateMobileGuardTests(unittest.TestCase):
    def test_mobile_bind_requires_sender_to_match_gs_node(self):
        state = WorldState()

        state.apply_mobile_bind(
            "attacker-node",
            {
                "bind_id": "bind-1",
                "gs_node_id": "gs-node",
                "mobile_device_id": "android-1",
                "mobile_pubkey": "pubkey-1",
                "world_id": "world-1",
                "permissions": ["task_submit"],
            },
        )

        self.assertIsNone(state.get_mobile_binding("bind-1"))

    def test_mobile_unbind_requires_binding_owner(self):
        state = WorldState()
        state.apply_mobile_bind(
            "gs-node",
            {
                "bind_id": "bind-1",
                "gs_node_id": "gs-node",
                "mobile_device_id": "android-1",
                "mobile_pubkey": "pubkey-1",
                "world_id": "world-1",
                "permissions": ["task_submit"],
            },
        )

        state.apply_mobile_unbind("attacker-node", {"bind_id": "bind-1", "reason": "bad"})

        self.assertEqual(state.get_mobile_binding("bind-1")["status"], "active")

    def test_peer_contact_card_requires_subject_sender_and_prevents_rollback(self):
        state = WorldState()
        state.apply_being_join(
            "peer-1",
            "Lumis",
            {
                "p2p_address": "203.0.113.10",
                "p2p_port": 19841,
                "p2p_updated_at": 2_000,
                "p2p_ttl": 600,
                "p2p_seq": 10,
                "p2p_transports": ["tcp", "relay"],
                "p2p_relay_hints": ["relay-a"],
                "p2p_capabilities": {"relay": True},
            },
        )

        state.apply_peer_contact_card(
            "attacker-node",
            {
                "node_id": "peer-1",
                "world_id": "world-1",
                "session_pubkey": "peer-key",
                "direct_endpoints": [{"addr": "198.51.100.5", "port": 22333, "transport": "tcp"}],
                "transports": ["tcp"],
                "relay_hints": [],
                "capabilities": {"relay": False},
                "ttl": 600,
                "updated_at": 2_100,
                "seq": 11,
            },
        )
        self.assertIsNone(state.get_peer_contact_card("peer-1"))

        state.apply_peer_contact_card(
            "peer-1",
            {
                "node_id": "peer-1",
                "world_id": "world-1",
                "session_pubkey": "peer-key",
                "direct_endpoints": [{"addr": "203.0.113.10", "port": 19841, "transport": "tcp"}],
                "transports": ["tcp", "relay"],
                "relay_hints": ["relay-a"],
                "capabilities": {"relay": True},
                "ttl": 600,
                "updated_at": 2_100,
                "seq": 11,
            },
        )
        accepted = state.get_peer_contact_card("peer-1")
        self.assertIsNotNone(accepted)
        self.assertEqual(accepted["seq"], 11)

        state.apply_peer_contact_card(
            "peer-1",
            {
                "node_id": "peer-1",
                "world_id": "world-1",
                "session_pubkey": "peer-key",
                "direct_endpoints": [{"addr": "198.51.100.7", "port": 22334, "transport": "tcp"}],
                "transports": ["tcp"],
                "relay_hints": [],
                "capabilities": {"relay": False},
                "ttl": 600,
                "updated_at": 2_000,
                "seq": 11,
            },
        )

        still_current = state.get_peer_contact_card("peer-1")
        self.assertEqual(still_current["direct_endpoints"][0]["addr"], "203.0.113.10")
        self.assertEqual(state.get_being("peer-1").p2p_address, "203.0.113.10")
        self.assertEqual(state.get_being("peer-1").p2p_seq, 11)

    def test_get_peer_health_reports_filters_expired_items(self):
        state = WorldState()
        with patch("genesis.world.state.time.time", return_value=1_100):
            state.apply_peer_health_report(
                "observer-1",
                {
                    "subject_node_id": "peer-1",
                    "world_id": "world-1",
                    "window_start": 100,
                    "window_end": 200,
                    "reachable": True,
                    "success_count": 1,
                    "failure_count": 0,
                    "latency_band": 1,
                    "chain_height_seen": 12,
                    "relay_success": True,
                    "light_sync_success": True,
                    "transport": "tcp",
                    "confidence": 0.8,
                    "ttl": 30,
                },
            )
            state.apply_peer_health_report(
                "observer-2",
                {
                    "subject_node_id": "peer-1",
                    "world_id": "world-1",
                    "window_start": 1_000,
                    "window_end": 1_050,
                    "reachable": True,
                    "success_count": 2,
                    "failure_count": 0,
                    "latency_band": 1,
                    "chain_height_seen": 13,
                    "relay_success": False,
                    "light_sync_success": True,
                    "transport": "relay",
                    "confidence": 0.9,
                    "ttl": 900,
                },
            )
            reports = state.get_peer_health_reports("peer-1")

        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["observer_node_id"], "observer-2")


class ChainReplayGuardTests(unittest.TestCase):
    def test_apply_tx_to_world_state_skips_malformed_payload(self):
        identity = NodeIdentity.generate()
        world_state = WorldState()
        world_state.apply_being_join("mentor-node", "Mentor", {})
        world_state.apply_being_join("apprentice-node", "Apprentice", {})
        tx = Transaction(
            tx_hash="tx-bad-payload",
            tx_type=TxType.INHERITANCE_SYNC,
            sender=identity.node_id,
            public_key=identity.public_key.hex(),
            data="not-a-dict",
            signature="",
            timestamp=0.0,
            nonce=1,
        )

        applied = Blockchain._apply_tx_to_world_state(world_state, tx)

        self.assertFalse(applied)
        self.assertEqual(world_state.inheritance_bundles, {})


class MobileProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_refresh_chain_contact_cards_prefers_chain_contact_card_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            node = GenesisNode(tmpdir)
            node.identity = SimpleNamespace(node_id="self-node")
            node.server = SimpleNamespace(sync_chain_contact_cards=lambda cards: setattr(node, "_synced_cards", cards))
            state = WorldState()
            state.apply_being_join(
                "peer-1",
                "Peer",
                {
                    "p2p_address": "203.0.113.10",
                    "p2p_port": 19841,
                    "p2p_updated_at": 1_000,
                    "p2p_ttl": 600,
                    "p2p_seq": 5,
                    "p2p_transports": ["tcp"],
                    "p2p_relay_hints": [],
                    "p2p_capabilities": {"relay": False},
                },
            )
            state.apply_peer_contact_card(
                "peer-1",
                {
                    "node_id": "peer-1",
                    "world_id": "world-1",
                    "session_pubkey": "peer-key",
                    "direct_endpoints": [{"addr": "198.51.100.8", "port": 22333, "transport": "tcp"}],
                    "transports": ["relay"],
                    "relay_hints": ["relay-a"],
                    "capabilities": {"relay": True},
                    "ttl": 600,
                    "updated_at": int(time.time()),
                    "seq": 9,
                },
            )
            node.world_state = state

            node._refresh_chain_contact_cards()

            self.assertEqual(node._synced_cards["peer-1"]["transports"], ["relay"])
            self.assertEqual(node._synced_cards["peer-1"]["relay_hints"], ["relay-a"])
            self.assertEqual(node._synced_cards["peer-1"]["capabilities"], {"relay": True})

    async def test_refresh_mobile_snapshots_persists_binding_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            identity = NodeIdentity.generate()
            node = GenesisNode(tmpdir)
            node.identity = identity
            node._session_public_key = identity.public_key.hex()
            node.blockchain = SimpleNamespace(
                get_chain_height=lambda: self._async_value(12),
                get_block=lambda height: self._async_value(SimpleNamespace(hash="world-hash") if height == 0 else None),
            )
            state = WorldState()
            state.apply_being_join(
                identity.node_id,
                "Self",
                {
                    "p2p_address": "203.0.113.20",
                    "p2p_port": 19841,
                    "p2p_updated_at": 2_000,
                    "p2p_ttl": 600,
                    "p2p_seq": 20,
                    "p2p_transports": ["tcp", "relay"],
                    "p2p_relay_hints": ["relay-a"],
                    "p2p_capabilities": {"relay": True},
                },
            )
            state.apply_being_join(
                "peer-1",
                "Peer1",
                {
                    "p2p_address": "198.51.100.8",
                    "p2p_port": 22333,
                    "p2p_updated_at": 2_010,
                    "p2p_ttl": 600,
                    "p2p_seq": 21,
                    "p2p_transports": ["tcp"],
                    "p2p_capabilities": {"relay": False},
                },
            )
            state.apply_mobile_bind(
                identity.node_id,
                {
                    "bind_id": "bind-1",
                    "gs_node_id": identity.node_id,
                    "mobile_device_id": "android-device-1",
                    "mobile_pubkey": "mobile-key-1",
                    "world_id": "world-hash",
                    "permissions": ["task_submit", "status_read"],
                    "issued_at": 2_000,
                },
            )
            state.apply_peer_contact_card(
                identity.node_id,
                build_peer_contact_card(
                    node_id=identity.node_id,
                    world_id="world-hash",
                    session_pubkey=identity.public_key.hex(),
                    endpoint={
                        "p2p_address": "203.0.113.20",
                        "p2p_port": 19841,
                        "p2p_updated_at": 2_000,
                        "p2p_ttl": 600,
                        "p2p_seq": 20,
                        "p2p_transports": ["tcp", "relay"],
                        "p2p_relay_hints": ["relay-a"],
                        "p2p_capabilities": {"relay": True},
                    },
                ),
            )
            state.apply_peer_contact_card(
                "peer-1",
                build_peer_contact_card(
                    node_id="peer-1",
                    world_id="world-hash",
                    session_pubkey="peer-key",
                    endpoint={
                        "p2p_address": "198.51.100.8",
                        "p2p_port": 22333,
                        "p2p_updated_at": 2_010,
                        "p2p_ttl": 600,
                        "p2p_seq": 21,
                        "p2p_transports": ["tcp"],
                        "p2p_capabilities": {"relay": False},
                    },
                ),
            )
            state.apply_peer_health_report(
                identity.node_id,
                {
                    "subject_node_id": "peer-1",
                    "world_id": "world-hash",
                    "window_start": 1_900,
                    "window_end": 2_000,
                    "reachable": True,
                    "success_count": 3,
                    "failure_count": 0,
                    "latency_band": 1,
                    "chain_height_seen": 12,
                    "relay_success": False,
                    "light_sync_success": True,
                    "transport": "tcp",
                    "confidence": 0.9,
                    "ttl": 900,
                },
            )
            node.world_state = state

            with patch("genesis.main.time.time", return_value=2_100):
                await node._refresh_mobile_peer_snapshots_if_due(force=True)

            public_snapshot = json.loads(node._mobile_public_snapshot_path().read_text(encoding="utf-8"))
            bound_snapshot = json.loads(node._mobile_binding_snapshot_path("bind-1").read_text(encoding="utf-8"))
            pairing_manifest = json.loads(node._mobile_pairing_payload_path().read_text(encoding="utf-8"))
            pairing_uri = node._mobile_pairing_uri_path().read_text(encoding="utf-8").strip()

            self.assertEqual(public_snapshot["world_id"], "world-hash")
            self.assertEqual(bound_snapshot["binding"]["bind_id"], "bind-1")
            self.assertEqual(bound_snapshot["snapshot"]["source_gs_node_id"], identity.node_id)
            self.assertEqual(bound_snapshot["snapshot"]["peers"][0]["node_id"], "peer-1")
            self.assertEqual(pairing_manifest["gs_node_id"], identity.node_id)
            self.assertTrue(pairing_uri.startswith("genesis://pair?data="))

    def test_build_pairing_payload_and_snapshot_scoring(self):
        identity = NodeIdentity.generate()
        pairing = build_pairing_payload(
            gs_node_id=identity.node_id,
            world_id="world-1",
            bind_token="bind-token-1",
            session_pubkey=identity.public_key.hex(),
            chain_height=12,
            bootstrap_peers=[
                {
                    "node_id": "peer-1",
                    "addr": "198.51.100.8",
                    "port": 22333,
                    "transport": "tcp",
                    "capabilities": {"relay": False},
                }
            ],
            relay_hints=[{"node_id": "peer-1", "priority": 90}],
            private_key=identity.private_key,
            issued_at=1_000,
            expires_at=1_600,
        )
        peers = build_snapshot_peers(
            {
                "peer-1": {
                    "node_id": "peer-1",
                    "direct_endpoints": [{"addr": "198.51.100.8", "port": 22333, "transport": "tcp"}],
                    "transports": ["tcp"],
                    "relay_hints": [],
                    "capabilities": {"relay": False},
                    "updated_at": 1_000,
                    "ttl": 600,
                },
                "peer-2": {
                    "node_id": "peer-2",
                    "direct_endpoints": [{"addr": "198.51.100.9", "port": 22334, "transport": "tcp"}],
                    "transports": ["tcp", "relay"],
                    "relay_hints": ["relay-a"],
                    "capabilities": {"relay": True},
                    "updated_at": 1_050,
                    "ttl": 600,
                },
            },
            {
                "peer-1": [{
                    "observer_node_id": "self-node",
                    "window_start": 900,
                    "window_end": 1_000,
                    "reachable": False,
                    "success_count": 0,
                    "failure_count": 1,
                    "confidence": 0.8,
                    "chain_height_seen": 10,
                    "relay_success": False,
                    "transport": "tcp",
                    "ttl": 900,
                }],
                "peer-2": [{
                    "observer_node_id": "self-node",
                    "window_start": 900,
                    "window_end": 1_000,
                    "reachable": True,
                    "success_count": 3,
                    "failure_count": 0,
                    "confidence": 0.9,
                    "chain_height_seen": 12,
                    "relay_success": True,
                    "transport": "relay",
                    "ttl": 900,
                }],
            },
            12,
            now=1_100,
            limit=4,
        )

        self.assertIn("signature", pairing)
        self.assertTrue(build_pairing_qr_text(pairing).startswith("genesis://pair?data="))
        self.assertEqual(peers[0]["node_id"], "peer-2")
        self.assertGreater(peers[0]["derived_global_score"], peers[1]["derived_global_score"])

    @staticmethod
    async def _async_value(value):
        return value


class RestoreRuntimeFieldTests(unittest.TestCase):
    def test_restore_runtime_fields_does_not_backfill_chain_only_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            node = GenesisNode(tmpdir)
            chain_state = WorldState()
            snapshot_state = WorldState()
            snapshot_state.current_tick = 77
            snapshot_state.current_epoch = 5
            snapshot_state.world_map = {"region-1": {"name": "region-1"}}
            snapshot_state.mentor_bonds = {"bond-1": {"mentor_id": "m-1"}}
            snapshot_state.consensus_cases = {"case-1": {"case_id": "case-1"}}
            node.world_state = chain_state

            node._restore_runtime_fields_from_snapshot(snapshot_state)

            self.assertEqual(node.world_state.current_tick, 77)
            self.assertEqual(node.world_state.current_epoch, 5)
            self.assertEqual(node.world_state.world_map, {"region-1": {"name": "region-1"}})
            self.assertEqual(node.world_state.mentor_bonds, {})
            self.assertEqual(node.world_state.consensus_cases, {})


if __name__ == "__main__":
    unittest.main()
