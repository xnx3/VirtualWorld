import unittest

from genesis.chain.block import Block
from genesis.chain.transaction import Transaction, TxType
from genesis.network.peer import PeerInfo, PeerManager
from genesis.network.protocol import Message, MessageType
from genesis.network.server import P2PServer
from genesis.network.sync import ChainSync
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
    def __init__(self, height: int = 0) -> None:
        self.height = height
        self.blocks = []
        self.pending_txs = []

    async def get_chain_height(self) -> int:
        return self.height

    async def add_block(self, block: Block) -> bool:
        self.blocks.append(block)
        self.height = block.index
        return True

    async def add_pending_tx(self, tx_data: dict) -> bool:
        self.pending_txs.append(tx_data)
        return True


class DummyStorage:
    async def get_chain_height(self) -> int:
        return 0


class ChainSyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_chain_starts_from_next_missing_height(self):
        server = DummyServer()
        peer_manager = PeerManager()
        peer_manager.add_peer(PeerInfo("peer-1", "127.0.0.1", 19841, chain_height=2))
        sync = ChainSync(server, peer_manager)
        blockchain = DummyBlockchain(height=0)

        requested = []

        async def fake_request_blocks(peer_id: str, start: int, end: int):
            requested.append((peer_id, start, end))
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
        self.assertEqual(requested, [("peer-1", 1, 2)])
        self.assertEqual([block.index for block in blockchain.blocks], [1, 2])

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
        await server._handle_builtin(Message.get_blocks("peer-1", 1, 1), "peer-1")

        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0], "peer-1")
        self.assertEqual(sent[0][1].msg_type, MessageType.BLOCKS)
        self.assertEqual(sent[0][1].payload["blocks"][0]["index"], 1)


class BlockchainPendingTxTests(unittest.IsolatedAsyncioTestCase):
    async def test_add_pending_tx_accepts_serialized_transaction(self):
        from genesis.chain.chain import Blockchain
        from genesis.chain.mempool import Mempool

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
