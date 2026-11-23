"""ADR 0013: conferência do IP de saída antes de conectar."""

from __future__ import annotations

import pytest

from pokeidle_farm import main
from pokeidle_farm.config import Settings
from pokeidle_farm.netcheck import blocks_connection, parse

DIGITALOCEAN = {
    "ip": "164.90.1.2",
    "is_datacenter": True,
    "is_vpn": False,
    "is_proxy": False,
    "company": {"name": "DigitalOcean, LLC", "type": "hosting"},
    "asn": {"type": "hosting"},
}
ISP = {
    "ip": "189.10.20.30",
    "is_datacenter": False,
    "is_vpn": False,
    "is_proxy": True,
    "company": {"name": "Claro S.A.", "type": "isp"},
    "asn": {"type": "isp"},
}


def test_parse_and_block_rules():
    dc = parse(DIGITALOCEAN)
    assert blocks_connection(dc)
    assert dc.masked_ip == "164.90.x.x"
    assert "DigitalOcean" in dc.summary() and "datacenter" in dc.summary()
    isp = parse(ISP)
    assert not blocks_connection(isp)  # proxy marcado não bloqueia: o suporte liberou
    assert "164.90.1.2" not in dc.summary() and "189.10.20.30" not in isp.summary()
    hosting_only = parse({**ISP, "company": {"type": "hosting"}})
    assert blocks_connection(hosting_only)


def test_parse_tolerates_other_shapes():
    """ipapi.is mudou o formato e o parse quebrava com AttributeError (23/11)."""
    as_text = parse({"ip": "1.2.3.4", "company": "GTI BRASIL", "asn": "AS273443"})
    assert as_text.company == "GTI BRASIL" and not blocks_connection(as_text)
    as_list = parse({"ip": "1.2.3.4", "company": [{"name": "X", "type": "hosting"}], "asn": None})
    assert as_list.company == "X" and blocks_connection(as_list)
    nothing = parse({"ip": "1.2.3.4"})
    assert nothing.company is None and not blocks_connection(nothing)


def settings(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


@pytest.fixture
def fake_fetch(monkeypatch):
    calls: list[str | None] = []

    def use(payload=None, exc=None):
        async def fetch(proxy, wait_s=15.0):
            calls.append(proxy)
            if exc:
                raise exc
            return parse(payload)

        monkeypatch.setattr(main, "fetch_exit_ip", fetch)
        return calls

    return use


async def test_datacenter_exit_refuses(fake_fetch, caplog):
    fake_fetch(DIGITALOCEAN)
    assert await main._exit_ip_ok(settings()) is False
    assert "provedorBanido" in caplog.text


async def test_proxy_exit_goes_through_proxy(fake_fetch, caplog):
    calls = fake_fetch(ISP)
    s = settings(game_proxy_url="http://u:segredo@proxy.exemplo:8080")
    assert await main._exit_ip_ok(s) is True
    assert calls == ["http://u:segredo@proxy.exemplo:8080"]
    assert "segredo" not in caplog.text  # credencial do proxy nunca vai para o log


async def test_check_failure_does_not_block(fake_fetch):
    fake_fetch(exc=ConnectionError("fora do ar"))
    assert await main._exit_ip_ok(settings()) is True


async def test_check_disabled(fake_fetch):
    calls = fake_fetch(DIGITALOCEAN)
    assert await main._exit_ip_ok(settings(exit_ip_check=False)) is True
    assert calls == []


def test_settings_hide_proxy_secret():
    s = settings(game_proxy_url="socks5://u:segredo@h:1080")
    assert s.game_proxy == "socks5://u:segredo@h:1080"
    assert "segredo" not in repr(s)
