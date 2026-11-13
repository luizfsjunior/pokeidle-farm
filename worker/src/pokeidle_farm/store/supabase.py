"""Store no Supabase (ver supabase/migrations/0001_init.sql).

O token nunca é lido direto de tabela: só pelas funções `get_account_token`
e `set_account_token`, que usam o Supabase Vault e só a service_role executa.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from supabase import AsyncClient, acreate_client

from .base import AccountRecord, CommandRecord, TokenRecord


class SupabaseStore:
    def __init__(self, client: AsyncClient) -> None:
        self._db = client

    @classmethod
    async def connect(cls, url: str, service_role_key: str) -> SupabaseStore:
        return cls(await acreate_client(url, service_role_key))

    async def list_accounts(self, *, include_disabled: bool = False) -> list[AccountRecord]:
        q = self._db.table("accounts").select("id,nick,role,enabled").eq("role", "farm")
        if not include_disabled:
            q = q.eq("enabled", True)
        res = await q.execute()
        return [
            AccountRecord(id=UUID(r["id"]), nick=r["nick"], role=r["role"], enabled=r["enabled"])
            for r in res.data or []
        ]

    async def get_token(self, account_id: UUID) -> TokenRecord | None:
        res = await self._db.rpc("get_account_token", {"p_account": str(account_id)}).execute()
        rows = res.data or []
        if not rows:
            return None
        return TokenRecord(token=rows[0]["token"], device_id=rows[0]["device_id"])

    async def set_token(self, account_id: UUID, token: str, device_id: str) -> None:
        await self._db.rpc(
            "set_account_token",
            {"p_account": str(account_id), "p_token": token, "p_device": device_id},
        ).execute()

    async def acquire_lease(self, account_id: UUID, holder: str, ttl_s: int) -> bool:
        res = await self._db.rpc(
            "acquire_account_lease",
            {"p_account": str(account_id), "p_holder": holder, "p_ttl_seconds": ttl_s},
        ).execute()
        return bool(res.data)

    async def release_lease(self, account_id: UUID, holder: str) -> None:
        await self._db.rpc(
            "release_account_lease", {"p_account": str(account_id), "p_holder": holder}
        ).execute()

    async def set_status(self, account_id: UUID, status: str) -> None:
        await (
            self._db.table("accounts")
            .update({"status": status})
            .eq("id", str(account_id))
            .execute()
        )

    async def insert_events(self, rows: list[dict[str, Any]]) -> None:
        if rows:
            await (
                self._db.table("events")
                .upsert(rows, on_conflict="id", ignore_duplicates=True)
                .execute()
            )

    async def refresh_metrics(self, start: datetime, end: datetime) -> int:
        res = await self._db.rpc(
            "refresh_metric_hourly", {"p_from": start.isoformat(), "p_to": end.isoformat()}
        ).execute()
        return int(res.data or 0)

    async def plugin_configs(self, account_id: UUID) -> dict[str, tuple[bool, dict[str, Any]]]:
        res = await (
            self._db.table("strategy_configs")
            .select("plugin,enabled,config")
            .eq("account_id", str(account_id))
            .execute()
        )
        return {r["plugin"]: (r["enabled"], r["config"] or {}) for r in res.data or []}

    async def recent_events(
        self, account_id: UUID, type_: str, since: datetime
    ) -> list[tuple[datetime, dict[str, Any]]]:
        res = await (
            self._db.table("events")
            .select("received_at, data")
            .eq("account_id", str(account_id))
            .eq("type", type_)
            .gte("received_at", since.isoformat())
            .order("received_at")
            .limit(1000)
            .execute()
        )
        return [(datetime.fromisoformat(r["received_at"]), r["data"] or {}) for r in res.data or []]

    # --- comandos -----------------------------------------------------------

    async def set_account_enabled(self, account_id: UUID, enabled: bool) -> None:
        await (
            self._db.table("accounts")
            .update({"enabled": enabled})
            .eq("id", str(account_id))
            .execute()
        )

    async def set_plugin_config(
        self, account_id: UUID, plugin: str, enabled: bool, config: dict[str, Any]
    ) -> None:
        await (
            self._db.table("strategy_configs")
            .upsert(
                {
                    "account_id": str(account_id),
                    "plugin": plugin,
                    "enabled": enabled,
                    "config": config,
                    "updated_at": datetime.now(UTC).isoformat(),
                },
                on_conflict="account_id,plugin",
            )
            .execute()
        )

    async def claim_commands(self, holder: str, account_ids: list[UUID]) -> list[CommandRecord]:
        res = await self._db.rpc(
            "claim_commands",
            {"p_holder": holder, "p_accounts": [str(a) for a in account_ids]},
        ).execute()
        return [
            CommandRecord(UUID(r["id"]), UUID(r["account_id"]), r["type"], r["params"] or {})
            for r in res.data or []
        ]

    async def finish_command(
        self, command_id: UUID, status: str, result: dict[str, Any] | None, error: str | None
    ) -> None:
        await self._db.rpc(
            "finish_command",
            {"p_id": str(command_id), "p_status": status, "p_result": result, "p_error": error},
        ).execute()

    async def recover_commands(self, holder: str) -> int:
        res = await self._db.rpc("recover_commands", {"p_holder": holder}).execute()
        return int(res.data or 0)
