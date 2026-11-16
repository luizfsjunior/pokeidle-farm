"""Store no Supabase (ver supabase/migrations/0001_init.sql).

O token nunca é lido direto de tabela: só pelas funções `get_account_token`
e `set_account_token`, que usam o Supabase Vault e só a service_role executa.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from supabase import AsyncClient, acreate_client

from .base import AccountRecord, CommandRecord, HuntStats, TokenRecord


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

    # --- dados do jogo (fase 3b) --------------------------------------------

    async def get_catalog(self, key: str) -> tuple[str, Any] | None:
        res = await self._db.table("game_catalog").select("version,data").eq("key", key).execute()
        rows = res.data or []
        return (rows[0]["version"], rows[0]["data"]) if rows else None

    async def save_hunt_catalog(
        self, version: str, hunts: list[dict[str, Any]], tables: dict[str, Any]
    ) -> None:
        await self._db.rpc(
            "replace_game_hunts", {"p_version": version, "p_hunts": hunts, "p_tables": tables}
        ).execute()

    async def save_species(
        self, version: str, rows: list[dict[str, Any]], meta: dict[str, Any]
    ) -> None:
        await self._db.rpc(
            "replace_game_species", {"p_version": version, "p_rows": rows, "p_meta": meta}
        ).execute()

    async def save_items(
        self, source: str, version: str, rows: list[dict[str, Any]], meta: dict[str, Any]
    ) -> None:
        await self._db.rpc(
            "replace_game_items",
            {"p_source": source, "p_version": version, "p_rows": rows, "p_meta": meta},
        ).execute()

    async def save_market_prices(self, rows: list[dict[str, Any]]) -> None:
        for i in range(0, len(rows), 1000):
            await self._db.table("market_prices").upsert(rows[i : i + 1000]).execute()

    async def latest_item_prices(self) -> dict[str, dict[str, Any]]:
        last = await (
            self._db.table("market_prices")
            .select("taken_at")
            .order("taken_at", desc=True)
            .limit(1)
            .execute()
        )
        if not last.data:
            return {}
        rows = (
            await self._db.table("market_prices")
            .select("item_id,currency,avg,units,days")
            .eq("taken_at", last.data[0]["taken_at"])
            .execute()
        ).data or []
        ids = sorted({r["item_id"] for r in rows})
        items: list[dict[str, Any]] = []
        if ids:
            res = (
                await self._db.table("game_items")
                .select("item_id,name")
                .in_("item_id", ids)
                .execute()
            )
            items = res.data or []
        names = {i["item_id"]: i["name"] for i in items}
        out: dict[str, dict[str, Any]] = {}
        for r in rows:
            name = names.get(r["item_id"])
            if name is None:
                continue
            days = r.get("days") or 7
            entry = out.setdefault(name, {})
            entry[r["currency"]] = r["avg"]
            entry[f"{r['currency']}_units_week"] = (r.get("units") or 0) * 7 / days
        asks = await self.latest_asks()
        for item_id, a in asks.items():
            name = names.get(item_id)
            if name is not None and a.get("min_price") is not None:
                entry = out.setdefault(name, {})
                entry["orb_min_ask"] = a["min_price"]
                entry["orb_ask_units"] = a.get("total_units")
        return out

    async def item_ids_by_name(self, names: list[str]) -> dict[int, str]:
        if not names:
            return {}
        res = await self._db.table("game_items").select("item_id,name").in_("name", names).execute()
        out: dict[int, str] = {}
        for r in sorted(res.data or [], key=lambda r: r["item_id"]):
            if r["name"] not in out.values():
                out[r["item_id"]] = r["name"]
        return out

    async def stone_items(self) -> dict[int, str]:
        res = await (
            self._db.table("game_items").select("item_id,name").eq("category", "stone").execute()
        )
        return {r["item_id"]: r["name"] for r in res.data or []}

    async def upsert_account_profile(self, row: dict[str, Any]) -> None:
        await self._db.table("account_profile").upsert(row).execute()

    async def market_reference(self) -> dict[str, dict[str, Any]]:
        res = await self._db.rpc("market_reference", {}).execute()
        out: dict[str, dict[str, Any]] = {}
        for r in res.data or []:
            if r.get("currency") != "orb" or r.get("median_unit") is None:
                continue
            out[r["item_name"]] = {
                "median": float(r["median_unit"]),
                "sales": int(r.get("sales") or 0),
                "units": float(r.get("units") or 0),
                "raw_mean": float(r["raw_mean_unit"])
                if r.get("raw_mean_unit") is not None
                else None,
            }
        return out

    async def save_market_asks(self, rows: list[dict[str, Any]]) -> None:
        if rows:
            await self._db.table("market_asks").upsert(rows).execute()

    async def latest_asks(self) -> dict[int, dict[str, Any]]:
        since = (datetime.now(UTC) - timedelta(hours=6)).isoformat()
        res = await (
            self._db.table("market_asks")
            .select("taken_at,item_id,min_price,units_at_min,total_units,listings")
            .eq("currency", "orb")
            .gte("taken_at", since)
            .order("taken_at", desc=True)
            .limit(1000)
            .execute()
        )
        out: dict[int, dict[str, Any]] = {}
        for r in res.data or []:
            out.setdefault(r["item_id"], r)  # o mais recente de cada item
        return out

    async def save_game_file(self, path: str, etag: str | None, content: str) -> None:
        await (
            self._db.table("game_files")
            .upsert(
                {
                    "path": path,
                    "etag": etag,
                    "content": content,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            )
            .execute()
        )

    async def save_catalog_entry(self, key: str, version: str, data: Any) -> None:
        await (
            self._db.table("game_catalog")
            .upsert(
                {
                    "key": key,
                    "version": version,
                    "data": data,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            )
            .execute()
        )

    async def load_species(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        page = 1000
        while True:
            res = await (
                self._db.table("game_species")
                .select("data")
                .order("species_id")
                .range(len(out), len(out) + page - 1)
                .execute()
            )
            rows = res.data or []
            out.extend(r["data"] for r in rows)
            if len(rows) < page:
                return out

    async def rank_hunt_stats(self, account_id: UUID, since: datetime) -> list[HuntStats]:
        res = await self._db.rpc(
            "rank_hunt_stats", {"p_account": str(account_id), "p_since": since.isoformat()}
        ).execute()
        return [
            HuntStats(
                hunt_slug=r["hunt_slug"],
                kills=float(r.get("kills") or 0),
                active_minutes=float(r.get("active_minutes") or 0),
                last_chance=r.get("last_chance"),
                last_ball_id=r.get("last_ball_id"),
                avg_active_level=(
                    float(r["avg_active_level"]) if r.get("avg_active_level") is not None else None
                ),
                xp=float(r.get("xp") or 0),
            )
            for r in res.data or []
        ]
