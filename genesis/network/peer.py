"""Peer representation and tracking for the P2P network."""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from typing import Any

import logging

logger = logging.getLogger(__name__)


@dataclass
class PeerInfo:
    """Information about a known peer in the network."""

    node_id: str
    address: str
    port: int
    last_seen: float = field(default_factory=time.time)
    status: str = "active"  # 'active', 'hibernating', 'dead'
    chain_height: int = 0
    transports: list[str] = field(default_factory=list)
    relay_hints: list[str] = field(default_factory=list)
    capabilities: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for wire transmission."""
        return {
            "node_id": self.node_id,
            "address": self.address,
            "port": self.port,
            "last_seen": self.last_seen,
            "status": self.status,
            "chain_height": self.chain_height,
            "transports": self.transports,
            "relay_hints": self.relay_hints,
            "capabilities": self.capabilities,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PeerInfo:
        """Deserialize from a plain dict."""
        return cls(
            node_id=data["node_id"],
            address=data["address"],
            port=data["port"],
            last_seen=data.get("last_seen", time.time()),
            status=data.get("status", "active"),
            chain_height=data.get("chain_height", 0),
            transports=list(data.get("transports", []) or []),
            relay_hints=list(data.get("relay_hints", []) or []),
            capabilities=dict(data.get("capabilities", {}) or {}),
        )


class PeerManager:
    """Thread-safe container for tracking known peers."""

    # Seconds after which an active peer with no heartbeat is marked dead.
    _DEAD_TIMEOUT: float = 300.0
    # Seconds after which a peer is considered hibernating.
    _HIBERNATE_TIMEOUT: float = 120.0

    def __init__(self, max_peers: int = 50) -> None:
        self._max_peers = max_peers
        self._peers: dict[str, PeerInfo] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Mutators
    # ------------------------------------------------------------------

    def add_peer(self, peer: PeerInfo) -> bool:
        """Add a peer.  Returns True if the peer was added, False if at capacity
        or the peer already exists."""
        with self._lock:
            if peer.node_id in self._peers:
                # Refresh metadata on re-discovery or reconnect.
                existing = self._peers[peer.node_id]
                existing.address = peer.address
                existing.port = peer.port
                existing.last_seen = time.time()
                existing.status = peer.status
                existing.chain_height = peer.chain_height
                existing.transports = list(peer.transports)
                existing.relay_hints = list(peer.relay_hints)
                existing.capabilities = dict(peer.capabilities)
                return False
            if len(self._peers) >= self._max_peers:
                logger.warning(
                    "Peer limit reached (%d), cannot add %s",
                    self._max_peers,
                    peer.node_id[:16],
                )
                return False
            self._peers[peer.node_id] = peer
            logger.info("Added peer %s (%s:%d)", peer.node_id[:16], peer.address, peer.port)
            return True

    def remove_peer(self, node_id: str) -> None:
        """Remove a peer by node_id.  No-op if not present."""
        with self._lock:
            removed = self._peers.pop(node_id, None)
        if removed:
            logger.info("Removed peer %s", node_id[:16])

    def update_peer(self, node_id: str, **kwargs: Any) -> None:
        """Update fields on an existing peer.  Unknown node_ids are silently ignored."""
        with self._lock:
            peer = self._peers.get(node_id)
            if peer is None:
                return
            for key, value in kwargs.items():
                if hasattr(peer, key):
                    setattr(peer, key, value)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_peer(self, node_id: str) -> PeerInfo | None:
        """Return a peer by node_id, or None."""
        with self._lock:
            return self._peers.get(node_id)

    def get_active_peers(self) -> list[PeerInfo]:
        """Return all peers whose status is 'active'."""
        with self._lock:
            return [p for p in self._peers.values() if p.status == "active"]

    def get_all_peers(self) -> list[PeerInfo]:
        """Return a copy of all tracked peers."""
        with self._lock:
            return list(self._peers.values())

    def peer_count(self) -> int:
        """Total number of tracked peers (any status)."""
        with self._lock:
            return len(self._peers)

    def get_best_peer(self) -> PeerInfo | None:
        """Return the active peer with the highest chain_height, or None."""
        active = self.get_active_peers()
        if not active:
            return None
        return max(active, key=lambda p: p.chain_height)

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    def to_list(self) -> list[dict[str, Any]]:
        """Serialize all peers for a PEERS message payload."""
        with self._lock:
            return [p.to_dict() for p in self._peers.values()]

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def expire_peers(self) -> None:
        """Mark or remove peers that have not been seen recently."""
        now = time.time()
        with self._lock:
            to_remove: list[str] = []
            for nid, peer in self._peers.items():
                elapsed = now - peer.last_seen
                if elapsed > self._DEAD_TIMEOUT:
                    to_remove.append(nid)
                elif elapsed > self._HIBERNATE_TIMEOUT and peer.status == "active":
                    peer.status = "hibernating"
            for nid in to_remove:
                del self._peers[nid]
                logger.info("Expired dead peer %s", nid[:16])
