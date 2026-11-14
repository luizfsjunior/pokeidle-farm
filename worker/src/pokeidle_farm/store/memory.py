"""Store em memória: desenvolvimento sem Supabase e testes."""

from __future__ import annotations

import time
from dataclasses import replace
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from .base import AccountRecord, CommandRecord, TokenRecord


class MemoryStore:
    def __init__(self, clock: Any = time.monotonic) -> None:
        self.accounts: dict[UUID, AccountRecord] = {}
        self.tokens: dict[UUID, TokenRecord] = {}
        self.leases: dict[UUID, tuple[str, float]] = {}
        self.status: dict[UUID, str] = {}
        self.events: list[dict[str, Any]] = []
        self.configs: dict[UUID, dict[str, tuple[bool, dict[str, Any]]]] = {}
        # comandos: id -> {"account_id", "type", "params", "status", "result", "error", "holder"}
        self.commands: dict[UUID, dict[str, Any]] = {}
        self.fail_inserts = False  # para testar o buffer da telemetria
        # dados do jogo (fase 3b)
        self.game_hunts: dict[str, dict[str, Any]] = {}
        self.game_species: dict[int, dict[str, Any]] = {}
        self.game_catalog: dict[str, dict[str, Any]] = {}  # key -> {"version", "data"}
        self.catalog_writes = 0
        self._clock = clock

    def add_account(self, account: AccountRecord, token: str, device_id: str) -> None:
        self.accounts[account.id] = account
        self.tokens[account.id] = TokenRecord(token=token, device_id=device_id)

    async def list_accounts(self, *, include_disabled: bool = False) -> list[AccountRecord]:
        return [a for a in self.accounts.values() if include_disabled or a.enabled]

    async def get_token(self, account_id: UUID) -> TokenRecord | None:
        return self.tokens.get(account_id)

    async def set_token(self, account_id: UUID, token: str, device_id: str) -> None:
        self.tokens[account_id] = TokenRecord(token=token, device_id=device_id)

    async def acquire_lease(self, account_id: UUID, holder: str, ttl_s: int) -> bool:
        now = self._clock()
        current = self.leases.get(account_id)
        if current and current[0] != holder and current[1] > now:
            return False
        self.leases[account_id] = (holder, now + ttl_s)
        return True

    async def release_lease(self, account_id: UUID, holder: str) -> None:
        current = self.leases.get(account_id)
        if current and current[0] == holder:
            del self.leases[account_id]

    async def set_status(self, account_id: UUID, status: str) -> None:
        self.status[account_id] = status

    async def insert_events(self, rows: list[dict[str, Any]]) -> None:
        if self.fail_inserts:
            raise ConnectionError("falha simulada")
        self.events.extend(rows)

    async def refresh_metrics(self, start: datetime, end: datetime) -> int:
        return 0  # agregados só existem no Postgres

    async def plugin_configs(self, account_id: UUID) -> dict[str, tuple[bool, dict[str, Any]]]:
        return self.configs.get(account_id, {})

    async def recent_events(
        self, account_id: UUID, type_: str, since: datetime
    ) -> list[tuple[datetime, dict[str, Any]]]:
        out = []
        for row in self.events:
            if row.get("type") != type_ or str(row.get("account_id")) != str(account_id):
                continue
            at = row.get("received_at")
            at = datetime.fromisoformat(at) if isinstance(at, str) else at
            if at is not None and at >= since:
                out.append((at, row.get("data") or {}))
        return sorted(out, key=lambda x: x[0])

    # --- comandos -----------------------------------------------------------

    def add_command(
        self, account_id: UUID, type_: str, params: dict[str, Any] | None = None
    ) -> UUID:
        cid = uuid4()
        self.commands[cid] = {
            "account_id": account_id,
            "type": type_,
            "params": params or {},
            "status": "pending",
            "result": None,
            "error": None,
            "holder": None,
        }
        return cid

    async def set_account_enabled(self, account_id: UUID, enabled: bool) -> None:
        acc = self.accounts[account_id]
        self.accounts[account_id] = replace(acc, enabled=enabled)

    async def set_plugin_config(
        self, account_id: UUID, plugin: str, enabled: bool, config: dict[str, Any]
    ) -> None:
        self.configs.setdefault(account_id, {})[plugin] = (enabled, config)

    async def claim_commands(self, holder: str, account_ids: list[UUID]) -> list[CommandRecord]:
        out = []
        for cid, c in self.commands.items():
            if c["status"] == "pending" and c["account_id"] in account_ids:
                c["status"], c["holder"] = "running", holder
                out.append(CommandRecord(cid, c["account_id"], c["type"], c["params"]))
        return out

    async def finish_command(
        self, command_id: UUID, status: str, result: dict[str, Any] | None, error: str | None
    ) -> None:
        c = self.commands[command_id]
        if c["status"] == "running":
            c.update(status=status, result=result, error=error)

    async def recover_commands(self, holder: str) -> int:
        n = 0
        for c in self.commands.values():
            if c["status"] == "running" and c["holder"] == holder:
                c.update(status="failed", error="interrompido (o worker reiniciou)")
                n += 1
        return n

    # --- dados do jogo ------------------------------------------------------

    async def get_catalog(self, key: str) -> tuple[str, Any] | None:
        row = self.game_catalog.get(key)
        return (row["version"], row["data"]) if row else None

    async def save_hunt_catalog(
        self, version: str, hunts: list[dict[str, Any]], tables: dict[str, Any]
    ) -> None:
        self.game_hunts = {h["slug"]: h for h in hunts}
        for key, data in tables.items():
            self.game_catalog[key] = {"version": version, "data": data}
        self.game_catalog["hunts"] = {"version": version, "data": None}
        self.catalog_writes += 1

    async def save_species(
        self, version: str, rows: list[dict[str, Any]], meta: dict[str, Any]
    ) -> None:
        self.game_species = {r["species_id"]: r for r in rows}
        self.game_catalog["species"] = {"version": version, "data": meta}
        self.catalog_writes += 1

    async def load_species(self) -> list[dict[str, Any]]:
        return [r["data"] for r in self.game_species.values()]
