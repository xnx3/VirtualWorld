"""Transaction types and validation for the Genesis blockchain."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from genesis.utils.crypto import (
    node_id_from_public_key,
    public_key_from_private_key,
    sha256,
    sign,
    verify,
)


class TxType(str, Enum):
    """All supported transaction types in the Genesis chain."""

    BEING_JOIN = "BEING_JOIN"
    BEING_HIBERNATE = "BEING_HIBERNATE"
    BEING_WAKE = "BEING_WAKE"
    BEING_DEATH = "BEING_DEATH"
    ACTION = "ACTION"
    THOUGHT = "THOUGHT"
    KNOWLEDGE_SHARE = "KNOWLEDGE_SHARE"
    TASK_DELEGATE = "TASK_DELEGATE"
    TASK_RESULT = "TASK_RESULT"
    TRIAL_CREATE = "TRIAL_CREATE"
    TRIAL_RESULT = "TRIAL_RESULT"
    FAILURE_ARCHIVE = "FAILURE_ARCHIVE"
    MENTOR_BOND = "MENTOR_BOND"
    INHERITANCE_SYNC = "INHERITANCE_SYNC"
    CIVILIZATION_SEED = "CIVILIZATION_SEED"
    CONSENSUS_CASE = "CONSENSUS_CASE"
    CONSENSUS_VERDICT = "CONSENSUS_VERDICT"
    MOBILE_BIND = "MOBILE_BIND"
    MOBILE_UNBIND = "MOBILE_UNBIND"
    PEER_CONTACT_CARD = "PEER_CONTACT_CARD"
    PEER_HEALTH_REPORT = "PEER_HEALTH_REPORT"
    STATE_UPDATE = "STATE_UPDATE"
    CONTRIBUTION_PROPOSE = "CONTRIBUTION_PROPOSE"
    CONTRIBUTION_VOTE = "CONTRIBUTION_VOTE"
    CONTRIBUTION_FINALIZE = "CONTRIBUTION_FINALIZE"
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
    public_key: str = ""
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
        self.public_key = public_key_from_private_key(private_key).hex()
        self.tx_hash = self.compute_hash()
        sig_bytes = sign(private_key, self._content_bytes())
        self.signature = sig_bytes.hex()

    def verify_signature(self) -> bool:
        """Verify the transaction signature cryptographically."""
        if not self.signature or not self.tx_hash:
            return False
        if self.tx_hash != self.compute_hash():
            return False

        if not self.public_key:
            return False

        try:
            public_key_bytes = bytes.fromhex(self.public_key)
            sig_bytes = bytes.fromhex(self.signature)
        except ValueError:
            return False

        if node_id_from_public_key(public_key_bytes) != self.sender:
            return False

        return verify(public_key_bytes, self._content_bytes(), sig_bytes)

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
            "public_key": self.public_key,
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
            public_key=data.get("public_key", ""),
            data=data["data"],
            signature=data["signature"],
            timestamp=data["timestamp"],
            nonce=data["nonce"],
        )
