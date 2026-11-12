"""Store em memória: desenvolvimento sem Supabase e testes."""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from .base import AccountRecord, TokenRecord


class MemoryStore:
    def __init__(self, clock: Any = time.monotonic) -> None:
        self.accounts: dict[UUID, AccountRecord] = {}
        self.tokens: dict[UUID, TokenRecord] = {}
        self.leases: dict[UUID, tuple[str, float]] = {}
        self.status: dict[UUID, str] = {}
        self.events: list[dict[str, Any]] = []
        self.configs: dict[UUID, dict[str, tuple[bool, dict[str, Any]]]] = {}
        self.fail_inserts = False  # para testar o buffer da telemetria
        self._clock = clock

    def add_account(self, account: AccountRecord, token: str, device_id: str) -> None:
        self.accounts[account.id] = account
        self.tokens[account.id] = TokenRecord(token=token, device_id=device_id)

    async def list_accounts(self) -> list[AccountRecord]:
        return list(self.accounts.values())

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

    async def plugin_configs(self, account_id: UUID) -> dict[str, tuple[bool, dict[str, Any]]]:
        return self.configs.get(account_id, {})
