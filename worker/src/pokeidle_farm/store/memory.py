"""Store em memória: desenvolvimento sem Supabase e testes."""

from __future__ import annotations

import time
from dataclasses import replace
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from .base import AccountRecord, CommandRecord, HuntStats, TokenRecord


class MemoryStore:
    def __init__(self, clock: Any = time.monotonic) -> None:
        self.accounts: dict[UUID, AccountRecord] = {}
        self.tokens: dict[UUID, TokenRecord] = {}
        self.leases: dict[UUID, tuple[str, float]] = {}
        self.status: dict[UUID, str] = {}
        self.events: list[dict[str, Any]] = []
        self.kill_minutes: list[dict[str, Any]] = []  # linhas de kill_minute (kill_minutes.py)
        self.configs: dict[UUID, dict[str, tuple[bool, dict[str, Any]]]] = {}
        # comandos: id -> {"account_id", "type", "params", "status", "result", "error", "holder"}
        self.commands: dict[UUID, dict[str, Any]] = {}
        self.fail_inserts = False  # para testar o buffer da telemetria
        # dados do jogo (fase 3b)
        self.game_hunts: dict[str, dict[str, Any]] = {}
        self.game_species: dict[int, dict[str, Any]] = {}
        self.game_catalog: dict[str, dict[str, Any]] = {}  # key -> {"version", "data"}
        self.catalog_writes = 0
        self.protected: dict[UUID, set[int]] = {}  # protected_pokemon
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

    async def insert_kill_minutes(self, rows: list[dict[str, Any]]) -> None:
        if self.fail_inserts:
            raise ConnectionError("falha simulada")
        seen = {_kill_minute_key(r) for r in self.kill_minutes}
        for row in rows:  # como o `on conflict do nothing` do banco
            if _kill_minute_key(row) not in seen:
                seen.add(_kill_minute_key(row))
                self.kill_minutes.append(row)

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

    async def save_items(
        self, source: str, version: str, rows: list[dict[str, Any]], meta: dict[str, Any]
    ) -> None:
        items = getattr(self, "game_items", {})
        items = {k: v for k, v in items.items() if v.get("source") != source}
        for r in rows:
            items[r["item_id"]] = {**r, "source": source}
        self.game_items = items
        self.game_catalog[f"items_{source}"] = {"version": version, "data": meta}
        self.catalog_writes += 1

    async def save_market_prices(self, rows: list[dict[str, Any]]) -> None:
        self.market_prices = [*getattr(self, "market_prices", []), *rows]

    async def latest_item_prices(self) -> dict[str, dict[str, Any]]:
        rows = getattr(self, "market_prices", [])
        if not rows:
            return {}
        last = max(r["taken_at"] for r in rows)
        names = {k: v["name"] for k, v in getattr(self, "game_items", {}).items()}
        out: dict[str, dict[str, Any]] = {}
        for r in rows:
            name = names.get(r["item_id"])
            if r["taken_at"] != last or name is None:
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
        wanted, out = set(names), {}
        for k in sorted(getattr(self, "game_items", {})):
            n = self.game_items[k]["name"]
            if n in wanted and n not in out.values():
                out[k] = n
        return out

    async def stone_items(self) -> dict[int, str]:
        return {
            k: v["name"]
            for k, v in getattr(self, "game_items", {}).items()
            if v.get("category") == "stone"
        }

    async def upsert_account_profile(self, row: dict[str, Any]) -> None:
        if not hasattr(self, "profiles"):
            self.profiles: dict[str, dict[str, Any]] = {}
        self.profiles[row["account_id"]] = row

    async def sync_account_pokemon(
        self,
        account_id: UUID,
        upsert: list[dict[str, Any]],
        delete: list[int],
        *,
        full: bool = False,
    ) -> None:
        if not hasattr(self, "pokemon"):
            self.pokemon: dict[str, dict[int, dict[str, Any]]] = {}
        rows = self.pokemon.setdefault(str(account_id), {})
        if full:
            rows.clear()
        for r in upsert:
            rows[int(r["pokemon_id"])] = r
        for pid in delete:
            rows.pop(int(pid), None)

    async def market_reference(self) -> dict[str, dict[str, Any]]:
        return dict(getattr(self, "reference", {}))

    async def protected_pokemon(self, account_id: UUID) -> set[int]:
        return set(self.protected.get(account_id, set()))

    async def save_market_asks(self, rows: list[dict[str, Any]]) -> None:
        self.market_asks = [*getattr(self, "market_asks", []), *rows]

    async def latest_asks(self) -> dict[int, dict[str, Any]]:
        out: dict[int, dict[str, Any]] = {}
        for r in getattr(self, "market_asks", []):
            if r.get("currency", "orb") != "orb":
                continue
            cur = out.get(r["item_id"])
            if cur is None or r["taken_at"] >= cur["taken_at"]:
                out[r["item_id"]] = r
        return out

    async def save_game_file(self, path: str, etag: str | None, content: str) -> None:
        files = getattr(self, "game_files", {})
        files[path] = {"etag": etag, "content": content}
        self.game_files = files

    async def set_notify_settings(self, webhook: str | None, panel_url: str | None) -> None:
        self.notify_settings = (webhook, panel_url)

    async def save_catalog_entry(self, key: str, version: str, data: Any) -> None:
        self.game_catalog[key] = {"version": version, "data": data}

    async def rank_hunt_stats(self, account_id: UUID, since: datetime) -> list[HuntStats]:
        """Igual à função do banco, a partir dos eventos em memória: cada minuto
        distinto com abate numa hunt conta como um minuto ativo."""
        kills: dict[str, int] = {}
        minutes: dict[str, set[datetime]] = {}
        chances: dict[str, tuple[datetime, float, int | None]] = {}
        levels: dict[str, tuple[float, int]] = {}
        xp: dict[str, float] = {}
        for row in self.kill_minutes:  # os abates do worker novo (somados por minuto)
            minute = datetime.fromisoformat(row["minute"])
            slug = row.get("hunt_slug")
            if str(row.get("account_id")) != str(account_id) or minute < since or not slug:
                continue
            if row.get("kills"):
                kills[slug] = kills.get(slug, 0) + row["kills"]
                minutes.setdefault(slug, set()).add(minute)
                xp[slug] = xp.get(slug, 0.0) + float(row.get("xp") or 0)
            if row.get("kills_leveled"):
                s, n = levels.get(slug, (0.0, 0))
                levels[slug] = (s + row["active_level_sum"], n + row["kills_leveled"])
            chance = row.get("last_chance")
            if chance is not None:
                prev = chances.get(slug)
                if prev is None or minute >= prev[0]:
                    chances[slug] = (minute, float(chance), row.get("last_ball_id"))
        for row in self.events:
            if str(row.get("account_id")) != str(account_id):
                continue
            at = row.get("received_at")
            at = datetime.fromisoformat(at) if isinstance(at, str) else at
            data = row.get("data") or {}
            slug = data.get("hunt_slug")
            if at is None or at < since or not slug:
                continue
            if row.get("type") == "kill":
                kills[slug] = kills.get(slug, 0) + 1
                minutes.setdefault(slug, set()).add(at.replace(second=0, microsecond=0))
                xp[slug] = xp.get(slug, 0.0) + float(data.get("xp") or 0)
                lvl = data.get("active_level")
                if isinstance(lvl, int) and not isinstance(lvl, bool):
                    s, n = levels.get(slug, (0.0, 0))
                    levels[slug] = (s + lvl, n + 1)
            elif row.get("type") == "capture_attempt":
                chance = data.get("chance")
                if not isinstance(chance, int | float) or isinstance(chance, bool):
                    continue
                prev = chances.get(slug)
                if prev is None or at >= prev[0]:
                    chances[slug] = (at, float(chance), data.get("ball_id"))
        return [
            HuntStats(
                hunt_slug=slug,
                kills=kills.get(slug, 0),
                active_minutes=len(minutes.get(slug, ())),
                last_chance=chances[slug][1] if slug in chances else None,
                last_ball_id=chances[slug][2] if slug in chances else None,
                avg_active_level=levels[slug][0] / levels[slug][1] if slug in levels else None,
                xp=xp.get(slug, 0.0),
            )
            for slug in sorted(set(kills) | set(chances))
        ]


def _kill_minute_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(
        row.get(k)
        for k in (
            "account_id",
            "session_id",
            "minute",
            "hunt_slug",
            "active_species_id",
            "season",
            "part",
        )
    )
