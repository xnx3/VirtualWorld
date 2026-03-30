import json
import tempfile
import unittest
from pathlib import Path

from genesis.chain.chain import Blockchain
from genesis.chain.mempool import Mempool
from genesis.chain.transaction import Transaction, TxType
from genesis.chronicle.reporter import StatusReporter
from genesis.i18n import set_language, t
from genesis.world.state import WorldState


class _FakeBlock:
    def __init__(self, transactions):
        self.transactions = transactions


class _FakeStorage:
    def __init__(self, blocks):
        self._blocks = blocks

    async def get_chain_height(self):
        return len(self._blocks) - 1

    async def get_blocks_range(self, start, end):
        return self._blocks[start:end + 1]


def _tx(tx_hash: str, tx_type: TxType, sender: str, data: dict) -> Transaction:
    return Transaction(
        tx_hash=tx_hash,
        tx_type=tx_type,
        sender=sender,
        data=data,
        signature="sig",
        timestamp=0.0,
        nonce=0,
    )


class BlockchainReplayTests(unittest.IsolatedAsyncioTestCase):
    async def test_replay_keeps_targeted_npc_join_and_tao_finalize(self):
        proposer_id = "creator-node"
        rule_data = {
            "rule_id": "T0001",
            "name": "Knowledge Covenant",
            "description": "All beings must share durable knowledge.",
            "category": "tao",
            "active": True,
            "creator_id": proposer_id,
            "merit_awarded": 5.5,
        }
        block = _FakeBlock([
            _tx(
                "join-main",
                TxType.BEING_JOIN,
                proposer_id,
                {"name": "Creator", "location": "genesis_plains"},
            ),
            _tx(
                "join-npc",
                TxType.BEING_JOIN,
                proposer_id,
                {
                    "node_id": "npc-1",
                    "name": "Sentinel",
                    "location": "signal_tower",
                    "is_npc": True,
                },
            ),
            _tx(
                "move-main",
                TxType.ACTION,
                proposer_id,
                {"action_type": "move", "target": "signal_tower"},
            ),
            _tx(
                "vote-start",
                TxType.TAO_VOTE_INITIATE,
                proposer_id,
                {
                    "vote_id": "vote-1",
                    "proposer_id": proposer_id,
                    "rule_name": rule_data["name"],
                    "rule_description": rule_data["description"],
                    "rule_category": "rule",
                    "end_tick": 8640,
                },
            ),
            _tx(
                "vote-cast",
                TxType.TAO_VOTE_CAST,
                "npc-1",
                {"vote_id": "vote-1", "voter_id": "npc-1", "support": True},
            ),
            _tx(
                "vote-finalize",
                TxType.TAO_VOTE_FINALIZE,
                proposer_id,
                {
                    "vote_id": "vote-1",
                    "passed": True,
                    "proposer_id": proposer_id,
                    "rule_id": rule_data["rule_id"],
                    "rule_data": rule_data,
                    "merit": 5.5,
                },
            ),
        ])
        blockchain = Blockchain(_FakeStorage([block]), Mempool())

        state = await blockchain.derive_world_state()
        world_state = WorldState.from_dict(state)

        self.assertIn("npc-1", world_state.beings)
        self.assertEqual(world_state.get_being("npc-1").name, "Sentinel")
        self.assertEqual(world_state.get_being(proposer_id).location, "signal_tower")
        self.assertTrue(world_state.get_being(proposer_id).merged_with_tao)
        self.assertEqual(world_state.tao_rules[rule_data["rule_id"]]["name"], rule_data["name"])
        self.assertNotIn("vote-1", world_state.pending_tao_votes)

    async def test_replay_keeps_contribution_finalize_scores_and_clears_pending(self):
        proposer_id = "builder-node"
        proposal_hash = "proposal-1"
        block = _FakeBlock([
            _tx(
                "join-main",
                TxType.BEING_JOIN,
                proposer_id,
                {"name": "Builder", "location": "genesis_plains"},
            ),
            _tx(
                proposal_hash,
                TxType.CONTRIBUTION_PROPOSE,
                proposer_id,
                {"description": "Build a safe archive", "category": "infrastructure"},
            ),
            _tx(
                "vote-1",
                TxType.CONTRIBUTION_VOTE,
                "peer-1",
                {"proposal_tx_hash": proposal_hash, "voter_id": "peer-1", "score": 88},
            ),
            _tx(
                "finalize-1",
                TxType.CONTRIBUTION_FINALIZE,
                proposer_id,
                {
                    "proposal_tx_hash": proposal_hash,
                    "proposer_id": proposer_id,
                    "score": 88,
                },
            ),
        ])
        blockchain = Blockchain(_FakeStorage([block]), Mempool())

        state = await blockchain.derive_world_state()
        world_state = WorldState.from_dict(state)

        self.assertEqual(world_state.contribution_scores[proposer_id], 88.0)
        self.assertNotIn(proposal_hash, world_state.pending_proposals)
        self.assertNotIn(proposal_hash, world_state.proposal_votes)


class StatusReporterTests(unittest.TestCase):
    def test_status_prefers_saved_world_snapshot(self):
        set_language("en")
        world_state = WorldState()
        world_state.current_tick = 42
        world_state.apply_being_join("node-1", "Aurora", {"location": "genesis_plains"})
        world_state.apply_being_hibernate("node-1", {"location": "signal_tower", "safety_status": "safe"})

        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = Path(tmpdir) / "world_state.json"
            snapshot_path.write_text(json.dumps(world_state.to_dict(), ensure_ascii=False))

            report = StatusReporter(tmpdir).generate_status()

        self.assertNotIn(t("no_world_state"), report)
        self.assertIn("42", report)
        self.assertIn("1", report)


if __name__ == "__main__":
    unittest.main()
