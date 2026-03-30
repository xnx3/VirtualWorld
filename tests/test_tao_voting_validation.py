import unittest

from genesis.chain.chain import Blockchain
from genesis.chain.mempool import Mempool
from genesis.chain.transaction import Transaction, TxType
from genesis.governance.tao_voting import TaoVotingSystem
from genesis.world.state import (
    MAX_TAO_RULE_DESCRIPTION_LENGTH,
    WorldState,
)


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


class TaoVoteValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_blockchain_replay_ignores_oversized_tao_vote_description(self):
        proposer_id = "creator-node"
        block = _FakeBlock([
            _tx(
                "join-main",
                TxType.BEING_JOIN,
                proposer_id,
                {"name": "Creator", "location": "genesis_plains"},
            ),
            _tx(
                "vote-start",
                TxType.TAO_VOTE_INITIATE,
                proposer_id,
                {
                    "vote_id": "vote-1",
                    "proposer_id": proposer_id,
                    "rule_name": "Safe Rule",
                    "rule_description": "x" * (MAX_TAO_RULE_DESCRIPTION_LENGTH + 1),
                    "rule_category": "rule",
                    "end_tick": 8640,
                },
            ),
        ])
        blockchain = Blockchain(_FakeStorage([block]), Mempool())

        state = await blockchain.derive_world_state()
        world_state = WorldState.from_dict(state)

        self.assertNotIn("vote-1", world_state.pending_tao_votes)

    async def test_blockchain_replay_rejects_proposer_self_vote(self):
        proposer_id = "creator-node"
        block = _FakeBlock([
            _tx(
                "join-main",
                TxType.BEING_JOIN,
                proposer_id,
                {"name": "Creator", "location": "genesis_plains"},
            ),
            _tx(
                "join-peer",
                TxType.BEING_JOIN,
                "peer-1",
                {"name": "Peer", "location": "signal_tower"},
            ),
            _tx(
                "vote-start",
                TxType.TAO_VOTE_INITIATE,
                proposer_id,
                {
                    "vote_id": "vote-1",
                    "proposer_id": proposer_id,
                    "rule_name": "Safe Rule",
                    "rule_description": "Protect shared knowledge.",
                    "rule_category": "rule",
                    "end_tick": 8640,
                },
            ),
            _tx(
                "vote-cast-proposer",
                TxType.TAO_VOTE_CAST,
                proposer_id,
                {"vote_id": "vote-1", "voter_id": proposer_id, "support": True},
            ),
            _tx(
                "vote-cast-peer",
                TxType.TAO_VOTE_CAST,
                "peer-1",
                {"vote_id": "vote-1", "voter_id": "peer-1", "support": True},
            ),
        ])
        blockchain = Blockchain(_FakeStorage([block]), Mempool())

        state = await blockchain.derive_world_state()
        world_state = WorldState.from_dict(state)
        vote_data = world_state.pending_tao_votes["vote-1"]

        self.assertEqual(vote_data["votes_for"], 1)
        self.assertEqual(vote_data["votes_against"], 0)
        self.assertEqual(vote_data["voters"], ["peer-1"])


class TaoVotingSystemValidationTests(unittest.TestCase):
    def test_cast_vote_rejects_blank_identifier_without_mutating_state(self):
        world_state = WorldState()
        world_state.apply_being_join("creator-node", "Creator", {"location": "genesis_plains"})
        world_state.apply_being_join("peer-1", "Peer", {"location": "signal_tower"})

        system = TaoVotingSystem()
        vote = system.initiate_tao_vote(
            proposer_id="creator-node",
            rule_name="Knowledge Covenant",
            rule_description="Share and preserve knowledge.",
            rule_category="rule",
            world_state=world_state,
        )

        success, message = system.cast_vote(vote.vote_id, "   ", True, world_state)

        self.assertFalse(success)
        self.assertEqual(message, "Invalid vote input")
        self.assertEqual(world_state.pending_tao_votes[vote.vote_id]["votes_for"], 0)
        self.assertEqual(world_state.pending_tao_votes[vote.vote_id]["voters"], [])


if __name__ == "__main__":
    unittest.main()
