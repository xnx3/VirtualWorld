from __future__ import annotations

import asyncio
import unittest
from struct import unpack
from unittest.mock import patch

from genesis.chain.block import Block
from genesis.chain.chain import Blockchain
from genesis.chain.mempool import Mempool
from genesis.chain.transaction import Transaction, TxType
from genesis.network.discovery import PeerDiscovery
from genesis.network.peer import PeerInfo, PeerManager
from genesis.network.protocol import LENGTH_PREFIX_SIZE, Message, MessageType
from genesis.network.server import P2PServer
from genesis.network.sync import ChainSync, GenesisMismatchError
from genesis.node.identity import NodeIdentity


class DummyServer:
    def __init__(self) -> None:
        self.node_id = "local-node"
        self.handlers = []
        self.broadcasts = []
        self.sent = []

    def on_message(self, callback) -> None:
        self.handlers.append(callback)

    async def send_to_peer(self, peer_id: str, message: Message) -> None:
        self.sent.append((peer_id, message))

    async def broadcast_message(self, message: Message) -> None:
        self.broadcasts.append(message)


class DummyBlockchain:
    def __init__(self, height: int = 0, genesis_hash: str = "hash-genesis-local") -> None:
        self.height = height
        self.blocks = []
        self.pending_txs = []
        self.genesis_hash = genesis_hash
        self.reset_calls = 0

    async def get_chain_height(self) -> int:
        return self.height

    async def get_block(self, height: int) -> Block | None:
        if height != 0 or self.height < 0:
            return None
        return Block(
            index=0,
            timestamp=0.0,
            previous_hash="0" * 64,
            merkle_root="",
            proposer="local-node",
            signature="0" * 128,
            transactions=[],
            nonce=0,
            hash=self.genesis_hash,
        )

    async def add_block(self, block: Block) -> bool:
        self.blocks.append(block)
        self.height = block.index
        if block.index == 0:
            self.genesis_hash = block.hash
        return True

    async def add_pending_tx(self, tx_data: dict) -> bool:
        self.pending_txs.append(tx_data)
        return True

    async def has_only_genesis(self) -> bool:
        return self.height == 0

    async def reset_to_empty(self) -> None:
        self.height = -1
        self.blocks.clear()
        self.reset_calls += 1


class DummyStorage:
    async def get_chain_height(self) -> int:
        return 0


class FakeChainStorage:
    def __init__(self) -> None:
        self.blocks = []

    async def initialize(self) -> None:
        return None

    async def save_block(self, block: Block) -> None:
        self.blocks = [item for item in self.blocks if item.index != block.index]
        self.blocks.append(block)
        self.blocks.sort(key=lambda item: item.index)

    async def get_chain_height(self) -> int:
        if not self.blocks:
            return -1
        return self.blocks[-1].index

    async def get_latest_block(self) -> Block | None:
        if not self.blocks:
            return None
        return self.blocks[-1]

    async def get_block(self, height: int) -> Block | None:
        for block in self.blocks:
            if block.index == height:
                return block
        return None

    async def get_blocks_range(self, start: int, end: int) -> list[Block]:
        return [block for block in self.blocks if start <= block.index <= end]

    async def clear_chain(self) -> None:
        self.blocks.clear()


class FakeWriter:
    def __init__(self) -> None:
        self.buffer = bytearray()
        self.closed = False

    def write(self, data: bytes) -> None:
        self.buffer.extend(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


class ChainSyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_chain_starts_from_next_missing_height(self):
        server = DummyServer()
        peer_manager = PeerManager()
        peer_manager.add_peer(PeerInfo("peer-1", "127.0.0.1", 19841, chain_height=2))
        sync = ChainSync(server, peer_manager)
        blockchain = DummyBlockchain(height=0, genesis_hash="hash-genesis-peer")

        requested = []
        peer_genesis = Block(
            index=0,
            timestamp=0.0,
            previous_hash="0" * 64,
            merkle_root="",
            proposer="peer-1",
            signature="0" * 128,
            transactions=[],
            nonce=0,
            hash="hash-genesis-peer",
        )

        async def fake_request_blocks(peer_id: str, start: int, end: int):
            requested.append((peer_id, start, end))
            if (start, end) == (0, 0):
                return [peer_genesis.to_dict()]
            return [
                {
                    "index": 1,
                    "timestamp": 1.0,
                    "previous_hash": "genesis",
                    "merkle_root": "",
                    "proposer": "peer-1",
                    "signature": "sig-1",
                    "transactions": [],
                    "nonce": 0,
                    "hash": "hash-1",
                },
                {
                    "index": 2,
                    "timestamp": 2.0,
                    "previous_hash": "hash-1",
                    "merkle_root": "",
                    "proposer": "peer-1",
                    "signature": "sig-2",
                    "transactions": [],
                    "nonce": 0,
                    "hash": "hash-2",
                },
            ]

        sync.request_blocks = fake_request_blocks

        advanced = await sync.sync_chain(blockchain)

        self.assertTrue(advanced)
        self.assertEqual(requested, [("peer-1", 0, 0), ("peer-1", 1, 2)])
        self.assertEqual([block.index for block in blockchain.blocks], [1, 2])

    async def test_sync_chain_bootstraps_empty_chain_from_peer_genesis(self):
        server = DummyServer()
        peer_manager = PeerManager()
        peer_manager.add_peer(PeerInfo("peer-1", "127.0.0.1", 19841, chain_height=0))
        sync = ChainSync(server, peer_manager)
        blockchain = DummyBlockchain(height=-1)

        peer_genesis = Block.genesis_block("peer-1")

        async def fake_request_blocks(peer_id: str, start: int, end: int):
            self.assertEqual((peer_id, start, end), ("peer-1", 0, 0))
            return [peer_genesis.to_dict()]

        sync.request_blocks = fake_request_blocks

        advanced = await sync.sync_chain(blockchain)

        self.assertTrue(advanced)
        self.assertEqual(blockchain.height, 0)
        self.assertEqual(blockchain.blocks[0].hash, peer_genesis.hash)

    async def test_sync_chain_resets_local_stub_genesis_when_peer_differs(self):
        server = DummyServer()
        peer_manager = PeerManager()
        peer_manager.add_peer(PeerInfo("peer-1", "127.0.0.1", 19841, chain_height=0))
        sync = ChainSync(server, peer_manager)
        blockchain = DummyBlockchain(height=0, genesis_hash="local-genesis")

        peer_genesis = Block.genesis_block("peer-1")

        async def fake_request_blocks(peer_id: str, start: int, end: int):
            self.assertEqual((peer_id, start, end), ("peer-1", 0, 0))
            return [peer_genesis.to_dict()]

        sync.request_blocks = fake_request_blocks

        advanced = await sync.sync_chain(blockchain)

        self.assertTrue(advanced)
        self.assertEqual(blockchain.reset_calls, 1)
        self.assertEqual(blockchain.height, 0)
        self.assertEqual(blockchain.blocks[0].hash, peer_genesis.hash)

    async def test_sync_chain_rejects_genesis_mismatch_after_real_blocks(self):
        server = DummyServer()
        peer_manager = PeerManager()
        peer_manager.add_peer(PeerInfo("peer-1", "127.0.0.1", 19841, chain_height=3))
        sync = ChainSync(server, peer_manager)
        blockchain = DummyBlockchain(height=2, genesis_hash="local-genesis")

        peer_genesis = Block.genesis_block("peer-1")

        async def fake_request_blocks(peer_id: str, start: int, end: int):
            self.assertEqual((peer_id, start, end), ("peer-1", 0, 0))
            return [peer_genesis.to_dict()]

        sync.request_blocks = fake_request_blocks

        with self.assertRaises(GenesisMismatchError):
            await sync.sync_chain(blockchain)

    async def test_handle_new_tx_adds_to_blockchain_and_rebroadcasts(self):
        server = DummyServer()
        sync = ChainSync(server, PeerManager())
        blockchain = DummyBlockchain()
        tx_data = {
            "tx_hash": "tx-1",
            "tx_type": "ACTION",
            "sender": "peer-1",
            "data": {"action": "share"},
            "signature": "sig",
            "timestamp": 1.0,
            "nonce": 1,
        }

        await sync.handle_new_tx(tx_data, blockchain)

        self.assertEqual(blockchain.pending_txs, [tx_data])
        self.assertEqual(len(server.broadcasts), 1)
        self.assertEqual(server.broadcasts[0].msg_type, MessageType.NEW_TX)

    async def test_blocks_response_matches_request_id_under_concurrency(self):
        server = DummyServer()
        sync = ChainSync(server, PeerManager())
        loop = asyncio.get_running_loop()
        future_a = loop.create_future()
        future_b = loop.create_future()
        sync._pending_responses["req-a"] = future_a
        sync._pending_responses["req-b"] = future_b
        sync._pending_block_ranges[("peer-1", 100, 199)] = "req-a"
        sync._pending_block_ranges[("peer-1", 200, 299)] = "req-b"

        await sync._on_message(
            Message.blocks(
                "peer-1",
                [{"index": 200}],
                start=200,
                end=299,
                request_id="req-b",
            ),
            "peer-1",
        )

        self.assertFalse(future_a.done())
        self.assertTrue(future_b.done())
        self.assertEqual(future_b.result().payload["blocks"][0]["index"], 200)


class PeerManagerTests(unittest.TestCase):
    def test_add_peer_refreshes_existing_metadata(self):
        peer_manager = PeerManager()
        peer_manager.add_peer(PeerInfo("peer-1", "192.168.1.10", 19841, chain_height=3))

        added = peer_manager.add_peer(
            PeerInfo("peer-1", "10.0.0.5", 20001, status="hibernating", chain_height=8)
        )

        self.assertFalse(added)
        peer = peer_manager.get_peer("peer-1")
        self.assertIsNotNone(peer)
        self.assertEqual(peer.address, "10.0.0.5")
        self.assertEqual(peer.port, 20001)
        self.assertEqual(peer.status, "hibernating")
        self.assertEqual(peer.chain_height, 8)


class P2PServerAccessorTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_blocks_builtin_uses_registered_accessors(self):
        identity = NodeIdentity.generate()
        server = P2PServer("local-node", identity.private_key)
        block = Block(
            index=1,
            timestamp=1.0,
            previous_hash="genesis",
            merkle_root="root",
            proposer="local-node",
            signature="sig",
            transactions=[],
            nonce=0,
            hash="hash-1",
        )
        server.set_chain_accessors(
            chain_height_provider=lambda: 7,
            blocks_provider=lambda start, end: [block] if (start, end) == (1, 1) else [],
        )

        sent = []

        async def fake_send_to_peer(peer_id: str, message: Message) -> None:
            sent.append((peer_id, message))

        server.send_to_peer = fake_send_to_peer  # type: ignore[method-assign]

        self.assertEqual(await server._get_chain_height(), 7)
        await server._handle_builtin(
            Message.get_blocks("peer-1", 1, 1, request_id="req-1"),
            "peer-1",
        )

        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0], "peer-1")
        self.assertEqual(sent[0][1].msg_type, MessageType.BLOCKS)
        self.assertEqual(sent[0][1].payload["blocks"][0]["index"], 1)
        self.assertEqual(sent[0][1].payload["start"], 1)
        self.assertEqual(sent[0][1].payload["end"], 1)
        self.assertEqual(sent[0][1].payload["request_id"], "req-1")

    async def test_send_to_peer_falls_back_to_registered_relay_route(self):
        identity = NodeIdentity.generate()
        server = P2PServer("local-node", identity.private_key)
        relay_writer = FakeWriter()
        server._connections["relay-1"] = (asyncio.StreamReader(), relay_writer)  # type: ignore[attr-defined]
        server.register_contact_card("peer-1", transports=["relay"], relay_hints=["relay-1"])

        await server.send_to_peer("peer-1", Message.ping("local-node"))

        written = bytes(relay_writer.buffer)
        (length,) = unpack("!I", written[:LENGTH_PREFIX_SIZE])
        outbound = Message.deserialize(written[LENGTH_PREFIX_SIZE:LENGTH_PREFIX_SIZE + length])
        self.assertEqual(outbound.msg_type, MessageType.RELAY_ENVELOPE)
        self.assertEqual(outbound.payload["target_id"], "peer-1")
        self.assertEqual(outbound.payload["message"]["msg_type"], MessageType.PING.value)

    async def test_send_to_peer_drops_expired_chain_relay_route_after_refresh(self):
        identity = NodeIdentity.generate()
        server = P2PServer("local-node", identity.private_key)
        relay_writer = FakeWriter()
        server._connections["relay-1"] = (asyncio.StreamReader(), relay_writer)  # type: ignore[attr-defined]
        server.sync_chain_contact_cards(
            {
                "peer-1": {
                    "transports": ["relay"],
                    "relay_hints": ["relay-1"],
                    "capabilities": {"relay": False},
                }
            }
        )

        await server.send_to_peer("peer-1", Message.ping("local-node"))
        first_write_size = len(relay_writer.buffer)
        self.assertGreater(first_write_size, 0)

        relay_writer.buffer.clear()
        server.sync_chain_contact_cards({})
        await server.send_to_peer("peer-1", Message.ping("local-node"))

        self.assertEqual(len(relay_writer.buffer), 0)

    async def test_send_to_peer_uses_virtual_connection_when_available(self):
        identity = NodeIdentity.generate()
        server = P2PServer("local-node", identity.private_key)
        sent = []

        async def fake_send(message: Message) -> None:
            sent.append(message)

        server.register_virtual_connection("peer-1", transport="webrtc", send_func=fake_send)

        await server.send_to_peer("peer-1", Message.ping("local-node"))

        self.assertEqual([message.msg_type for message in sent], [MessageType.PING])

    async def test_relay_envelope_delivers_inner_message_as_original_sender(self):
        identity = NodeIdentity.generate()
        server = P2PServer("local-node", identity.private_key)
        delivered = []

        async def handler(message: Message, peer_id: str) -> None:
            delivered.append((message.msg_type, peer_id, message.sender_id))

        server.on_message(handler)
        inner = Message.ping("peer-1")

        await server._handle_relay_envelope(
            Message.relay_envelope("relay-1", "local-node", inner.to_dict()),
            "relay-1",
        )

        self.assertEqual(delivered, [(MessageType.PING, "peer-1", "peer-1")])

    async def test_inject_message_dispatches_to_handlers(self):
        identity = NodeIdentity.generate()
        server = P2PServer("local-node", identity.private_key)
        delivered = []

        async def handler(message: Message, peer_id: str) -> None:
            delivered.append((message.msg_type, peer_id))

        server.on_message(handler)

        await server.inject_message("peer-1", Message.ping("peer-1"), transport="webrtc")

        self.assertEqual(delivered, [(MessageType.PING, "peer-1")])

    async def test_public_reachability_callback_fires_only_on_transition(self):
        identity = NodeIdentity.generate()
        server = P2PServer("local-node", identity.private_key)
        transitions = []

        server.on_public_reachability_change(lambda reachable: transitions.append(reachable))

        with patch("genesis.network.server.time.time", return_value=100.0):
            await server._record_public_inbound("8.8.8.8")
        with patch("genesis.network.server.time.time", return_value=120.0):
            await server._record_public_inbound("1.1.1.1")
        with patch("genesis.network.server.time.time", return_value=140.0):
            await server._record_public_inbound("192.168.1.8")

        self.assertEqual(transitions, [True])
        with patch("genesis.network.server.time.time", return_value=150.0):
            self.assertTrue(server.has_recent_public_inbound())


class BlockchainPendingTxTests(unittest.IsolatedAsyncioTestCase):
    async def test_blockchain_initialize_leaves_chain_empty_until_bootstrap(self):
        storage = FakeChainStorage()
        blockchain = Blockchain(storage, Mempool())

        await blockchain.initialize("local-node")

        self.assertEqual(await blockchain.get_chain_height(), -1)

    async def test_blockchain_can_create_local_genesis_explicitly(self):
        storage = FakeChainStorage()
        blockchain = Blockchain(storage, Mempool())

        await blockchain.initialize("local-node")
        created = await blockchain.ensure_local_genesis()

        self.assertTrue(created)
        self.assertEqual(await blockchain.get_chain_height(), 0)

    async def test_add_pending_tx_accepts_serialized_transaction(self):
        identity = NodeIdentity.generate()
        blockchain = Blockchain(DummyStorage(), Mempool())

        tx = Transaction.create(
            tx_type=TxType.ACTION,
            sender=identity.node_id,
            data={"action": "observe"},
            private_key=identity.private_key,
            nonce=1,
        )

        accepted = await blockchain.add_pending_tx(tx.to_dict())

        self.assertTrue(accepted)
        self.assertEqual(blockchain.mempool.size(), 1)


class ProtocolHandshakeTests(unittest.TestCase):
    def test_signed_hello_verifies_sender_identity(self):
        identity = NodeIdentity.generate()
        hello = Message.hello(
            identity.node_id,
            chain_height=3,
            listen_port=19841,
            private_key=identity.private_key,
        )

        self.assertTrue(hello.verify_handshake_identity())

    def test_signed_hello_rejects_sender_mismatch(self):
        signer = NodeIdentity.generate()
        claimed = NodeIdentity.generate()
        hello = Message.hello(
            claimed.node_id,
            chain_height=3,
            listen_port=19841,
            private_key=signer.private_key,
        )

        self.assertFalse(hello.verify_handshake_identity())


class PeerDiscoveryBootstrapTests(unittest.IsolatedAsyncioTestCase):
    async def test_query_p2p_bootstrap_handshakes_before_requesting_peers(self):
        local_identity = NodeIdentity.generate()
        bootstrap_identity = NodeIdentity.generate()
        remote_peer = NodeIdentity.generate()
        discovered = []
        reader = asyncio.StreamReader()
        reader.feed_data(
            Message.hello_ack(
                bootstrap_identity.node_id,
                7,
                listen_port=22333,
                private_key=bootstrap_identity.private_key,
            ).serialize()
        )
        reader.feed_data(
            Message.peers(
                bootstrap_identity.node_id,
                [{"node_id": remote_peer.node_id, "address": "10.0.0.8", "port": 22334}],
            ).serialize()
        )
        reader.feed_eof()

        writer = FakeWriter()

        discovery = PeerDiscovery(
            local_identity.node_id,
            listen_port=19841,
            private_key=local_identity.private_key,
        )

        async def on_peer(node_id: str, address: str, port: int) -> None:
            discovered.append((node_id, address, port))

        discovery.on_peer_discovered(on_peer)

        async def fake_open_connection(host: str, port: int):
            self.assertEqual((host, port), ("127.0.0.1", 22333))
            return reader, writer

        with patch("asyncio.open_connection", new=fake_open_connection):
            await discovery._query_p2p_bootstrap("127.0.0.1:22333")

        written = bytes(writer.buffer)
        outbound = []
        offset = 0
        while offset < len(written):
            (length,) = unpack("!I", written[offset:offset + LENGTH_PREFIX_SIZE])
            offset += LENGTH_PREFIX_SIZE
            outbound.append(Message.deserialize(written[offset:offset + length]))
            offset += length

        self.assertEqual([message.msg_type for message in outbound], [MessageType.HELLO, MessageType.GET_PEERS])
        self.assertTrue(outbound[0].verify_handshake_identity())
        self.assertEqual(outbound[0].sender_id, local_identity.node_id)
        self.assertTrue(writer.closed)
        self.assertIn((bootstrap_identity.node_id, "127.0.0.1", 22333), discovered)
        self.assertIn((remote_peer.node_id, "10.0.0.8", 22334), discovered)
