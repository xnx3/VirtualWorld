"""Helpers for peer contact-card payload generation."""

from __future__ import annotations

import json
from typing import Any


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_strings(values: Any, *, limit: int = 8, exclude: str = "") -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for item in values[:limit]:
        text = str(item or "").strip()
        if not text or text == exclude or text in normalized:
            continue
        normalized.append(text)
    return normalized


def _normalize_capabilities(values: Any) -> dict[str, bool]:
    if not isinstance(values, dict):
        return {}
    return {
        str(key).strip()[:64]: bool(value)
        for key, value in list(values.items())[:16]
        if str(key).strip()
    }


def build_peer_contact_card(
    *,
    node_id: str,
    world_id: str,
    session_pubkey: str,
    endpoint: dict[str, Any],
) -> dict[str, Any]:
    """Build a normalized PEER_CONTACT_CARD payload from a runtime endpoint."""
    address = str(endpoint.get("p2p_address", "") or "").strip()
    port = max(0, _safe_int(endpoint.get("p2p_port", 0), 0))
    updated_at = max(0, _safe_int(endpoint.get("p2p_updated_at", 0), 0))
    ttl = max(60, _safe_int(endpoint.get("p2p_ttl", 600), 600))
    seq = max(0, _safe_int(endpoint.get("p2p_seq", 0), 0))

    transports = _normalize_strings(endpoint.get("p2p_transports"))
    if not transports:
        transports = ["tcp"]

    relay_hints = _normalize_strings(endpoint.get("p2p_relay_hints"), exclude=str(node_id).strip())
    legacy_relay = str(endpoint.get("p2p_relay", "") or "").strip()
    if legacy_relay and legacy_relay not in relay_hints and legacy_relay != str(node_id).strip():
        relay_hints.append(legacy_relay)

    direct_endpoints: list[dict[str, Any]] = []
    if address and 1 <= port <= 65535:
        priority = 100
        for transport in transports:
            if transport == "relay":
                continue
            direct_endpoints.append(
                {
                    "addr": address,
                    "port": port,
                    "transport": transport,
                    "priority": priority,
                }
            )
            priority = max(20, priority - 10)
        if not direct_endpoints:
            direct_endpoints.append(
                {
                    "addr": address,
                    "port": port,
                    "transport": "tcp",
                    "priority": 100,
                }
            )

    return {
        "node_id": str(node_id).strip(),
        "world_id": str(world_id).strip(),
        "session_pubkey": str(session_pubkey).strip(),
        "direct_endpoints": direct_endpoints,
        "relay_hints": relay_hints,
        "transports": transports,
        "capabilities": _normalize_capabilities(endpoint.get("p2p_capabilities")),
        "ttl": ttl,
        "updated_at": updated_at,
        "seq": seq,
    }


def contact_card_runtime_signature(card: dict[str, Any] | None) -> tuple[Any, ...]:
    """Return a deterministic signature tuple for freshness/equality checks."""
    if not isinstance(card, dict):
        return ((), (), (), "", "")
    endpoints = []
    for endpoint in card.get("direct_endpoints", []) or []:
        if not isinstance(endpoint, dict):
            continue
        endpoints.append(
            (
                str(endpoint.get("addr", "") or "").strip(),
                _safe_int(endpoint.get("port", 0), 0),
                str(endpoint.get("transport", "") or "").strip(),
                _safe_int(endpoint.get("priority", 0), 0),
            )
        )
    transports = tuple(_normalize_strings(card.get("transports")))
    relays = tuple(_normalize_strings(card.get("relay_hints"), exclude=str(card.get("node_id", "") or "").strip()))
    capabilities = json.dumps(_normalize_capabilities(card.get("capabilities")), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (
        tuple(endpoints),
        transports,
        relays,
        capabilities,
        str(card.get("world_id", "") or "").strip(),
        str(card.get("session_pubkey", "") or "").strip(),
    )
