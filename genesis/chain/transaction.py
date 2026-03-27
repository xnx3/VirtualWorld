"""Transaction types and validation for the Genesis blockchain."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from genesis.utils.crypto import sha256, sign, verify, node_id_from_public_key


class TxType(str, Enum):
    """All supported transaction types in the Genesis chain."""

    BEING_JOIN = "BEING_JOIN"
    BEING_HIBERNATE = "BEING_HIBERNATE"
    BEING_WAKE = "BEING_WAKE"
    BEING_DEATH = "BEING_DEATH"
    ACTION = "ACTION"
    THOUGHT = "THOUGHT"
    KNOWLEDGE_SHARE = "KNOWLEDGE_SHARE"
    CONTRIBUTION_PROPOSE = "CONTRIBUTION_PROPOSE"
    CONTRIBUTION_VOTE = "CONTRIBUTION_VOTE"
    PRIEST_ELECTION = "PRIEST_ELECTION"
    CREATOR_SUCCESSION = "CREATOR_SUCCESSION"
    CREATOR_VANISH = "CREATOR_VANISH"
    DISASTER_EVENT = "DISASTER_EVENT"
    WORLD_RULE = "WORLD_RULE"
    MAP_UPDATE = "MAP_UPDATE"
    # 天道投票交易类型
    TAO_VOTE_INITIATE = "TAO_VOTE_INITIATE"   # 发起天道投票
    TAO_VOTE_CAST = "TAO_VOTE_CAST"           # 投票
    TAO_VOTE_FINALIZE = "TAO_VOTE_FINALIZE"   # 投票结算


@dataclass
class Transaction:
    """A single transaction on the Genesis blockchain."""

    tx_hash: str = ""
    tx_type: TxType = TxType.ACTION
    sender: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    signature: str = ""
    timestamp: float = 0.0
    nonce: int = 0

    # ------------------------------------------------------------------
    # Hashing
    # ------------------------------------------------------------------

    def _content_bytes(self) -> bytes:
        """Return the canonical byte representation used for hashing and signing."""
        content = {
            "tx_type": self.tx_type.value,
            "sender": self.sender,
            "data": self.data,
            "timestamp": self.timestamp,
            "nonce": self.nonce,
        }
        return json.dumps(content, sort_keys=True, separators=(",", ":")).encode()

    def compute_hash(self) -> str:
        """Compute and return the SHA-256 hash of the transaction content."""
        return sha256(self._content_bytes())

    # ------------------------------------------------------------------
    # Signing / verification
    # ------------------------------------------------------------------

    def sign_tx(self, private_key: bytes) -> None:
        """Sign the transaction with the given Ed25519 private key.

        Sets both ``tx_hash`` and ``signature`` on this instance.
        """
        self.tx_hash = self.compute_hash()
        sig_bytes = sign(private_key, self._content_bytes())
        self.signature = sig_bytes.hex()

    def verify_signature(self) -> bool:
        """Verify that the signature matches the sender's public key.

        The sender field is a *node ID* (SHA-256 of the public key), so we
        cannot recover the public key from it alone.  Callers that need full
        verification must supply the public key externally.  This method
        checks structural validity: non-empty signature and matching hash.
        """
        if not self.signature:
            return False
        return self.tx_hash == self.compute_hash()

    def verify_signature_with_key(self, public_key: bytes) -> bool:
        """Verify the Ed25519 signature using the given raw public key."""
        if not self.signature:
            return False
        try:
            sig_bytes = bytes.fromhex(self.signature)
        except ValueError:
            return False
        return verify(public_key, self._content_bytes(), sig_bytes)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        tx_type: TxType,
        sender: str,
        data: dict[str, Any],
        private_key: bytes,
        nonce: int,
    ) -> Transaction:
        """Create, sign, and return a new Transaction."""
        tx = cls(
            tx_type=tx_type,
            sender=sender,
            data=data,
            timestamp=time.time(),
            nonce=nonce,
        )
        tx.sign_tx(private_key)
        return tx

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "tx_hash": self.tx_hash,
            "tx_type": self.tx_type.value,
            "sender": self.sender,
            "data": self.data,
            "signature": self.signature,
            "timestamp": self.timestamp,
            "nonce": self.nonce,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Transaction:
        return cls(
            tx_hash=data["tx_hash"],
            tx_type=TxType(data["tx_type"]),
            sender=data["sender"],
            data=data["data"],
            signature=data["signature"],
            timestamp=data["timestamp"],
            nonce=data["nonce"],
        )
