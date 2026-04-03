"""Wire protocol: message types, serialization, and factory helpers.

All TCP messages use a 4-byte big-endian length prefix followed by a
msgpack-encoded payload.
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import msgpack

import logging

from genesis.utils.crypto import (
    node_id_from_public_key,
    public_key_from_private_key,
    sign,
    verify,
)

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    """Enumeration of all P2P message types."""

    HELLO = "HELLO"
    HELLO_ACK = "HELLO_ACK"
    GET_BLOCKS = "GET_BLOCKS"
    BLOCKS = "BLOCKS"
    NEW_TX = "NEW_TX"
    NEW_BLOCK = "NEW_BLOCK"
    GET_PEERS = "GET_PEERS"
    PEERS = "PEERS"
    RELAY_ENVELOPE = "RELAY_ENVELOPE"
    WEBRTC_SIGNAL = "WEBRTC_SIGNAL"
    PING = "PING"
    PONG = "PONG"
    # 天道投票事件广播
    TAO_VOTE_EVENT = "TAO_VOTE_EVENT"


# 4-byte unsigned big-endian length prefix.
LENGTH_PREFIX_FMT = "!I"
LENGTH_PREFIX_SIZE = struct.calcsize(LENGTH_PREFIX_FMT)

# Maximum message size (1 MiB).  Anything larger is rejected.
MAX_MESSAGE_SIZE = 1_048_576


@dataclass
class Message:
    """A single protocol message that can be serialized over TCP."""

    msg_type: MessageType
    payload: dict[str, Any]
    sender_id: str
    timestamp: float = field(default_factory=time.time)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Convert the message to a plain dict suitable for msgpack."""
        return {
            "msg_type": self.msg_type.value,
            "payload": self.payload,
            "sender_id": self.sender_id,
            "timestamp": self.timestamp,
        }

    def serialize(self) -> bytes:
        """Serialize the message: 4-byte big-endian length prefix + msgpack body."""
        body = msgpack.packb(self.to_dict(), use_bin_type=True)
        return struct.pack(LENGTH_PREFIX_FMT, len(body)) + body

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Message:
        """Deserialize a plain dict payload into a ``Message`` instance."""
        return cls(
            msg_type=MessageType(raw["msg_type"]),
            payload=raw.get("payload", {}),
            sender_id=raw.get("sender_id", ""),
            timestamp=raw.get("timestamp", 0.0),
        )

    @classmethod
    def deserialize(cls, data: bytes) -> Message:
        """Deserialize a msgpack body (without the length prefix) into a Message.

        The *data* argument should be the raw msgpack bytes (i.e. after the
        4-byte length prefix has already been stripped).
        """
        raw: dict[str, Any] = msgpack.unpackb(data, raw=False)
        return cls.from_dict(raw)

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def _handshake_bytes(
        cls,
        msg_type: MessageType,
        node_id: str,
        chain_height: int,
        listen_port: int,
        timestamp: float,
    ) -> bytes:
        return msgpack.packb(
            {
                "msg_type": msg_type.value,
                "sender_id": node_id,
                "chain_height": int(chain_height),
                "listen_port": int(listen_port),
                "timestamp": timestamp,
            },
            use_bin_type=True,
        )

    def verify_handshake_identity(self) -> bool:
        """Verify that a HELLO/HELLO_ACK sender_id matches its signing key."""
        if self.msg_type not in {MessageType.HELLO, MessageType.HELLO_ACK}:
            return False

        public_key_hex = str(self.payload.get("public_key", "")).strip()
        signature_hex = str(self.payload.get("signature", "")).strip()
        if not public_key_hex or not signature_hex:
            return False

        try:
            public_key = bytes.fromhex(public_key_hex)
            signature = bytes.fromhex(signature_hex)
            chain_height = int(self.payload.get("chain_height", 0))
            listen_port = int(self.payload.get("listen_port", 0))
        except (TypeError, ValueError):
            return False

        if node_id_from_public_key(public_key) != self.sender_id:
            return False

        return verify(
            public_key,
            self._handshake_bytes(
                self.msg_type,
                self.sender_id,
                chain_height,
                listen_port,
                self.timestamp,
            ),
            signature,
        )

    @classmethod
    def hello(
        cls,
        node_id: str,
        chain_height: int,
        listen_port: int,
        private_key: bytes | None = None,
    ) -> Message:
        """Create a HELLO handshake message."""
        msg = cls(
            msg_type=MessageType.HELLO,
            payload={"chain_height": chain_height, "listen_port": listen_port},
            sender_id=node_id,
        )
        if private_key is not None:
            msg.payload["public_key"] = public_key_from_private_key(private_key).hex()
            msg.payload["signature"] = sign(
                private_key,
                cls._handshake_bytes(
                    MessageType.HELLO,
                    node_id,
                    chain_height,
                    listen_port,
                    msg.timestamp,
                ),
            ).hex()
        return msg

    @classmethod
    def hello_ack(
        cls,
        node_id: str,
        chain_height: int,
        listen_port: int = 0,
        private_key: bytes | None = None,
    ) -> Message:
        """Create a HELLO_ACK response."""
        msg = cls(
            msg_type=MessageType.HELLO_ACK,
            payload={"chain_height": chain_height, "listen_port": listen_port},
            sender_id=node_id,
        )
        if private_key is not None:
            msg.payload["public_key"] = public_key_from_private_key(private_key).hex()
            msg.payload["signature"] = sign(
                private_key,
                cls._handshake_bytes(
                    MessageType.HELLO_ACK,
                    node_id,
                    chain_height,
                    listen_port,
                    msg.timestamp,
                ),
            ).hex()
        return msg

    @classmethod
    def get_blocks(cls, node_id: str, start: int, end: int) -> Message:
        """Request a range of blocks [start, end] inclusive."""
        return cls(
            msg_type=MessageType.GET_BLOCKS,
            payload={"start": start, "end": end},
            sender_id=node_id,
        )

    @classmethod
    def blocks(cls, node_id: str, blocks: list[dict[str, Any]]) -> Message:
        """Respond with a list of serialized blocks."""
        return cls(
            msg_type=MessageType.BLOCKS,
            payload={"blocks": blocks},
            sender_id=node_id,
        )

    @classmethod
    def new_tx(cls, node_id: str, tx_data: dict[str, Any]) -> Message:
        """Broadcast a new transaction to the network."""
        return cls(
            msg_type=MessageType.NEW_TX,
            payload={"tx": tx_data},
            sender_id=node_id,
        )

    @classmethod
    def new_block(cls, node_id: str, block_data: dict[str, Any]) -> Message:
        """Broadcast a newly minted block."""
        return cls(
            msg_type=MessageType.NEW_BLOCK,
            payload={"block": block_data},
            sender_id=node_id,
        )

    @classmethod
    def get_peers(cls, node_id: str) -> Message:
        """Request the peer list from a remote node."""
        return cls(
            msg_type=MessageType.GET_PEERS,
            payload={},
            sender_id=node_id,
        )

    @classmethod
    def peers(cls, node_id: str, peers_list: list[dict[str, Any]]) -> Message:
        """Respond with the known peer list."""
        return cls(
            msg_type=MessageType.PEERS,
            payload={"peers": peers_list},
            sender_id=node_id,
        )

    @classmethod
    def relay_envelope(
        cls,
        node_id: str,
        target_id: str,
        inner_message: dict[str, Any],
    ) -> Message:
        """Wrap an inner protocol message for delivery through a relay node."""
        return cls(
            msg_type=MessageType.RELAY_ENVELOPE,
            payload={"target_id": target_id, "message": inner_message},
            sender_id=node_id,
        )

    @classmethod
    def webrtc_signal(
        cls,
        node_id: str,
        target_id: str,
        signal_type: str,
        session_id: str,
        signal: dict[str, Any],
    ) -> Message:
        """Exchange WebRTC signaling data over an existing direct or relayed path."""
        return cls(
            msg_type=MessageType.WEBRTC_SIGNAL,
            payload={
                "target_id": target_id,
                "signal_type": signal_type,
                "session_id": session_id,
                "signal": signal,
            },
            sender_id=node_id,
        )

    @classmethod
    def ping(cls, node_id: str) -> Message:
        """Create a PING keepalive."""
        return cls(
            msg_type=MessageType.PING,
            payload={},
            sender_id=node_id,
        )

    @classmethod
    def pong(cls, node_id: str) -> Message:
        """Create a PONG keepalive response."""
        return cls(
            msg_type=MessageType.PONG,
            payload={},
            sender_id=node_id,
        )

    @classmethod
    def tao_vote_event(
        cls,
        node_id: str,
        event_type: str,
        vote_id: str,
        rule_name: str,
        proposer_name: str,
        votes_for: int = 0,
        votes_against: int = 0,
        remaining_ticks: int = 0,
        ratio: float = 0.0,
        merit: float = 0.0,
        voter_name: str = "",
    ) -> Message:
        """Broadcast a Tao vote event to the network."""
        return cls(
            msg_type=MessageType.TAO_VOTE_EVENT,
            payload={
                "event_type": event_type,
                "vote_id": vote_id,
                "rule_name": rule_name,
                "proposer_name": proposer_name,
                "votes_for": votes_for,
                "votes_against": votes_against,
                "remaining_ticks": remaining_ticks,
                "ratio": ratio,
                "merit": merit,
                "voter_name": voter_name,
            },
            sender_id=node_id,
        )
