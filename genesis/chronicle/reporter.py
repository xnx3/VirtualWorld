"""Status reporter for genesis.sh status command."""

from __future__ import annotations

import json
import os
from pathlib import Path

from genesis.i18n import t
from genesis.world.state import WorldState


class StatusReporter:
    """Generates status reports for the Creator God."""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)

    def generate_status(self, world_state: WorldState | None = None) -> str:
        """Generate a human-readable status report."""
        lines = []
        lines.append("=" * 50)
        lines.append(f"  {t('status_title')}")
        lines.append("=" * 50)

        # Check if world is running
        pid_file = self.data_dir / "genesis.pid"
        if pid_file.exists():
            pid = pid_file.read_text().strip()
            try:
                os.kill(int(pid), 0)
                lines.append(f"  {t('status_running', pid=pid)}")
            except (ProcessLookupError, ValueError):
                lines.append(f"  {t('status_stopped_stale')}")
        else:
            lines.append(f"  {t('status_stopped')}")

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
            lines.append(f"  {t('no_world_state')}")
            lines.append(f"  {t('run_start_hint')}")
            lines.append("=" * 50)
            return "\n".join(lines)

        lines.append("")
        lines.append(f"  {t('phase_label')}: {world_state.phase.value}")
        lines.append(f"  {t('civ_level')}: {world_state.civ_level:.3f}")
        lines.append(f"  {t('current_tick')}: {world_state.current_tick}")
        lines.append(f"  {t('total_beings')}: {world_state.total_beings_ever}")

        # Population
        active = world_state.get_active_beings()
        hibernating = [b for b in world_state.beings.values() if b.status == "hibernating"]
        dead = [b for b in world_state.beings.values() if b.status == "dead"]
        lines.append("")
        lines.append(f"  {t('population')}:")
        lines.append(f"    {t('active')}: {len(active)}")
        lines.append(f"    {t('hibernating')}: {len(hibernating)}")
        lines.append(f"    {t('dead')}: {len(dead)}")

        # Governance
        lines.append("")
        lines.append(f"  {t('governance')}:")
        god_id = world_state.creator_god_node_id
        lines.append(f"    {t('creator_god')}: {god_id[:12] + '...' if god_id else 'None'}")
        priest_id = world_state.priest_node_id
        lines.append(f"    {t('priest')}: {priest_id[:12] + '...' if priest_id else 'None'}")
        if not priest_id:
            lines.append(f"    {t('ticks_no_priest')}: {world_state.ticks_without_priest}")

        # Knowledge
        lines.append("")
        lines.append(f"  {t('knowledge_items')}: {len(world_state.knowledge_corpus)}")

        # Top contributors
        ranking = world_state.get_contribution_ranking()
        if ranking:
            lines.append("")
            lines.append(f"  {t('top_contributors')}:")
            for i, (node_id, score) in enumerate(ranking[:5]):
                lines.append(f"    {i+1}. {node_id[:12]}... - {score:.1f}")

        # Chain info
        chain_db = self.data_dir / "chain.db"
        if chain_db.exists():
            size_mb = chain_db.stat().st_size / (1024 * 1024)
            lines.append("")
            lines.append(f"  {t('chain_db_size')}: {size_mb:.1f} MB")

        lines.append("")
        lines.append("=" * 50)
        return "\n".join(lines)
