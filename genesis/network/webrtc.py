"""Optional WebRTC signaling and DataChannel transport integration."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from genesis.network.protocol import Message

logger = logging.getLogger(__name__)
_DEFAULT_STUN_SERVERS = ["stun:stun.l.google.com:19302"]


def _load_aiortc_backend() -> dict[str, Any] | None:
    """Load aiortc lazily so the core node still works without the dependency."""
    try:
        from aiortc import (
            RTCPeerConnection,
            RTCSessionDescription,
            RTCIceCandidate,
            RTCConfiguration,
            RTCIceServer,
        )
    except Exception:
        return None

    return {
        "RTCPeerConnection": RTCPeerConnection,
        "RTCSessionDescription": RTCSessionDescription,
        "RTCIceCandidate": RTCIceCandidate,
        "RTCConfiguration": RTCConfiguration,
        "RTCIceServer": RTCIceServer,
    }


def _normalize_timeout(value: Any, *, default: int, minimum: int) -> int:
    try:
        parsed = int(value if value is not None else default)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _normalize_urls(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, (list, tuple, set)):
        items = list(raw)
    else:
        return []

    normalized: list[str] = []
    for item in items:
        value = str(item).strip()
        if value and value not in normalized:
            normalized.append(value)
    return normalized


@dataclass
class WebRTCSession:
    """Bookkeeping for one peer-to-peer WebRTC negotiation."""

    session_id: str
    peer_id: str
    role: str
    connection: Any
    state: str = "new"
    last_signal_type: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    transport_ready: bool = False
    channel: Any | None = None


class WebRTCSessionManager:
    """Negotiate optional direct DataChannel transports over existing routes."""

    def __init__(
        self,
        node_id: str,
        server: Any,
        *,
        enabled: bool = True,
        stun_servers: list[str] | None = None,
        turn_servers: list[dict[str, Any]] | None = None,
        offer_timeout: int = 20,
        session_ttl: int = 300,
    ) -> None:
        self._node_id = node_id
        self._server = server
        self._enabled = bool(enabled)
        self._backend = _load_aiortc_backend() if self._enabled else None
        self._sessions: dict[str, WebRTCSession] = {}
        self._peer_sessions: dict[str, str] = {}
        self._offer_timeout = _normalize_timeout(offer_timeout, default=20, minimum=5)
        self._session_ttl = max(
            self._offer_timeout,
            _normalize_timeout(session_ttl, default=300, minimum=30),
        )
        default_stun = _DEFAULT_STUN_SERVERS if stun_servers is None else stun_servers
        self._stun_servers = _normalize_urls(default_stun)
        self._turn_servers = self._normalize_turn_servers(turn_servers)

    @property
    def available(self) -> bool:
        return self._enabled and self._backend is not None

    def advertised_transports(self, base: list[str] | None = None) -> list[str]:
        """Return transport names suitable for publishing in the on-chain contact card."""
        transports: list[str] = []
        for item in base or []:
            item_str = str(item).strip()
            if item_str and item_str not in transports:
                transports.append(item_str)
        if self.available and "webrtc" not in transports:
            transports.append("webrtc")
        return transports

    def session_snapshot(self) -> list[dict[str, Any]]:
        """Return a compact view for debugging and tests."""
        return [
            {
                "session_id": record.session_id,
                "peer_id": record.peer_id,
                "role": record.role,
                "state": record.state,
                "last_signal_type": record.last_signal_type,
                "transport_ready": record.transport_ready,
            }
            for record in self._sessions.values()
        ]

    async def ensure_session(self, peer_id: str) -> bool:
        """Initiate a WebRTC session to *peer_id* if no active session exists."""
        await self._expire_stale_sessions()
        if not self.available:
            return False
        if not self._server.has_route_to_peer(peer_id):
            return False

        existing = self._peer_sessions.get(peer_id)
        if existing:
            record = self._sessions.get(existing)
            if record and record.state not in {"closed", "failed"}:
                return True

        record = await self._create_session(peer_id, role="offerer")
        try:
            channel = record.connection.createDataChannel("genesis")
        except Exception as exc:
            logger.debug("Failed to create WebRTC data channel for %s: %s", peer_id[:16], exc)
            await self._close_session(record.session_id)
            return False

        self._configure_data_channel(record, channel)

        offer = await record.connection.createOffer()
        await record.connection.setLocalDescription(offer)
        record.state = "offer-sent"
        record.last_signal_type = "offer"
        record.updated_at = time.time()
        await self._send_signal(
            peer_id,
            "offer",
            record.session_id,
            self._serialize_description(record.connection.localDescription),
        )
        return True

    async def handle_signal(self, peer_id: str, payload: dict[str, Any]) -> bool:
        """Process a received ``WEBRTC_SIGNAL`` message."""
        await self._expire_stale_sessions()
        if not self.available:
            return False

        target_id = str(payload.get("target_id", "")).strip()
        if target_id and target_id != self._node_id:
            return False

        signal_type = str(payload.get("signal_type", "")).strip()
        session_id = str(payload.get("session_id", "")).strip()
        signal = payload.get("signal")
        if not signal_type or not session_id or not isinstance(signal, dict):
            return False

        record = self._sessions.get(session_id)
        if record is None:
            if signal_type != "offer":
                return False
            record = await self._create_session(peer_id, session_id=session_id, role="answerer")

        if record.peer_id != peer_id:
            return False

        record.last_signal_type = signal_type
        record.updated_at = time.time()

        if signal_type == "offer":
            description = self._make_session_description(signal)
            await record.connection.setRemoteDescription(description)
            answer = await record.connection.createAnswer()
            await record.connection.setLocalDescription(answer)
            record.state = "answer-sent"
            await self._send_signal(
                peer_id,
                "answer",
                session_id,
                self._serialize_description(record.connection.localDescription),
            )
            return True

        if signal_type == "answer":
            description = self._make_session_description(signal)
            await record.connection.setRemoteDescription(description)
            record.state = "connecting"
            return True

        if signal_type == "ice-candidate":
            candidate = self._make_ice_candidate(signal)
            if candidate is not None:
                await record.connection.addIceCandidate(candidate)
            return True

        return False

    async def close(self) -> None:
        """Close all active peer connections."""
        for session_id in list(self._sessions.keys()):
            await self._close_session(session_id)

    @staticmethod
    def _normalize_turn_servers(turn_servers: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for entry in turn_servers or []:
            if not isinstance(entry, dict):
                continue
            urls = _normalize_urls(entry.get("urls") or entry.get("url"))
            if not urls:
                continue
            item: dict[str, Any] = {"urls": urls if len(urls) > 1 else urls[0]}
            username = str(entry.get("username", "") or "").strip()
            credential = str(entry.get("credential", "") or "")
            credential_type = str(
                entry.get("credential_type", "")
                or entry.get("credentialType", "")
                or ""
            ).strip()
            if username:
                item["username"] = username
            if credential:
                item["credential"] = credential
            if credential_type:
                item["credentialType"] = credential_type
            normalized.append(item)
        return normalized

    def _create_peer_connection(self) -> Any:
        backend = self._backend
        if backend is None:
            raise RuntimeError("WebRTC backend unavailable")

        connection_cls = backend["RTCPeerConnection"]
        configuration = self._build_rtc_configuration()
        if configuration is None:
            return connection_cls()
        try:
            return connection_cls(configuration=configuration)
        except TypeError:
            try:
                return connection_cls(configuration)
            except TypeError:
                return connection_cls()

    def _build_rtc_configuration(self) -> Any | None:
        backend = self._backend
        if backend is None:
            return None
        rtc_configuration_cls = backend.get("RTCConfiguration")
        if backend.get("RTCIceServer") is None or rtc_configuration_cls is None:
            return None

        ice_servers: list[Any] = []
        for stun_url in self._stun_servers:
            server = self._create_ice_server(stun_url)
            if server is not None:
                ice_servers.append(server)
        for turn_server in self._turn_servers:
            server = self._create_ice_server(**turn_server)
            if server is not None:
                ice_servers.append(server)
        if not ice_servers:
            return None

        try:
            return rtc_configuration_cls(iceServers=ice_servers)
        except TypeError:
            try:
                return rtc_configuration_cls(ice_servers)
            except TypeError:
                logger.debug("RTCConfiguration constructor rejected ICE servers", exc_info=True)
                return None

    def _create_ice_server(self, urls: str | list[str], **kwargs: Any) -> Any | None:
        backend = self._backend
        if backend is None:
            return None
        ice_server_cls = backend.get("RTCIceServer")
        if ice_server_cls is None:
            return None

        try:
            return ice_server_cls(urls=urls, **kwargs)
        except TypeError:
            try:
                return ice_server_cls(urls, **kwargs)
            except TypeError:
                logger.debug("RTCIceServer constructor rejected ICE config for %s", urls, exc_info=True)
                return None

    async def _create_session(
        self,
        peer_id: str,
        *,
        session_id: str | None = None,
        role: str,
    ) -> WebRTCSession:
        backend = self._backend
        if backend is None:
            raise RuntimeError("WebRTC backend unavailable")

        connection = self._create_peer_connection()
        record = WebRTCSession(
            session_id=session_id or uuid.uuid4().hex,
            peer_id=peer_id,
            role=role,
            connection=connection,
        )
        self._sessions[record.session_id] = record
        self._peer_sessions[peer_id] = record.session_id
        self._bind_connection_events(record)
        return record

    def _bind_connection_events(self, record: WebRTCSession) -> None:
        connection = record.connection
        if not hasattr(connection, "on"):
            return

        @connection.on("icecandidate")
        async def on_icecandidate(candidate: Any) -> None:
            if candidate is None:
                return
            record.updated_at = time.time()
            await self._send_signal(
                record.peer_id,
                "ice-candidate",
                record.session_id,
                self._serialize_candidate(candidate),
            )

        @connection.on("connectionstatechange")
        async def on_connectionstatechange() -> None:
            state = str(getattr(connection, "connectionState", "unknown"))
            record.state = state
            record.updated_at = time.time()
            if state in {"closed", "failed", "disconnected"}:
                await self._close_session(record.session_id)

        @connection.on("datachannel")
        def on_datachannel(channel: Any) -> None:
            self._configure_data_channel(record, channel)

    def _configure_data_channel(self, record: WebRTCSession, channel: Any) -> None:
        record.channel = channel
        if not hasattr(channel, "on"):
            return

        @channel.on("open")
        def on_open() -> None:
            record.transport_ready = True
            record.state = "connected"
            record.updated_at = time.time()
            self._server.register_virtual_connection(
                record.peer_id,
                transport="webrtc",
                send_func=lambda message: self._send_over_channel(channel, message),
            )

        @channel.on("message")
        def on_message(data: Any) -> None:
            asyncio.create_task(self._handle_channel_message(record.peer_id, data))

        @channel.on("close")
        def on_close() -> None:
            record.transport_ready = False
            record.state = "closed"
            record.updated_at = time.time()
            self._server.unregister_virtual_connection(record.peer_id, transport="webrtc")

    async def _handle_channel_message(self, peer_id: str, data: Any) -> None:
        if isinstance(data, str):
            raw = data.encode("utf-8")
        elif isinstance(data, (bytes, bytearray)):
            raw = bytes(data)
        else:
            return

        try:
            message = Message.deserialize(raw)
        except Exception as exc:
            logger.debug("Invalid WebRTC message from %s: %s", peer_id[:16], exc)
            return

        await self._server.inject_message(peer_id, message, transport="webrtc")

    async def _send_over_channel(self, channel: Any, message: Message) -> None:
        payload = message.serialize_body()
        result = channel.send(payload)
        if asyncio.iscoroutine(result):
            await result

    async def _send_signal(
        self,
        peer_id: str,
        signal_type: str,
        session_id: str,
        signal: dict[str, Any],
    ) -> None:
        message = Message.webrtc_signal(
            self._node_id,
            peer_id,
            signal_type,
            session_id,
            signal,
        )
        await self._server.send_to_peer(peer_id, message)

    @staticmethod
    def _serialize_description(description: Any) -> dict[str, Any]:
        return {
            "type": str(getattr(description, "type", "") or ""),
            "sdp": str(getattr(description, "sdp", "") or ""),
        }

    def _make_session_description(self, payload: dict[str, Any]) -> Any:
        backend = self._backend
        if backend is None:
            raise RuntimeError("WebRTC backend unavailable")
        return backend["RTCSessionDescription"](
            sdp=str(payload.get("sdp", "") or ""),
            type=str(payload.get("type", "") or ""),
        )

    @staticmethod
    def _serialize_candidate(candidate: Any) -> dict[str, Any]:
        return {
            "component": getattr(candidate, "component", 1),
            "foundation": str(getattr(candidate, "foundation", "") or ""),
            "ip": str(
                getattr(candidate, "ip", "")
                or getattr(candidate, "address", "")
                or ""
            ),
            "port": int(getattr(candidate, "port", 0) or 0),
            "priority": int(getattr(candidate, "priority", 0) or 0),
            "protocol": str(getattr(candidate, "protocol", "") or ""),
            "type": str(getattr(candidate, "type", "") or ""),
            "relatedAddress": getattr(candidate, "relatedAddress", None),
            "relatedPort": getattr(candidate, "relatedPort", None),
            "sdpMid": getattr(candidate, "sdpMid", None),
            "sdpMLineIndex": getattr(candidate, "sdpMLineIndex", None),
            "tcpType": getattr(candidate, "tcpType", None),
        }

    def _make_ice_candidate(self, payload: dict[str, Any]) -> Any | None:
        backend = self._backend
        if backend is None:
            raise RuntimeError("WebRTC backend unavailable")

        ip = str(payload.get("ip", "") or "")
        port = int(payload.get("port", 0) or 0)
        protocol = str(payload.get("protocol", "") or "")
        candidate_type = str(payload.get("type", "") or "")
        if not ip or port <= 0 or not protocol or not candidate_type:
            return None

        return backend["RTCIceCandidate"](
            component=int(payload.get("component", 1) or 1),
            foundation=str(payload.get("foundation", "") or ""),
            ip=ip,
            port=port,
            priority=int(payload.get("priority", 0) or 0),
            protocol=protocol,
            type=candidate_type,
            relatedAddress=payload.get("relatedAddress"),
            relatedPort=payload.get("relatedPort"),
            sdpMid=payload.get("sdpMid"),
            sdpMLineIndex=payload.get("sdpMLineIndex"),
            tcpType=payload.get("tcpType"),
        )

    async def _expire_stale_sessions(self) -> None:
        now = time.time()
        stale_ids: list[str] = []
        for record in list(self._sessions.values()):
            if record.state in {"closed", "failed"}:
                stale_ids.append(record.session_id)
                continue
            if record.transport_ready:
                continue
            if record.state in {"offer-sent", "answer-sent", "connecting"}:
                if (now - record.updated_at) > self._offer_timeout:
                    stale_ids.append(record.session_id)
                    continue
            if (now - record.created_at) > self._session_ttl:
                stale_ids.append(record.session_id)

        for session_id in stale_ids:
            await self._close_session(session_id)

    async def _close_session(self, session_id: str) -> None:
        record = self._sessions.pop(session_id, None)
        if record is None:
            return
        if self._peer_sessions.get(record.peer_id) == session_id:
            self._peer_sessions.pop(record.peer_id, None)
        self._server.unregister_virtual_connection(record.peer_id, transport="webrtc")
        try:
            result = record.connection.close()
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            logger.debug("WebRTC close failed for %s", record.peer_id[:16], exc_info=True)
