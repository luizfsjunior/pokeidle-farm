"""Plugin de telemetria: grava os eventos brutos no Supabase, em lotes.

Os abates, o consumo de itens e as bolas lançadas não viram uma linha cada: são somados por minuto e
gravados em kill_minute quando o minuto fecha (kill_minutes.py, docs/design/retencao-eventos.md). O
`action.sent` das ações de alto volume (QUIET_ACTIONS) não é gravado.

Se o banco falhar, guarda as linhas num buffer local (JSONL, um arquivo por tabela) e reenvia
depois, para não perder evento por queda de rede.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, ClassVar

from ..events import NOT_PERSISTED, QUIET_ACTIONS, Event, utcnow
from ..kill_minutes import AGGREGATED, KillMinutes
from .base import Plugin, PluginContext


class TelemetryPlugin(Plugin):
    name: ClassVar[str] = "telemetry"
    description: ClassVar[str] = "Grava os eventos brutos e os abates por minuto no banco"
    subscribes = "*"
    excludes: ClassVar[set[str]] = set(NOT_PERSISTED)
    queue_size: ClassVar[int] = 10_000
    always_on: ClassVar[bool] = True

    async def start(self, ctx: PluginContext) -> None:
        await super().start(ctx)
        self._batch: list[dict[str, Any]] = []
        self._minutes = KillMinutes()
        self._lock = asyncio.Lock()
        self._batch_size = ctx.settings.telemetry_batch_size
        self._flush_s = ctx.settings.telemetry_flush_s
        base = Path(ctx.settings.telemetry_buffer_path)
        self._buffer = base.with_suffix(f".{ctx.account_id}.jsonl")
        self._buffer_minutes = base.with_suffix(f".{ctx.account_id}.minutes.jsonl")
        self._timer = asyncio.create_task(self._periodic_flush())

    async def on_event(self, event: Event) -> None:
        if event.type in AGGREGATED:
            self._minutes.add(event)
            return
        if event.type == "action.sent" and event.data.get("action") in QUIET_ACTIONS:
            return
        self._batch.append(event.to_row())
        if len(self._batch) >= self._batch_size:
            await self.flush()

    async def flush(self, *, all_minutes: bool = False) -> None:
        """Grava o lote de eventos e os minutos fechados (todos, com `all_minutes`)."""
        async with self._lock:
            rows, self._batch = self._batch, []
            minutes = self._minutes.take(None if all_minutes else utcnow())
            await self._send(self._buffer, rows, self.ctx.store.insert_events, "eventos")
            await self._send(
                self._buffer_minutes,
                minutes,
                self.ctx.store.insert_kill_minutes,
                "minutos de abate",
            )

    async def _send(
        self,
        buffer: Path,
        rows: list[dict[str, Any]],
        insert: Callable[[list[dict[str, Any]]], Awaitable[None]],
        what: str,
    ) -> None:
        pending = self._read_buffer(buffer)
        to_send = pending + rows
        if not to_send:
            return
        try:
            await insert(to_send)
        except Exception as exc:
            self.ctx.log.warning(
                "telemetria: falha ao gravar %d %s (%r); indo para o buffer local",
                len(to_send),
                what,
                exc,
            )
            self._write_buffer(buffer, to_send)
            return
        if pending:
            self._clear_buffer(buffer)

    async def stop(self) -> None:
        self._timer.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._timer
        await self.flush(all_minutes=True)

    async def _periodic_flush(self) -> None:
        while True:
            await asyncio.sleep(self._flush_s)
            await self.flush()

    @staticmethod
    def _read_buffer(buffer: Path) -> list[dict[str, Any]]:
        if not buffer.exists():
            return []
        with buffer.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    @staticmethod
    def _clear_buffer(buffer: Path) -> None:
        buffer.unlink(missing_ok=True)

    @staticmethod
    def _write_buffer(buffer: Path, rows: list[dict[str, Any]]) -> None:
        buffer.parent.mkdir(parents=True, exist_ok=True)
        # reescreve o buffer inteiro (pendentes + novos): evita duplicar linhas
        tmp = buffer.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        tmp.replace(buffer)
