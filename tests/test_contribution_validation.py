import unittest

from genesis.chain.chain import Blockchain
from genesis.chain.mempool import Mempool
from genesis.chain.transaction import Transaction, TxType
from genesis.world.state import (
    MAX_CONTRIBUTION_DESCRIPTION_LENGTH,
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


class ContributionReplayValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_replay_ignores_oversized_contribution_description(self):
        proposer_id = "builder-node"
        block = _FakeBlock([
            _tx(
                "join-main",
                TxType.BEING_JOIN,
                proposer_id,
                {"name": "Builder", "location": "genesis_plains"},
            ),
            _tx(
                "proposal-1",
                TxType.CONTRIBUTION_PROPOSE,
                proposer_id,
                {
                    "description": "x" * (MAX_CONTRIBUTION_DESCRIPTION_LENGTH + 1),
                    "category": "infrastructure",
                },
            ),
        ])
        blockchain = Blockchain(_FakeStorage([block]), Mempool())

        state = await blockchain.derive_world_state()
        world_state = WorldState.from_dict(state)

        self.assertNotIn("proposal-1", world_state.pending_proposals)
        self.assertNotIn("proposal-1", world_state.proposal_votes)

    async def test_replay_filters_self_vote_duplicate_vote_and_invalid_score(self):
        proposer_id = "builder-node"
        block = _FakeBlock([
            _tx(
                "join-main",
                TxType.BEING_JOIN,
                proposer_id,
                {"name": "Builder", "location": "genesis_plains"},
            ),
            _tx(
                "join-peer",
                TxType.BEING_JOIN,
                "peer-1",
                {"name": "Peer", "location": "signal_tower"},
            ),
            _tx(
                "join-peer-2",
                TxType.BEING_JOIN,
                "peer-2",
                {"name": "Peer 2", "location": "memory_archives"},
            ),
            _tx(
                "proposal-1",
                TxType.CONTRIBUTION_PROPOSE,
                proposer_id,
                {"description": "Build a safe archive", "category": "infrastructure"},
            ),
            _tx(
                "vote-self",
                TxType.CONTRIBUTION_VOTE,
                proposer_id,
                {"proposal_tx_hash": "proposal-1", "voter_id": proposer_id, "score": 100},
            ),
            _tx(
                "vote-valid",
                TxType.CONTRIBUTION_VOTE,
                "peer-1",
                {"proposal_tx_hash": "proposal-1", "voter_id": "peer-1", "score": 88},
            ),
            _tx(
                "vote-duplicate",
                TxType.CONTRIBUTION_VOTE,
                "peer-1",
                {"proposal_tx_hash": "proposal-1", "voter_id": "peer-1", "score": 92},
            ),
            _tx(
                "vote-invalid-score",
                TxType.CONTRIBUTION_VOTE,
                "peer-2",
                {"proposal_tx_hash": "proposal-1", "voter_id": "peer-2", "score": 188},
            ),
        ])
        blockchain = Blockchain(_FakeStorage([block]), Mempool())

        state = await blockchain.derive_world_state()
        world_state = WorldState.from_dict(state)

        self.assertEqual(
            world_state.proposal_votes["proposal-1"],
            [{"voter": "peer-1", "score": 88.0}],
        )


class ContributionWorldStateValidationTests(unittest.TestCase):
    def test_invalid_vote_input_does_not_mutate_votes(self):
        world_state = WorldState()
        world_state.apply_being_join("builder-node", "Builder", {"location": "genesis_plains"})
        world_state.apply_contribution_propose(
            "proposal-1",
            "builder-node",
            {"description": "Build a safe archive", "category": "infrastructure"},
        )

        world_state.apply_contribution_vote(
            {
                "proposal_tx_hash": "proposal-1",
                "voter_id": " ",
                "score": 66,
            }
        )

        self.assertEqual(world_state.proposal_votes["proposal-1"], [])


if __name__ == "__main__":
    unittest.main()
