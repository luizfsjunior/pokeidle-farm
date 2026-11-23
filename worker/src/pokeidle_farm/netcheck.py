"""Conferência do IP de saída antes de conectar no jogo (ADR 0013).

O jogo recusa IP de datacenter com `auth.provedorBanido` (ADR 0011). Antes de abrir
qualquer sessão, o worker pergunta ao ipapi.is (o mesmo serviço que a moderação usa,
pelos Termos, seção 8) que tipo de IP é o de saída, pelo mesmo caminho do tráfego do
jogo. Se for datacenter, não conecta.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

IPAPI_URL = "https://api.ipapi.is/"


@dataclass(frozen=True)
class ExitIp:
    ip: str
    datacenter: bool
    vpn: bool
    proxy: bool
    company_type: str | None
    asn_type: str | None
    company: str | None

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


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


async def fetch_exit_ip(proxy: str | None, wait_s: float = 15.0) -> ExitIp:
    import httpx

    async with httpx.AsyncClient(timeout=wait_s, proxy=proxy, trust_env=False) as client:
        res = await client.get(IPAPI_URL, headers={"User-Agent": "pokeidle-farm-worker"})
        res.raise_for_status()
        return parse(res.json())


def blocks_connection(exit_ip: ExitIp) -> bool:
    """IP de datacenter (ou hosting) não conecta. VPN e proxy não bloqueiam: o suporte
    liberou o uso (ADR 0013); o que o jogo barra é o provedor de servidor."""
    return exit_ip.datacenter or exit_ip.company_type == "hosting" or exit_ip.asn_type == "hosting"
