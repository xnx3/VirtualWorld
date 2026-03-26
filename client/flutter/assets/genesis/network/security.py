"""Network security: rate limiting, banning, message size checks, and
connection diversity enforcement."""

from __future__ import annotations

import time
import threading
import logging

logger = logging.getLogger(__name__)


class NetworkSecurity:
    """Stateful security checks for incoming P2P connections and messages.

    All public methods are thread-safe.
    """

    def __init__(self) -> None:
        self._rate_limits: dict[str, list[float]] = {}   # IP -> list of timestamps
        self._banned: dict[str, float] = {}               # IP -> ban_until (epoch)
        self._connection_counts: dict[str, int] = {}      # /24 subnet -> count
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def check_rate_limit(self, ip: str, max_per_minute: int = 60) -> bool:
        """Return True if the request from *ip* should be allowed.

        Uses a sliding-window counter over the last 60 seconds.
        """
        now = time.time()
        window = 60.0

        with self._lock:
            timestamps = self._rate_limits.setdefault(ip, [])
            # Prune entries older than the window.
            timestamps[:] = [t for t in timestamps if now - t < window]
            if len(timestamps) >= max_per_minute:
                return False
            timestamps.append(now)
            return True

    # ------------------------------------------------------------------
    # Banning
    # ------------------------------------------------------------------

    def ban_peer(self, ip: str, duration: float = 300.0) -> None:
        """Ban *ip* for *duration* seconds (default 5 minutes)."""
        with self._lock:
            self._banned[ip] = time.time() + duration
        logger.warning("Banned %s for %.0f seconds", ip, duration)

    def is_banned(self, ip: str) -> bool:
        """Return True if *ip* is currently banned."""
        with self._lock:
            ban_until = self._banned.get(ip)
            if ban_until is None:
                return False
            if time.time() >= ban_until:
                del self._banned[ip]
                return False
            return True

    # ------------------------------------------------------------------
    # Message size
    # ------------------------------------------------------------------

    @staticmethod
    def check_message_size(data: bytes, max_size: int = 1_048_576) -> bool:
        """Return True if *data* is within the allowed size (default 1 MiB)."""
        return len(data) <= max_size

    # ------------------------------------------------------------------
    # Connection diversity
    # ------------------------------------------------------------------

    def record_connection(self, ip: str) -> None:
        """Record a new connection from *ip* for subnet diversity tracking."""
        subnet = self._subnet_of(ip)
        with self._lock:
            self._connection_counts[subnet] = self._connection_counts.get(subnet, 0) + 1

    def check_connection_diversity(self, ip: str, min_subnets: int = 3) -> bool:
        """Return True if accepting a connection from *ip* would not
        over-concentrate connections in a single /24 subnet.

        The check passes if either:
          - We already have connections from at least *min_subnets* different subnets, or
          - The subnet of *ip* does not yet dominate (fewer than 50 % of total).
        """
        subnet = self._subnet_of(ip)
        with self._lock:
            total = sum(self._connection_counts.values())
            if total == 0:
                return True
            subnet_count = self._connection_counts.get(subnet, 0)
            unique_subnets = len(self._connection_counts)

            # If we have enough subnets already, allow.
            if unique_subnets >= min_subnets:
                return True
            # If this subnet would become >50 % of connections, deny.
            if total > 0 and (subnet_count + 1) / (total + 1) > 0.5:
                return False
            return True

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        """Remove expired bans and stale rate-limit entries."""
        now = time.time()
        window = 60.0

        with self._lock:
            # Expired bans.
            expired = [ip for ip, until in self._banned.items() if now >= until]
            for ip in expired:
                del self._banned[ip]

            # Stale rate-limit buckets.
            empty: list[str] = []
            for ip, timestamps in self._rate_limits.items():
                timestamps[:] = [t for t in timestamps if now - t < window]
                if not timestamps:
                    empty.append(ip)
            for ip in empty:
                del self._rate_limits[ip]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _subnet_of(ip: str) -> str:
        """Return the /24 subnet prefix of an IPv4 address.

        For non-IPv4 addresses, returns the address unchanged.
        """
        parts = ip.split(".")
        if len(parts) == 4:
            return ".".join(parts[:3])
        return ip
