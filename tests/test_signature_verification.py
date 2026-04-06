import unittest

from genesis.chain.block import Block
from genesis.chain.transaction import Transaction, TxType
from genesis.node.identity import NodeIdentity


class TransactionSignatureTests(unittest.TestCase):
    def test_created_transaction_verifies_cryptographically(self):
        identity = NodeIdentity.generate()
        tx = Transaction.create(
            tx_type=TxType.ACTION,
            sender=identity.node_id,
            data={"action": "observe"},
            private_key=identity.private_key,
            nonce=1,
        )

        self.assertTrue(tx.public_key)
        self.assertTrue(tx.verify_signature())

    def test_transaction_rejects_sender_mismatch_even_with_valid_signature(self):
        identity = NodeIdentity.generate()
        other_identity = NodeIdentity.generate()
        tx = Transaction.create(
            tx_type=TxType.ACTION,
            sender=other_identity.node_id,
            data={"action": "observe"},
            private_key=identity.private_key,
            nonce=1,
        )

        self.assertFalse(tx.verify_signature())

    def test_transaction_rejects_missing_public_key(self):
        identity = NodeIdentity.generate()
        tx = Transaction.create(
            tx_type=TxType.ACTION,
            sender=identity.node_id,
            data={"action": "observe"},
            private_key=identity.private_key,
            nonce=1,
        )
        tx.public_key = ""

        self.assertFalse(tx.verify_signature())


class BlockSignatureTests(unittest.TestCase):
    def test_signed_block_verifies_cryptographically(self):
        identity = NodeIdentity.generate()
        block = Block(
            index=1,
            timestamp=1.0,
            previous_hash="genesis",
            merkle_root="root",
            proposer=identity.node_id,
            transactions=[],
            nonce=0,
        )
        block.sign_block(identity.private_key)

        self.assertTrue(block.proposer_public_key)
        self.assertTrue(block.verify_signature())

    def test_block_rejects_proposer_mismatch_even_with_valid_signature(self):
        identity = NodeIdentity.generate()
        other_identity = NodeIdentity.generate()
        block = Block(
            index=1,
            timestamp=1.0,
            previous_hash="genesis",
            merkle_root="root",
            proposer=other_identity.node_id,
            transactions=[],
            nonce=0,
        )
        block.sign_block(identity.private_key)

        self.assertFalse(block.verify_signature())

    def test_block_rejects_missing_public_key(self):
        identity = NodeIdentity.generate()
        block = Block(
            index=1,
            timestamp=1.0,
            previous_hash="genesis",
            merkle_root="root",
            proposer=identity.node_id,
            transactions=[],
            nonce=0,
        )
        block.sign_block(identity.private_key)
        block.proposer_public_key = ""

        self.assertFalse(block.verify_signature())

    def test_genesis_block_keeps_placeholder_signature_contract(self):
        block = Block.genesis_block("creator")

        self.assertTrue(block.verify_signature())


class SerializationPublicKeyRoundTripTests(unittest.TestCase):
    def test_block_and_transaction_dict_round_trip_preserves_public_keys(self):
        identity = NodeIdentity.generate()
        tx = Transaction.create(
            tx_type=TxType.ACTION,
            sender=identity.node_id,
            data={"action": "observe"},
            private_key=identity.private_key,
            nonce=1,
        )
        block = Block(
            index=1,
            timestamp=1.0,
            previous_hash="genesis",
            merkle_root=tx.tx_hash,
            proposer=identity.node_id,
            transactions=[tx],
            nonce=0,
        )
        block.sign_block(identity.private_key)
        loaded = Block.from_dict(block.to_dict())

        self.assertEqual(loaded.proposer_public_key, block.proposer_public_key)
        self.assertEqual(loaded.transactions[0].public_key, tx.public_key)
        self.assertTrue(loaded.verify_signature())
        self.assertTrue(loaded.transactions[0].verify_signature())


if __name__ == "__main__":
    unittest.main()
