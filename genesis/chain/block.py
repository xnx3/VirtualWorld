"""Block data structure for the Genesis blockchain."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from genesis.utils.crypto import (
    merkle_root,
    node_id_from_public_key,
    public_key_from_private_key,
    sha256,
    sign,
    verify,
)
from genesis.chain.transaction import Transaction


@dataclass
class Block:
    """A single block in the Genesis blockchain."""

    index: int = 0
    timestamp: float = 0.0
    previous_hash: str = ""
    merkle_root: str = ""
    proposer: str = ""
    proposer_public_key: str = ""
    signature: str = ""
    transactions: list[Transaction] = field(default_factory=list)
    nonce: int = 0
    hash: str = ""

    # ------------------------------------------------------------------
    # Header helpers
    # ------------------------------------------------------------------

    def header_bytes(self) -> bytes:
        """Return the canonical byte representation of the block header.

        Used for both hashing and signing.  Does **not** include ``hash``
        or ``signature`` themselves.
        """
        header = {
            "index": self.index,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
            "merkle_root": self.merkle_root,
            "proposer": self.proposer,
            "nonce": self.nonce,
        }
        return json.dumps(header, sort_keys=True, separators=(",", ":")).encode()

    # ------------------------------------------------------------------
    # Hashing
    # ------------------------------------------------------------------

    def compute_hash(self) -> str:
        """Compute and return the SHA-256 hash of the block header."""
        return sha256(self.header_bytes())

    # ------------------------------------------------------------------
    # Signing / verification
    # ------------------------------------------------------------------

    def sign_block(self, private_key: bytes) -> None:
        """Sign the block header with an Ed25519 private key.

        Sets ``signature`` (hex-encoded) and then computes ``hash``.
        """
        self.proposer_public_key = public_key_from_private_key(private_key).hex()
        sig_bytes = sign(private_key, self.header_bytes())
        self.signature = sig_bytes.hex()
        self.hash = self.compute_hash()

    def verify_signature(self) -> bool:
        """Verify the block signature.

        New blocks carry ``proposer_public_key`` and are verified
        cryptographically against ``proposer``. Legacy blocks without that
        field fall back to structural hash verification so older chains remain
        readable.
        """
        if not self.signature or not self.hash:
            return False
        if self.hash != self.compute_hash():
            return False

        if not self.proposer_public_key:
            return True

        try:
            public_key_bytes = bytes.fromhex(self.proposer_public_key)
            sig_bytes = bytes.fromhex(self.signature)
        except ValueError:
            return False

        if node_id_from_public_key(public_key_bytes) != self.proposer:
            return False

        return verify(public_key_bytes, self.header_bytes(), sig_bytes)

    def verify_signature_with_key(self, public_key: bytes) -> bool:
        """Verify the Ed25519 signature using the given raw public key."""
        if not self.signature:
            return False
        try:
            sig_bytes = bytes.fromhex(self.signature)
        except ValueError:
            return False
        return verify(public_key, self.header_bytes(), sig_bytes)

    # ------------------------------------------------------------------
    # Genesis
    # ------------------------------------------------------------------

    @classmethod
    def genesis_block(cls, creator_node_id: str) -> Block:
        """Create the genesis (height-0) block.

        The genesis block has no transactions, an empty previous hash, and
        is *not* signed (signature is set to a fixed placeholder).
        """
        blk = cls(
            index=0,
            timestamp=0.0,
            previous_hash="0" * 64,
            merkle_root=merkle_root([]),
            proposer=creator_node_id,
            proposer_public_key="",
            signature="0" * 128,
            transactions=[],
            nonce=0,
        )
        blk.hash = blk.compute_hash()
        return blk

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
            "merkle_root": self.merkle_root,
            "proposer": self.proposer,
            "proposer_public_key": self.proposer_public_key,
            "signature": self.signature,
            "transactions": [tx.to_dict() for tx in self.transactions],
            "nonce": self.nonce,
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Block:
        return cls(
            index=data["index"],
            timestamp=data["timestamp"],
            previous_hash=data["previous_hash"],
            merkle_root=data["merkle_root"],
            proposer=data["proposer"],
            proposer_public_key=data.get("proposer_public_key", ""),
            signature=data["signature"],
            transactions=[Transaction.from_dict(tx) for tx in data.get("transactions", [])],
            nonce=data["nonce"],
            hash=data["hash"],
        )
