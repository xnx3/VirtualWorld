"""Derive public bootstrap scores from contact cards and health evidence."""

from __future__ import annotations

import time
from typing import Any


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _fresh_reports(reports: list[dict[str, Any]], now: int) -> list[dict[str, Any]]:
    fresh: list[dict[str, Any]] = []
    for report in reports:
        if not isinstance(report, dict):
            continue
        try:
            window_end = max(0, int(report.get("window_end", 0) or 0))
            ttl = max(0, int(report.get("ttl", 0) or 0))
        except (TypeError, ValueError):
            continue
        if ttl > 0 and window_end > 0 and (window_end + ttl) < now:
            continue
        fresh.append(dict(report))
    return fresh


def _freshness_score(card: dict[str, Any], now: int) -> float:
    try:
        updated_at = max(0, int(card.get("updated_at", 0) or 0))
        ttl = max(0, int(card.get("ttl", 0) or 0))
    except (TypeError, ValueError):
        return 0.0
    if updated_at <= 0 or ttl <= 0:
        return 0.0
    age = max(0, now - updated_at)
    if age >= ttl:
        return 0.0
    return _clamp(1.0 - (age / float(ttl)))


def _weighted_average(reports: list[dict[str, Any]], extractor) -> float:
    total = 0.0
    weight_sum = 0.0
    for report in reports:
        try:
            confidence = max(0.1, min(1.0, float(report.get("confidence", 0.5) or 0.5)))
            success = max(0, int(report.get("success_count", 0) or 0))
            failure = max(0, int(report.get("failure_count", 0) or 0))
        except (TypeError, ValueError):
            confidence = 0.5
            success = 0
            failure = 0
        attempts = max(1, success + failure)
        weight = attempts * confidence
        total += weight * float(extractor(report))
        weight_sum += weight
    if weight_sum <= 0:
        return 0.0
    return _clamp(total / weight_sum)


def _reachability_score(card: dict[str, Any], reports: list[dict[str, Any]]) -> float:
    if reports:
        return _weighted_average(
            reports,
            lambda report: 1.0 if report.get("reachable") else (
                max(0.0, min(1.0, int(report.get("success_count", 0) or 0) / float(max(1, int(report.get("success_count", 0) or 0) + int(report.get("failure_count", 0) or 0)))))
            ),
        )
    return 0.25 if (card.get("direct_endpoints") or []) else 0.0


def _chain_alignment_score(reports: list[dict[str, Any]], chain_height: int) -> float:
    if not reports or chain_height < 0:
        return 0.0
    return _weighted_average(
        reports,
        lambda report: 1.0 - min(64, abs(chain_height - int(report.get("chain_height_seen", 0) or 0))) / 64.0,
    )


def _relay_quality_score(card: dict[str, Any], reports: list[dict[str, Any]]) -> float:
    relay_capable = "relay" in (card.get("transports") or []) or bool(card.get("relay_hints")) or bool((card.get("capabilities") or {}).get("relay"))
    if reports:
        return _weighted_average(
            reports,
            lambda report: 1.0 if report.get("relay_success") else (0.35 if relay_capable else 0.0),
        )
    return 0.35 if relay_capable else 0.0


def _capability_score(card: dict[str, Any]) -> float:
    capabilities = card.get("capabilities", {}) or {}
    if not isinstance(capabilities, dict) or not capabilities:
        return 0.0
    weights = {
        "relay": 0.45,
        "bootstrap": 0.25,
        "light_sync": 0.15,
        "task_submit": 0.15,
    }
    score = 0.0
    for key, value in capabilities.items():
        if not value:
            continue
        score += weights.get(str(key), 0.1)
    return _clamp(score)


def _transport_score(card: dict[str, Any]) -> float:
    transports = [str(item).strip() for item in (card.get("transports") or []) if str(item).strip()]
    unique = []
    for transport in transports:
        if transport not in unique:
            unique.append(transport)
    return _clamp(len(unique) / 3.0)


def derive_global_score(
    card: dict[str, Any] | None,
    reports: list[dict[str, Any]] | None,
    chain_height: int,
    *,
    now: int | None = None,
) -> dict[str, Any]:
    """Compute the chain-wide public bootstrap score for one peer."""
    now_value = int(now or time.time())
    card_data = dict(card or {})
    fresh_reports = _fresh_reports(list(reports or []), now_value)
    components = {
        "freshness": round(_freshness_score(card_data, now_value), 4),
        "reachability": round(_reachability_score(card_data, fresh_reports), 4),
        "chain_alignment": round(_chain_alignment_score(fresh_reports, chain_height), 4),
        "relay_quality": round(_relay_quality_score(card_data, fresh_reports), 4),
        "capability_score": round(_capability_score(card_data), 4),
        "transport_score": round(_transport_score(card_data), 4),
    }
    score = (
        0.30 * components["freshness"]
        + 0.25 * components["reachability"]
        + 0.15 * components["chain_alignment"]
        + 0.15 * components["relay_quality"]
        + 0.10 * components["capability_score"]
        + 0.05 * components["transport_score"]
    )
    return {
        "global_score": round(score * 100.0, 2),
        "components": components,
        "report_count": len(fresh_reports),
    }
