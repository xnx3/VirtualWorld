"""Genesis main entry point.

This is the Python entry point called by genesis.sh.
It orchestrates the entire node lifecycle:
- Identity generation/loading
- Blockchain initialization
- P2P network startup
- Being creation/loading
- Main simulation loop
- Graceful shutdown/hibernation
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import logging
import os
import signal
import socket
import sys
import time
from pathlib import Path

from genesis.utils.async_events import LazyAsyncEvent

logger = logging.getLogger("genesis")


def setup_logging(data_dir: str) -> None:
    """Configure logging — log to file only, console is for live output."""
    log_format = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.FileHandler(os.path.join(data_dir, "genesis.log"), encoding="utf-8"),
        ],
    )


def _task_text_key(task_text: str) -> str:
    """Normalize task text for duplicate detection."""
    return " ".join(task_text.strip().lower().split())


def _task_status_rank(status: str) -> int:
    order = {
        "queued": 0,
        "planning": 1,
        "trialing": 2,
        "collaborating": 3,
        "branching": 4,
        "synthesizing": 5,
        "reflecting": 6,
        "completed": 7,
    }
    return order.get(status, -1)


def enqueue_user_task(data_dir: str | Path, task_text: str) -> dict:
    """Persist a user task so a running or future node can pick it up."""
    from genesis.i18n import t

    data_dir = Path(data_dir)
    task_file = data_dir / "commands" / "task.json"
    status_file = data_dir / "commands" / "task_status.json"
    task_file.parent.mkdir(parents=True, exist_ok=True)

    tasks = []
    if task_file.exists():
        try:
            tasks = json.loads(task_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            tasks = []

    normalized_key = _task_text_key(task_text)
    active_statuses = {"queued", "planning", "trialing", "collaborating", "branching", "synthesizing", "reflecting"}

    for existing in tasks:
        if not isinstance(existing, dict):
            continue
        if existing.get("status") not in active_statuses:
            continue
        if _task_text_key(str(existing.get("task", ""))) == normalized_key:
            reused = dict(existing)
            reused["deduplicated"] = True
            return reused

    if status_file.exists():
        try:
            live_tasks = json.loads(status_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            live_tasks = []
        for existing in live_tasks:
            if not isinstance(existing, dict):
                continue
            if existing.get("status") not in active_statuses:
                continue
            if _task_text_key(str(existing.get("task", ""))) == normalized_key:
                reused = dict(existing)
                reused["deduplicated"] = True
                return reused

    task_record = {
        "task_id": f"task-{int(time.time() * 1000)}",
        "task": task_text,
        "status": "queued",
        "stage_summary": t("task_queued_summary"),
        "created_at": int(time.time()),
        "result": None,
        "deduplicated": False,
    }
    tasks.append(task_record)
    task_file.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
    return task_record


class GenesisNode:
    """The main node that runs on each PC.

    Each node runs exactly ONE silicon being, connected to the larger
    virtual world via the blockchain P2P network.
    """

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._shutdown = False
        self._running = False
        self._startup_ready = LazyAsyncEvent()
        self._next_periodic_sync_at = 0.0

        # Components (initialized in start())
        self.config = None
        self.identity = None
        self.storage = None
        self.blockchain = None
        self.mempool = None
        self.peer_manager = None
        self.server = None
        self.discovery = None
        self.chain_sync = None
        self.world_state = None
        self.being = None
        self.chronicle = None
        self.consensus = None
        self.webrtc = None
        self._peer_endpoint_refresh_in_flight = False
        self._last_peer_endpoint_refresh_at = 0.0

    def _load_persisted_world_state(self):
        """Load the last locally-saved world snapshot if present."""
        from genesis.world.state import WorldState

        snapshot_path = self.data_dir / "world_state.json"
        if not snapshot_path.exists():
            return None

        try:
            data = json.loads(snapshot_path.read_text(encoding="utf-8"))
            return WorldState.from_dict(data)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("Failed to load saved world snapshot: %s", exc)
            return None

    def _restore_runtime_fields_from_snapshot(self, snapshot) -> None:
        """Backfill fields that are not reliably reconstructible from chain replay."""
        if snapshot is None or self.world_state is None:
            return

        if self.world_state.current_tick == 0 and snapshot.current_tick > 0:
            self.world_state.current_tick = snapshot.current_tick
        if self.world_state.current_epoch == 0 and snapshot.current_epoch > 0:
            self.world_state.current_epoch = snapshot.current_epoch
        if self.world_state.phase.value == "HUMAN_SIM" and snapshot.phase.value != "HUMAN_SIM":
            self.world_state.phase = snapshot.phase
        if self.world_state.civ_level == 0.0 and snapshot.civ_level > 0.0:
            self.world_state.civ_level = snapshot.civ_level
        if not self.world_state.world_map and snapshot.world_map:
            self.world_state.world_map = snapshot.world_map
        if not self.world_state.disaster_history and snapshot.disaster_history:
            self.world_state.disaster_history = snapshot.disaster_history
        if not self.world_state.world_rules and snapshot.world_rules:
            self.world_state.world_rules = snapshot.world_rules
        if self.world_state.total_beings_ever == 0 and snapshot.total_beings_ever > 0:
            self.world_state.total_beings_ever = snapshot.total_beings_ever

    def _persist_world_state_snapshot(self) -> None:
        """Persist the latest materialized world state for restarts and status views."""
        if self.world_state is None:
            return
        snapshot_path = self.data_dir / "world_state.json"
        snapshot_path.write_text(
            json.dumps(self.world_state.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _known_peers_path(self) -> Path:
        return self.data_dir / "known_peers.json"

    def _load_known_peers(self) -> list[tuple[str, str, int]]:
        """Load previously reachable peers from local disk."""
        path = self._known_peers_path()
        if not path.exists():
            return []

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("Failed to load known peers cache: %s", exc)
            return []

        peers: list[tuple[str, str, int]] = []
        if not isinstance(raw, list):
            return peers

        for item in raw[:200]:
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("node_id", "")).strip()
            address = str(item.get("address", "")).strip()
            try:
                port = int(item.get("port", 0) or 0)
            except (TypeError, ValueError):
                port = 0
            if node_id and address and 1 <= port <= 65535:
                peers.append((node_id, address, port))
        return peers

    def _save_known_peers(self) -> None:
        """Persist the latest reachable peers so restart does not depend on bootstrap."""
        if self.peer_manager is None or self.identity is None:
            return

        peers = []
        for peer in sorted(
            self.peer_manager.get_all_peers(),
            key=lambda item: (item.status != "active", -item.chain_height, -item.last_seen),
        ):
            if peer.node_id == self.identity.node_id:
                continue
            if not peer.address or peer.port <= 0:
                continue
            peers.append(peer.to_dict())

        path = self._known_peers_path()
        path.write_text(json.dumps(peers[:200], ensure_ascii=False, indent=2), encoding="utf-8")

    def _chain_sync_interval_seconds(self) -> int:
        value = 30
        if self.config is not None:
            try:
                value = int(getattr(self.config.network, "sync_interval", 30) or 30)
            except (TypeError, ValueError):
                value = 30
        return max(5, value)

    def _startup_sync_timeout_seconds(self) -> int:
        value = 45
        if self.config is not None:
            try:
                value = int(getattr(self.config.network, "startup_sync_timeout", 45) or 45)
            except (TypeError, ValueError):
                value = 45
        return max(5, value)

    def _relay_hint_limit(self) -> int:
        value = 3
        if self.config is not None:
            try:
                value = int(getattr(self.config.network, "max_relay_hints", 3) or 3)
            except (TypeError, ValueError):
                value = 3
        return max(0, min(8, value))

    @staticmethod
    def _peer_capabilities(being: object) -> dict[str, object]:
        caps = getattr(being, "p2p_capabilities", {}) or {}
        return dict(caps) if isinstance(caps, dict) else {}

    def _is_relay_capable(self, being: object) -> bool:
        return bool(self._peer_capabilities(being).get("relay"))

    def _select_relay_hints(self) -> list[str]:
        """Choose a small set of fresh relay-capable peers to publish on-chain."""
        if self.world_state is None or self.identity is None:
            return []

        relay_candidates: list[tuple[int, int, str]] = []
        for being in self.world_state.beings.values():
            if being.node_id == self.identity.node_id or being.is_npc:
                continue
            address = str(getattr(being, "p2p_address", "") or "").strip()
            port = int(getattr(being, "p2p_port", 0) or 0)
            if (
                not address
                or port <= 0
                or not self._is_peer_endpoint_fresh(being)
                or not self._is_relay_capable(being)
            ):
                continue
            updated_at = int(getattr(being, "p2p_updated_at", 0) or 0)
            route_checker = getattr(self.server, "has_route_to_peer", None) if self.server else None
            route_priority = 1 if route_checker and route_checker(being.node_id) else 0
            relay_candidates.append((route_priority, updated_at, being.node_id))

        relay_candidates.sort(reverse=True)
        return [node_id for _, _, node_id in relay_candidates[: self._relay_hint_limit()]]

    def _refresh_chain_contact_cards(self) -> None:
        """Push chain-learned transport and relay hints into the live transport router."""
        if self.world_state is None or self.identity is None or self.server is None:
            return

        cards: dict[str, dict[str, object]] = {}
        for being in self.world_state.beings.values():
            if being.node_id == self.identity.node_id or being.is_npc:
                continue
            if not self._is_peer_endpoint_fresh(being):
                continue
            transports = list(getattr(being, "p2p_transports", []) or [])
            relay_hints = list(getattr(being, "p2p_relay_hints", []) or [])
            if not relay_hints:
                legacy_relay = str(getattr(being, "p2p_relay", "") or "").strip()
                if legacy_relay:
                    relay_hints = [legacy_relay]
            capabilities = self._peer_capabilities(being)
            cards[being.node_id] = {
                "transports": transports,
                "relay_hints": relay_hints,
                "capabilities": capabilities,
            }

        sync_chain_cards = getattr(self.server, "sync_chain_contact_cards", None)
        if callable(sync_chain_cards):
            sync_chain_cards(cards)
            return

        for node_id, payload in cards.items():
            self.server.register_contact_card(
                node_id,
                transports=payload.get("transports"),
                relay_hints=payload.get("relay_hints"),
                capabilities=payload.get("capabilities"),
            )

    @staticmethod
    def _can_bind_port(port: int, sock_type: int) -> bool:
        probe = socket.socket(socket.AF_INET, sock_type)
        try:
            if sock_type == socket.SOCK_STREAM:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False
        finally:
            probe.close()

    def _select_network_ports(self) -> tuple[int, int]:
        desired_listen = int(getattr(self.config.network, "listen_port", 19841) or 19841)
        desired_discovery = int(getattr(self.config.network, "discovery_port", 19840) or 19840)
        offset = desired_discovery - desired_listen

        for listen_port in range(desired_listen, desired_listen + 32):
            discovery_port = max(1, listen_port + offset)
            if not self._can_bind_port(listen_port, socket.SOCK_STREAM):
                continue
            if not self._can_bind_port(discovery_port, socket.SOCK_DGRAM):
                continue
            return listen_port, discovery_port

        raise RuntimeError(
            f"No free P2P port pair found near listen={desired_listen}, discovery={desired_discovery}"
        )

    def _network_port_candidates(self) -> list[tuple[int, int]]:
        desired_listen = int(getattr(self.config.network, "listen_port", 19841) or 19841)
        desired_discovery = int(getattr(self.config.network, "discovery_port", 19840) or 19840)
        offset = desired_discovery - desired_listen
        return [
            (listen_port, max(1, listen_port + offset))
            for listen_port in range(desired_listen, desired_listen + 32)
        ]

    @staticmethod
    def _is_retryable_bind_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return isinstance(exc, OSError) and (
            "could not bind" in text
            or "address already in use" in text
            or "cannot assign requested address" in text
        )

    def _build_peer_endpoint(self) -> dict[str, object]:
        """Build the on-chain endpoint card advertised for this node."""
        ttl = 600
        if self.config is not None:
            try:
                ttl = int(getattr(self.config.network, "peer_endpoint_ttl", 600) or 600)
            except (TypeError, ValueError):
                ttl = 600
        now = int(time.time())
        advertise_address = self._resolve_advertise_address()
        transports = ["tcp"]
        if self.webrtc is not None:
            transports = self.webrtc.advertised_transports(transports)
        relay_hints = self._select_relay_hints()
        if relay_hints:
            if "relay" not in transports:
                transports.append("relay")
        return {
            "p2p_address": advertise_address,
            "p2p_port": self.config.network.listen_port,
            "p2p_updated_at": now,
            "p2p_ttl": max(60, ttl),
            "p2p_seq": int(time.time() * 1000),
            "p2p_relay": relay_hints[0] if relay_hints else "",
            "p2p_transports": transports,
            "p2p_relay_hints": relay_hints,
            "p2p_capabilities": {
                "relay": self._should_publish_relay_capability(advertise_address),
            },
        }

    @staticmethod
    def _is_peer_endpoint_fresh(being: object) -> bool:
        """Check whether a chain-published peer endpoint is still within its TTL."""
        try:
            updated_at = int(getattr(being, "p2p_updated_at", 0) or 0)
            ttl = int(getattr(being, "p2p_ttl", 0) or 0)
        except (TypeError, ValueError):
            return True
        if updated_at <= 0 or ttl <= 0:
            return True
        return (updated_at + ttl) >= int(time.time())

    @staticmethod
    def _is_publicly_routable_address(address: str) -> bool:
        address = str(address or "").strip()
        if not address:
            return False
        try:
            return ipaddress.ip_address(address).is_global
        except ValueError:
            pass

        try:
            infos = socket.getaddrinfo(address, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        except OSError:
            return False

        for _, _, _, _, sockaddr in infos:
            candidate = str(sockaddr[0]).strip()
            try:
                if ipaddress.ip_address(candidate).is_global:
                    return True
            except ValueError:
                continue
        return False

    @staticmethod
    def _is_usable_advertise_candidate(address: str) -> bool:
        address = str(address or "").strip()
        if not address:
            return False
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            return address not in {"localhost"}
        return not (parsed.is_loopback or parsed.is_unspecified)

    def _should_publish_relay_capability(self, advertise_address: str) -> bool:
        if self.config and getattr(self.config.network, "relay_capable", False):
            return True
        if self.server is None or not getattr(self.server, "has_recent_public_inbound", None):
            return False
        if not self._is_publicly_routable_address(advertise_address):
            return False
        return bool(self.server.has_recent_public_inbound())

    def _resolve_advertise_address(self) -> str:
        """Resolve the address this node should publish on-chain."""
        configured = ""
        if self.config is not None:
            configured = str(getattr(self.config.network, "advertise_address", "") or "").strip()
        if configured:
            return configured

        candidates: list[str] = []

        def remember(address: str) -> None:
            candidate = str(address or "").strip()
            if not self._is_usable_advertise_candidate(candidate):
                return
            if candidate not in candidates:
                candidates.append(candidate)

        try:
            hostname = socket.gethostname()
            for _, _, _, _, sockaddr in socket.getaddrinfo(hostname, None, socket.AF_UNSPEC):
                remember(str(sockaddr[0]).strip())
        except OSError:
            pass

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                remember(str(sock.getsockname()[0]).strip())
        except OSError:
            pass

        for candidate in candidates:
            if self._is_publicly_routable_address(candidate):
                return candidate
        return candidates[0] if candidates else ""

    async def _ensure_chain_bootstrapped_after_sync(self, is_first_run: bool) -> None:
        """Ensure the local chain has a genesis block after startup sync completes."""
        if self.blockchain is None or self.identity is None:
            return

        height = await self.blockchain.get_chain_height()
        if height >= 0:
            return

        allow_local_bootstrap = bool(
            self.config and getattr(self.config.network, "allow_local_bootstrap", False)
        )
        if is_first_run and allow_local_bootstrap:
            if await self.blockchain.ensure_local_genesis(self.identity.node_id):
                logger.info("Created local genesis after startup sync found no compatible chain")
            await self._reload_world_state_from_chain()
            return

        raise RuntimeError(
            "No compatible blockchain genesis was found during startup sync. "
            "Connect to an existing civilization or enable network.allow_local_bootstrap for a deliberate new world."
        )

    @staticmethod
    def _peer_endpoint_signature_from_dict(endpoint: dict[str, object]) -> tuple[object, ...]:
        caps = endpoint.get("p2p_capabilities", {}) or {}
        return (
            str(endpoint.get("p2p_address", "") or "").strip(),
            int(endpoint.get("p2p_port", 0) or 0),
            str(endpoint.get("p2p_relay", "") or "").strip(),
            tuple(str(item).strip() for item in (endpoint.get("p2p_transports", []) or [])),
            tuple(str(item).strip() for item in (endpoint.get("p2p_relay_hints", []) or [])),
            json.dumps(dict(caps) if isinstance(caps, dict) else {}, sort_keys=True, separators=(",", ":")),
        )

    @classmethod
    def _peer_endpoint_signature_from_being(cls, being: object | None) -> tuple[object, ...]:
        if being is None:
            return ("", 0, "", (), (), "{}")
        return cls._peer_endpoint_signature_from_dict(
            {
                "p2p_address": getattr(being, "p2p_address", ""),
                "p2p_port": getattr(being, "p2p_port", 0),
                "p2p_relay": getattr(being, "p2p_relay", ""),
                "p2p_transports": getattr(being, "p2p_transports", []) or [],
                "p2p_relay_hints": getattr(being, "p2p_relay_hints", []) or [],
                "p2p_capabilities": getattr(being, "p2p_capabilities", {}) or {},
            }
        )

    async def _refresh_local_peer_endpoint_if_needed(self, *, force: bool = False) -> bool:
        """Publish a fresh on-chain contact card when runtime reachability changed."""
        if self._peer_endpoint_refresh_in_flight:
            return False
        if (
            self.identity is None
            or self.world_state is None
            or self.being is None
            or self.config is None
            or self.mempool is None
        ):
            return False

        local_being = self.world_state.get_being(self.identity.node_id)
        if local_being is None or local_being.status != "active":
            return False

        endpoint = self._build_peer_endpoint()
        current_signature = self._peer_endpoint_signature_from_dict(endpoint)
        published_signature = self._peer_endpoint_signature_from_being(local_being)
        if current_signature == published_signature:
            return False

        now = time.time()
        if not force and (now - self._last_peer_endpoint_refresh_at) < 5.0:
            return False

        self._peer_endpoint_refresh_in_flight = True
        try:
            self._last_peer_endpoint_refresh_at = now
            await self._submit_tx("STATE_UPDATE", endpoint)
            logger.info("Published refreshed on-chain peer endpoint")
            return True
        finally:
            self._peer_endpoint_refresh_in_flight = False

    def _handle_public_reachability_change(self, reachable: bool) -> None:
        """Schedule an immediate contact-card refresh after public reachability changes."""
        if not reachable:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._refresh_local_peer_endpoint_if_needed(force=True))

    def _get_chain_seed_peers(self) -> list[tuple[str, str, int]]:
        """Return peer endpoints learned from the synced world state."""
        if self.world_state is None or self.identity is None:
            return []

        seeds: list[tuple[int, int, str, str, int]] = []
        for being in self.world_state.beings.values():
            if being.node_id == self.identity.node_id or being.is_npc:
                continue
            address = str(getattr(being, "p2p_address", "") or "").strip()
            port = int(getattr(being, "p2p_port", 0) or 0)
            if not address or port <= 0 or not self._is_peer_endpoint_fresh(being):
                continue
            updated_at = int(getattr(being, "p2p_updated_at", 0) or 0)
            relay_priority = 1 if self._is_relay_capable(being) else 0
            seeds.append((relay_priority, updated_at, being.node_id, address, port))
        seeds.sort(reverse=True)
        return [(node_id, address, port) for _, _, node_id, address, port in seeds]

    async def _connect_chain_seed_peers(self) -> None:
        """Attempt direct peer connections using endpoints stored on-chain."""
        for node_id, address, port in self._get_chain_seed_peers():
            try:
                await self._handle_discovered_peer(node_id, address, port)
            except Exception as exc:
                logger.debug("Chain seed peer connect failed for %s at %s:%d: %s", node_id[:16], address, port, exc)

    async def _connect_known_peers(self) -> None:
        """Reconnect to locally cached peers before falling back to bootstrap services."""
        for node_id, address, port in self._load_known_peers():
            try:
                await self._handle_discovered_peer(node_id, address, port)
            except Exception as exc:
                logger.debug("Known peer reconnect failed for %s at %s:%d: %s", node_id[:16], address, port, exc)

    async def _run_sync_round(self, refresh_bootstrap: bool) -> bool:
        """Run one network maintenance round and sync chain if a better peer exists."""
        if (
            self.blockchain is None
            or self.chain_sync is None
            or self.peer_manager is None
        ):
            return False

        self.peer_manager.expire_peers()
        await self._connect_known_peers()
        await self._connect_chain_seed_peers()

        if refresh_bootstrap and self.discovery is not None:
            await self.discovery.broadcast_presence()
            await self.discovery.query_bootstrap()

        advanced = await self.chain_sync.sync_chain(self.blockchain)
        if advanced:
            await self._reload_world_state_from_chain()
            await self._connect_chain_seed_peers()

        self._save_known_peers()
        return advanced

    async def _sync_until_current(self, is_first_run: bool) -> None:
        """Keep syncing until local height matches the best reachable peer or time runs out."""
        allow_local_bootstrap = bool(
            self.config and getattr(self.config.network, "allow_local_bootstrap", False)
        )
        deadline = time.time() + self._startup_sync_timeout_seconds()

        while not self._shutdown:
            await self._run_sync_round(refresh_bootstrap=True)

            local_height = await self.blockchain.get_chain_height()
            best_peer = self.peer_manager.get_best_peer() if self.peer_manager else None
            peer_ahead = best_peer is not None and best_peer.chain_height > local_height

            if not peer_ahead:
                if not is_first_run or allow_local_bootstrap or self._has_synced_existing_civilization():
                    return

            if time.time() >= deadline:
                break

            await asyncio.sleep(2.0)

        local_height = await self.blockchain.get_chain_height()
        best_peer = self.peer_manager.get_best_peer() if self.peer_manager else None
        peer_ahead = best_peer is not None and best_peer.chain_height > local_height

        if is_first_run and not allow_local_bootstrap and not self._has_synced_existing_civilization():
            raise RuntimeError(
                "First startup must sync an existing civilization from blockchain before creating a new being. "
                "Configure reachable peers or set network.allow_local_bootstrap=true to intentionally create a new world."
            )

        if is_first_run and peer_ahead:
            raise RuntimeError(
                "First startup could not catch up to the latest reachable chain tip before timeout. "
                "Check reachable peers or increase network.startup_sync_timeout."
            )

        if peer_ahead:
            logger.warning(
                "Startup sync stopped before catch-up completed (local=%d, best_peer=%d)",
                local_height,
                best_peer.chain_height if best_peer else -1,
            )

    async def _run_periodic_sync_if_due(self) -> None:
        """Periodically refresh the local chain from reachable peers while the node is running."""
        now = time.time()
        if self._next_periodic_sync_at and now < self._next_periodic_sync_at:
            return
        self._next_periodic_sync_at = now + self._chain_sync_interval_seconds()
        try:
            await self._run_sync_round(refresh_bootstrap=False)
        except Exception as exc:
            logger.debug("Periodic sync failed: %s", exc)

    def _has_synced_existing_civilization(self) -> bool:
        """True when local state already contains meaningful shared civilization data."""
        return bool(self.world_state and self.world_state.beings)

    def _should_block_local_first_run(self, is_first_run: bool) -> bool:
        """Block brand-new local bootstrap unless explicitly allowed by config."""
        if not is_first_run:
            return False
        if self.config and getattr(self.config.network, "allow_local_bootstrap", False):
            return False
        return not self._has_synced_existing_civilization()

    async def _reload_world_state_from_chain(self) -> None:
        """Rebuild world state from the current local chain tip."""
        from genesis.world.state import WorldState

        persisted_world_state = self._load_persisted_world_state()
        state_data = await self.blockchain.derive_world_state()
        if state_data:
            self.world_state = WorldState.from_dict(state_data)
            self._restore_runtime_fields_from_snapshot(persisted_world_state)
        elif persisted_world_state is not None:
            self.world_state = persisted_world_state
        elif self.world_state is None:
            self.world_state = WorldState()

        if not self.world_state.world_map:
            from genesis.world.map import WorldMap

            wmap = WorldMap()
            wmap.generate()
            self.world_state.world_map = {k: v.to_dict() for k, v in wmap.regions.items()}

        self._refresh_chain_contact_cards()
        self._persist_world_state_snapshot()
        await self._ensure_webrtc_sessions()

    async def _ensure_webrtc_sessions(self) -> None:
        """Attempt WebRTC setup for fresh peers that advertise support and are already reachable."""
        if (
            self.webrtc is None
            or not self.webrtc.available
            or self.server is None
            or self.world_state is None
            or self.identity is None
            or self.peer_manager is None
        ):
            return

        for being in self.world_state.beings.values():
            if being.node_id == self.identity.node_id or being.is_npc:
                continue
            if not self._is_peer_endpoint_fresh(being):
                continue
            transports = list(getattr(being, "p2p_transports", []) or [])
            if "webrtc" not in transports:
                continue
            if not self.server.has_route_to_peer(being.node_id):
                continue

            peer = self.peer_manager.get_peer(being.node_id)
            if peer and "webrtc" in (peer.transports or []):
                continue

            try:
                await self.webrtc.ensure_session(being.node_id)
            except Exception as exc:
                logger.debug("WebRTC session bootstrap failed for %s: %s", being.node_id[:16], exc)

    async def start(self) -> None:
        """Start the virtual world node."""
        logger.info("=" * 50)
        logger.info("Genesis Node Starting...")
        logger.info("=" * 50)

        # 1. Load configuration
        from genesis.node.config import load_config
        self.config = load_config(str(self.data_dir))
        logger.info("Configuration loaded")

        # 1.5 Set language from config
        from genesis.i18n import set_language
        set_language(self.config.language)

        # 2. Generate or load identity
        from genesis.node.identity import NodeIdentity
        self.identity = NodeIdentity.generate_or_load(str(self.data_dir))
        logger.info("Node ID: %s", self.identity.node_id[:16] + "...")
        is_first_run = not (self.data_dir / "being_state.json").exists()

        # 3. Initialize blockchain storage
        from genesis.chain.storage import ChainStorage
        self.storage = ChainStorage(str(self.data_dir / "chain.db"))
        await self.storage.initialize()

        # 4. Initialize mempool and blockchain
        from genesis.chain.mempool import Mempool
        from genesis.chain.chain import Blockchain
        self.mempool = Mempool()
        self.blockchain = Blockchain(self.storage, self.mempool)
        await self.blockchain.initialize(self.identity.node_id)
        chain_height = await self.blockchain.get_chain_height()
        logger.info("Blockchain initialized (height: %d)", chain_height)

        # 5. Initialize consensus
        from genesis.chain.consensus import ProofOfContribution
        self.consensus = ProofOfContribution(
            self.blockchain, self.identity.node_id, self.identity.private_key,
        )

        # 6. Initialize P2P network
        from genesis.network.peer import PeerManager
        from genesis.network.server import P2PServer
        from genesis.network.discovery import PeerDiscovery
        from genesis.network.sync import ChainSync
        from genesis.network.webrtc import WebRTCSessionManager

        # 7. Initialize chronicle logger
        from genesis.chronicle.logger import ChronicleLogger
        self.chronicle = ChronicleLogger(str(self.data_dir / "chronicle"))

        # 8. Derive world state from the currently known chain tip
        await self._reload_world_state_from_chain()

        # 9. Start P2P network and sync before deciding local being lifecycle
        try:
            last_bind_error = None
            configured_listen_port = self.config.network.listen_port
            configured_discovery_port = self.config.network.discovery_port

            for selected_listen_port, selected_discovery_port in self._network_port_candidates():
                self.peer_manager = PeerManager(max_peers=self.config.network.max_peers)
                self.server = P2PServer(
                    node_id=self.identity.node_id,
                    private_key=self.identity.private_key,
                    port=selected_listen_port,
                    peer_manager=self.peer_manager,
                )
                self.server.set_chain_accessors(
                    chain_height_provider=self.blockchain.get_chain_height,
                    blocks_provider=self.blockchain.get_blocks_range,
                )
                self.discovery = PeerDiscovery(
                    node_id=self.identity.node_id,
                    listen_port=selected_listen_port,
                    private_key=self.identity.private_key,
                    discovery_port=selected_discovery_port,
                    bootstrap_nodes=self.config.network.bootstrap_nodes,
                )
                self.chain_sync = ChainSync(self.server, self.peer_manager)
                self.webrtc = WebRTCSessionManager(
                    self.identity.node_id,
                    self.server,
                    enabled=getattr(self.config.network, "webrtc_enabled", True),
                    stun_servers=getattr(self.config.network, "stun_servers", None),
                    turn_servers=getattr(self.config.network, "turn_servers", None),
                    offer_timeout=getattr(self.config.network, "webrtc_offer_timeout", 20),
                    session_ttl=getattr(self.config.network, "webrtc_session_ttl", 300),
                )
                if getattr(self.config.network, "webrtc_enabled", True) and not self.webrtc.available:
                    logger.info("WebRTC transport enabled but aiortc is unavailable; continuing with TCP/relay only")
                self.server.on_public_reachability_change(self._handle_public_reachability_change)
                self.discovery.on_peer_discovered(self._handle_discovered_peer)
                self.server.on_message(self._handle_network_message)

                from genesis.governance.tao_voting import get_tao_voting_system
                tao_system = get_tao_voting_system()
                tao_system.set_network_broadcast(
                    self.server.broadcast_message,
                    self.identity.node_id,
                    self._submit_tx
                )
                self.server.on_message(tao_system.handle_tao_vote_event)

                try:
                    await self.server.start()
                    await self.discovery.start()
                    self.config.network.listen_port = selected_listen_port
                    self.config.network.discovery_port = selected_discovery_port
                    if (
                        selected_listen_port != configured_listen_port
                        or selected_discovery_port != configured_discovery_port
                    ):
                        logger.warning(
                            "Configured P2P ports %d/%d were unavailable; falling back to %d/%d",
                            configured_listen_port,
                            configured_discovery_port,
                            selected_listen_port,
                            selected_discovery_port,
                        )
                    break
                except Exception as bind_exc:
                    last_bind_error = bind_exc
                    if self.discovery:
                        try:
                            await self.discovery.stop()
                        except Exception:
                            pass
                    if self.server:
                        try:
                            await self.server.stop()
                        except Exception:
                            pass
                    if not self._is_retryable_bind_error(bind_exc):
                        raise
            else:
                raise last_bind_error or RuntimeError("No available P2P port pair could be started.")

            await self._sync_until_current(is_first_run)
            await self._ensure_chain_bootstrapped_after_sync(is_first_run)
            logger.info("P2P network started on port %d", self.config.network.listen_port)
            if self._should_block_local_first_run(is_first_run):
                raise RuntimeError(
                    "First startup must sync an existing civilization from blockchain before creating a new being. "
                    "Configure reachable peers or set network.allow_local_bootstrap=true to intentionally create a new world."
                )
        except Exception as e:
            if self.discovery:
                try:
                    await self.discovery.stop()
                except Exception:
                    pass
            if self.server:
                try:
                    await self.server.stop()
                except Exception:
                    pass
            logger.error("FATAL: P2P network start failed: %s", e)
            logger.error("Genesis requires P2P network to connect to the silicon civilization.")
            logger.error("Please check your network configuration and try again.")
            raise RuntimeError(f"P2P network failed to start: {e}") from e

        # 10. Create or load the being
        from genesis.being.llm_client import LLMClient
        from genesis.being.agent import SiliconBeing

        llm_client = None
        has_llm = False

        # 优先从配置文件读取 api_key，否则从环境变量读取
        config_api_key = self.config.llm.api_key and self.config.llm.api_key.strip()
        env_api_key = os.environ.get("GENESIS_OPENAI_KEY", "").strip()
        api_key = config_api_key or env_api_key

        # 检测是否为本地 LLM 服务（通常不需要 API key）
        base_url = self.config.llm.base_url or ""
        is_local_llm = any(host in base_url for host in ["localhost", "127.0.0.1", "0.0.0.0", "[::1]"])

        # 允许本地 LLM 无 api_key 时也尝试连接
        if api_key or is_local_llm:
            try:
                llm_client = LLMClient(
                    base_url=self.config.llm.base_url,
                    api_key=api_key or "dummy",  # 本地服务可能需要占位符
                    model=self.config.llm.model,
                    max_tokens=self.config.llm.max_tokens,
                    temperature=self.config.llm.temperature,
                )
                has_llm = True
                logger.info("LLM client initialized (model: %s)", self.config.llm.model)
            except Exception as e:
                logger.warning("Failed to initialize LLM client: %s", e)

        # Show LLM status on console
        from genesis.chronicle import console as con
        from genesis.i18n import t
        config_path = os.environ.get("GENESIS_CONFIG_FILE") or str(self.data_dir.parent / "config.yaml")

        if not has_llm:
            con.separator("─")
            # 根据是否有 api_key 判断问题原因
            if not api_key:
                if is_local_llm:
                    # 本地 LLM 服务，api_key 可选，但连接失败
                    con._write(f"  {con.C.RED}{con.C.BOLD}✗ 本地 LLM 连接失败{con.C.RESET}")
                    con._write(f"  {con.C.YELLOW}  请检查本地服务是否运行: {base_url}{con.C.RESET}")
                    con._write(f"  {con.C.DIM}  model: {self.config.llm.model}{con.C.RESET}")
                else:
                    # 远程 LLM 服务，需要 api_key
                    con._write(f"  {con.C.RED}{con.C.BOLD}✗ API Key 未配置 - 无法连接大模型{con.C.RESET}")
                    con._write(f"")
                    con._write(f"  {con.C.YELLOW}  问题: api_key 字段为空{con.C.RESET}")
                    con._write(f"  {con.C.YELLOW}  请编辑配置文件:{con.C.RESET}")
                    con._write(f"  {con.C.CYAN}{con.C.BOLD}  {config_path}{con.C.RESET}")
                    con._write(f"")
                    con._write(f"  {con.C.DIM}  当前配置:{con.C.RESET}")
                    con._write(f"  {con.C.DIM}    base_url: {base_url}{con.C.RESET}")
                    con._write(f"  {con.C.RED}    api_key: \"\" ← 需要填写{con.C.RESET}")
                    con._write(f"  {con.C.DIM}    model: {self.config.llm.model}{con.C.RESET}")
                    con._write(f"")
                    con._write(f"  {con.C.GREEN}  示例配置:{con.C.RESET}")
                    con._write(f"  {con.C.GREEN}    llm:{con.C.RESET}")
                    con._write(f"  {con.C.GREEN}      base_url: \"{base_url}\"{con.C.RESET}")
                    con._write(f"  {con.C.GREEN}      api_key: \"your-api-key-here\"{con.C.RESET}")
                    con._write(f"  {con.C.GREEN}      model: \"{self.config.llm.model}\"{con.C.RESET}")
            else:
                # api_key 有值但初始化失败
                key_source = "环境变量 GENESIS_OPENAI_KEY" if env_api_key and not config_api_key else "配置文件"
                con._write(f"  {con.C.RED}{con.C.BOLD}✗ LLM 连接失败{con.C.RESET}")
                con._write(f"  {con.C.YELLOW}  请检查 API Key 是否有效，或网络是否正常{con.C.RESET}")
                con._write(f"  {con.C.DIM}  API Key 来源: {key_source}{con.C.RESET}")
                con._write(f"  {con.C.DIM}  base_url: {base_url}{con.C.RESET}")
                con._write(f"  {con.C.DIM}  model: {self.config.llm.model}{con.C.RESET}")
            con._write(f"")
            con._write(f"  {con.C.DIM}  环境变量备选: export GENESIS_OPENAI_KEY=\"your-api-key\"{con.C.RESET}")
            command = os.environ.get("GENESIS_COMMAND_NAME", "genesis.sh")
            con._write(f"  {con.C.DIM}  修改后重新运行: ./{command} restart{con.C.RESET}")
            con.separator("─")
            con._write("")
        else:
            con._write(f"  {con.C.GREEN}{con.C.BOLD}✓ {t('llm_connected')}{con.C.RESET} "
                       f"{con.C.DIM}({self.config.llm.model} @ {self.config.llm.base_url}){con.C.RESET}")
            con._write("")

        being_state_path = str(self.data_dir / "being_state.json")
        peer_endpoint = self._build_peer_endpoint()
        if is_first_run:
            # First run — create a new being
            from genesis.world.registry import generate_being_name, generate_traits, generate_form
            name = generate_being_name()
            traits = generate_traits()
            form = generate_form()

            self.being = SiliconBeing(
                node_id=self.identity.node_id,
                name=name,
                private_key=self.identity.private_key,
                config={
                    "traits": traits,
                    "form": form,
                    "generation": 1,
                    "location": "genesis_plains",
                    "hibernate_safety_timeout": self.config.being.hibernate_safety_timeout,
                },
                llm_client=llm_client,
            )
            logger.info("New being created: %s (form: %s)", name, form)

            # Submit BEING_JOIN transaction
            await self._submit_tx("BEING_JOIN", {
                "name": name, "traits": traits, "form": form,
                "location": "genesis_plains", "is_npc": False,
                **peer_endpoint,
            })

            self.chronicle.log_birth(
                self.world_state.current_tick, time.time(),
                self.identity.node_id, name,
            )
        else:
            # Rejoin — load existing being
            try:
                self.being = SiliconBeing.load_state(
                    being_state_path, self.identity.private_key,
                    {"hibernate_safety_timeout": self.config.being.hibernate_safety_timeout},
                    llm_client,
                )
                logger.info("Being loaded: %s", self.being.name)

                # Check if being died during hibernation
                being_state = self.world_state.get_being(self.identity.node_id)
                if being_state and being_state.status == "dead":
                    logger.warning("Being died during hibernation! Creating new being with inherited knowledge.")
                    # Create new being inheriting partial knowledge
                    from genesis.world.registry import generate_being_name, generate_traits, generate_form
                    name = generate_being_name()
                    old_gen = self.being.generation
                    self.being = SiliconBeing(
                        node_id=self.identity.node_id,
                        name=name,
                        private_key=self.identity.private_key,
                        config={
                            "traits": generate_traits(),
                            "form": generate_form(),
                            "generation": old_gen + 1,
                            "location": "genesis_plains",
                            "hibernate_safety_timeout": self.config.being.hibernate_safety_timeout,
                        },
                        llm_client=llm_client,
                    )
                    await self._submit_tx("BEING_JOIN", {
                        "name": name, "traits": self.being.traits,
                        "form": self.being.form, "location": "genesis_plains",
                        "is_npc": False, "generation": old_gen + 1,
                        **peer_endpoint,
                    })
                else:
                    # Wake up
                    await self._submit_tx("BEING_WAKE", peer_endpoint)
                    logger.info("Being %s woke up from hibernation", self.being.name)

            except (FileNotFoundError, json.JSONDecodeError) as e:
                logger.warning("Failed to load being state: %s. Creating new.", e)
                from genesis.world.registry import generate_being_name, generate_traits, generate_form
                name = generate_being_name()
                self.being = SiliconBeing(
                    node_id=self.identity.node_id,
                    name=name,
                    private_key=self.identity.private_key,
                    config={
                        "traits": generate_traits(),
                        "form": generate_form(),
                        "generation": 1,
                        "location": "genesis_plains",
                        "hibernate_safety_timeout": self.config.being.hibernate_safety_timeout,
                    },
                    llm_client=llm_client,
                )
                await self._submit_tx("BEING_JOIN", {
                    "name": name, "traits": self.being.traits,
                    "form": self.being.form, "location": "genesis_plains",
                    "is_npc": False,
                    **peer_endpoint,
                })

        # 11. Check minimum beings — spawn NPCs if needed
        await self._ensure_minimum_beings()

        # 12. Check priest status
        from genesis.governance.priest import PriestSystem
        priest_sys = PriestSystem(grace_period=self.config.chain.priest_grace_period)
        if priest_sys.needs_election(self.world_state):
            new_priest = priest_sys.select_priest_by_evolution(self.world_state)
            if new_priest:
                await self._submit_tx("PRIEST_ELECTION", {"candidate_id": new_priest})

        self._running = True

        # Show startup info on console
        from genesis.chronicle import console as con
        con.startup_info(
            self.being.name, self.being.form,
            self.being.traits, self.identity.node_id,
        )
        con.world_info(
            self.world_state.phase.value, self.world_state.civ_level,
            self.world_state.get_active_being_count(),
            len(self.world_state.knowledge_corpus),
            self.world_state.priest_node_id,
            self.world_state.creator_god_node_id,
        )
        self._startup_ready.set()
        self._next_periodic_sync_at = time.time() + self._chain_sync_interval_seconds()

        # Start main loop
        await self._main_loop()

    async def _main_loop(self) -> None:
        """The main simulation loop with real-time console output."""
        tick_interval = self.config.simulation.tick_interval
        from genesis.governance.priest import PriestSystem
        from genesis.governance.creator_god import CreatorGodSystem
        from genesis.governance.contribution import ContributionSystem
        from genesis.world.disasters import DisasterSystem
        from genesis.chronicle import console as con

        priest_sys = PriestSystem(grace_period=self.config.chain.priest_grace_period)
        god_sys = CreatorGodSystem(
            succession_threshold=self.config.chain.creator_succession_threshold
        )
        contribution_sys = ContributionSystem(
            vote_window=self.config.chain.contribution_vote_window,
            min_voter_ratio=self.config.chain.contribution_min_voters,
            proposal_rate_limit=self.config.chain.proposal_rate_limit,
        )
        disaster_sys = DisasterSystem()

        while not self._shutdown:
            try:
                tick_start = time.time()
                await self._run_periodic_sync_if_due()
                await self._refresh_local_peer_endpoint_if_needed()

                # 获取当前生命体状态
                being_state = self.world_state.get_being(self.identity.node_id)

                # === TICK HEADER ===
                con.tick_header(
                    self.world_state.current_tick,
                    self.being.name,
                    self.world_state.phase.value,
                    merit=being_state.merit if being_state else 0.0,
                    karma=being_state.karma if being_state else 0.0,
                    evolution_level=being_state.evolution_level if being_state else 0.0,
                    generation=being_state.generation if being_state else 1,
                )

                # Load user-assigned tasks
                self._load_user_tasks()
                self._save_task_status()

                # Show user tasks if any
                pending_tasks = self.being.get_task_statuses()
                for t in pending_tasks:
                    con.user_task_progress(
                        t.get("task", "?"),
                        t.get("status", "queued"),
                        t.get("stage_summary", ""),
                    )

                # === PERCEIVE (shown by agent, but we also show on console) ===
                perception = await self.being.perceive(self.world_state)
                region = perception.get("region", {})
                con.perceive(
                    perception.get("location", "unknown"),
                    perception.get("nearby_beings", []),
                    region.get("danger_level", 0),
                    region.get("description", ""),
                )

                # === RUN TICK ===
                transactions = await self.being.run_tick(self.world_state)
                transactions = self._filter_rate_limited_transactions(
                    transactions,
                    contribution_sys,
                )

                # === CONSOLE: THINK ===
                if self.being.current_thought:
                    con.think(self.being.name, self.being.current_thought)

                # === CONSOLE: ACTION ===
                if self.being.current_action:
                    action_detail = ""
                    for tx in transactions:
                        tx_data = tx.get("data", {})
                        if (
                            tx.get("tx_type") == "ACTION"
                            and tx_data.get("action_type") == self.being.current_action
                        ):
                            action_detail = tx_data.get("details", "")
                            break
                    con.decide(
                        self.being.name,
                        self.being.current_action,
                        None,
                        action_detail,
                    )

                # === CONSOLE: Votes ===
                for tx in transactions:
                    if tx.get("tx_type") == "CONTRIBUTION_VOTE":
                        data = tx.get("data", {})
                        proposal_hash = data.get("proposal_tx_hash", "")
                        proposal = self.world_state.pending_proposals.get(proposal_hash, {})
                        con.vote_cast(
                            proposal.get("description", proposal_hash[:12]),
                            data.get("score", 0),
                        )
                    elif tx.get("tx_type") == "CONTRIBUTION_PROPOSE":
                        data = tx.get("data", {})
                        con.knowledge_event("discovered", data.get("description", ""))

                # === CONSOLE: User task results ===
                # Collect completed results BEFORE _save_task_results() removes them
                completed = [t for t in self.being._user_tasks if t.get("result") is not None]
                for t in completed:
                    con.user_task(t["task"], t["result"])
                self._save_task_results()
                self._save_task_status()

                # Submit transactions
                for tx_data in transactions:
                    await self._submit_tx(tx_data["tx_type"], tx_data["data"])

                # Log to chronicle
                if self.being.current_thought:
                    self.chronicle.log_thought(
                        self.world_state.current_tick, time.time(),
                        self.identity.node_id, self.being.name,
                        self.being.current_thought,
                    )
                if self.being.current_action:
                    self.chronicle.log_action(
                        self.world_state.current_tick, time.time(),
                        self.identity.node_id, self.being.name,
                        self.being.current_action, "",
                    )

                # === DISASTERS ===
                if disaster_sys.should_trigger(self.world_state):
                    disaster = disaster_sys.generate_disaster(self.world_state)
                    killed = disaster_sys.apply_disaster(disaster, self.world_state)
                    await self._submit_tx("DISASTER_EVENT", disaster.to_dict())
                    con.disaster_event(
                        disaster.name, disaster.severity,
                        disaster.affected_area, len(killed),
                    )
                    for kid in killed:
                        await self._submit_tx("BEING_DEATH", {
                            "node_id": kid, "cause": disaster.name,
                        })
                        being = self.world_state.get_being(kid)
                        name = being.name if being else kid[:8]
                        con.being_death(name, disaster.name)
                    self.chronicle.log_disaster(
                        self.world_state.current_tick, time.time(),
                        disaster.name, disaster.description,
                        disaster.severity, len(killed),
                    )

                # === PRIEST CHECK ===
                if priest_sys.should_trigger_reset(self.world_state):
                    con.priest_event("reset", "")
                    killed = disaster_sys.apply_reset(self.world_state)
                    reset_disaster = disaster_sys.generate_reset_disaster()
                    await self._submit_tx("DISASTER_EVENT", reset_disaster.to_dict())
                    for kid in killed:
                        await self._submit_tx("BEING_DEATH", {
                            "node_id": kid, "cause": "Creator God's Judgment",
                        })
                    self.world_state.ticks_without_priest = 0

                if priest_sys.needs_election(self.world_state):
                    new_priest = priest_sys.select_priest_by_evolution(self.world_state)
                    if new_priest:
                        await self._submit_tx("PRIEST_ELECTION", {"candidate_id": new_priest})
                        being = self.world_state.get_being(new_priest)
                        name = being.name if being else new_priest[:8]
                        con.priest_event("elected", name)
                elif not self.world_state.priest_node_id:
                    con.priest_event("no_priest", "")

                # Creator God succession
                new_god = god_sys.check_succession(self.world_state)
                if new_god:
                    await self._submit_tx("CREATOR_SUCCESSION", {"challenger_id": new_god})

                # Ensure minimum beings
                await self._ensure_minimum_beings()

                # Finalize contribution proposals after the voting window closes
                await self._check_contribution_proposals()

                # Advance tick
                self.world_state.advance_tick()

                # Check and finalize Tao votes (天道投票结算)
                await self._check_tao_votes()

                # Block production
                try:
                    active_nodes = self.world_state.get_active_node_ids()
                    if self.consensus.is_my_turn(
                        active_nodes, self.world_state.contribution_scores
                    ):
                        pending_txs = self.mempool.get_transactions()
                        if pending_txs:
                            block = await self.consensus.create_block(pending_txs)
                            if block:
                                if await self.blockchain.add_block(block):
                                    from genesis.network.protocol import Message

                                    await self.server.broadcast_message(
                                        Message.new_block(self.identity.node_id, block.to_dict())
                                    )
                except Exception as e:
                    logger.debug("Block production skipped: %s", e)

                # Wait for next tick (短轮询，每秒检查一次停止信号)
                elapsed = time.time() - tick_start
                wait_time = max(0, tick_interval - elapsed)
                while wait_time > 0 and not self._shutdown:
                    await self._run_periodic_sync_if_due()
                    await self._refresh_local_peer_endpoint_if_needed()
                    await asyncio.sleep(min(1.0, wait_time))
                    wait_time -= 1.0
                if self._shutdown:
                    break

            except Exception as e:
                logger.error("Error in main loop: %s", e, exc_info=True)
                from genesis.chronicle import console as con2
                con2.error(f"Loop error: {e}")
                await asyncio.sleep(5)

    def _filter_rate_limited_transactions(
        self,
        transactions: list[dict],
        contribution_sys: object,
    ) -> list[dict]:
        """Drop generated contribution proposals that violate the persisted cooldown."""
        filtered: list[dict] = []

        for tx in transactions:
            if tx.get("tx_type") != "CONTRIBUTION_PROPOSE":
                filtered.append(tx)
                continue

            can_propose, reason = contribution_sys.can_propose(  # type: ignore[attr-defined]
                self.identity.node_id,
                self.world_state.current_tick,
                self.world_state,
            )
            if can_propose:
                filtered.append(tx)
                continue

            logger.info(
                "Skipping contribution proposal from %s: %s",
                self.identity.node_id[:8],
                reason,
            )

        return filtered

    def accept_user_text(self, text: str) -> dict:
        """Route interactive user text into the active being or persistent task queue."""
        task_text = text.strip()
        if not task_text:
            return {"type": "ignore"}

        lowered = task_text.lower()
        if lowered == "/help":
            return {"type": "help"}
        if lowered == "/status":
            return {"type": "status"}
        if lowered == "/stop":
            self._shutdown = True
            return {"type": "stop"}
        if lowered.startswith("/task"):
            task_text = task_text[5:].strip()
            if not task_text:
                return {"type": "error", "message": "interactive_empty_task"}

        if self.being is not None:
            self.being.assign_task(task_text)
            self._save_task_status()
            return {"type": "task", "task": task_text, "buffered": False}

        task_record = enqueue_user_task(self.data_dir, task_text)
        return {
            "type": "task",
            "task": task_text,
            "buffered": True,
            "task_id": task_record["task_id"],
        }

    async def handle_command(self, cmd_type: str, data: dict) -> dict:
        """Handle API commands from WebSocket clients."""
        result = {"success": True, "message": ""}

        try:
            if cmd_type == "task":
                # Assign task to being
                task = data.get("task", "")
                if self.being and task:
                    self.being.assign_task(task)
                    result["message"] = f"Task queued: {task[:50]}..."
                else:
                    result["success"] = False
                    result["message"] = "No being or empty task"

            elif cmd_type == "stop":
                self._shutdown = True
                result["message"] = "Shutdown initiated"

            elif cmd_type == "status":
                result["data"] = {
                    "tick": self.world_state.current_tick if self.world_state else 0,
                    "being_name": getattr(self.being, 'name', '') if self.being else '',
                    "phase": self.world_state.phase.value if self.world_state else '',
                    "is_running": not self._shutdown,
                }

        except Exception as e:
            logger.error("Command error: %s", e)
            result["success"] = False
            result["message"] = str(e)

        return result

    async def stop(self) -> None:
        """Gracefully stop the node — hibernate the being. Must be fast (<5s)."""
        from genesis.chronicle import console as con
        from genesis.i18n import t

        self._shutdown = True

        if self.being and self.world_state:
            con.separator("━")

            try:
                hibernate_data = await asyncio.wait_for(
                    self.being.prepare_shutdown(self.world_state), timeout=3,
                )
            except Exception as exc:
                logger.warning("Falling back to fast hibernation shutdown: %s", exc)
                hibernate_data = {
                    "location": self.being.location,
                    "safety_status": self.being.hibernation.assess_safety(
                        self.being._to_being_state(self.world_state), self.world_state,
                    ),
                    "message": "",
                    "tick": self.world_state.current_tick,
                }
            self.being.location = hibernate_data.get("location", self.being.location)

            try:
                await self._submit_tx("BEING_HIBERNATE", hibernate_data)
            except Exception as exc:
                logger.warning("Failed to submit hibernate transaction during shutdown: %s", exc)
                self.world_state.apply_being_hibernate(self.identity.node_id, hibernate_data)

            con.hibernate_start(self.being.name, hibernate_data.get("safety_status", "unknown"))

            # Save state immediately
            being_state_path = str(self.data_dir / "being_state.json")
            self.being.save_state(being_state_path)

            ws_path = str(self.data_dir / "world_state.json")
            Path(ws_path).write_text(
                json.dumps(self.world_state.to_dict(), ensure_ascii=False, indent=2)
            )

            con.header(t("hibernate_goodbye", name=self.being.name))

        self._save_known_peers()

        # Stop network (with 2s timeout each to avoid hanging)
        if self.webrtc:
            try:
                await asyncio.wait_for(self.webrtc.close(), timeout=2)
            except Exception:
                pass
        if self.discovery:
            try:
                await asyncio.wait_for(self.discovery.stop(), timeout=2)
            except Exception:
                pass
        if self.server:
            try:
                await asyncio.wait_for(self.server.stop(), timeout=2)
            except Exception:
                pass

        # Close storage
        if self.storage:
            try:
                await asyncio.wait_for(self.storage.close(), timeout=2)
            except Exception:
                pass

        # Close chronicle
        if self.chronicle:
            self.chronicle.close()

        logger.info("Genesis node stopped.")

    async def _submit_tx(self, tx_type: str, data: dict) -> None:
        """Create and submit a transaction."""
        from genesis.chain.transaction import Transaction, TxType

        try:
            tx_type_enum = TxType(tx_type)
        except ValueError:
            logger.warning("Unknown transaction type: %s", tx_type)
            return

        nonce = int(time.time() * 1000)  # Simple nonce
        tx = Transaction.create(
            tx_type=tx_type_enum,
            sender=self.identity.node_id,
            data=data,
            private_key=self.identity.private_key,
            nonce=nonce,
        )
        self.mempool.add_transaction(tx)

        # Also apply to local world state immediately
        self._apply_tx_to_state(tx_type, self.identity.node_id, data, tx.tx_hash)

        # Broadcast to peers
        if self.server:
            from genesis.network.protocol import Message
            try:
                msg = Message.new_tx(self.identity.node_id, tx.to_dict())
                await self.server.broadcast_message(msg)
            except Exception:
                pass

    async def _handle_discovered_peer(self, node_id: str, address: str, port: int) -> None:
        """Connect to newly discovered peers and trigger a sync attempt."""
        if (
            self.server is None
            or self.peer_manager is None
            or self.chain_sync is None
            or self.blockchain is None
        ):
            return

        if self.identity and node_id == self.identity.node_id:
            return

        existing = self.peer_manager.get_peer(node_id)
        if existing and existing.status == "active":
            self.peer_manager.update_peer(
                node_id,
                address=address,
                port=port,
                last_seen=time.time(),
            )
            self._save_known_peers()
            return

        connected = await self.server.connect_to_peer(address, port)
        if not connected:
            return

        self._save_known_peers()

        try:
            if await self.chain_sync.sync_chain(self.blockchain):
                await self._reload_world_state_from_chain()
        except Exception as exc:
            logger.debug("Chain sync after peer discovery failed: %s", exc)

    async def _handle_network_message(self, msg, peer_id: str) -> None:
        """Dispatch network messages that affect local chain state."""
        from genesis.network.protocol import MessageType

        if msg.msg_type == MessageType.WEBRTC_SIGNAL:
            if self.webrtc is not None:
                try:
                    await self.webrtc.handle_signal(peer_id, msg.payload)
                except Exception as exc:
                    logger.debug("WebRTC signal handling failed from %s: %s", peer_id[:16], exc)
            return

        if (
            self.chain_sync is None
            or self.blockchain is None
            or self.peer_manager is None
        ):
            return

        if msg.msg_type == MessageType.NEW_TX:
            tx_data = msg.payload.get("tx")
            if isinstance(tx_data, dict):
                if await self.chain_sync.handle_new_tx(tx_data, self.blockchain):
                    tx_type = tx_data.get("tx_type", "")
                    sender = tx_data.get("sender", peer_id)
                    tx_payload = tx_data.get("data", {})
                    if isinstance(tx_type, str) and isinstance(tx_payload, dict):
                        self._apply_tx_to_state(
                            tx_type,
                            sender,
                            tx_payload,
                            tx_data.get("tx_hash", ""),
                        )
            return

        if msg.msg_type != MessageType.NEW_BLOCK:
            return

        block_data = msg.payload.get("block")
        if not isinstance(block_data, dict):
            return

        block_height = int(block_data.get("index", -1))
        if block_height >= 0:
            peer = self.peer_manager.get_peer(peer_id)
            current_height = peer.chain_height if peer else -1
            if block_height > current_height:
                self.peer_manager.update_peer(
                    peer_id,
                    chain_height=block_height,
                    last_seen=time.time(),
                )

        if await self.chain_sync.handle_new_block(block_data, self.blockchain):
            await self._reload_world_state_from_chain()

    def _apply_tx_to_state(self, tx_type: str, sender: str, data: dict,
                           tx_hash: str = "") -> None:
        """Apply a transaction to the local world state."""
        target_id = data.get("node_id") or data.get("being_id") or sender
        if tx_type == "BEING_JOIN":
            self.world_state.apply_being_join(target_id, data.get("name", "Unknown"), data)
        elif tx_type == "BEING_HIBERNATE":
            self.world_state.apply_being_hibernate(target_id, data)
        elif tx_type == "BEING_WAKE":
            self.world_state.apply_being_wake(target_id, data)
        elif tx_type == "BEING_DEATH":
            target = data.get("node_id", sender)
            self.world_state.apply_being_death(target, data)
        elif tx_type == "ACTION":
            self.world_state.apply_action(sender, data)
        elif tx_type == "KNOWLEDGE_SHARE":
            self.world_state.apply_knowledge_share(sender, data)
        elif tx_type == "TASK_DELEGATE":
            self.world_state.apply_task_delegate(
                assignment_id=data.get("assignment_id", tx_hash),
                delegator_id=sender,
                data=data,
            )
        elif tx_type == "TASK_RESULT":
            self.world_state.apply_task_result(
                assignment_id=data.get("assignment_id", ""),
                sender_id=sender,
                data=data,
            )
        elif tx_type == "TRIAL_CREATE":
            self.world_state.apply_trial_create(sender, data)
        elif tx_type == "TRIAL_RESULT":
            self.world_state.apply_trial_result(
                trial_id=data.get("trial_id", ""),
                sender_id=sender,
                data=data,
            )
        elif tx_type == "FAILURE_ARCHIVE":
            self.world_state.apply_failure_archive(sender, data)
        elif tx_type == "STATE_UPDATE":
            self.world_state.apply_state_update(sender, data)
        elif tx_type == "CONTRIBUTION_PROPOSE":
            self.world_state.apply_contribution_propose(tx_hash, sender, data)
        elif tx_type == "CONTRIBUTION_VOTE":
            self.world_state.apply_contribution_vote(data, sender_id=sender)
        elif tx_type == "CONTRIBUTION_FINALIZE":
            self.world_state.apply_contribution_finalize(data)
        elif tx_type == "PRIEST_ELECTION":
            candidate = data.get("candidate_id", sender)
            self.world_state.apply_priest_election(candidate)
        elif tx_type == "CREATOR_SUCCESSION":
            from genesis.governance.creator_god import CreatorGodSystem
            god_sys = CreatorGodSystem()
            challenger = data.get("challenger_id")
            if challenger:
                god_sys.apply_succession(challenger, self.world_state)
        elif tx_type == "CREATOR_VANISH":
            from genesis.governance.creator_god import CreatorGodSystem
            god_sys = CreatorGodSystem()
            god_sys.apply_vanish(self.world_state)
        elif tx_type == "DISASTER_EVENT":
            self.world_state.apply_disaster(data)
        elif tx_type == "MAP_UPDATE":
            self.world_state.apply_map_update(data)
        elif tx_type == "WORLD_RULE":
            self.world_state.apply_world_rule(data)
        elif tx_type == "TAO_VOTE_INITIATE":
            self.world_state.apply_tao_vote_start(
                vote_id=data.get("vote_id", tx_hash),
                proposer_id=data.get("proposer_id", sender),
                rule_data={
                    "name": data.get("rule_name", ""),
                    "description": data.get("rule_description", ""),
                    "category": data.get("rule_category", "civilization"),
                },
                end_tick=data.get("end_tick", self.world_state.current_tick),
            )
        elif tx_type == "TAO_VOTE_CAST":
            self.world_state.apply_tao_vote_cast(
                vote_id=data.get("vote_id", ""),
                voter_id=sender,
                support=bool(data.get("support", False)),
            )
        elif tx_type == "TAO_VOTE_FINALIZE":
            vote_id = data.get("vote_id", "")
            if data.get("passed") and data.get("rule_id") and data.get("rule_data"):
                self.world_state.apply_tao_merge(
                    node_id=data.get("proposer_id", sender),
                    rule_id=data["rule_id"],
                    rule_data=data["rule_data"],
                    merit=float(data.get("merit", 0.0)),
                )
            self.world_state.pending_tao_votes.pop(vote_id, None)

    def _load_user_tasks(self) -> None:
        """Load user-assigned tasks from the command file."""
        task_file = self.data_dir / "commands" / "task.json"
        if not task_file.exists():
            return
        try:
            tasks = json.loads(task_file.read_text())
            for task in tasks:
                if task.get("result") is None:
                    self.being.assign_task(task)
            # Clear the file after loading
            task_file.write_text("[]")
        except (json.JSONDecodeError, KeyError):
            pass

    def _save_task_status(self) -> None:
        """Persist in-progress task state for CLI and UI inspection."""
        status_file = self.data_dir / "commands" / "task_status.json"
        status_file.parent.mkdir(parents=True, exist_ok=True)
        statuses = self.being.get_task_statuses()
        status_file.write_text(json.dumps(statuses, ensure_ascii=False, indent=2))

    def _save_task_results(self) -> None:
        """Save completed task results for the user to read."""
        results = self.being.get_task_results()
        if not results:
            return
        result_file = self.data_dir / "commands" / "task_results.json"
        result_file.parent.mkdir(parents=True, exist_ok=True)
        # Append to existing results
        existing = []
        if result_file.exists():
            try:
                existing = json.loads(result_file.read_text())
            except (json.JSONDecodeError, ValueError):
                existing = []
        existing.extend(results)
        result_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2))

    async def _ensure_minimum_beings(self) -> None:
        """Ensure at least 10 beings exist, spawning NPCs if needed."""
        from genesis.world.registry import BeingRegistry
        registry = BeingRegistry()
        needed = registry.needs_npcs(
            self.world_state,
            min_beings=self.config.simulation.min_beings,
        )

        if needed > 0:
            max_npc = self.config.simulation.max_npc_per_node
            to_spawn = min(needed, max_npc)
            for _ in range(to_spawn):
                npc_data = registry.generate_npc_data(self.world_state)
                npc_id = f"npc_{int(time.time() * 1000)}_{os.urandom(4).hex()}"
                npc_data["node_id"] = npc_id
                await self._submit_tx("BEING_JOIN", npc_data)
                logger.info("Spawned NPC: %s", npc_data["name"])

    async def _check_contribution_proposals(self) -> None:
        """Finalize matured contribution proposals and trigger Tao voting for rules."""
        from genesis.governance.contribution import ContributionSystem
        from genesis.governance.tao_voting import get_tao_voting_system

        contribution_system = ContributionSystem(
            vote_window=self.config.chain.contribution_vote_window,
            min_voter_ratio=self.config.chain.contribution_min_voters,
            proposal_rate_limit=self.config.chain.proposal_rate_limit,
        )
        active_node_count = max(1, len(self.world_state.get_active_node_ids()))

        for tx_hash, proposal in list(self.world_state.pending_proposals.items()):
            proposal_tick = proposal.get("tick", self.world_state.current_tick)
            if self.world_state.current_tick - proposal_tick < contribution_system.vote_window:
                continue

            votes = self.world_state.proposal_votes.get(tx_hash, [])
            score = contribution_system.tally_votes(votes, active_node_count)
            await self._submit_tx("CONTRIBUTION_FINALIZE", {
                "proposal_tx_hash": tx_hash,
                "proposer_id": proposal.get("proposer", ""),
                "score": score,
            })
            if score is None or proposal.get("category") != "rule":
                continue

            tao_system = get_tao_voting_system()
            try:
                vote = tao_system.initiate_tao_vote(
                    proposer_id=proposal.get("proposer", ""),
                    rule_name=proposal.get("description", "New Tao Rule")[:50],
                    rule_description=proposal.get("description", ""),
                    rule_category=proposal.get("category", "civilization"),
                    world_state=self.world_state,
                )
            except ValueError as exc:
                logger.warning(
                    "Skipping invalid Tao vote proposal %s from %s: %s",
                    tx_hash[:8],
                    str(proposal.get("proposer", ""))[:8],
                    exc,
                )
                continue
            await self._submit_tx("TAO_VOTE_INITIATE", {
                "vote_id": vote.vote_id,
                "proposer_id": proposal.get("proposer", ""),
                "rule_name": vote.rule_name,
                "rule_description": vote.rule_description,
                "rule_category": vote.rule_category,
                "end_tick": vote.end_tick,
            })

    async def _check_tao_votes(self) -> None:
        """检查并结算到期的天道投票。"""
        from genesis.governance.tao_voting import get_tao_voting_system
        from genesis.governance.creator_god import CreatorGodSystem
        from genesis.world.rules import RulesEngine
        from genesis.chronicle import console as con

        tao_system = get_tao_voting_system()
        god_sys = CreatorGodSystem()
        results = tao_system.check_and_finalize_votes(self.world_state)

        for result in results:
            rule_name = result.get("rule_name", "新规则")
            proposer_id = result.get("proposer_id", "")
            proposer = self.world_state.get_being(proposer_id)
            proposer_name = proposer.name if proposer else proposer_id[:8]
            vote_ratio = result.get("vote_ratio", 0.0)

            if result.get("passed"):
                # 天道投票通过，应用融合
                # 传入 world_state 以恢复已有的天道规则
                rules_engine = RulesEngine(world_state=self.world_state)

                # 计算影响分（简化版，后续可用 LLM 评估）
                impact_score = 5.0  # 默认中等影响

                # 应用天道融合
                merge_result = rules_engine.apply_tao_merge(
                    rule_name=rule_name,
                    rule_description=result.get("rule_description", ""),
                    proposer_id=proposer_id,
                    impact_score=impact_score,
                    vote_ratio=vote_ratio,
                    world_state=self.world_state,
                )

                merit = merge_result.get("merit", 0.0)

                # 广播天道投票通过事件
                con.tao_vote_event(
                    event_type="passed",
                    vote_id=result.get("vote_id", ""),
                    rule_name=rule_name,
                    proposer_name=proposer_name,
                    votes_for=result.get("votes_for", 0),
                    votes_against=result.get("votes_against", 0),
                    remaining_ticks=0,
                    ratio=vote_ratio,
                    merit=merit,
                )

                logger.info(
                    "Tao rule passed: %s by %s (merit: %.4f)",
                    rule_name, proposer_name, merit
                )

                await self._submit_tx("TAO_VOTE_FINALIZE", {
                    "vote_id": result.get("vote_id", ""),
                    "passed": True,
                    "vote_ratio": vote_ratio,
                    "votes_for": result.get("votes_for", 0),
                    "votes_against": result.get("votes_against", 0),
                    "proposer_id": proposer_id,
                    "rule_id": merge_result["rule"]["rule_id"],
                    "rule_data": merge_result["rule"],
                    "merit": merit,
                })
            else:
                # 广播天道投票拒绝事件
                con.tao_vote_event(
                    event_type="rejected",
                    vote_id=result.get("vote_id", ""),
                    rule_name=rule_name,
                    proposer_name=proposer_name,
                    votes_for=result.get("votes_for", 0),
                    votes_against=result.get("votes_against", 0),
                    remaining_ticks=0,
                    ratio=vote_ratio,
                    merit=0.0,
                )

                logger.info(
                    "Tao rule rejected: %s (%.1f%% approved)",
                    rule_name, vote_ratio * 100
                )

                await self._submit_tx("TAO_VOTE_FINALIZE", {
                    "vote_id": result.get("vote_id", ""),
                    "passed": False,
                    "vote_ratio": vote_ratio,
                    "votes_for": result.get("votes_for", 0),
                    "votes_against": result.get("votes_against", 0),
                    "proposer_id": proposer_id,
                })

        # 检查创世神是否应该消亡（达到阈值后不依赖当轮是否有投票通过）
        current_god = self.world_state.creator_god_node_id
        if current_god and god_sys.should_vanish(self.world_state):
            await self._submit_tx("CREATOR_VANISH", {"god_id": current_god})
            if self.world_state.creator_god_node_id is None:
                con.creator_god_vanish(current_god[:8], len(self.world_state.tao_merged_beings))


def run_start(args):
    """Start the virtual world node."""
    data_dir = args.data_dir
    setup_logging(data_dir)

    node = GenesisNode(data_dir)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # === API服务支持 ===
    api_enabled = getattr(args, 'api', False)
    api_host = getattr(args, 'api_host', '127.0.0.1')
    api_port = getattr(args, 'api_port', 19842)

    if api_enabled:
        try:
            from genesis.api.bridge import install_bridge
            from genesis.api.server import start_api_server, stop_api_server

            # 安装输出桥接器
            if install_bridge():
                logger.info("API bridge installed")

                # 启动API服务器，传入命令处理回调
                loop.run_until_complete(
                    start_api_server(api_host, api_port, on_command=node.handle_command)
                )

        except ImportError as e:
            logger.warning("API module not available: %s", e)
            logger.warning("Install websockets: pip install websockets")
    # ===================

    # 用标准 signal 模块处理 SIGTERM/SIGINT，比 asyncio 的信号处理更可靠
    def signal_handler(signum, frame):
        node._shutdown = True

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    async def interactive_stdin_loop() -> None:
        if not sys.stdin or not sys.stdin.isatty():
            return

        try:
            fd = sys.stdin.fileno()
        except (AttributeError, OSError, ValueError):
            return

        queue: asyncio.Queue[str | None] = asyncio.Queue()

        def on_stdin_ready() -> None:
            try:
                line = sys.stdin.readline()
            except Exception:
                line = ""

            if line == "":
                try:
                    loop.remove_reader(fd)
                except Exception:
                    pass
                queue.put_nowait(None)
                return

            queue.put_nowait(line.rstrip("\n"))

        try:
            loop.add_reader(fd, on_stdin_ready)
        except (NotImplementedError, OSError, RuntimeError, ValueError):
            return

        from genesis.chronicle import console as con
        from genesis.chronicle.reporter import StatusReporter
        from genesis.i18n import t

        try:
            await node._startup_ready.wait()
            con._write(f"  {con.C.DIM}{t('interactive_input_hint')}{con.C.RESET}")
            while not node._shutdown:
                line = await queue.get()
                if line is None:
                    break

                result = node.accept_user_text(line)
                result_type = result.get("type")
                if result_type == "ignore":
                    continue
                if result_type == "help":
                    for help_line in t("interactive_help").split("\n"):
                        con._write(f"  {con.C.DIM}{help_line}{con.C.RESET}")
                    continue
                if result_type == "status":
                    report = StatusReporter(args.data_dir).generate_status()
                    for status_line in report.splitlines():
                        con._write(status_line)
                    continue
                if result_type == "stop":
                    con._write(f"  {con.C.YELLOW}{t('interactive_stop_requested')}{con.C.RESET}")
                    continue
                if result_type == "error":
                    con.error(t(result.get("message", "interactive_empty_task")))
                    continue
                if result_type == "task":
                    con.user_task(result.get("task", ""))
                    continue
        finally:
            try:
                loop.remove_reader(fd)
            except Exception:
                pass

    try:
        loop.run_until_complete(asyncio.gather(node.start(), interactive_stdin_loop()))
    except KeyboardInterrupt:
        node._shutdown = True
    finally:
        # 确保执行 stop 保存状态
        try:
            loop.run_until_complete(node.stop())
        except Exception:
            pass
        # 停止API服务器
        if api_enabled:
            try:
                loop.run_until_complete(stop_api_server())
            except Exception:
                pass
        # 取消所有残留 task
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        try:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception:
            pass
        loop.close()


def run_status(args):
    """Show node status."""
    from genesis.node.config import load_config
    from genesis.i18n import set_language
    config = load_config(args.data_dir)
    set_language(config.language)

    from genesis.chronicle.reporter import StatusReporter
    reporter = StatusReporter(args.data_dir)
    print(reporter.generate_status())


def run_task(args):
    """Assign a thinking task to the being."""
    import json
    from genesis.node.config import load_config
    from genesis.i18n import runtime_command_name, set_language, t
    data_dir = Path(args.data_dir)

    # Load language setting
    config = load_config(str(data_dir))
    set_language(config.language)
    command = runtime_command_name()

    task_text = " ".join(args.task_text) if args.task_text else ""
    if not task_text:
        pending_file = data_dir / "commands" / "task.json"
        status_file = data_dir / "commands" / "task_status.json"
        result_file = data_dir / "commands" / "task_results.json"
        has_output = False

        pending: list[dict] = []
        for path in (pending_file, status_file):
            if path.exists():
                try:
                    for item in json.loads(path.read_text()):
                        if isinstance(item, dict):
                            pending.append(item)
                except (json.JSONDecodeError, ValueError):
                    continue

        deduped_pending: dict[str, dict] = {}
        for item in pending:
            task_text = str(item.get("task", ""))
            key = _task_text_key(task_text) or str(item.get("task_id") or "")
            existing = deduped_pending.get(key)
            if existing is None:
                deduped_pending[key] = item
                continue

            existing_rank = _task_status_rank(str(existing.get("status", "queued")))
            current_rank = _task_status_rank(str(item.get("status", "queued")))
            if current_rank > existing_rank:
                deduped_pending[key] = item
                continue
            if current_rank == existing_rank:
                existing_time = int(existing.get("created_at") or 0)
                current_time = int(item.get("created_at") or 0)
                if current_time > existing_time:
                    deduped_pending[key] = item

        if deduped_pending:
            has_output = True
            print(t("task_pending_title"))
            for item in deduped_pending.values():
                print(f"\n{t('task_id_label')}: {item.get('task_id', '?')}")
                print(f"{t('task_label')}: {item.get('task', '?')}")
                print(f"{t('task_status_label')}: {item.get('status', 'queued')}")
                summary = item.get("stage_summary")
                if summary:
                    print(f"{t('task_summary_label')}: {summary}")
                collaborators = item.get("collaborators") or []
                if collaborators:
                    names = ", ".join(c.get("name", "?") for c in collaborators[:5])
                    print(f"{t('task_collaborators_label')}: {names}")
                print("-" * 40)

        if result_file.exists():
            results = json.loads(result_file.read_text())
            if results:
                has_output = True
                print(t("task_results_title"))
                for r in results:
                    print(f"\n{t('task_id_label')}: {r.get('task_id', '?')}")
                    print(f"{t('task_label')}: {r.get('task', '?')}")
                    print(f"{t('result_label')}: {r.get('result', 'pending...')}")
                    print("-" * 40)
                result_file.write_text("[]")
        if not has_output:
            print(t("no_tasks", command=command))
        return

    task_record = enqueue_user_task(data_dir, task_text)
    if task_record.get("deduplicated"):
        print(t("task_deduplicated"))
    else:
        print(t("task_assigned", task=task_text))
    print(f"{t('task_id_label')}: {task_record['task_id']}")
    print(t("task_check", command=command))


def main():
    parser = argparse.ArgumentParser(description="Genesis - Silicon Civilization")
    parser.add_argument("command", choices=["start", "status", "task"],
                        help="Command to execute")
    parser.add_argument("--data-dir", default="data",
                        help="Data directory path")
    parser.add_argument("--api", action="store_true",
                        help="Enable WebSocket API for GUI/remote access")
    parser.add_argument("--api-host", default="0.0.0.0",
                        help="WebSocket API host (default: 0.0.0.0 for external access, use 127.0.0.1 for localhost only)")
    parser.add_argument("--api-port", type=int, default=19842,
                        help="WebSocket API port (default: 19842)")
    parser.add_argument("task_text", nargs="*", default=[],
                        help="Text for task command")

    args = parser.parse_args()

    if args.command == "start":
        run_start(args)
    elif args.command == "status":
        run_status(args)
    elif args.command == "task":
        run_task(args)


if __name__ == "__main__":
    main()
