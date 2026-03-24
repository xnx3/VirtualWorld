"""Async TCP server and client for the Genesis P2P network."""

from __future__ import annotations

import asyncio
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
        chain_height = self._get_chain_height()
        hello = Message.hello(self._node_id, chain_height, self._port)
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

        if ack is None or ack.msg_type != MessageType.HELLO_ACK:
            logger.debug("Invalid handshake response from %s:%d", address, port)
            writer.close()
            return False

        peer_id = ack.sender_id
        peer_chain_height = ack.payload.get("chain_height", 0)

        # Track the connection.
        self._connections[peer_id] = (reader, writer)
        self._peer_manager.add_peer(
            PeerInfo(
                node_id=peer_id,
                address=address,
                port=port,
                last_seen=time.time(),
                status="active",
                chain_height=peer_chain_height,
            )
        )

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
            logger.debug("Cannot send to %s -- not connected", node_id[:16])
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

        self._security.record_connection(remote_ip)

        # Expect HELLO as first message.
        try:
            hello = await asyncio.wait_for(self._read_message(reader), timeout=10.0)
        except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, Exception):
            writer.close()
            return

        if hello is None or hello.msg_type != MessageType.HELLO:
            writer.close()
            return

        peer_id = hello.sender_id
        peer_chain_height = hello.payload.get("chain_height", 0)
        peer_listen_port = hello.payload.get("listen_port", 0)

        # Reply with HELLO_ACK.
        chain_height = self._get_chain_height()
        ack = Message.hello_ack(self._node_id, chain_height)
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
            )
        )

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

                # Update last_seen.
                self._peer_manager.update_peer(peer_id, last_seen=time.time())

                # Handle built-in message types.
                await self._handle_builtin(msg, peer_id)

                # Fire user callbacks.
                for handler in self._message_handlers:
                    try:
                        result = handler(msg, peer_id)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception:
                        logger.exception("Error in message handler")

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

    def _get_chain_height(self) -> int:
        """Return the current chain height.

        In a full integration this would query the blockchain object.
        For now, returns 0.
        """
        return 0
