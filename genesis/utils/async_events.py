"""Small asyncio-compatible primitives that do not require a loop at construction."""

from __future__ import annotations

import asyncio


class LazyAsyncEvent:
    """An ``asyncio.Event``-like primitive safe to construct outside a running loop."""

    def __init__(self) -> None:
        self._flag = False
        self._waiters: list[asyncio.Future[bool]] = []

    def is_set(self) -> bool:
        return self._flag

    def set(self) -> None:
        if self._flag:
            return
        self._flag = True
        for waiter in list(self._waiters):
            if not waiter.done():
                waiter.set_result(True)
        self._waiters.clear()

    async def wait(self) -> bool:
        if self._flag:
            return True

        loop = asyncio.get_running_loop()
        waiter: asyncio.Future[bool] = loop.create_future()
        self._waiters.append(waiter)
        try:
            await waiter
            return True
        finally:
            if waiter in self._waiters:
                self._waiters.remove(waiter)
