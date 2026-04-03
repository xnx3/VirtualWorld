"""Configuration loading and defaults for Genesis nodes.

Configuration is read from ``data_dir/config.yaml`` (YAML).  Missing keys
fall back to sensible defaults that match ``config.yaml.example``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Section dataclasses
# ---------------------------------------------------------------------------

@dataclass
class LLMConfig:
    base_url: str = "http://localhost:11434/v1"
    api_key: str = ""
    model: str = "llama3"
    max_tokens: int = 2048
    temperature: float = 0.8


@dataclass
class NetworkConfig:
    listen_port: int = 19841
    discovery_port: int = 19840
    bootstrap_nodes: list[str] = field(default_factory=lambda: ["http://45.205.24.48:8760"])
    advertise_address: str = ""
    allow_local_bootstrap: bool = False
    max_peers: int = 50
    discovery_interval: int = 30
    sync_interval: int = 30
    startup_sync_timeout: int = 45
    peer_endpoint_ttl: int = 600
    relay_capable: bool = False
    max_relay_hints: int = 3


@dataclass
class SimulationConfig:
    tick_interval: int = 30
    block_interval: int = 30
    min_beings: int = 10
    max_npc_per_node: int = 5


@dataclass
class ChainConfig:
    contribution_vote_window: int = 5
    contribution_min_voters: float = 0.51
    proposal_rate_limit: int = 10
    priest_grace_period: int = 50
    creator_succession_threshold: int = 1000


@dataclass
class BeingConfig:
    initial_lifespan: int = 1000
    hibernate_safety_timeout: int = 30


@dataclass
class APIConfig:
    """WebSocket API configuration for GUI/remote access."""
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 19842


# ---------------------------------------------------------------------------
# Top-level configuration
# ---------------------------------------------------------------------------

@dataclass
class VWConfig:
    """Complete Genesis node configuration."""

    llm: LLMConfig = field(default_factory=LLMConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    simulation: SimulationConfig = field(default_factory=SimulationConfig)
    chain: ChainConfig = field(default_factory=ChainConfig)
    being: BeingConfig = field(default_factory=BeingConfig)
    api: APIConfig = field(default_factory=APIConfig)
    language: str = "en"  # "en" or "zh"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _merge_section(dc_class: type, raw: dict[str, Any] | None) -> Any:
    """Instantiate a dataclass, overlaying values from *raw* on top of defaults."""
    if raw is None:
        return dc_class()
    known = {f.name for f in fields(dc_class)}
    filtered = {k: v for k, v in raw.items() if k in known}
    return dc_class(**filtered)


_CONFIG_FILE = "config.yaml"


def load_config(data_dir: str | Path) -> VWConfig:
    """Load configuration from ``<data_dir>/config.yaml``.

    If the file does not exist, all-default values are returned.
    Unknown top-level or nested keys are silently ignored.
    """
    config_path = Path(data_dir) / _CONFIG_FILE

    raw: dict[str, Any] = {}
    if config_path.exists():
        text = config_path.read_text(encoding="utf-8")
        parsed = yaml.safe_load(text)
        if isinstance(parsed, dict):
            raw = parsed

    return VWConfig(
        llm=_merge_section(LLMConfig, raw.get("llm")),
        network=_merge_section(NetworkConfig, raw.get("network")),
        simulation=_merge_section(SimulationConfig, raw.get("simulation")),
        chain=_merge_section(ChainConfig, raw.get("chain")),
        being=_merge_section(BeingConfig, raw.get("being")),
        api=_merge_section(APIConfig, raw.get("api")),
        language=raw.get("language", "en"),
    )
