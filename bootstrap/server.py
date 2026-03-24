"""Genesis Bootstrap Server

轻量级节点发现服务，帮助不同网络的节点互相找到彼此。
无需数据库，内存存储，自动清理离线节点。

部署:
    pip install aiohttp
    python server.py --port 8765

API:
    POST /register  - 节点注册/续约
    GET  /peers     - 获取活跃节点列表
    GET  /health    - 健康检查
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from dataclasses import dataclass, field, asdict

from aiohttp import web

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [bootstrap] %(levelname)s: %(message)s",
)
logger = logging.getLogger("bootstrap")

# 节点超时时间（秒）：超过此时间未续约则视为离线
NODE_TTL = 300  # 5 分钟

# 每个 IP 最多注册节点数（Sybil 初步防护）
MAX_NODES_PER_IP = 3

# 每次返回的最大节点数
MAX_PEERS_RETURNED = 100


@dataclass
class NodeEntry:
    node_id: str
    ip: str
    port: int
    public_key: str
    last_seen: float = field(default_factory=time.time)
    genesis_version: str = "0.1"

    def is_alive(self) -> bool:
        return time.time() - self.last_seen < NODE_TTL

    def to_peer_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "address": self.ip,
            "port": self.port,
            "public_key": self.public_key,
        }


class BootstrapRegistry:
    """内存节点注册表，线程安全。"""

    def __init__(self):
        self._nodes: dict[str, NodeEntry] = {}  # node_id -> NodeEntry
        self._ip_count: dict[str, int] = {}     # ip -> count

    def register(self, node_id: str, ip: str, port: int,
                 public_key: str = "") -> tuple[bool, str]:
        """注册或续约节点。返回 (success, message)。"""
        # 基本字段验证
        if not node_id or len(node_id) > 128:
            return False, "Invalid node_id"
        if not (1 <= port <= 65535):
            return False, "Invalid port"
        if len(public_key) > 256:
            return False, "Invalid public_key"

        existing = self._nodes.get(node_id)

        if existing:
            # 续约
            existing.last_seen = time.time()
            existing.port = port
            logger.debug("Renewed: %s from %s:%d", node_id[:16], ip, port)
            return True, "renewed"

        # 新注册 — 检查 IP 限制
        ip_count = self._ip_count.get(ip, 0)
        if ip_count >= MAX_NODES_PER_IP:
            logger.warning("IP %s exceeded max nodes (%d)", ip, MAX_NODES_PER_IP)
            return False, f"Too many nodes from this IP (max {MAX_NODES_PER_IP})"

        entry = NodeEntry(
            node_id=node_id, ip=ip, port=port, public_key=public_key,
        )
        self._nodes[node_id] = entry
        self._ip_count[ip] = ip_count + 1
        logger.info("Registered: %s from %s:%d", node_id[:16], ip, port)
        return True, "registered"

    def get_peers(self, exclude_node_id: str = "") -> list[dict]:
        """获取活跃节点列表，排除请求者自身。"""
        self._cleanup()
        peers = [
            entry.to_peer_dict()
            for entry in self._nodes.values()
            if entry.is_alive() and entry.node_id != exclude_node_id
        ]
        # 最新活跃的排前面
        peers.sort(
            key=lambda p: self._nodes[p["node_id"]].last_seen,
            reverse=True,
        )
        return peers[:MAX_PEERS_RETURNED]

    def stats(self) -> dict:
        self._cleanup()
        alive = sum(1 for e in self._nodes.values() if e.is_alive())
        return {
            "total_registered": len(self._nodes),
            "alive": alive,
            "unique_ips": len(self._ip_count),
        }

    def _cleanup(self) -> None:
        """清理离线节点。"""
        dead = [nid for nid, e in self._nodes.items() if not e.is_alive()]
        for nid in dead:
            entry = self._nodes.pop(nid)
            ip_count = self._ip_count.get(entry.ip, 1)
            if ip_count <= 1:
                self._ip_count.pop(entry.ip, None)
            else:
                self._ip_count[entry.ip] = ip_count - 1
        if dead:
            logger.info("Cleaned up %d offline nodes", len(dead))


registry = BootstrapRegistry()


# ---------------------------------------------------------------------------
# HTTP handlers
# ---------------------------------------------------------------------------

async def handle_register(request: web.Request) -> web.Response:
    """POST /register — 节点注册/续约。"""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    node_id = str(data.get("node_id", "")).strip()
    port = int(data.get("port", 0))
    public_key = str(data.get("public_key", "")).strip()

    # 从请求头或字段获取 IP
    ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.remote
        or "0.0.0.0"
    )

    success, message = registry.register(node_id, ip, port, public_key)
    if success:
        return web.json_response({"status": message, "node_id": node_id})
    else:
        return web.json_response({"error": message}, status=429)


async def handle_peers(request: web.Request) -> web.Response:
    """GET /peers — 获取活跃节点列表。"""
    exclude = request.rel_url.query.get("exclude", "")
    peers = registry.get_peers(exclude_node_id=exclude)
    return web.json_response({"peers": peers, "count": len(peers)})


async def handle_health(request: web.Request) -> web.Response:
    """GET /health — 健康检查。"""
    stats = registry.stats()
    stats["status"] = "ok"
    stats["timestamp"] = time.time()
    return web.json_response(stats)


# ---------------------------------------------------------------------------
# Periodic cleanup task
# ---------------------------------------------------------------------------

async def cleanup_task() -> None:
    """每分钟清理一次离线节点。"""
    while True:
        await asyncio.sleep(60)
        registry._cleanup()


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/register", handle_register)
    app.router.add_get("/peers", handle_peers)
    app.router.add_get("/health", handle_health)
    # cleanup_task is started manually in _run(), not via on_startup
    return app


def main():
    parser = argparse.ArgumentParser(description="Genesis Bootstrap Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    logger.info("Genesis Bootstrap Server starting on %s:%d", args.host, args.port)
    logger.info("Node TTL: %ds | Max per IP: %d", NODE_TTL, MAX_NODES_PER_IP)

    async def _run():
        app = create_app()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, args.host, args.port)
        await site.start()
        logger.info("Bootstrap server running on http://%s:%d", args.host, args.port)
        # Start cleanup task
        asyncio.create_task(cleanup_task())
        try:
            while True:
                await asyncio.sleep(10)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await runner.cleanup()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
