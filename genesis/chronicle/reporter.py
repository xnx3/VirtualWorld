"""Status reporter for vw.sh status command."""

from __future__ import annotations

import json
import os
from pathlib import Path

from genesis.world.state import WorldState


class StatusReporter:
    """Generates status reports for the Creator God."""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)

    def generate_status(self, world_state: WorldState | None = None) -> str:
        """Generate a human-readable status report."""
        lines = []
        lines.append("=" * 50)
        lines.append("  Genesis Status / 虚拟世界状态")
        lines.append("=" * 50)

        # Check if world is running
        pid_file = self.data_dir / "genesis.pid"
        if pid_file.exists():
            pid = pid_file.read_text().strip()
            try:
                os.kill(int(pid), 0)
                lines.append(f"  Status: RUNNING (PID {pid})")
            except (ProcessLookupError, ValueError):
                lines.append("  Status: STOPPED (stale PID file)")
        else:
            lines.append("  Status: STOPPED")

        # Try to load world state from saved file
        if world_state is None:
            state_file = self.data_dir / "being_state.json"
            if state_file.exists():
                try:
                    data = json.loads(state_file.read_text())
                    ws_data = data.get("world_state")
                    if ws_data:
                        world_state = WorldState.from_dict(ws_data)
                except (json.JSONDecodeError, KeyError):
                    pass

        if world_state is None:
            lines.append("")
            lines.append("  No world state available.")
            lines.append("  Run 'genesis.sh start' to begin.")
            lines.append("=" * 50)
            return "\n".join(lines)

        lines.append("")
        lines.append(f"  Phase: {world_state.phase.value}")
        lines.append(f"  Civilization Level: {world_state.civ_level:.3f}")
        lines.append(f"  Current Tick: {world_state.current_tick}")
        lines.append(f"  Total Beings Ever: {world_state.total_beings_ever}")

        # Population
        active = world_state.get_active_beings()
        hibernating = [b for b in world_state.beings.values() if b.status == "hibernating"]
        dead = [b for b in world_state.beings.values() if b.status == "dead"]
        lines.append("")
        lines.append("  Population:")
        lines.append(f"    Active: {len(active)}")
        lines.append(f"    Hibernating: {len(hibernating)}")
        lines.append(f"    Dead: {len(dead)}")

        # Governance
        lines.append("")
        lines.append("  Governance:")
        god_id = world_state.creator_god_node_id
        lines.append(f"    Creator God: {god_id[:12] + '...' if god_id else 'None'}")
        priest_id = world_state.priest_node_id
        lines.append(f"    Priest: {priest_id[:12] + '...' if priest_id else 'None'}")
        if not priest_id:
            lines.append(f"    Ticks without Priest: {world_state.ticks_without_priest}")

        # Knowledge
        lines.append("")
        lines.append(f"  Knowledge Items: {len(world_state.knowledge_corpus)}")

        # Top contributors
        ranking = world_state.get_contribution_ranking()
        if ranking:
            lines.append("")
            lines.append("  Top Contributors:")
            for i, (node_id, score) in enumerate(ranking[:5]):
                lines.append(f"    {i+1}. {node_id[:12]}... - {score:.1f}")

        # Chain info
        chain_db = self.data_dir / "chain.db"
        if chain_db.exists():
            size_mb = chain_db.stat().st_size / (1024 * 1024)
            lines.append("")
            lines.append(f"  Chain DB Size: {size_mb:.1f} MB")

        lines.append("")
        lines.append("=" * 50)
        return "\n".join(lines)

    def generate_being_report(self, being_data: dict) -> str:
        """Generate a report for a specific being."""
        lines = []
        lines.append(f"  Being: {being_data.get('name', 'Unknown')}")
        lines.append(f"  Node ID: {being_data.get('node_id', 'Unknown')[:16]}...")
        lines.append(f"  Status: {being_data.get('status', 'unknown')}")
        lines.append(f"  Location: {being_data.get('location', 'unknown')}")
        lines.append(f"  Evolution: {being_data.get('evolution_level', 0.0):.3f}")
        lines.append(f"  Generation: {being_data.get('generation', 1)}")

        traits = being_data.get("traits", {})
        if traits:
            lines.append("  Traits:")
            for k, v in traits.items():
                bar = "#" * int(v * 20) + "." * (20 - int(v * 20))
                lines.append(f"    {k:15s} [{bar}] {v:.2f}")

        return "\n".join(lines)
