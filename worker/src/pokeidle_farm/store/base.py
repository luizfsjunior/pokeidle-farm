from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True)
class AccountRecord:
    id: UUID
    nick: str
    role: str  # "farm" | "personal"
    enabled: bool = True


@dataclass(frozen=True)
class TokenRecord:
    token: str
    device_id: str

    def __repr__(self) -> str:  # nunca vazar o token em logs
        return f"TokenRecord(token=***, device_id={self.device_id!r})"


@dataclass(frozen=True)
class CommandRecord:
    id: UUID
    account_id: UUID
    type: str
    params: dict[str, Any]


class Store(Protocol):
    async def list_accounts(self, *, include_disabled: bool = False) -> list[AccountRecord]:
        """Contas de farm (só as habilitadas, a menos que include_disabled)."""
        ...

    async def get_token(self, account_id: UUID) -> TokenRecord | None: ...

    async def set_token(self, account_id: UUID, token: str, device_id: str) -> None: ...

    async def acquire_lease(self, account_id: UUID, holder: str, ttl_s: int) -> bool:
        """Pega ou renova o lease. False se outra instância detém um lease válido."""
        ...

    async def release_lease(self, account_id: UUID, holder: str) -> None: ...

    async def set_status(self, account_id: UUID, status: str) -> None: ...

    async def insert_events(self, rows: list[dict[str, Any]]) -> None: ...

    async def refresh_metrics(self, start: datetime, end: datetime) -> int:
        """Recalcula os agregados por hora do intervalo. Retorna linhas gravadas."""
        ...

    async def plugin_configs(self, account_id: UUID) -> dict[str, tuple[bool, dict[str, Any]]]:
        """{plugin: (enabled, config)} da tabela strategy_configs."""
        ...

    async def recent_events(
        self, account_id: UUID, type_: str, since: datetime
    ) -> list[tuple[datetime, dict[str, Any]]]:
        """(received_at, data) dos eventos do tipo desde `since`, do mais antigo ao mais novo."""
        ...

    # --- comandos (fase 4b) -------------------------------------------------

    async def set_account_enabled(self, account_id: UUID, enabled: bool) -> None: ...

    async def set_plugin_config(
        self, account_id: UUID, plugin: str, enabled: bool, config: dict[str, Any]
    ) -> None: ...

    async def claim_commands(self, holder: str, account_ids: list[UUID]) -> list[CommandRecord]:
        """Pega os comandos pendentes (atômico) e os marca como running."""
        ...

    async def finish_command(
        self, command_id: UUID, status: str, result: dict[str, Any] | None, error: str | None
    ) -> None: ...

    async def recover_commands(self, holder: str) -> int:
        """Marca como failed os comandos running deste holder (o worker reiniciou)."""
        ...

    # --- dados do jogo (fase 3b) ----------------------------------------------

    async def get_catalog(self, key: str) -> tuple[str, Any] | None:
        """(version, data) da linha `key` de game_catalog, ou None."""
        ...

    async def save_hunt_catalog(
        self, version: str, hunts: list[dict[str, Any]], tables: dict[str, Any]
    ) -> None:
        """Substitui game_hunts (apaga as que sumiram) e grava as tabelas e a versão."""
        ...

    async def save_species(
        self, version: str, rows: list[dict[str, Any]], meta: dict[str, Any]
    ) -> None:
        """Substitui game_species e grava a versão (com `meta`, ex.: os ETags)."""
        ...

    async def load_species(self) -> list[dict[str, Any]]:
        """O `data` de cada linha de game_species (a espécie como veio do jogo)."""
        ...
