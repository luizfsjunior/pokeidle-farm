"""Conferência do IP de saída antes de falar com o jogo (ADR 0013 e ADR 0015).

O jogo recusa IP de datacenter com `auth.provedorBanido` (ADR 0011). Antes de cada
conexão, o worker pergunta ao ipapi.is (o mesmo serviço que a moderação usa, pelos
Termos, seção 8) que tipo de IP é o de saída, pelo mesmo caminho do tráfego do jogo.
Se o ipapi.is não responder, pergunta ao ip-api.com. Se for datacenter, ou se nenhum
dos dois confirmar, não conecta: na dúvida, o jogo não vê o IP (ADR 0015).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

IPAPI_URL = "https://api.ipapi.is/"
# Segundo serviço, só quando o ipapi.is falha. O plano grátis do ip-api.com é só HTTP; o que
# trafega é o próprio IP de saída, que o serviço já vê. O ipinfo.io grátis não diz se é hosting.
IP_API_COM_URL = (
    "http://ip-api.com/json/?fields=status,message,query,isp,org,as,mobile,proxy,hosting"
)


@dataclass(frozen=True)
class ExitIp:
    ip: str
    datacenter: bool
    vpn: bool
    proxy: bool
    company_type: str | None
    asn_type: str | None
    company: str | None
    source: str = "ipapi.is"

    @property
    def masked_ip(self) -> str:
        """Só o começo do IP no log (o IP inteiro não precisa ir para o log nem para o banco)."""
        parts = self.ip.split(".")
        return ".".join([*parts[:2], "x", "x"]) if len(parts) == 4 else self.ip[:9] + "…"

    def summary(self) -> str:
        flags = [
            n
            for n, v in (("datacenter", self.datacenter), ("vpn", self.vpn), ("proxy", self.proxy))
            if v
        ]
        kind = self.company_type or self.asn_type or "?"
        return f"{self.masked_ip} ({self.company or '?'}, tipo {kind}{', ' + '/'.join(flags) if flags else ''})"


def _obj(value: Any) -> dict[str, Any]:
    """`company` e `asn` vinham como objeto; o ipapi.is passou a mandar outros formatos
    (texto, lista) e o `.get` quebrava com AttributeError (23/11). Aceita qualquer um."""
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return next((v for v in value if isinstance(v, dict)), {})
    if isinstance(value, str):
        return {"name": value}
    return {}


def parse(data: dict[str, Any]) -> ExitIp:
    if not isinstance(data, dict):
        raise ValueError(f"resposta inesperada do ipapi.is: {type(data).__name__}")
    company = _obj(data.get("company"))
    asn = _obj(data.get("asn"))
    return ExitIp(
        ip=str(data.get("ip") or ""),
        datacenter=bool(data.get("is_datacenter")),
        vpn=bool(data.get("is_vpn")),
        proxy=bool(data.get("is_proxy")),
        company_type=_str(company.get("type")),
        asn_type=_str(asn.get("type")),
        company=_str(company.get("name") or asn.get("org")),
    )


def parse_ip_api_com(data: dict[str, Any]) -> ExitIp:
    """Resposta do ip-api.com: `hosting` marca datacenter; `mobile`, operadora de celular."""
    if not isinstance(data, dict) or data.get("status") != "success":
        msg = data.get("message") if isinstance(data, dict) else type(data).__name__
        raise ValueError(f"ip-api.com não respondeu: {msg}")
    hosting = bool(data.get("hosting"))
    kind = "hosting" if hosting else ("mobile" if data.get("mobile") else "isp")
    return ExitIp(
        ip=str(data.get("query") or ""),
        datacenter=hosting,
        vpn=False,
        proxy=bool(data.get("proxy")),
        company_type=kind,
        asn_type=None,
        company=_str(data.get("isp")) or _str(data.get("org")),
        source="ip-api.com",
    )


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


class ExitIpUnknown(Exception):
    """Nenhum serviço confirmou o IP de saída: o worker não fala com o jogo (ADR 0015)."""


async def _get_json(url: str, proxy: str | None, wait_s: float) -> Any:
    import httpx

    async with httpx.AsyncClient(timeout=wait_s, proxy=proxy, trust_env=False) as client:
        res = await client.get(url, headers={"User-Agent": "pokeidle-farm-worker"})
        res.raise_for_status()
        return res.json()


async def fetch_exit_ip(proxy: str | None, wait_s: float = 15.0) -> ExitIp:
    """O IP de saída pelo ipapi.is; se ele falhar, pelo ip-api.com. ExitIpUnknown se os dois
    falharem. `wait_s` vale para cada serviço."""
    errors: list[str] = []
    services = (("ipapi.is", IPAPI_URL, parse), ("ip-api.com", IP_API_COM_URL, parse_ip_api_com))
    for name, url, parser in services:
        try:
            got = parser(await _get_json(url, proxy, wait_s))
        except Exception as exc:
            errors.append(f"{name}: {exc!r}")
            continue
        if got.ip:
            return got
        errors.append(f"{name}: resposta sem IP")
    raise ExitIpUnknown("; ".join(errors))


def blocks_connection(exit_ip: ExitIp) -> bool:
    """IP de datacenter (ou hosting) não conecta. VPN e proxy não bloqueiam: o suporte
    liberou o uso (ADR 0013); o que o jogo barra é o provedor de servidor."""
    return exit_ip.datacenter or exit_ip.company_type == "hosting" or exit_ip.asn_type == "hosting"


class ExitIpBlocked(Exception):
    """O IP de saída é de datacenter: o jogo recusa e insistir piora a situação da conta."""

    def __init__(self, exit_ip: ExitIp) -> None:
        super().__init__(f"IP de saída de datacenter: {exit_ip.summary()}")
        self.exit_ip = exit_ip


Fetch = Callable[[str | None, float], Awaitable[ExitIp]]


class ExitGuard:
    """Só deixa falar com o jogo depois de confirmar que o IP de saída não é de datacenter.

    Para os downloads do jogo (Pokedex, itens, arquivos): uma confirmação vale por `ttl_s` e
    as chamadas ao mesmo tempo esperam a mesma consulta. As sessões conferem a cada conexão
    (session.py), sem cache.
    """

    def __init__(
        self,
        proxy: str | None,
        *,
        enabled: bool = True,
        ttl_s: float = 600.0,
        wait_s: float = 8.0,
        fetch: Fetch | None = None,
    ) -> None:
        self.proxy = proxy
        self.enabled = enabled
        self.ttl_s = ttl_s
        self.wait_s = wait_s
        self._fetch = fetch
        self._ok_at: float | None = None
        self._lock = asyncio.Lock()

    async def ensure(self) -> None:
        """Retorna se o IP de saída está confirmado; senão ExitIpBlocked ou ExitIpUnknown."""
        if not self.enabled:
            return
        async with self._lock:
            if self._ok_at is not None and time.monotonic() - self._ok_at < self.ttl_s:
                return
            self._ok_at = None
            fetch = self._fetch or fetch_exit_ip
            got = await fetch(self.proxy, self.wait_s)
            if blocks_connection(got):
                raise ExitIpBlocked(got)
            self._ok_at = time.monotonic()

    def wrap(self, get: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        """Um http_get que só sai depois do `ensure`."""

        async def guarded(*args: Any, **kwargs: Any) -> Any:
            await self.ensure()
            return await get(*args, **kwargs)

        return guarded
