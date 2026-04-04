"""Helpers for building and signing mobile pairing payloads."""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import time
from typing import Any

from genesis.utils.crypto import sign


PAIRING_VERSION = 1


def canonical_json(data: dict[str, Any]) -> str:
    """Return a deterministic JSON representation for signing and encoding."""
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sign_mobile_payload(payload: dict[str, Any], private_key: bytes) -> str:
    """Sign a payload excluding its existing signature field."""
    body = {key: value for key, value in payload.items() if key != "signature"}
    return sign(private_key, canonical_json(body).encode("utf-8")).hex()


def build_pairing_payload(
    *,
    gs_node_id: str,
    world_id: str,
    bind_token: str,
    session_pubkey: str,
    chain_height: int,
    bootstrap_peers: list[dict[str, Any]],
    relay_hints: list[dict[str, Any]] | None = None,
    private_key: bytes,
    issued_at: int | None = None,
    expires_at: int | None = None,
) -> dict[str, Any]:
    """Build a signed pairing payload for the Android bootstrap QR."""
    now = int(issued_at or time.time())
    expires = int(expires_at or (now + 600))
    payload: dict[str, Any] = {
        "version": PAIRING_VERSION,
        "gs_node_id": str(gs_node_id).strip(),
        "world_id": str(world_id).strip(),
        "bind_token": str(bind_token).strip(),
        "issued_at": now,
        "expires_at": max(now, expires),
        "session_pubkey": str(session_pubkey).strip(),
        "bootstrap_peers": [dict(item) for item in bootstrap_peers[:8] if isinstance(item, dict)],
        "relay_hints": [dict(item) for item in (relay_hints or [])[:8] if isinstance(item, dict)],
        "chain_height": max(0, int(chain_height or 0)),
    }
    payload["signature"] = sign_mobile_payload(payload, private_key)
    return payload


def encode_pairing_payload(payload: dict[str, Any]) -> str:
    """Encode the signed pairing payload for QR transport."""
    encoded = base64.urlsafe_b64encode(canonical_json(payload).encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def build_pairing_qr_text(payload: dict[str, Any]) -> str:
    """Return the compact URI encoded into a QR code."""
    return f"genesis://pair?data={encode_pairing_payload(payload)}"


def render_pairing_qr(qr_text: str) -> str:
    """Render an ANSI QR code when the host provides qrencode, else return empty."""
    if not qr_text:
        return ""
    if shutil.which("qrencode") is None:
        return ""
    try:
        result = subprocess.run(
            ["qrencode", "-t", "ANSIUTF8", qr_text],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()
