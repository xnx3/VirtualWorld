"""LAN peer discovery via UDP broadcast and optional bootstrap nodes."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

# How often to broadcast presence on LAN (seconds).
_BROADCAST_INTERVAL: float = 30.0

# How often to query bootstrap nodes (seconds).
_BOOTSTRAP_INTERVAL: float = 60.0


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    """asyncio UDP protocol that receives discovery announcements on LAN."""

    def __init__(self, on_received: Callable[[dict[str, Any], tuple[str, int]], None]) -> None:
        self._on_received = on_received
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:  # type: ignore[override]
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            payload = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.debug("Malformed discovery datagram from %s", addr)
            return
        self._on_received(payload, addr)

    def error_received(self, exc: Exception) -> None:
        logger.debug("Discovery UDP error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        pass


class PeerDiscovery:
    """Discovers peers on the local network via UDP broadcast and
    optionally queries a list of bootstrap nodes for additional peers.

    Bootstrap nodes can be either:
    - HTTP bootstrap server: "http://host:port"  (Genesis bootstrap server)
    - P2P node addresses: "host:port" (direct peer)
    """

    def __init__(
        self,
        node_id: str,
        listen_port: int,
        private_key: bytes | None = None,
        discovery_port: int = 19840,
        bootstrap_nodes: list[str] | None = None,
    ) -> None:
        self._node_id = node_id
        self._listen_port = listen_port
        self._private_key = private_key
        self._discovery_port = discovery_port
        self._bootstrap_nodes: list[str] = bootstrap_nodes or []

        self._callbacks: list[Callable[[str, str, int], Awaitable[None] | None]] = []
        self._transport: asyncio.DatagramTransport | None = None
        self._protocol: _DiscoveryProtocol | None = None
        self._running = False
        self._tasks: list[asyncio.Task[None]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start listening for UDP announcements and periodically broadcast."""
        if self._running:
            return
        self._running = True

        loop = asyncio.get_running_loop()

        # Create a UDP socket that can receive broadcasts.
        self._transport, self._protocol = await loop.create_datagram_endpoint(
            lambda: _DiscoveryProtocol(self._handle_datagram),
            local_addr=("0.0.0.0", self._discovery_port),
            allow_broadcast=True,
        )  # type: ignore[assignment]

        self._tasks.append(asyncio.create_task(self._broadcast_loop()))
        if self._bootstrap_nodes:
            self._tasks.append(asyncio.create_task(self._bootstrap_loop()))

        logger.info(
            "Peer discovery started on UDP port %d (listen_port=%d)",
            self._discovery_port,
            self._listen_port,
        )

    async def stop(self) -> None:
        """Stop all discovery tasks and close the UDP socket."""
        self._running = False
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        if self._transport is not None:
            self._transport.close()
            self._transport = None
        logger.info("Peer discovery stopped")

    async def broadcast_presence(self) -> None:
        """Send a single UDP broadcast announcing this node."""
        if self._transport is None:
            return
        announcement = json.dumps({
            "type": "HELLO",
            "node_id": self._node_id,
            "port": self._listen_port,
        }).encode("utf-8")
        try:
            self._transport.sendto(announcement, ("<broadcast>", self._discovery_port))
        except OSError as exc:
            logger.debug("Broadcast send failed: %s", exc)

    async def query_bootstrap(self) -> None:
        """Connect to each bootstrap node and request their peer lists.

        Supports two formats:
        - "http://host:port"  → Genesis HTTP bootstrap server
        - "host:port"         → Direct P2P peer connection
        """
        from genesis.network.protocol import Message  # avoid circular import

        for addr_str in self._bootstrap_nodes:
            if addr_str.startswith("http://") or addr_str.startswith("https://"):
                await self._query_http_bootstrap(addr_str)
            else:
                await self._query_p2p_bootstrap(addr_str)

    def _validate_peer_data(self, peer_data: dict) -> tuple[bool, str, int]:
        """Validate peer data from bootstrap response. Returns (valid, address, port)."""
        node_id = str(peer_data.get("node_id", "")).strip()
        address = str(peer_data.get("address", "")).strip()
        port = peer_data.get("port", 0)

        if not node_id or len(node_id) > 128:
            return False, "", 0
        if not address or len(address) > 64:
            return False, "", 0
        try:
            port = int(port)
        except (TypeError, ValueError):
            return False, "", 0
        if not (1 <= port <= 65535):
            return False, "", 0

        return True, address, port

    async def _query_http_bootstrap(self, base_url: str) -> None:
        """Query a Genesis HTTP bootstrap server."""
        import urllib.request
        import urllib.parse

        try:
            # Register this node
            import json as _json
            register_data = _json.dumps({
                "node_id": self._node_id,
                "port": self._listen_port,
            }).encode()
            req = urllib.request.Request(
                f"{base_url.rstrip('/')}/register",
                data=register_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as exc:
            logger.debug("HTTP bootstrap register to %s failed: %s", base_url, exc)

        try:
            # Get peers
            import json as _json
            url = f"{base_url.rstrip('/')}/peers?exclude={urllib.parse.quote(self._node_id)}"
            resp = urllib.request.urlopen(url, timeout=5)
            data = _json.loads(resp.read())
            peers_list = data.get("peers", [])[:100]  # Max 100 peers
            for peer_data in peers_list:
                valid, address, port = self._validate_peer_data(peer_data)
                if valid:
                    await self._fire_callbacks(
                        peer_data.get("node_id", ""),
                        address,
                        port,
                    )
            logger.debug("HTTP bootstrap %s returned %d peers", base_url, len(peers_list))
        except Exception as exc:
            logger.debug("HTTP bootstrap peers from %s failed: %s", base_url, exc)

    async def _query_p2p_bootstrap(self, addr_str: str) -> None:
        """Query a direct P2P bootstrap node."""
        from genesis.network.protocol import Message, MessageType

        try:
            host, port_str = addr_str.rsplit(":", 1)
            port = int(port_str)
        except ValueError:
            logger.warning("Invalid bootstrap address: %s", addr_str)
            return

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=5.0
            )
        except (OSError, asyncio.TimeoutError) as exc:
            logger.debug("Bootstrap %s unreachable: %s", addr_str, exc)
            return

        try:
            hello = Message.hello(
                self._node_id,
                chain_height=0,
                listen_port=self._listen_port,
                private_key=self._private_key,
            )
            writer.write(hello.serialize())
            await writer.drain()

            length_data = await asyncio.wait_for(reader.readexactly(4), timeout=5.0)
            import struct
            (length,) = struct.unpack("!I", length_data)
            if length > 1_048_576:
                logger.warning("Bootstrap %s sent oversized handshake response", addr_str)
                return
            body = await asyncio.wait_for(reader.readexactly(length), timeout=10.0)
            ack = Message.deserialize(body)

            if ack.msg_type != MessageType.HELLO_ACK or not ack.verify_handshake_identity():
                logger.debug(
                    "Bootstrap %s rejected handshake with response %s",
                    addr_str,
                    ack.msg_type,
                )
                return

            if ack.sender_id:
                try:
                    peer_port = int(ack.payload.get("listen_port", port) or port)
                except (TypeError, ValueError):
                    peer_port = port
                await self._fire_callbacks(ack.sender_id, host, peer_port)

            msg = Message.get_peers(self._node_id)
            writer.write(msg.serialize())
            await writer.drain()

            length_data = await asyncio.wait_for(reader.readexactly(4), timeout=5.0)
            (length,) = struct.unpack("!I", length_data)
            if length > 1_048_576:
                logger.warning("Bootstrap %s sent oversized peer response", addr_str)
                return
            body = await asyncio.wait_for(reader.readexactly(length), timeout=10.0)
            resp = Message.deserialize(body)

            if resp.msg_type == MessageType.PEERS:
                peers_list = resp.payload.get("peers", [])[:100]  # Max 100 peers
                for peer_data in peers_list:
                    valid, address, port_p = self._validate_peer_data(peer_data)
                    if valid:
                        await self._fire_callbacks(
                            peer_data.get("node_id", ""),
                            address,
                            port_p,
                        )
        except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, Exception) as exc:
            logger.debug("Bootstrap query to %s failed: %s", addr_str, exc)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    def on_peer_discovered(
        self, callback: Callable[[str, str, int], Awaitable[None] | None]
    ) -> None:
        """Register a callback invoked when a new peer is discovered.

        The callback receives ``(node_id, address, port)``.
        """
        self._callbacks.append(callback)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _handle_datagram(self, payload: dict[str, Any], addr: tuple[str, int]) -> None:
        """Called synchronously by the UDP protocol when a datagram arrives."""
        if payload.get("type") != "HELLO":
            return
        node_id = payload.get("node_id", "")
        port = payload.get("port", 0)
        if not node_id or not port:
            return
        # Ignore our own broadcasts.
        if node_id == self._node_id:
            return

        host = addr[0]
        # Schedule callback on the event loop.
        loop = asyncio.get_event_loop()
        loop.create_task(self._fire_callbacks(node_id, host, port))

    async def _fire_callbacks(self, node_id: str, address: str, port: int) -> None:
        for cb in self._callbacks:
            try:
                result = cb(node_id, address, port)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception("Error in discovery callback")

    async def _broadcast_loop(self) -> None:
        """Periodically broadcast presence on LAN."""
        while self._running:
            await self.broadcast_presence()
            await asyncio.sleep(_BROADCAST_INTERVAL)

    async def _bootstrap_loop(self) -> None:
        """Periodically query bootstrap nodes."""
        while self._running:
            await self.query_bootstrap()
            await asyncio.sleep(_BOOTSTRAP_INTERVAL)
