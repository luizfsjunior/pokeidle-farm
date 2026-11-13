"""Ponto de entrada do worker.

    pokeidle-farm run                       # sobe as sessões das contas de farm
    pokeidle-farm set-token --nick NICK     # grava token e dispositivo no Vault
    pokeidle-farm simulate --nick NICK      # grava eventos simulados (dev sem o jogo)
    pokeidle-farm listen --fake             # só os comandos do painel, sem conectar no jogo

Sem SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY no ambiente, o `run` usa o modo
memória com a conta ACCOUNT_1_* do .env (só para desenvolvimento).
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import signal
import sys
from uuid import NAMESPACE_URL, uuid5

from .commands import CommandError, CommandLoop, FakeSession, SessionLike, Supervisor
from .config import Settings
from .plugins.registry import PluginHost, discover
from .session import AccountSession
from .store.base import AccountRecord, Store
from .store.memory import MemoryStore

log = logging.getLogger("pokeidle_farm")


async def _make_store(settings: Settings) -> Store:
    if settings.uses_supabase:
        from .store.supabase import SupabaseStore

        assert settings.supabase_url and settings.supabase_service_role_key
        return await SupabaseStore.connect(
            settings.supabase_url, settings.supabase_service_role_key.get_secret_value()
        )

    log.warning("Supabase não configurado: modo memória (eventos não são persistidos no banco)")
    store = MemoryStore()
    if settings.account_1_nick and settings.account_1_token and settings.account_1_device_id:
        account = AccountRecord(
            id=uuid5(NAMESPACE_URL, f"pokeidle:{settings.account_1_nick}"),
            nick=settings.account_1_nick,
            role="farm",
        )
        store.add_account(
            account, settings.account_1_token.get_secret_value(), settings.account_1_device_id
        )
    return store


async def run(settings: Settings, *, fake: bool = False) -> int:
    """Sobe as sessões das contas habilitadas e atende os comandos do painel.

    Com `fake=True` (`listen --fake`) as sessões não conectam no jogo: serve para
    testar os comandos de ponta a ponta.
    """
    store = await _make_store(settings)
    available = discover()
    log.info("plugins disponíveis: %s", ", ".join(sorted(available)) or "nenhum")

    def make_session(acc: AccountRecord) -> SessionLike:
        if fake:
            return FakeSession(acc, PluginHost(available))
        return AccountSession(acc, store, settings, PluginHost(available))

    sup = Supervisor(store, make_session, available, settings.worker_holder)
    try:
        await sup.load()
    except CommandError as exc:
        log.error("%s", exc)
        return 1
    if not sup.accounts:
        log.error("nenhuma conta de farm cadastrada")
        return 1
    if not any(a.enabled for a in sup.accounts.values()):
        log.warning("nenhuma conta de farm habilitada; esperando comandos do painel")

    sup.start_enabled()
    commands = CommandLoop(sup, store, poll_s=settings.commands_poll_s)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, commands.stop)
        except NotImplementedError:  # Windows
            pass

    try:
        if settings.uses_supabase:
            # Fica no ar mesmo com as sessões paradas (needs_login, rejected):
            # um comando pode religá-las. Estados terminais não se resolvem
            # reiniciando o processo (ver docker-compose.yml).
            await commands.run()
        else:
            # modo memória: sem painel, termina quando as sessões terminam
            await asyncio.gather(*(live.task for live in sup.live.values()))
    finally:
        await sup.stop_all()
    return 0


async def set_token(settings: Settings, nick: str, device_id: str) -> int:
    if not settings.uses_supabase:
        log.error("set-token precisa de SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY")
        return 1
    store = await _make_store(settings)
    account = next((a for a in await store.list_accounts() if a.nick == nick), None)
    if account is None:
        log.error("conta %s não encontrada (ou desabilitada) na tabela accounts", nick)
        return 1
    token = getpass.getpass(f"token de {nick} (não aparece na tela): ").strip()
    if not token:
        log.error("token vazio")
        return 1
    await store.set_token(account.id, token, device_id)
    log.info("token de %s gravado no Vault", nick)
    return 0


async def simulate(settings: Settings, nick: str, days: float, live: bool, seed: int | None) -> int:
    from collections import Counter
    from datetime import UTC, datetime, timedelta

    from .sim.generator import EventSimulator, SimConfig

    store = await _make_store(settings)
    account = next((a for a in await store.list_accounts() if a.nick == nick), None)
    if account is None:
        log.error("conta %s não encontrada (ou desabilitada) na tabela accounts", nick)
        return 1

    sim = EventSimulator(account.id, SimConfig(seed=seed))
    counts: Counter[str] = Counter()
    batch: list[dict] = []

    async def flush() -> None:
        if batch:
            await store.insert_events(batch)
            batch.clear()

    now = datetime.now(UTC)
    log.info("simulando %.1f dia(s) de eventos para %s...", days, nick)
    for ev in sim.generate(now - timedelta(days=days), now):
        counts[ev.type] += 1
        batch.append(ev.to_row())
        if len(batch) >= 500:
            await flush()
    await flush()
    log.info("gravados: %s", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    try:
        rows = await store.refresh_metrics(now - timedelta(days=days), now)
    except Exception as exc:
        log.warning(
            "eventos gravados, mas não deu para recalcular as métricas (%s). "
            "A migration 20261112010000_metrics.sql foi aplicada?",
            exc,
        )
    else:
        if rows:
            log.info("métricas por hora recalculadas: %d linhas", rows)

    if live:
        log.info("modo ao vivo: gerando eventos em tempo real (Ctrl+C para parar)")
        try:
            while True:
                start = datetime.now(UTC)
                await asyncio.sleep(settings.telemetry_flush_s)
                for ev in sim.generate(start, datetime.now(UTC)):
                    if ev.type not in ("state.snapshot", "session.connected"):
                        batch.append(ev.to_row())
                await flush()
        except asyncio.CancelledError:
            await flush()
    log.info(
        "para apagar: delete from public.events where raw->>'_sim' = 'true'; "
        "depois: select public.refresh_metric_hourly('2026-01-01', now());"
    )
    return 0


def cli() -> None:
    parser = argparse.ArgumentParser(prog="pokeidle-farm")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="sobe as sessões das contas de farm e atende os comandos")
    ls = sub.add_parser("listen", help="atende os comandos do painel com sessões falsas")
    ls.add_argument("--fake", action="store_true", required=True, help="não conecta no jogo")
    st = sub.add_parser("set-token", help="grava o token de uma conta no Vault")
    st.add_argument("--nick", required=True)
    st.add_argument("--device", required=True, help="valor de localStorage['id-dispositivo']")
    sm = sub.add_parser(
        "simulate", help="grava eventos simulados (para desenvolver métricas e painel)"
    )
    sm.add_argument("--nick", required=True)
    sm.add_argument("--days", type=float, default=3.0, help="dias de histórico a gerar (padrão: 3)")
    sm.add_argument(
        "--live", action="store_true", help="depois do histórico, continua gerando ao vivo"
    )
    sm.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    settings = Settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    # O cliente do Supabase loga cada requisição HTTP em INFO; só interessa se der erro.
    for noisy in ("httpx", "httpcore", "hpack"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    if args.cmd == "run":
        code = asyncio.run(run(settings))
    elif args.cmd == "listen":
        if not settings.uses_supabase:
            log.error("listen precisa de SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY")
            sys.exit(1)
        code = asyncio.run(run(settings, fake=True))
    elif args.cmd == "simulate":
        try:
            code = asyncio.run(simulate(settings, args.nick, args.days, args.live, args.seed))
        except KeyboardInterrupt:
            code = 0
    else:
        code = asyncio.run(set_token(settings, args.nick, args.device))
    sys.exit(code)


if __name__ == "__main__":
    cli()
