"""Helpers for building mobile peer snapshots from chain evidence."""

from __future__ import annotations

import time
from typing import Any

from genesis.mobile.pairing_qr import sign_mobile_payload
from genesis.mobile.peer_scoring import derive_global_score
from genesis.utils.crypto import sha256


def build_snapshot_peers(
    cards: dict[str, dict[str, Any]],
    health_reports: dict[str, list[dict[str, Any]]],
    chain_height: int,
    *,
    now: int | None = None,
    limit: int = 12,
    exclude_node_id: str = "",
) -> list[dict[str, Any]]:
    """Build sorted peer entries for mobile snapshot export."""
    now_value = int(now or time.time())
    entries: list[dict[str, Any]] = []
    for node_id, card in cards.items():
        normalized_id = str(node_id or "").strip()
        if not normalized_id or normalized_id == exclude_node_id:
            continue
        scoring = derive_global_score(card, health_reports.get(normalized_id, []), chain_height, now=now_value)
        entries.append(
            {
                "node_id": normalized_id,
                "contact_card": dict(card),
                "derived_global_score": scoring["global_score"],
                "score_components": dict(scoring["components"]),
                "health_report_count": scoring["report_count"],
            }
        )
    entries.sort(
        key=lambda item: (
            float(item.get("derived_global_score", 0.0) or 0.0),
            int((item.get("contact_card", {}) or {}).get("updated_at", 0) or 0),
            str(item.get("node_id", "")),
        ),
        reverse=True,
    )
    return entries[: max(1, limit)]


def select_bootstrap_peers(peers: list[dict[str, Any]], *, limit: int = 6) -> list[dict[str, Any]]:
    """Reduce scored peer entries to compact bootstrap descriptors for QR transport."""
    bootstrap: list[dict[str, Any]] = []
    for entry in peers:
        card = entry.get("contact_card", {}) or {}
        endpoints = card.get("direct_endpoints", []) or []
        if not endpoints:
            continue
        primary = endpoints[0]
        bootstrap.append(
            {
                "node_id": str(entry.get("node_id", "") or "").strip(),
                "addr": str(primary.get("addr", "") or "").strip(),
                "port": int(primary.get("port", 0) or 0),
                "transport": str(primary.get("transport", "tcp") or "tcp").strip() or "tcp",
                "capabilities": dict(card.get("capabilities", {}) or {}),
                "score": float(entry.get("derived_global_score", 0.0) or 0.0),
            }
        )
        if len(bootstrap) >= max(1, limit):
            break
    return bootstrap


def build_peer_snapshot(
    *,
    source_gs_node_id: str,
    world_id: str,
    chain_height: int,
    peers: list[dict[str, Any]],
    private_key: bytes,
    generated_at: int | None = None,
) -> dict[str, Any]:
    """Build a signed peer snapshot for Android-side peer cache refresh."""
    snapshot_time = int(generated_at or time.time())
    snapshot_id = sha256(
        f"snapshot:{source_gs_node_id}:{world_id}:{chain_height}:{snapshot_time}".encode("utf-8")
    )[:24]
    snapshot: dict[str, Any] = {
        "snapshot_id": snapshot_id,
        "world_id": str(world_id).strip(),
        "source_gs_node_id": str(source_gs_node_id).strip(),
        "generated_at": snapshot_time,
        "chain_height": max(0, int(chain_height or 0)),
        "peers": [dict(item) for item in peers],
    }
    snapshot["signature"] = sign_mobile_payload(snapshot, private_key)
    return snapshot
