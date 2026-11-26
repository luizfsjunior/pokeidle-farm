"""Plugin notifier: avisos no Discord (épico A do plano de 26/11).

Ouve eventos que o worker já publica e manda um embed para um webhook do Discord:

| aviso            | evento                                                     | filtro                        |
|------------------|------------------------------------------------------------|-------------------------------|
| shiny visto      | `kill` com `shiny`; `ball_thrower.shiny_missed`            | um por corpo                  |
| shiny capturado  | `pokemon.captured` com `shiny`                             | sempre                        |
| captura rara     | `pokemon.captured`                                         | potência ou nota no corte     |
| drop raro        | `kill` (os `drops`)                                        | nome contém um da lista       |
| conta caiu       | `session.disconnected` por X min, `session.rejected`, `watchdog.no_kills` | um aviso e um de volta |
| Top Catch        | `rank.position`                                            | mudou de faixa                |
| nível            | `level_up` do treinador                                    | bateu um marco                |

- Preferências por conta em `strategy_configs` (plugin `notifier`, campo `config`), um interruptor por tipo.
- O webhook é um só para as 4 contas e fica no `.env` (`DISCORD_WEBHOOK_URL`), nunca no banco. Sem ele o
  plugin fica degradado e a sessão segue normal.
- Limite por minuto **compartilhado entre as contas** (`NOTIFY_PER_MINUTE`, padrão 10): uma fila só no
  processo; o que passa do limite vira um resumo ("+7 avisos").
- Nada é gravado em `events`: o aviso enviado fica só no log (Supabase Free, retenção curta).

Sempre ligado, para ver as quedas antes do primeiro READY; `active: false` desliga os avisos da conta.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time
from collections import Counter, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field

from ..events import Event
from ..model.capture import pokemon_grade
from ..model.combat import BASE_KEYS, STATS
from ..sim.rolls import roll_ivs, roll_potency, roll_quality
from .base import Plugin, PluginContext

log = logging.getLogger(__name__)

WINDOW_S = 60.0
SPRITE = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{shiny}{id}.png"
MAX_DEX = 1025  # acima disso (Mega, formas) não há sprite pelo número

# cores dos embeds
GOLD, PURPLE, BLUE, RED, GREEN, GREY = 0xF1C40F, 0x9B59B6, 0x3498DB, 0xE74C3C, 0x2ECC71, 0x95A5A6

LABELS = {
    "shiny_seen": "shiny visto",
    "shiny_captured": "shiny capturado",
    "rare_capture": "captura rara",
    "rare_drop": "drop raro",
    "account_down": "conta",
    "rank": "Top Catch",
    "level": "nível",
    "test": "teste",
}


class NotifierConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: bool = True
    shiny_seen: bool = True
    shiny_captured: bool = True
    rare_capture: bool = True
    # captura rara: potência a partir de min_potency OU nota (a do jogo) entre as top_pct% melhores
    # da espécie (sorteio do nascimento, sim/rolls.py; 0 desliga). P4+ é ~0,5% das capturas.
    min_potency: int = Field(4, ge=1, le=5)
    top_pct: float = Field(5.0, ge=0, le=50)
    rare_drop: bool = True
    # drop raro: o nome do item contém um destes (sem diferença de maiúsculas)
    drops: list[str] = Field(default_factory=lambda: ["fragment", "boss token", "shiny stone"])
    account_down: bool = True
    down_after_min: float = Field(10.0, ge=1)  # desconectada há mais que isso: avisa
    rank: bool = True
    # faixas do Top Catch: avisa quando a posição muda de faixa (top 1, top 3, top 10...)
    rank_marks: list[int] = Field(default_factory=lambda: [1, 3, 10, 50, 100])
    level: bool = True
    level_marks: list[int] = Field(
        default_factory=lambda: [100, 150, 200, 250, 300, 350, 400, 450, 500]
    )
    tick_s: float = Field(30.0, ge=1)


# --- envio: fila única do processo ---------------------------------------------------------------


Post = Callable[[dict[str, Any]], Awaitable[None]]


class WebhookError(Exception):
    pass


@dataclass
class Notice:
    kind: str
    payload: dict[str, Any]


@dataclass
class Dispatcher:
    """Um webhook para as 4 contas: fila e limite por minuto compartilhados."""

    url: str
    per_minute: int = 10
    post: Post | None = None
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep
    sent: deque[float] = field(default_factory=deque)
    queue: deque[Notice] = field(default_factory=deque)
    overflow: Counter[str] = field(default_factory=Counter)
    _task: asyncio.Task[None] | None = None

    def submit(self, notice: Notice) -> None:
        """Põe na fila sem esperar; com a fila cheia (um minuto de avisos), conta para o resumo."""
        if len(self.queue) >= self.per_minute:
            self.overflow[notice.kind] += 1
        else:
            self.queue.append(notice)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="notifier:dispatch")

    async def send_now(self, payload: dict[str, Any]) -> None:
        """Manda já (aviso de teste do painel), contando no limite; erro sobe para o comando."""
        self._prune()
        self.sent.append(self.clock())
        await self._post(payload)

    async def idle(self) -> None:
        """Espera a fila esvaziar (testes e encerramento)."""
        if self._task is not None:
            await self._task

    async def close(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    def _prune(self) -> None:
        now = self.clock()
        while self.sent and now - self.sent[0] >= WINDOW_S:
            self.sent.popleft()

    async def _wait_slot(self) -> None:
        while True:
            self._prune()
            if len(self.sent) < self.per_minute:
                return
            await self.sleep(max(0.1, WINDOW_S - (self.clock() - self.sent[0])))

    async def _run(self) -> None:
        while self.queue or self.overflow:
            await self._wait_slot()
            if self.queue:  # a fila primeiro; o resumo do que passou sai quando ela esvazia
                payload = self.queue.popleft().payload
            else:
                payload = summary_payload(self.overflow)
                self.overflow.clear()
            self.sent.append(self.clock())
            try:
                await self._post(payload)
            except Exception as exc:
                log.warning("notifier: aviso não enviado: %r", exc)

    async def _post(self, payload: dict[str, Any]) -> None:
        if self.post is not None:
            await self.post(payload)
            return
        async with httpx.AsyncClient(timeout=10.0) as client:
            for _ in range(2):
                res = await client.post(self.url, json=payload)
                if res.status_code == 429:  # o Discord diz quanto esperar
                    try:
                        wait = float(res.json().get("retry_after", 1.0))
                    except Exception:
                        wait = 1.0
                    await self.sleep(min(wait, 30.0))
                    continue
                if res.status_code >= 400:
                    raise WebhookError(f"Discord respondeu HTTP {res.status_code}")
                return
            raise WebhookError("Discord limitou o webhook (HTTP 429)")


def summary_payload(overflow: Counter[str]) -> dict[str, Any]:
    total = sum(overflow.values())
    parts = ", ".join(f"{n} {LABELS.get(k, k)}" for k, n in overflow.most_common())
    return {"content": f"+{total} aviso(s) não enviados pelo limite por minuto ({parts})"}


_DISPATCHER: Dispatcher | None = None


def get_dispatcher(settings: Any) -> Dispatcher | None:
    """O dispatcher do processo (um por webhook); None sem DISCORD_WEBHOOK_URL."""
    global _DISPATCHER
    secret = getattr(settings, "discord_webhook_url", None)
    url = secret.get_secret_value() if secret else None
    if not url:
        return None
    per_minute = int(getattr(settings, "notify_per_minute", 10) or 10)
    if _DISPATCHER is None or _DISPATCHER.url != url or _DISPATCHER.per_minute != per_minute:
        _DISPATCHER = Dispatcher(url=url, per_minute=per_minute)
    return _DISPATCHER


def set_dispatcher(d: Dispatcher | None) -> None:
    """Para os testes: troca o dispatcher do processo."""
    global _DISPATCHER
    _DISPATCHER = d


# Estado que sobrevive ao reinício do plugin (plugin.set) e a uma sessão nova da mesma conta:
# conta caída avisada (para o "voltou") e a última faixa do Top Catch.
_DOWN: dict[UUID, tuple[str, datetime]] = {}
_RANK_BAND: dict[UUID, Any] = {}


def reset_state() -> None:
    _DOWN.clear()
    _RANK_BAND.clear()


_CUTS: dict[tuple[Any, float], float] = {}
CUT_SAMPLES = 4000


def grade_cut(species_id: Any, base: dict[str, float], top_pct: float) -> float:
    """Nota acima da qual fica a fatia top_pct% dos nascimentos da espécie (sorteio fixo, em cache).

    A nota depende dos stats base (um Bulbasaur P1 comum tira ~0,6; o top 5% passa de ~1,57), então
    um corte fixo não serve para todas as espécies.
    """
    key = (species_id, top_pct)
    if key not in _CUTS:
        rng = random.Random(f"grade:{species_id}")
        grades = sorted(
            pokemon_grade(
                roll_ivs(rng, shiny=False), roll_quality(rng), roll_potency(rng), False, base
            )
            for _ in range(CUT_SAMPLES)
        )
        _CUTS[key] = grades[min(len(grades) - 1, int(len(grades) * (1 - top_pct / 100)))]
    return _CUTS[key]


# --- links e formatação ---------------------------------------------------------------------------


def account_link(settings: Any, account_id: UUID) -> str | None:
    base = (getattr(settings, "panel_url", None) or "").rstrip("/")
    return f"{base}/contas/{account_id}" if base else None


def sprite_url(species_id: Any, shiny: bool = False) -> str | None:
    if not isinstance(species_id, int) or not 0 < species_id <= MAX_DEX:
        return None
    return SPRITE.format(shiny="shiny/" if shiny else "", id=species_id)


def rank_band(position: Any, marks: list[int]) -> int | None:
    """A menor faixa que contém a posição (None: fora de todas)."""
    if not isinstance(position, int):
        return None
    return next((m for m in sorted(marks) if position <= m), None)


def sample_payload(nick: str, link: str | None) -> dict[str, Any]:
    embed: dict[str, Any] = {
        "title": "Aviso de teste",
        "description": f"O webhook está funcionando para **{nick}**.",
        "color": GREY,
        "footer": {"text": nick},
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if link:
        embed["url"] = link
    return {"embeds": [embed]}


async def send_test(settings: Any, nick: str, account_id: UUID) -> dict[str, Any]:
    """Comando `notify.test` do painel: manda já um aviso, sem esperar a fila."""
    d = get_dispatcher(settings)
    if d is None:
        raise WebhookError("DISCORD_WEBHOOK_URL não está no .env do worker")
    await d.send_now(sample_payload(nick, account_link(settings, account_id)))
    return {"sent": True}


# --- plugin ---------------------------------------------------------------------------------------


class NotifierPlugin(Plugin):
    name: ClassVar[str] = "notifier"
    description: ClassVar[str] = (
        "Avisos no Discord: shiny, captura rara, drop raro, queda, rank e nível"
    )
    config_model: ClassVar[type[BaseModel]] = NotifierConfig
    subscribes: ClassVar[set[str]] = {
        "kill",
        "pokemon.captured",
        "ball_thrower.shiny_missed",
        "session.connected",
        "session.disconnected",
        "session.rejected",
        "watchdog.no_kills",
        "rank.position",
        "level_up",
    }
    always_on: ClassVar[bool] = True

    def __init__(self) -> None:
        self.clock: Callable[[], float] = time.monotonic
        self.sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep
        self.wall: Callable[[], datetime] = lambda: datetime.now(UTC)
        self.disconnected_at: float | None = None
        self.last_disconnect_reason: str | None = None
        self._timer: asyncio.Task[None] | None = None

    async def start(self, ctx: PluginContext) -> None:
        await super().start(ctx)
        self.cfg: NotifierConfig = ctx.config  # type: ignore[assignment]
        self.dispatcher = get_dispatcher(ctx.settings)
        if self.dispatcher is None:
            # o host marca o plugin como degradado; a sessão segue
            raise WebhookError("sem DISCORD_WEBHOOK_URL no .env")
        self._timer = asyncio.create_task(self._tick_loop())

    async def stop(self) -> None:
        if self._timer is not None and not self._timer.done():
            self._timer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._timer

    # --- eventos ---------------------------------------------------------------------------------

    async def on_event(self, event: Event) -> None:
        if not self.cfg.active:
            return
        t, d = event.type, event.data
        if t == "kill":
            await self._kill(d)
        elif t == "pokemon.captured":
            self._captured(d)
        elif t == "ball_thrower.shiny_missed" and self.cfg.shiny_seen:
            name = d.get("wild_name") or "?"
            self._send(
                "shiny_seen",
                f"Shiny {name} sem bola",
                f"Apareceu um **{name}** shiny em `{d.get('hunt_slug') or '?'}` e não havia bola.",
                RED,
                thumb=sprite_url(self._species_id(name), shiny=True),
            )
        elif t == "session.disconnected":
            if self.disconnected_at is None:
                self.disconnected_at = self.clock()
            self.last_disconnect_reason = d.get("reason")
        elif t == "session.connected":
            self.disconnected_at = None
            down = _DOWN.get(self.ctx.account_id)
            if down is not None and down[0] != "no_kills":
                self._back(down)
        elif t == "session.rejected":
            reason = f"{d.get('state')}: {d.get('reason') or '?'}"
            self._down("rejected", "Conta parada", f"A sessão terminou ({reason}). Refaça o login.")
        elif t == "watchdog.no_kills":
            self._down(
                "no_kills",
                "Conta sem abates",
                f"Nenhum abate há {d.get('minutes', '?')} min em `{d.get('hunt_slug') or '?'}`.",
            )
        elif t == "rank.position":
            self._rank(d)
        elif t == "level_up":
            self._level(d)

    async def _kill(self, d: dict[str, Any]) -> None:
        down = _DOWN.get(self.ctx.account_id)
        if down is not None:  # abater é o melhor sinal de que voltou
            self._back(down)
        name = d.get("wild_name") or "?"
        hunt = d.get("hunt_slug") or "?"
        if d.get("shiny") and self.cfg.shiny_seen:
            self._send(
                "shiny_seen",
                f"Shiny visto: {name}",
                f"Um **{name}** shiny caiu em `{hunt}`.",
                GOLD,
                thumb=sprite_url(self._species_id(name), shiny=True),
            )
        if self.cfg.rare_drop:
            wanted = [w.lower() for w in self.cfg.drops if w.strip()]
            for drop in d.get("drops") or []:
                item = str((drop or {}).get("name") or "")
                if item and any(w in item.lower() for w in wanted):
                    qty = (drop or {}).get("qty") or 1
                    self._send(
                        "rare_drop",
                        f"Drop raro: {item}",
                        f"**{qty}× {item}** de um {name} em `{hunt}`.",
                        PURPLE,
                    )

    def _captured(self, d: dict[str, Any]) -> None:
        name = d.get("species") or "?"
        sid = d.get("species_id")
        potency = d.get("potency")
        grade = self._grade(d)
        fields = [
            ("Nota", f"{grade:.3f}" if grade is not None else "?"),
            ("Potência", f"P{potency}" if potency else "?"),
            (
                "Qualidade",
                f"{d['quality']:.2f}" if isinstance(d.get("quality"), int | float) else "?",
            ),
            ("Nível", str(d.get("level") or "?")),
        ]
        where = f"em `{d.get('hunt_slug') or '?'}`"
        if d.get("shiny"):
            if self.cfg.shiny_captured:
                self._send(
                    "shiny_captured",
                    f"Shiny capturado: {name}",
                    f"**{name}** shiny capturado {where}.",
                    GOLD,
                    thumb=sprite_url(sid, shiny=True),
                    fields=fields,
                )
            return
        if not self.cfg.rare_capture:
            return
        by_potency = isinstance(potency, int) and potency >= self.cfg.min_potency
        cut = self._grade_cut(sid)
        by_grade = grade is not None and cut is not None and grade >= cut
        if by_potency or by_grade:
            self._send(
                "rare_capture",
                f"Captura rara: {name}",
                f"**{name}** capturado {where}.",
                BLUE,
                thumb=sprite_url(sid),
                fields=fields,
            )

    def _rank(self, d: dict[str, Any]) -> None:
        acc = self.ctx.account_id
        band = rank_band(d.get("position"), self.cfg.rank_marks) if d.get("inside") else None
        first = acc not in _RANK_BAND
        before = _RANK_BAND.get(acc)
        _RANK_BAND[acc] = band
        if first or band == before or not self.cfg.rank:
            return  # a primeira posição vista no processo só marca a faixa
        pos = d.get("position")
        if band is None:
            title = "Top Catch: fora dos premiados"
            desc = f"Faltam {d.get('missing') or '?'} espécie(s) para entrar ({d.get('species')} na semana)."
            color = RED
        else:
            better = before is None or band < before
            title = f"Top Catch: {'entrou no' if better else 'caiu para o'} top {band}"
            marks = sorted(m for m in self.cfg.rank_marks if m < band)
            nxt = f" Próximo marco: top {marks[-1]}." if marks else ""
            desc = f"{pos}º lugar com {d.get('species')} espécie(s) na semana.{nxt}"
            color = GREEN if better else RED
        self._send("rank", title, desc, color)

    def _level(self, d: dict[str, Any]) -> None:
        if not self.cfg.level or d.get("who") != "treinador":
            return
        level = d.get("level")
        if isinstance(level, int) and level in self.cfg.level_marks:
            self._send(
                "level", f"Nível {level}", f"O treinador chegou ao nível **{level}**.", GREEN
            )

    # --- queda e volta ---------------------------------------------------------------------------

    async def _tick_loop(self) -> None:
        while True:
            await self.sleep(self.cfg.tick_s)
            self.check_down()

    def check_down(self) -> None:
        since = self.disconnected_at
        if since is None or not self.cfg.active:
            return
        minutes = (self.clock() - since) / 60
        if minutes >= self.cfg.down_after_min and self.ctx.account_id not in _DOWN:
            self._down(
                "disconnected",
                "Conta desconectada",
                f"Sem conexão há {round(minutes)} min ({self.last_disconnect_reason or '?'}).",
            )

    def _down(self, reason: str, title: str, desc: str) -> None:
        prev = _DOWN.get(self.ctx.account_id)
        if prev is not None and not (reason == "rejected" and prev[0] != "rejected"):
            return  # um aviso por queda (a sessão encerrada ainda avisa: pede ação)
        _DOWN[self.ctx.account_id] = (reason, self.wall())
        if self.cfg.account_down:
            self._send("account_down", title, desc, RED)

    def _back(self, down: tuple[str, datetime]) -> None:
        _DOWN.pop(self.ctx.account_id, None)
        if not self.cfg.account_down:
            return
        minutes = max(1, round((self.wall() - down[1]).total_seconds() / 60))
        self._send("account_down", "Conta de volta", f"Voltou depois de {minutes} min.", GREEN)

    # --- apoio -----------------------------------------------------------------------------------

    def _species_id(self, name: str | None) -> int | None:
        catalog = getattr(self.ctx.species, "species", None) or {}
        low = (name or "").lower()
        return next((sid for sid, s in catalog.items() if (s.name or "").lower() == low), None)

    def _base(self, species_id: Any) -> dict[str, float] | None:
        raw = (getattr(self.ctx.species, "raw", None) or {}).get(species_id)
        try:
            return {k: float(raw[BASE_KEYS[k]]) for k in STATS} if raw else None
        except (KeyError, TypeError, ValueError):
            return None

    def _grade(self, d: dict[str, Any]) -> float | None:
        base = self._base(d.get("species_id"))
        ivs, q, p = d.get("ivs") or {}, d.get("quality"), d.get("potency")
        if not base or not ivs or not isinstance(q, int | float) or not isinstance(p, int):
            return None
        return pokemon_grade(ivs, float(q), p, bool(d.get("shiny")), base)

    def _grade_cut(self, species_id: Any) -> float | None:
        """A nota das top_pct% melhores capturas (não shiny) da espécie."""
        base = self._base(species_id)
        if base is None or self.cfg.top_pct <= 0:
            return None
        return grade_cut(species_id, base, self.cfg.top_pct)

    def _send(
        self,
        kind: str,
        title: str,
        desc: str,
        color: int,
        *,
        thumb: str | None = None,
        fields: list[tuple[str, str]] | None = None,
    ) -> None:
        nick = self.ctx.nick
        embed: dict[str, Any] = {
            "title": f"{title} · {nick}",
            "description": desc,
            "color": color,
            "footer": {"text": nick},
            "timestamp": self.wall().isoformat(),
        }
        link = account_link(self.ctx.settings, self.ctx.account_id)
        if link:
            embed["url"] = link
        if thumb:
            embed["thumbnail"] = {"url": thumb}
        if fields:
            embed["fields"] = [{"name": n, "value": v, "inline": True} for n, v in fields]
        log.info("[%s] aviso %s: %s", nick, kind, title)
        self.dispatcher.submit(Notice(kind, {"embeds": [embed]}))
