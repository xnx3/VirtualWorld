from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from genesis.network.protocol import Message, MessageType
from genesis.network.webrtc import WebRTCSessionManager


class _FakeDescription:
    def __init__(self, sdp: str, type: str) -> None:
        self.sdp = sdp
        self.type = type


class _FakeIceCandidate:
    def __init__(self, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


class _FakeDataChannel:
    def __init__(self) -> None:
        self._handlers = {}
        self.sent = []

    def on(self, event: str):
        def decorator(callback):
            self._handlers[event] = callback
            return callback

        return decorator

    def emit(self, event: str, *args):
        callback = self._handlers.get(event)
        if callback is None:
            return None
        return callback(*args)

    def send(self, data: bytes) -> None:
        self.sent.append(data)


class _FakePeerConnection:
    def __init__(self) -> None:
        self._handlers = {}
        self.localDescription = None
        self.remoteDescription = None
        self.connectionState = "new"
        self.channel = None
        self.candidates = []

    def on(self, event: str):
        def decorator(callback):
            self._handlers[event] = callback
            return callback

        return decorator

    def emit(self, event: str, *args):
        callback = self._handlers.get(event)
        if callback is None:
            return None
        return callback(*args)

    def createDataChannel(self, label: str):
        self.channel = _FakeDataChannel()
        return self.channel

    async def createOffer(self):
        return _FakeDescription("offer-sdp", "offer")

    async def createAnswer(self):
        return _FakeDescription("answer-sdp", "answer")

    async def setLocalDescription(self, description):
        self.localDescription = description

    async def setRemoteDescription(self, description):
        self.remoteDescription = description

    async def addIceCandidate(self, candidate):
        self.candidates.append(candidate)

    async def close(self):
        self.connectionState = "closed"


class _FakeServer:
    def __init__(self) -> None:
        self.routes = set()
        self.sent = []
        self.virtual = []
        self.injected = []

    def has_route_to_peer(self, peer_id: str) -> bool:
        return peer_id in self.routes

    async def send_to_peer(self, peer_id: str, message: Message) -> None:
        self.sent.append((peer_id, message))

    def register_virtual_connection(self, peer_id: str, *, transport: str, send_func) -> None:
        self.virtual.append((peer_id, transport, send_func))

    def unregister_virtual_connection(self, peer_id: str, *, transport: str | None = None) -> None:
        self.virtual = [entry for entry in self.virtual if entry[0] != peer_id]

    async def inject_message(self, peer_id: str, message: Message, *, transport: str = "virtual") -> None:
        self.injected.append((peer_id, message, transport))


class WebRTCManagerTests(unittest.IsolatedAsyncioTestCase):
    def test_manager_without_aiortc_does_not_advertise_webrtc(self):
        manager = WebRTCSessionManager("local-node", _FakeServer())

        self.assertFalse(manager.available)
        self.assertEqual(manager.advertised_transports(["tcp"]), ["tcp"])

    async def test_ensure_session_sends_offer_and_registers_virtual_transport(self):
        backend = {
            "RTCPeerConnection": _FakePeerConnection,
            "RTCSessionDescription": _FakeDescription,
            "RTCIceCandidate": _FakeIceCandidate,
        }
        server = _FakeServer()
        server.routes.add("peer-1")

        with patch("genesis.network.webrtc._load_aiortc_backend", return_value=backend):
            manager = WebRTCSessionManager("local-node", server)

        started = await manager.ensure_session("peer-1")

        self.assertTrue(started)
        self.assertEqual(len(server.sent), 1)
        self.assertEqual(server.sent[0][0], "peer-1")
        self.assertEqual(server.sent[0][1].msg_type, MessageType.WEBRTC_SIGNAL)
        self.assertEqual(server.sent[0][1].payload["signal_type"], "offer")

        record = manager._sessions[manager._peer_sessions["peer-1"]]
        record.channel.emit("open")
        self.assertEqual(server.virtual[0][0], "peer-1")
        await server.virtual[0][2](Message.ping("local-node"))
        self.assertEqual(len(record.channel.sent), 1)

        record.channel.emit("message", Message.ping("peer-1").serialize_body())
        await asyncio.sleep(0)
        self.assertEqual(server.injected[0][0], "peer-1")
        self.assertEqual(server.injected[0][1].msg_type, MessageType.PING)
        self.assertEqual(server.injected[0][2], "webrtc")

    async def test_handle_offer_creates_answer_session(self):
        backend = {
            "RTCPeerConnection": _FakePeerConnection,
            "RTCSessionDescription": _FakeDescription,
            "RTCIceCandidate": _FakeIceCandidate,
        }
        server = _FakeServer()
        server.routes.add("peer-2")

        with patch("genesis.network.webrtc._load_aiortc_backend", return_value=backend):
            manager = WebRTCSessionManager("local-node", server)

        handled = await manager.handle_signal(
            "peer-2",
            {
                "target_id": "local-node",
                "signal_type": "offer",
                "session_id": "session-1",
                "signal": {"type": "offer", "sdp": "remote-offer"},
            },
        )

        self.assertTrue(handled)
        self.assertEqual(len(server.sent), 1)
        self.assertEqual(server.sent[0][1].payload["signal_type"], "answer")
        record = manager._sessions["session-1"]
        self.assertEqual(record.connection.remoteDescription.sdp, "remote-offer")


if __name__ == "__main__":
    unittest.main()
