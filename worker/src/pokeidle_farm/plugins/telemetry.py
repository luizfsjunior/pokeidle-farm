"""Plugin de telemetria: grava os eventos brutos no Supabase, em lotes.

Se o banco falhar, guarda os eventos num buffer local (JSONL) e reenvia
depois, para não perder evento por queda de rede.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path
from typing import Any, ClassVar

from ..events import NOT_PERSISTED, Event
from .base import Plugin, PluginContext


class TelemetryPlugin(Plugin):
    name: ClassVar[str] = "telemetry"
    description: ClassVar[str] = "Grava todos os eventos brutos no banco"
    subscribes = "*"
    excludes: ClassVar[set[str]] = set(NOT_PERSISTED)
    queue_size: ClassVar[int] = 10_000
    always_on: ClassVar[bool] = True

    async def start(self, ctx: PluginContext) -> None:
        await super().start(ctx)
        self._batch: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._batch_size = ctx.settings.telemetry_batch_size
        self._flush_s = ctx.settings.telemetry_flush_s
        self._buffer = Path(ctx.settings.telemetry_buffer_path).with_suffix(
            f".{ctx.account_id}.jsonl"
        )
        self._timer = asyncio.create_task(self._periodic_flush())

    async def on_event(self, event: Event) -> None:
        self._batch.append(event.to_row())
        if len(self._batch) >= self._batch_size:
            await self.flush()

    async def flush(self) -> None:
        async with self._lock:
            rows, self._batch = self._batch, []
            pending = self._read_buffer()
            to_send = pending + rows
            if not to_send:
                return
            try:
                await self.ctx.store.insert_events(to_send)
            except Exception as exc:
                self.ctx.log.warning(
                    "telemetria: falha ao gravar %d eventos (%r); indo para o buffer local",
                    len(to_send),
                    exc,
                )
                self._write_buffer(to_send)
                return
            if pending:
                self._buffer.unlink(missing_ok=True)

    async def stop(self) -> None:
        self._timer.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._timer
        await self.flush()

    async def _periodic_flush(self) -> None:
        while True:
            await asyncio.sleep(self._flush_s)
            await self.flush()

    def _read_buffer(self) -> list[dict[str, Any]]:
        if not self._buffer.exists():
            return []
        with self._buffer.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def _write_buffer(self, rows: list[dict[str, Any]]) -> None:
        self._buffer.parent.mkdir(parents=True, exist_ok=True)
        # reescreve o buffer inteiro (pendentes + novos): evita duplicar linhas
        tmp = self._buffer.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        tmp.replace(self._buffer)
