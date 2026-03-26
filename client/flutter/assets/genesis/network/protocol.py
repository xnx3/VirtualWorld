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
    PING = "PING"
    PONG = "PONG"


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
    def deserialize(cls, data: bytes) -> Message:
        """Deserialize a msgpack body (without the length prefix) into a Message.

        The *data* argument should be the raw msgpack bytes (i.e. after the
        4-byte length prefix has already been stripped).
        """
        raw: dict[str, Any] = msgpack.unpackb(data, raw=False)
        return cls(
            msg_type=MessageType(raw["msg_type"]),
            payload=raw.get("payload", {}),
            sender_id=raw.get("sender_id", ""),
            timestamp=raw.get("timestamp", 0.0),
        )

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def hello(cls, node_id: str, chain_height: int, listen_port: int) -> Message:
        """Create a HELLO handshake message."""
        return cls(
            msg_type=MessageType.HELLO,
            payload={"chain_height": chain_height, "listen_port": listen_port},
            sender_id=node_id,
        )

    @classmethod
    def hello_ack(cls, node_id: str, chain_height: int) -> Message:
        """Create a HELLO_ACK response."""
        return cls(
            msg_type=MessageType.HELLO_ACK,
            payload={"chain_height": chain_height},
            sender_id=node_id,
        )

    @classmethod
    def get_blocks(cls, node_id: str, start: int, end: int) -> Message:
        """Request a range of blocks [start, end)."""
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
