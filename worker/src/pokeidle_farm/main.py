"""Ponto de entrada do worker.

    pokeidle-farm run                       # sobe as sessões das contas de farm
    pokeidle-farm set-token --nick NICK     # grava token e dispositivo no Vault

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


async def run(settings: Settings) -> int:
    store = await _make_store(settings)
    accounts = [a for a in await store.list_accounts() if a.enabled and a.role == "farm"]
    if not accounts:
        log.error("nenhuma conta de farm habilitada")
        return 1
    if len(accounts) > 3:
        # 4 contas por pessoa no total (Termos, seção 5); uma é a pessoal, fora do worker.
        log.error("%d contas de farm configuradas; o máximo é 3", len(accounts))
        return 1

    available = discover()
    log.info("plugins disponíveis: %s", ", ".join(sorted(available)) or "nenhum")

    sessions = [AccountSession(a, store, settings, PluginHost(available)) for a in accounts]

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: [s.stop() for s in sessions])
        except NotImplementedError:  # Windows
            pass

    results = await asyncio.gather(*(s.run() for s in sessions))
    for s, state in zip(sessions, results, strict=True):
        log.info("[%s] terminou em %s", s.account.nick, state.name)
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


def cli() -> None:
    parser = argparse.ArgumentParser(prog="pokeidle-farm")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="sobe as sessões das contas de farm")
    st = sub.add_parser("set-token", help="grava o token de uma conta no Vault")
    st.add_argument("--nick", required=True)
    st.add_argument("--device", required=True, help="valor de localStorage['id-dispositivo']")
    args = parser.parse_args()

    settings = Settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    if args.cmd == "run":
        code = asyncio.run(run(settings))
    else:
        code = asyncio.run(set_token(settings, args.nick, args.device))
    sys.exit(code)


if __name__ == "__main__":
    cli()
