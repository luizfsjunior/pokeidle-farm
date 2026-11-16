"""ActionGateway: único caminho para mandar ações ao jogo.

Toda ação é descrita por um `ActionSpec` com schema Pydantic de entrada e de
resultado. Isso deixa as ações prontas para serem expostas como *tools* de um
agente no futuro (ver docs/roadmap.md, "Ideias futuras").

Com `ACTION_MODE=observe_only` (o padrão) toda ação é recusada e registrada.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


class ActionMode(StrEnum):
    OBSERVE_ONLY = "observe_only"  # recusa tudo (fase 2)
    ENABLED = "enabled"


class ActionBlocked(Exception):
    """A ação foi recusada pelo gateway (modo, rate limit ou trava do jogo)."""

    def __init__(self, action: str, reason: str, wait_s: float | None = None) -> None:
        super().__init__(f"{action}: {reason}")
        self.action = action
        self.reason = reason
        self.wait_s = wait_s  # no rate_limit: quantos segundos faltam


class ActionSpec(BaseModel):
    """Base de toda ação. Subclasses definem os campos de entrada."""

    name: ClassVar[str]
    description: ClassVar[str]
    result_model: ClassVar[type[BaseModel]]
    min_interval_s: ClassVar[float] = 5.0

    def to_wire(self) -> dict[str, Any]:
        """Mensagem do protocolo correspondente. Implementado por cada ação."""
        raise NotImplementedError


class Ack(BaseModel):
    """Resultado genérico: o jogo confirma pelo `estado`, não por uma resposta própria."""

    ok: bool = True


class ShopBuy(ActionSpec):
    name: ClassVar[str] = "shop.buy"
    description: ClassVar[str] = "Compra bolas ou itens na loja do NPC com ouro"
    result_model: ClassVar[type[BaseModel]] = Ack
    min_interval_s: ClassVar[float] = 10.0

    kind: Literal["ball", "item"]
    id: int
    qty: int = Field(ge=1)

    def to_wire(self) -> dict[str, Any]:
        return {"t": "shop.buy", "kind": self.kind, "id": self.id, "qty": self.qty}


class AutoSet(ActionSpec):
    name: ClassVar[str] = "auto.set"
    description: ClassVar[str] = "Configura a automação nativa (sempre o objeto inteiro)"
    result_model: ClassVar[type[BaseModel]] = Ack
    min_interval_s: ClassVar[float] = 30.0

    automation: dict[str, Any]

    def to_wire(self) -> dict[str, Any]:
        # o jogo espera os campos achatados no topo, não dentro de "automation"
        return {"t": "auto.set", **self.automation}


class TopCatchRequest(ActionSpec):
    name: ClassVar[str] = "topcatch.pedir"
    description: ClassVar[str] = "Pede a lista das espécies da semana no Top Catch (só leitura)"
    result_model: ClassVar[type[BaseModel]] = Ack
    min_interval_s: ClassVar[float] = 300.0

    def to_wire(self) -> dict[str, Any]:
        return {"t": "topcatch.pedir"}


class RankingRequest(ActionSpec):
    name: ClassVar[str] = "ranking.pedir"
    description: ClassVar[str] = "Pede o ranking do Top Catch da semana (aba capturas, só leitura)"
    result_model: ClassVar[type[BaseModel]] = Ack
    min_interval_s: ClassVar[float] = 300.0

    aba: str = "capturas"

    def to_wire(self) -> dict[str, Any]:
        return {"t": "ranking.pedir", "aba": self.aba}


class MarketAverages(ActionSpec):
    name: ClassVar[str] = "market.medias"
    description: ClassVar[str] = "Pede as médias de preço do Mercado (7 dias, por item; só leitura)"
    result_model: ClassVar[type[BaseModel]] = Ack
    min_interval_s: ClassVar[float] = 300.0

    def to_wire(self) -> dict[str, Any]:
        return {"t": "market.medias"}


class MarketItemRequest(ActionSpec):
    name: ClassVar[str] = "market.item"
    description: ClassVar[str] = "Lê os anúncios abertos de um item no Mercado (só leitura)"
    result_model: ClassVar[type[BaseModel]] = Ack
    min_interval_s: ClassVar[float] = 10.0

    itemId: int  # nome do protocolo
    moeda: Literal["orb", "gold"] = "orb"

    def to_wire(self) -> dict[str, Any]:
        return {"t": "market.item", "itemId": self.itemId, "moeda": self.moeda}


class MarketHistoryGlobal(ActionSpec):
    name: ClassVar[str] = "market.historicoGlobal"
    description: ClassVar[str] = "Histórico global de vendas do Mercado (só leitura, paginado)"
    result_model: ClassVar[type[BaseModel]] = Ack
    min_interval_s: ClassVar[float] = 10.0

    pagina: int = 0
    tipo: Literal["pokemon", "item"] | None = None
    moeda: Literal["orb", "gold"] | None = None
    seq: int = 1

    def to_wire(self) -> dict[str, Any]:
        msg: dict[str, Any] = {
            "t": "market.historicoGlobal",
            "pagina": self.pagina,
            "seq": self.seq,
        }
        if self.tipo:
            msg["tipo"] = self.tipo
        if self.moeda:
            msg["moeda"] = self.moeda
        return msg


class MarketListPokemon(ActionSpec):
    name: ClassVar[str] = "market.listar"
    description: ClassVar[str] = "Anúncios abertos de pokémon no Mercado (só leitura, paginado)"
    result_model: ClassVar[type[BaseModel]] = Ack
    min_interval_s: ClassVar[float] = 10.0

    ordem: Literal["caros", "baratos", "recentes"] = "caros"
    moeda: Literal["orb", "gold"] = "orb"
    pagina: int = 0
    soShiny: bool = False  # nome do protocolo

    def to_wire(self) -> dict[str, Any]:
        # o mesmo pedido do navegador (app.js, pedirLeiturasDoMercado) com os filtros padrão
        return {
            "t": "market.listar",
            "tipo": "pokemon",
            "moeda": self.moeda,
            "busca": "",
            "ordem": self.ordem,
            "criterios": [],
            "elementos": [],
            "tiposUnidos": True,
            "categoria": "",
            "soShiny": self.soShiny,
            "soP5": False,
            "soMega": False,
            "soLendario": False,
            "soTmElemental": False,
            "soTmAoe": False,
            "semOutland": False,
            "pagina": self.pagina,
            "especieId": 0,
        }


class MarketMine(ActionSpec):
    name: ClassVar[str] = "market.meus"
    description: ClassVar[str] = "Lê os próprios anúncios no Mercado (só leitura)"
    result_model: ClassVar[type[BaseModel]] = Ack
    min_interval_s: ClassVar[float] = 2.0

    def to_wire(self) -> dict[str, Any]:
        return {"t": "market.meus"}


class MarketCreate(ActionSpec):
    name: ClassVar[str] = "market.criar"
    description: ClassVar[str] = "Anuncia um item no Mercado (até 20 anúncios; retenção de 2 min)"
    result_model: ClassVar[type[BaseModel]] = Ack
    min_interval_s: ClassVar[float] = 10.0

    tipo: Literal["item"] = "item"
    itemId: int  # nome do protocolo
    qtd: int = Field(ge=1)
    preco: int = Field(ge=1)
    moeda: Literal["orb", "gold"] = "orb"

    def to_wire(self) -> dict[str, Any]:
        # o mesmo formato do navegador (app.js, `cm-publicar`): dias só vale para pokémon
        return {
            "t": "market.criar",
            "tipo": self.tipo,
            "itemId": self.itemId,
            "pokemonId": None,
            "casaId": None,
            "bicicletaId": None,
            "qtd": self.qtd,
            "preco": self.preco,
            "moeda": self.moeda,
            "dias": None,
        }


class MarketCancel(ActionSpec):
    name: ClassVar[str] = "market.cancelar"
    description: ClassVar[str] = "Cancela um anúncio próprio no Mercado"
    result_model: ClassVar[type[BaseModel]] = Ack
    min_interval_s: ClassVar[float] = 5.0

    id: Any

    def to_wire(self) -> dict[str, Any]:
        return {"t": "market.cancelar", "id": self.id}


class PokemonEvolve(ActionSpec):
    name: ClassVar[str] = "pokemon.evoluir"
    description: ClassVar[str] = (
        "Evolui o pokémon (nível exigido + 1 pedra do tipo, gasta pelo jogo)"
    )
    result_model: ClassVar[type[BaseModel]] = Ack
    min_interval_s: ClassVar[float] = 30.0

    pokemon_id: int
    target_id: int

    def to_wire(self) -> dict[str, Any]:
        return {"t": "pokemon.evoluir", "pokemonId": self.pokemon_id, "alvoId": self.target_id}


class HuntSelect(ActionSpec):
    name: ClassVar[str] = "hunt.select"
    description: ClassVar[str] = "Troca de hunt (só fora da trava de combate e do trocaLivreEm)"
    result_model: ClassVar[type[BaseModel]] = Ack
    # cobre o trocaLivreEm (+10 s) com folga; o teto por hora fica no plugin rank (D-E)
    min_interval_s: ClassVar[float] = 20.0

    slug: str

    def to_wire(self) -> dict[str, Any]:
        return {"t": "hunt.select", "slug": self.slug}


class RateLimiter:
    """Intervalo mínimo por (conta, ação)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._last: dict[str, float] = {}
        self._clock = clock

    def check(self, key: str, min_interval_s: float) -> float:
        """Retorna 0 se pode executar agora, senão quantos segundos faltam."""
        last = self._last.get(key)
        if last is None:
            return 0.0
        return max(0.0, min_interval_s - (self._clock() - last))

    def mark(self, key: str) -> None:
        self._last[key] = self._clock()


Sender = Callable[[dict[str, Any]], Awaitable[None]]
Recorder = Callable[[str, dict[str, Any]], Awaitable[None]]


@dataclass
class ActionGateway:
    account_id: str
    mode: ActionMode
    send: Sender | None = None  # ligado pela sessão quando está READY
    record: Recorder | None = None  # publica action.* no barramento
    limiter: RateLimiter | None = None

    def __post_init__(self) -> None:
        self.limiter = self.limiter or RateLimiter()

    async def submit(self, action: ActionSpec, *, source: str) -> None:
        info = {"action": action.name, "source": source, "input": action.model_dump(mode="json")}

        if self.mode is ActionMode.OBSERVE_ONLY:
            await self._record("action.blocked", {**info, "reason": "observe_only"})
            raise ActionBlocked(action.name, "observe_only")

        assert self.limiter is not None
        key = f"{self.account_id}:{action.name}"
        wait = self.limiter.check(key, action.min_interval_s)
        if wait > 0:
            await self._record("action.blocked", {**info, "reason": "rate_limit", "wait_s": wait})
            raise ActionBlocked(action.name, f"rate_limit ({wait:.1f}s)", wait_s=wait)

        if self.send is None:
            await self._record("action.blocked", {**info, "reason": "not_connected"})
            raise ActionBlocked(action.name, "not_connected")

        self.limiter.mark(key)
        await self.send(action.to_wire())
        await self._record("action.sent", info)

    async def note(self, type_: str, data: dict[str, Any]) -> None:
        """Registra um evento de um plugin (ex.: restock.bought) no barramento."""
        await self._record(type_, data)

    async def _record(self, type_: str, data: dict[str, Any]) -> None:
        log.info("%s %s", type_, data.get("action"))
        if self.record:
            await self.record(type_, data)
