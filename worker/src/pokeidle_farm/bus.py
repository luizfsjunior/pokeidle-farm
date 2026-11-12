"""Barramento de eventos assíncrono, com fila própria por assinante.

- Um assinante lento não trava os outros nem a sessão.
- Fila cheia: descarta o evento mais antigo daquele assinante e registra.
- Exceção num handler: isolada, registrada e reportada via `on_error`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal

from .events import Event

log = logging.getLogger(__name__)

Handler = Callable[[Event], Awaitable[None]]
ErrorCallback = Callable[[str, BaseException], None]
Unsubscribe = Callable[[], Awaitable[None]]


@dataclass
class _Subscriber:
    name: str
    types: frozenset[str] | Literal["*"]
    exclude: frozenset[str]
    handler: Handler
    queue: asyncio.Queue[Event]
    task: asyncio.Task[None] | None = None
    dropped: int = 0
    errors: int = 0
    _done: asyncio.Event = field(default_factory=asyncio.Event)

    def wants(self, event: Event) -> bool:
        if event.type in self.exclude:
            return False
        return self.types == "*" or event.type in self.types


class EventBus:
    def __init__(self, on_error: ErrorCallback | None = None) -> None:
        self._subs: list[_Subscriber] = []
        self._on_error = on_error

    def subscribe(
        self,
        name: str,
        types: set[str] | frozenset[str] | Literal["*"],
        handler: Handler,
        *,
        exclude: set[str] | frozenset[str] = frozenset(),
        maxsize: int = 1000,
    ) -> Unsubscribe:
        sub = _Subscriber(
            name=name,
            types="*" if types == "*" else frozenset(types),
            exclude=frozenset(exclude),
            handler=handler,
            queue=asyncio.Queue(maxsize=maxsize),
        )
        sub.task = asyncio.create_task(self._pump(sub), name=f"bus:{name}")
        self._subs.append(sub)

        async def unsubscribe() -> None:
            if sub in self._subs:
                self._subs.remove(sub)
            await self._drain_and_stop(sub)

        return unsubscribe

    async def publish(self, event: Event) -> None:
        for sub in list(self._subs):
            if not sub.wants(event):
                continue
            if sub.queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    sub.queue.get_nowait()
                    sub.queue.task_done()
                sub.dropped += 1
                log.warning(
                    "bus: fila de %s cheia, evento antigo descartado (%d)", sub.name, sub.dropped
                )
            sub.queue.put_nowait(event)

    async def drain(self) -> None:
        """Espera todos os assinantes processarem o que já está na fila."""
        await asyncio.gather(*(s.queue.join() for s in self._subs))

    async def close(self) -> None:
        subs, self._subs = self._subs, []
        await asyncio.gather(*(self._drain_and_stop(s) for s in subs))

    async def _drain_and_stop(self, sub: _Subscriber) -> None:
        await sub.queue.join()
        if sub.task:
            sub.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sub.task

    async def _pump(self, sub: _Subscriber) -> None:
        while True:
            event = await sub.queue.get()
            try:
                await sub.handler(event)
            except asyncio.CancelledError:
                sub.queue.task_done()
                raise
            except Exception as exc:
                sub.errors += 1
                log.exception("bus: erro no assinante %s com evento %s", sub.name, event.type)
                if self._on_error:
                    self._on_error(sub.name, exc)
            sub.queue.task_done()
