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


class Store(Protocol):
    async def list_accounts(self) -> list[AccountRecord]: ...

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
