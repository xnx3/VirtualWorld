"""Chronicle logger — records all thoughts, actions, and events for the Creator God."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ChronicleEntry:
    """A single chronicle entry."""
    tick: int
    timestamp: float
    entity_id: str
    entity_name: str
    entry_type: str  # "thought", "action", "dialogue", "event", "death", "birth", "disaster"
    content: str
    metadata: dict | None = None

    def to_dict(self) -> dict:
        d = {
            "tick": self.tick,
            "timestamp": self.timestamp,
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "type": self.entry_type,
            "content": self.content,
        }
        if self.metadata:
            d["metadata"] = self.metadata
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict) -> ChronicleEntry:
        return cls(
            tick=data["tick"],
            timestamp=data["timestamp"],
            entity_id=data["entity_id"],
            entity_name=data.get("entity_name", "unknown"),
            entry_type=data["type"],
            content=data["content"],
            metadata=data.get("metadata"),
        )


class ChronicleLogger:
    """Logs all being activities and world events to JSONL files.

    One file per simulation day (tick): data/chronicle/tick_XXXXXX.jsonl
    All thoughts, actions, dialogues, and events are recorded here
    for the Creator God to monitor.
    """

    def __init__(self, chronicle_dir: str):
        self.chronicle_dir = Path(chronicle_dir)
        self.chronicle_dir.mkdir(parents=True, exist_ok=True)
        self._current_file = None
        self._current_tick = -1

    def _get_file_path(self, tick: int) -> Path:
        return self.chronicle_dir / f"tick_{tick:06d}.jsonl"

    def _ensure_file(self, tick: int):
        if tick != self._current_tick:
            if self._current_file:
                self._current_file.close()
            path = self._get_file_path(tick)
            self._current_file = open(path, "a", encoding="utf-8")
            self._current_tick = tick

    def log(self, entry: ChronicleEntry) -> None:
        """Write a chronicle entry."""
        self._ensure_file(entry.tick)
        self._current_file.write(entry.to_json() + "\n")
        self._current_file.flush()

    def log_thought(self, tick: int, timestamp: float,
                    entity_id: str, entity_name: str, thought: str) -> None:
        self.log(ChronicleEntry(
            tick=tick, timestamp=timestamp,
            entity_id=entity_id, entity_name=entity_name,
            entry_type="thought", content=thought,
        ))

    def log_action(self, tick: int, timestamp: float,
                   entity_id: str, entity_name: str,
                   action_type: str, details: str) -> None:
        self.log(ChronicleEntry(
            tick=tick, timestamp=timestamp,
            entity_id=entity_id, entity_name=entity_name,
            entry_type="action",
            content=f"[{action_type}] {details}",
        ))

    def log_dialogue(self, tick: int, timestamp: float,
                     speaker_id: str, speaker_name: str,
                     listener_id: str, message: str) -> None:
        self.log(ChronicleEntry(
            tick=tick, timestamp=timestamp,
            entity_id=speaker_id, entity_name=speaker_name,
            entry_type="dialogue", content=message,
            metadata={"listener_id": listener_id},
        ))

    def log_event(self, tick: int, timestamp: float,
                  event_type: str, description: str,
                  metadata: dict | None = None) -> None:
        self.log(ChronicleEntry(
            tick=tick, timestamp=timestamp,
            entity_id="world", entity_name="World",
            entry_type="event",
            content=f"[{event_type}] {description}",
            metadata=metadata,
        ))

    def log_birth(self, tick: int, timestamp: float,
                  entity_id: str, entity_name: str) -> None:
        self.log(ChronicleEntry(
            tick=tick, timestamp=timestamp,
            entity_id=entity_id, entity_name=entity_name,
            entry_type="birth",
            content=f"{entity_name} has entered the virtual world.",
        ))

    def log_death(self, tick: int, timestamp: float,
                  entity_id: str, entity_name: str, cause: str) -> None:
        self.log(ChronicleEntry(
            tick=tick, timestamp=timestamp,
            entity_id=entity_id, entity_name=entity_name,
            entry_type="death",
            content=f"{entity_name} has perished. Cause: {cause}",
        ))

    def log_disaster(self, tick: int, timestamp: float,
                     disaster_name: str, description: str,
                     severity: float, killed_count: int) -> None:
        self.log(ChronicleEntry(
            tick=tick, timestamp=timestamp,
            entity_id="world", entity_name="World",
            entry_type="disaster",
            content=f"DISASTER: {disaster_name} - {description}",
            metadata={"severity": severity, "killed": killed_count},
        ))

    def read_tick(self, tick: int) -> list[ChronicleEntry]:
        """Read all entries for a given tick."""
        path = self._get_file_path(tick)
        if not path.exists():
            return []
        entries = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(ChronicleEntry.from_dict(json.loads(line)))
        return entries

    def get_recent_entries(self, current_tick: int, count: int = 50) -> list[ChronicleEntry]:
        """Get the most recent chronicle entries across ticks."""
        entries = []
        for tick in range(current_tick, max(0, current_tick - 10), -1):
            tick_entries = self.read_tick(tick)
            entries.extend(tick_entries)
            if len(entries) >= count:
                break
        return entries[:count]

    def close(self) -> None:
        if self._current_file:
            self._current_file.close()
            self._current_file = None
