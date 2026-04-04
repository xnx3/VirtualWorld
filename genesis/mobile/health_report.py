"""Helpers for public peer health-report payload generation."""

from __future__ import annotations

import time
from typing import Any

from genesis.utils.crypto import sha256


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_peer_health_report(
    *,
    observer_node_id: str,
    subject_node_id: str,
    world_id: str,
    transport: str,
    reachable: bool,
    success_count: int,
    failure_count: int,
    chain_height_seen: int,
    relay_success: bool,
    light_sync_success: bool,
    confidence: float = 0.5,
    ttl: int = 900,
    latency_band: int = 0,
    window_start: int | None = None,
    window_end: int | None = None,
) -> dict[str, Any]:
    """Build a normalized PEER_HEALTH_REPORT payload."""
    end_time = max(0, _safe_int(window_end, int(time.time())))
    start_time = max(0, _safe_int(window_start, end_time - 300))
    if start_time > end_time:
        start_time = end_time
    transport_value = str(transport or "tcp").strip() or "tcp"
    report_id = sha256(
        f"{observer_node_id}:{subject_node_id}:{start_time}:{end_time}:{transport_value}".encode("utf-8")
    )[:24]
    return {
        "report_id": report_id,
        "subject_node_id": str(subject_node_id).strip(),
        "world_id": str(world_id).strip(),
        "window_start": start_time,
        "window_end": end_time,
        "reachable": bool(reachable),
        "success_count": max(0, _safe_int(success_count, 0)),
        "failure_count": max(0, _safe_int(failure_count, 0)),
        "latency_band": max(0, min(4, _safe_int(latency_band, 0))),
        "chain_height_seen": max(0, _safe_int(chain_height_seen, 0)),
        "relay_success": bool(relay_success),
        "light_sync_success": bool(light_sync_success),
        "transport": transport_value[:64],
        "confidence": round(max(0.0, min(1.0, _safe_float(confidence, 0.5))), 4),
        "ttl": max(60, _safe_int(ttl, 900)),
        "observer_node_id": str(observer_node_id).strip(),
    }
