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


@dataclass(frozen=True)
class HuntStats:
    """Ritmo e última chance de captura de uma hunt (fase 3b, plugin rank)."""

    hunt_slug: str
    kills: float
    active_minutes: float
    last_chance: float | None = None
    last_ball_id: int | None = None
    avg_active_level: float | None = None  # nível médio do pokémon ativo nos abates medidos
    xp: float = 0.0  # XP do treinador nos abates (com os bônus)


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

    # --- Mercado (fase 7) -------------------------------------------------------

    async def save_items(
        self, source: str, version: str, rows: list[dict[str, Any]], meta: dict[str, Any]
    ) -> None:
        """Substitui os itens da origem (`json` ou `welcome`) em game_items e grava a versão."""
        ...

    async def save_market_prices(self, rows: list[dict[str, Any]]) -> None:
        """Acrescenta um snapshot de médias do Mercado (linhas de market_prices)."""
        ...

    async def latest_item_prices(self) -> dict[str, dict[str, Any]]:
        """Último snapshot por nome de item: {name: {orb, orb_units_week, gold, gold_units_week,
        orb_min_ask, orb_ask_units}} (o menor anúncio aberto das últimas 6 h, se houver)."""
        ...

    async def item_ids_by_name(self, names: list[str]) -> dict[int, str]:
        """Itens do catálogo com esses nomes: {item_id: nome} (o menor id de cada nome)."""
        ...

    async def stone_items(self) -> dict[int, str]:
        """Pedras do catálogo de itens: {item_id: nome}."""
        ...

    async def market_reference(self) -> dict[str, dict[str, Any]]:
        """Mediana das vendas reais em gemas por item (função market_reference, 7 dias):
        {nome: {"median", "sales", "units", "raw_mean"}}. Ver docs/design/preco-de-referencia.md."""
        ...

    async def save_market_asks(self, rows: list[dict[str, Any]]) -> None:
        """Grava o resumo dos anúncios abertos de itens (linhas de market_asks)."""
        ...

    async def latest_asks(self) -> dict[int, dict[str, Any]]:
        """Último resumo de anúncios em gemas por item (das últimas 6 h)."""
        ...

    # --- arquivos do jogo (wiki e fórmulas; análise de 15/11) ---------------------

    async def save_game_file(self, path: str, etag: str | None, content: str) -> None:
        """Grava (ou substitui) um arquivo público do jogo em game_files."""
        ...

    async def save_catalog_entry(self, key: str, version: str, data: Any) -> None:
        """Grava uma linha em game_catalog (ex.: `loot_stones`, as constantes das pedras)."""
        ...

    # --- perfil da conta para o painel (docs/design/painel-perfil.md) ----------------

    async def upsert_account_profile(self, row: dict[str, Any]) -> None:
        """Grava (ou substitui) a linha da conta em account_profile."""
        ...

    async def rank_hunt_stats(self, account_id: UUID, since: datetime) -> list[HuntStats]:
        """Por hunt, desde `since`: abates e minutos ativos e a última chance de captura."""
        ...
