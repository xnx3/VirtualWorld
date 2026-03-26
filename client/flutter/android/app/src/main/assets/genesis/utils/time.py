"""Virtual-world time management.

The simulation is driven by discrete *ticks*.  A configurable number of ticks
make up an *epoch*.  ``WorldClock`` keeps track of both and can map any tick
to a virtual ``datetime``.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field


# Default virtual-time origin: 0001-01-01T00:00:00
_EPOCH_ORIGIN = _dt.datetime(1, 1, 1, tzinfo=_dt.timezone.utc)

# One tick equals this many virtual seconds (default: 1 virtual day per tick).
_DEFAULT_SECONDS_PER_TICK = 86_400  # 1 day

# Ticks per epoch (default 100).
_DEFAULT_TICKS_PER_EPOCH = 100


@dataclass
class WorldClock:
    """Tracks simulation time in ticks and epochs.

    Parameters:
        ticks_per_epoch:   Number of ticks in one epoch.
        seconds_per_tick:  Virtual seconds represented by a single tick.
        origin:            The virtual datetime corresponding to tick 0.
    """

    ticks_per_epoch: int = _DEFAULT_TICKS_PER_EPOCH
    seconds_per_tick: int = _DEFAULT_SECONDS_PER_TICK
    origin: _dt.datetime = field(default_factory=lambda: _EPOCH_ORIGIN)
    _current_tick: int = field(default=0, init=False, repr=False)

    # -- tick / epoch queries ------------------------------------------------

    @property
    def current_tick(self) -> int:
        """Return the current tick number (0-based)."""
        return self._current_tick

    @property
    def current_epoch(self) -> int:
        """Return the current epoch (0-based)."""
        return self._current_tick // self.ticks_per_epoch

    @property
    def tick_in_epoch(self) -> int:
        """Return the tick offset within the current epoch."""
        return self._current_tick % self.ticks_per_epoch

    # -- advancing time ------------------------------------------------------

    def advance(self, n: int = 1) -> int:
        """Advance the clock by *n* ticks and return the new tick number.

        Raises ``ValueError`` if *n* is not positive.
        """
        if n < 1:
            raise ValueError("Tick advancement must be positive")
        self._current_tick += n
        return self._current_tick

    def set_tick(self, tick: int) -> None:
        """Jump to an absolute *tick* value.

        Raises ``ValueError`` if *tick* is negative.
        """
        if tick < 0:
            raise ValueError("Tick cannot be negative")
        self._current_tick = tick

    # -- virtual datetime mapping --------------------------------------------

    def tick_to_datetime(self, tick: int | None = None) -> _dt.datetime:
        """Map a tick number to a virtual ``datetime``.

        If *tick* is ``None``, the current tick is used.
        """
        if tick is None:
            tick = self._current_tick
        delta = _dt.timedelta(seconds=tick * self.seconds_per_tick)
        return self.origin + delta

    @property
    def now(self) -> _dt.datetime:
        """Virtual "now" -- shorthand for ``tick_to_datetime()``."""
        return self.tick_to_datetime()

    # -- serialisation helpers -----------------------------------------------

    def to_dict(self) -> dict:
        """Serialize clock state to a plain dict."""
        return {
            "current_tick": self._current_tick,
            "ticks_per_epoch": self.ticks_per_epoch,
            "seconds_per_tick": self.seconds_per_tick,
            "origin": self.origin.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> WorldClock:
        """Restore a ``WorldClock`` from a dict produced by :meth:`to_dict`."""
        clock = cls(
            ticks_per_epoch=data.get("ticks_per_epoch", _DEFAULT_TICKS_PER_EPOCH),
            seconds_per_tick=data.get("seconds_per_tick", _DEFAULT_SECONDS_PER_TICK),
            origin=_dt.datetime.fromisoformat(data["origin"]) if "origin" in data else _EPOCH_ORIGIN,
        )
        clock._current_tick = data.get("current_tick", 0)
        return clock
