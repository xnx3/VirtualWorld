"""Async TCP server and client for the Genesis P2P network."""

from __future__ import annotations

import asyncio
import ipaddress
import inspect
import logging
import struct
import time
from typing import Any, Callable, Awaitable

from genesis.network.peer import PeerInfo, PeerManager
from genesis.network.protocol import (
    LENGTH_PREFIX_FMT,
    LENGTH_PREFIX_SIZE,
    MAX_MESSAGE_SIZE,
    Message,
    MessageType,
)
from genesis.network.security import NetworkSecurity

logger = logging.getLogger(__name__)


class P2PServer:
    """Asynchronous TCP server that accepts and initiates peer connections.

    The server maintains a set of open connections keyed by node_id and
    provides helpers to broadcast or send targeted messages.
    """

    def __init__(
        self,
        node_id: str,
        private_key: bytes,
        host: str = "0.0.0.0",
        port: int = 19841,
        peer_manager: PeerManager | None = None,
    ) -> None:
        self._node_id = node_id
        self._private_key = private_key
        self._host = host
        self._port = port
        self._peer_manager = peer_manager or PeerManager()
        self._security = NetworkSecurity()

        # node_id -> (reader, writer)
        self._connections: dict[str, tuple[asyncio.StreamReader, asyncio.StreamWriter]] = {}
        self._server: asyncio.Server | None = None
        self._message_handlers: list[
            Callable[[Message, str], Awaitable[None] | None]
        ] = []
        self._running = False
        self._chain_height_provider: Callable[[], Awaitable[int] | int] | None = None
        self._blocks_provider: Callable[[int, int], Awaitable[list[Any]] | list[Any]] | None = None
        self._relay_routes: dict[str, list[str]] = {}
        self._peer_capabilities: dict[str, dict[str, Any]] = {}
        self._peer_transports: dict[str, list[str]] = {}
        self._virtual_connections: dict[str, tuple[str, Callable[[Message], Awaitable[None] | None]]] = {}
        self._public_reachability_handlers: list[Callable[[bool], Awaitable[None] | None]] = []
        self._last_public_inbound_at: float = 0.0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def port(self) -> int:
        return self._port

    @property
    def peer_manager(self) -> PeerManager:
        return self._peer_manager

    @staticmethod
    def _is_public_ip(address: str) -> bool:
        try:
            return ipaddress.ip_address(str(address).strip()).is_global
        except ValueError:
            return False

    def has_recent_public_inbound(self, max_age: float = 3600.0) -> bool:
        """True after a recent inbound connection from a globally routable peer."""
        return self._last_public_inbound_at > 0 and (time.time() - self._last_public_inbound_at) <= max_age

    def on_public_reachability_change(
        self,
        callback: Callable[[bool], Awaitable[None] | None],
    ) -> None:
        """Register a callback for public reachability transitions."""
        self._public_reachability_handlers.append(callback)

    def has_route_to_peer(self, node_id: str) -> bool:
        """True when this node can currently reach *node_id* directly or via relay."""
        if node_id in self._connections or node_id in self._virtual_connections:
            return True
        return any(relay_id in self._connections for relay_id in self._relay_routes.get(node_id, []))

    def set_chain_accessors(
        self,
        chain_height_provider: Callable[[], Awaitable[int] | int] | None = None,
        blocks_provider: Callable[[int, int], Awaitable[list[Any]] | list[Any]] | None = None,
    ) -> None:
        """Register blockchain accessors used by the P2P protocol."""
        self._chain_height_provider = chain_height_provider
        self._blocks_provider = blocks_provider

    def register_contact_card(
        self,
        node_id: str,
        *,
        transports: list[str] | None = None,
        relay_hints: list[str] | None = None,
        capabilities: dict[str, Any] | None = None,
    ) -> None:
        """Register contact-card metadata learned from the chain or a relayed message."""
        node_id = str(node_id).strip()
        if not node_id or node_id == self._node_id:
            return
        if transports is not None:
            merged_transports = list(self._peer_transports.get(node_id, []))
            for transport in transports:
                transport_str = str(transport).strip()
                if transport_str and transport_str not in merged_transports:
                    merged_transports.append(transport_str)
            self._peer_transports[node_id] = merged_transports
        elif node_id not in self._peer_transports:
            self._peer_transports[node_id] = []

        if relay_hints is not None:
            merged_relays = list(self._relay_routes.get(node_id, []))
            for relay_id in relay_hints:
                relay_id_str = str(relay_id).strip()
                if relay_id_str and relay_id_str != node_id and relay_id_str not in merged_relays:
                    merged_relays.append(relay_id_str)
            self._relay_routes[node_id] = merged_relays
        elif node_id not in self._relay_routes:
            self._relay_routes[node_id] = []

        if capabilities is not None:
            merged_capabilities = dict(self._peer_capabilities.get(node_id, {}))
            merged_capabilities.update(dict(capabilities))
            self._peer_capabilities[node_id] = merged_capabilities
        elif node_id not in self._peer_capabilities:
            self._peer_capabilities[node_id] = {}

    def register_virtual_connection(
        self,
        node_id: str,
        *,
        transport: str,
        send_func: Callable[[Message], Awaitable[None] | None],
    ) -> None:
        """Register a non-TCP connection, such as a WebRTC data channel."""
        node_id = str(node_id).strip()
        transport = str(transport).strip()
        if not node_id or not transport or node_id == self._node_id:
            return

        self._virtual_connections[node_id] = (transport, send_func)

        existing = self._peer_manager.get_peer(node_id)
        if existing is None:
            self._peer_manager.add_peer(
                PeerInfo(
                    node_id=node_id,
                    address="",
                    port=0,
                    last_seen=time.time(),
                    status="active",
                    chain_height=0,
                    transports=[transport],
                )
            )
        else:
            transports = list(existing.transports or [])
            if transport not in transports:
                transports.append(transport)
            self._peer_manager.update_peer(
                node_id,
                last_seen=time.time(),
                status="active",
                transports=transports,
            )
        self.register_contact_card(node_id, transports=[transport])

    def unregister_virtual_connection(self, node_id: str, *, transport: str | None = None) -> None:
        """Remove a previously registered non-TCP connection."""
        existing = self._virtual_connections.get(node_id)
        if existing is None:
            return
        current_transport, _ = existing
        if transport is not None and current_transport != transport:
            return
        self._virtual_connections.pop(node_id, None)

        peer = self._peer_manager.get_peer(node_id)
        if peer is None:
            return

        transports = [item for item in peer.transports if item != current_transport]
        self._peer_manager.update_peer(node_id, transports=transports)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start accepting TCP connections."""
        if self._running:
            return
        self._running = True
        self._server = await asyncio.start_server(
            self._handle_inbound, self._host, self._port
        )
        addrs = [str(s.getsockname()) for s in self._server.sockets]
        logger.info("P2P server listening on %s", ", ".join(addrs))

    async def stop(self) -> None:
        """Gracefully close all connections and stop the server."""
        self._running = False

        # Close all peer connections.
        for nid, (_, writer) in list(self._connections.items()):
            try:
                writer.close()
                await writer.wait_closed()
            except OSError:
                pass
        self._connections.clear()
        self._virtual_connections.clear()
        self._relay_routes.clear()
        self._peer_capabilities.clear()
        self._peer_transports.clear()

        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        logger.info("P2P server stopped")

    # ------------------------------------------------------------------
    # Outbound connections
    # ------------------------------------------------------------------

    async def connect_to_peer(self, address: str, port: int) -> bool:
        """Initiate an outbound connection to a peer.

        Performs the HELLO handshake.  Returns True on success.
        """
        if self._security.is_banned(address):
            logger.debug("Skipping banned peer %s", address)
            return False

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(address, port), timeout=10.0
            )
        except (OSError, asyncio.TimeoutError) as exc:
            logger.debug("Failed to connect to %s:%d -- %s", address, port, exc)
            return False

        self._security.record_connection(address)

        # Send HELLO.
        chain_height = await self._get_chain_height()
        hello = Message.hello(
            self._node_id,
            chain_height,
            self._port,
            private_key=self._private_key,
        )
        try:
            await self._write_message(writer, hello)
        except OSError as exc:
            logger.debug("Failed to send HELLO to %s:%d -- %s", address, port, exc)
            writer.close()
            return False

        # Await HELLO_ACK.
        try:
            ack = await asyncio.wait_for(self._read_message(reader), timeout=10.0)
        except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, Exception) as exc:
            logger.debug("No HELLO_ACK from %s:%d -- %s", address, port, exc)
            writer.close()
            return False

        if (
            ack is None
            or ack.msg_type != MessageType.HELLO_ACK
            or not ack.verify_handshake_identity()
        ):
            logger.debug("Invalid handshake response from %s:%d", address, port)
            writer.close()
            return False

        peer_id = ack.sender_id
        if peer_id == self._node_id:
            logger.debug("Peer %s:%d echoed local node identity", address, port)
            writer.close()
            return False

        try:
            peer_chain_height = int(ack.payload.get("chain_height", 0))
            peer_listen_port = int(ack.payload.get("listen_port", port) or port)
        except (TypeError, ValueError):
            logger.debug("Peer %s:%d sent invalid handshake metadata", address, port)
            writer.close()
            return False

        # Track the connection.
        self._connections[peer_id] = (reader, writer)
        self._peer_manager.add_peer(
            PeerInfo(
                node_id=peer_id,
                address=address,
                port=peer_listen_port,
                last_seen=time.time(),
                status="active",
                chain_height=peer_chain_height,
                transports=["tcp"],
            )
        )
        self.register_contact_card(peer_id, transports=["tcp"])

        # Start reading from this peer in the background.
        asyncio.create_task(self._read_loop(peer_id, reader, writer))
        logger.info("Connected to peer %s (%s:%d)", peer_id[:16], address, port)
        return True

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    async def broadcast_message(self, message: Message) -> None:
        """Send *message* to every connected peer."""
        disconnected: list[str] = []
        for nid, (_, writer) in list(self._connections.items()):
            try:
                await self._write_message(writer, message)
            except OSError:
                disconnected.append(nid)
        for nid in disconnected:
            self._disconnect_peer(nid)

    async def send_to_peer(self, node_id: str, message: Message) -> None:
        """Send a message to a specific connected peer."""
        conn = self._connections.get(node_id)
        if conn is None:
            virtual_conn = self._virtual_connections.get(node_id)
            if virtual_conn is not None:
                transport_name, send_func = virtual_conn
                try:
                    result = send_func(message)
                    if asyncio.iscoroutine(result):
                        await result
                    return
                except OSError:
                    self.unregister_virtual_connection(node_id, transport=transport_name)

            for relay_id in self._relay_routes.get(node_id, []):
                relay_conn = self._connections.get(relay_id)
                if relay_conn is None:
                    continue
                _, relay_writer = relay_conn
                try:
                    await self._write_message(
                        relay_writer,
                        Message.relay_envelope(
                            self._node_id,
                            node_id,
                            message.to_dict(),
                        ),
                    )
                    return
                except OSError:
                    self._disconnect_peer(relay_id)

            logger.debug("Cannot send to %s -- not connected and no active relay route", node_id[:16])
            return
        _, writer = conn
        try:
            await self._write_message(writer, message)
        except OSError:
            self._disconnect_peer(node_id)

    def on_message(
        self, callback: Callable[[Message, str], Awaitable[None] | None]
    ) -> None:
        """Register a handler called for every received message.

        The callback receives ``(message, peer_node_id)``.
        """
        self._message_handlers.append(callback)

    async def _dispatch_public_reachability_change(self, reachable: bool) -> None:
        """Notify listeners that public reachability changed."""
        for handler in self._public_reachability_handlers:
            try:
                result = handler(reachable)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception("Error in public reachability handler")

    async def _record_public_inbound(self, remote_ip: str) -> None:
        """Record an inbound connection from a public IP and emit transitions."""
        if not self._is_public_ip(remote_ip):
            return

        was_public = self.has_recent_public_inbound()
        self._last_public_inbound_at = time.time()
        if not was_public:
            await self._dispatch_public_reachability_change(True)

    # ------------------------------------------------------------------
    # Internal: inbound handling
    # ------------------------------------------------------------------

    async def _handle_inbound(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle a new inbound TCP connection."""
        peername = writer.get_extra_info("peername")
        remote_ip = peername[0] if peername else "unknown"

        if self._security.is_banned(remote_ip):
            logger.debug("Rejected banned IP %s", remote_ip)
            writer.close()
            return

        if not self._security.check_rate_limit(remote_ip, max_per_minute=30):
            logger.warning("Rate-limited inbound connection from %s", remote_ip)
            writer.close()
            return

        # Connection diversity check — prevent single-subnet dominance
        if not self._security.check_connection_diversity(remote_ip):
            logger.warning("Rejected for subnet diversity from %s", remote_ip)
            writer.close()
            return

        self._security.record_connection(remote_ip)

        # Expect HELLO as first message.
        try:
            hello = await asyncio.wait_for(self._read_message(reader), timeout=10.0)
        except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, Exception):
            writer.close()
            return

        if (
            hello is None
            or hello.msg_type != MessageType.HELLO
            or not hello.verify_handshake_identity()
        ):
            writer.close()
            return

        peer_id = hello.sender_id
        if peer_id == self._node_id:
            writer.close()
            return

        try:
            peer_chain_height = int(hello.payload.get("chain_height", 0))
            peer_listen_port = int(hello.payload.get("listen_port", 0))
        except (TypeError, ValueError):
            writer.close()
            return

        # Reply with HELLO_ACK.
        chain_height = await self._get_chain_height()
        ack = Message.hello_ack(
            self._node_id,
            chain_height,
            listen_port=self._port,
            private_key=self._private_key,
        )
        try:
            await self._write_message(writer, ack)
        except OSError:
            writer.close()
            return

        self._connections[peer_id] = (reader, writer)
        self._peer_manager.add_peer(
            PeerInfo(
                node_id=peer_id,
                address=remote_ip,
                port=peer_listen_port or 0,
                last_seen=time.time(),
                status="active",
                chain_height=peer_chain_height,
                transports=["tcp"],
            )
        )
        self.register_contact_card(peer_id, transports=["tcp"])
        await self._record_public_inbound(remote_ip)

        logger.info("Inbound peer %s from %s", peer_id[:16], remote_ip)
        asyncio.create_task(self._read_loop(peer_id, reader, writer))

    # ------------------------------------------------------------------
    # Internal: message I/O
    # ------------------------------------------------------------------

    async def _read_message(self, reader: asyncio.StreamReader) -> Message | None:
        """Read a single length-prefixed msgpack message from the stream."""
        length_data = await reader.readexactly(LENGTH_PREFIX_SIZE)
        (length,) = struct.unpack(LENGTH_PREFIX_FMT, length_data)
        if length > MAX_MESSAGE_SIZE:
            raise ValueError(f"Message too large: {length} bytes")
        body = await reader.readexactly(length)
        return Message.deserialize(body)

    @staticmethod
    async def _write_message(writer: asyncio.StreamWriter, message: Message) -> None:
        """Write a length-prefixed msgpack message to the stream."""
        writer.write(message.serialize())
        await writer.drain()

    async def _read_loop(
        self,
        peer_id: str,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Continuously read messages from a peer until disconnect."""
        try:
            while self._running:
                try:
                    msg = await asyncio.wait_for(self._read_message(reader), timeout=120.0)
                except asyncio.TimeoutError:
                    # Send a PING to check liveness.
                    try:
                        await self._write_message(writer, Message.ping(self._node_id))
                    except OSError:
                        break
                    continue

                if msg is None:
                    break

                if msg.msg_type == MessageType.RELAY_ENVELOPE:
                    await self._handle_relay_envelope(msg, peer_id)
                    continue

                await self._dispatch_message(msg, peer_id)

        except (OSError, asyncio.IncompleteReadError, ValueError) as exc:
            logger.debug("Peer %s read error: %s", peer_id[:16], exc)
        finally:
            self._disconnect_peer(peer_id)

    async def _handle_builtin(self, msg: Message, peer_id: str) -> None:
        """Handle protocol-level messages (PING/PONG, GET_PEERS)."""
        if msg.msg_type == MessageType.PING:
            pong = Message.pong(self._node_id)
            await self.send_to_peer(peer_id, pong)

        elif msg.msg_type == MessageType.PONG:
            self._peer_manager.update_peer(peer_id, last_seen=time.time(), status="active")

        elif msg.msg_type == MessageType.GET_PEERS:
            peers_msg = Message.peers(self._node_id, self._peer_manager.to_list())
            await self.send_to_peer(peer_id, peers_msg)

        elif msg.msg_type == MessageType.GET_BLOCKS:
            start = int(msg.payload.get("start", 0))
            end = int(msg.payload.get("end", -1))
            blocks = await self._get_blocks_payload(start, end)
            await self.send_to_peer(peer_id, Message.blocks(self._node_id, blocks))

    async def _dispatch_message(self, msg: Message, peer_id: str) -> None:
        """Run built-in handlers then fan out to application handlers."""
        self._peer_manager.update_peer(peer_id, last_seen=time.time(), status="active")
        await self._handle_builtin(msg, peer_id)

        for handler in self._message_handlers:
            try:
                result = handler(msg, peer_id)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception("Error in message handler")

    async def _handle_relay_envelope(self, msg: Message, relay_peer_id: str) -> None:
        """Deliver or forward a relayed message."""
        target_id = str(msg.payload.get("target_id", "")).strip()
        inner_raw = msg.payload.get("message")
        if not target_id or not isinstance(inner_raw, dict):
            return

        if target_id != self._node_id:
            conn = self._connections.get(target_id)
            if conn is None:
                logger.debug(
                    "Dropping relayed message for %s from relay %s: target not connected",
                    target_id[:16],
                    relay_peer_id[:16],
                )
                return
            _, writer = conn
            try:
                await self._write_message(writer, msg)
            except OSError:
                self._disconnect_peer(target_id)
            return

        try:
            inner = Message.from_dict(inner_raw)
        except (KeyError, ValueError, TypeError):
            logger.debug("Dropping malformed relayed message from %s", relay_peer_id[:16])
            return

        sender_id = inner.sender_id
        if sender_id and sender_id != self._node_id:
            self.register_contact_card(sender_id, transports=["relay"], relay_hints=[relay_peer_id])
            existing = self._peer_manager.get_peer(sender_id)
            if existing is not None:
                transports = list(existing.transports or [])
                if "relay" not in transports:
                    transports.append("relay")
                relay_hints = list(existing.relay_hints or [])
                if relay_peer_id not in relay_hints:
                    relay_hints.append(relay_peer_id)
                self._peer_manager.update_peer(
                    sender_id,
                    last_seen=time.time(),
                    status="active",
                    transports=transports,
                    relay_hints=relay_hints,
                )
            else:
                self._peer_manager.add_peer(
                    PeerInfo(
                        node_id=sender_id,
                        address="",
                        port=0,
                        last_seen=time.time(),
                        status="active",
                        chain_height=0,
                        transports=["relay"],
                        relay_hints=[relay_peer_id],
                    )
                )

        await self._dispatch_message(inner, sender_id or relay_peer_id)

    async def inject_message(self, peer_id: str, message: Message, *, transport: str = "virtual") -> None:
        """Inject a message received from a non-TCP transport into normal dispatch."""
        peer_id = str(peer_id).strip()
        if not peer_id:
            return
        self.register_contact_card(peer_id, transports=[transport])
        self._peer_manager.update_peer(peer_id, last_seen=time.time(), status="active")
        await self._dispatch_message(message, peer_id)

    # ------------------------------------------------------------------
    # Internal: helpers
    # ------------------------------------------------------------------

    def _disconnect_peer(self, node_id: str) -> None:
        """Close and unregister a peer connection."""
        conn = self._connections.pop(node_id, None)
        if conn is not None:
            _, writer = conn
            try:
                writer.close()
            except OSError:
                pass
        self._peer_manager.update_peer(node_id, status="dead")
        logger.info("Disconnected peer %s", node_id[:16])

    async def _get_chain_height(self) -> int:
        """Return the current chain height for handshakes."""
        if self._chain_height_provider is None:
            return 0

        try:
            height = self._chain_height_provider()
            if inspect.isawaitable(height):
                height = await height
            return int(height)
        except Exception:
            logger.exception("Failed to obtain local chain height")
            return 0

    async def _get_blocks_payload(self, start: int, end: int) -> list[dict[str, Any]]:
        """Return serialized blocks for the requested inclusive range."""
        if self._blocks_provider is None or end < start:
            return []

        try:
            blocks = self._blocks_provider(start, end)
            if inspect.isawaitable(blocks):
                blocks = await blocks
        except Exception:
            logger.exception("Failed to obtain block range %d-%d", start, end)
            return []

        payload: list[dict[str, Any]] = []
        for block in blocks or []:
            if isinstance(block, dict):
                payload.append(block)
            elif hasattr(block, "to_dict"):
                payload.append(block.to_dict())
        return payload
