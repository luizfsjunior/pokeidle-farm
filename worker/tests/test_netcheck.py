"""ADR 0013 e 0015: conferência do IP de saída antes de falar com o jogo."""

from __future__ import annotations

import pytest

from pokeidle_farm import main, netcheck
from pokeidle_farm.config import Settings
from pokeidle_farm.netcheck import (
    IP_API_COM_URL,
    IPAPI_URL,
    ExitGuard,
    ExitIpBlocked,
    ExitIpUnknown,
    blocks_connection,
    fetch_exit_ip,
    parse,
    parse_ip_api_com,
)

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

    def use(payload=None, exc=None, fail_times=0):
        async def fetch(proxy, wait_s=15.0):
            calls.append(proxy)
            if exc and (not fail_times or len(calls) <= fail_times):
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


async def test_check_failure_waits_instead_of_going_ahead(fake_fetch, caplog):
    """Sem confirmação não sobe no escuro: espera e confere de novo (ADR 0015)."""
    calls = fake_fetch(ISP, exc=ExitIpUnknown("os dois fora"), fail_times=2)
    assert await main._exit_ip_ok(settings(), retry_s=0) is True
    assert len(calls) == 3
    assert "não falo com o jogo" in caplog.text


async def test_check_disabled(fake_fetch):
    calls = fake_fetch(DIGITALOCEAN)
    assert await main._exit_ip_ok(settings(exit_ip_check=False)) is True
    assert calls == []


def test_settings_hide_proxy_secret():
    s = settings(game_proxy_url="socks5://u:segredo@h:1080")
    assert s.game_proxy == "socks5://u:segredo@h:1080"
    assert "segredo" not in repr(s)


# --- segundo serviço (ip-api.com) -------------------------------------------------------

IP_API_DO = {
    "status": "success",
    "query": "165.22.1.2",
    "isp": "DigitalOcean, LLC",
    "hosting": True,
    "mobile": False,
    "proxy": False,
}
IP_API_VIVO = {
    "status": "success",
    "query": "179.84.141.61",
    "isp": "TELEFÔNICA BRASIL S.A",
    "hosting": False,
    "mobile": True,
    "proxy": False,
}


def test_parse_ip_api_com():
    dc = parse_ip_api_com(IP_API_DO)
    assert blocks_connection(dc) and dc.source == "ip-api.com"
    vivo = parse_ip_api_com(IP_API_VIVO)
    assert not blocks_connection(vivo) and vivo.company_type == "mobile"
    assert vivo.company == "TELEFÔNICA BRASIL S.A"
    with pytest.raises(ValueError):
        parse_ip_api_com({"status": "fail", "message": "quota"})


@pytest.fixture
def fake_http(monkeypatch):
    def use(answers: dict[str, object]):
        asked: list[str] = []

        async def get_json(url, proxy, wait_s):
            asked.append(url)
            got = answers[url]
            if isinstance(got, Exception):
                raise got
            return got

        monkeypatch.setattr(netcheck, "_get_json", get_json)
        return asked

    return use


async def test_fetch_uses_ipapi_is_first(fake_http):
    asked = fake_http({IPAPI_URL: ISP, IP_API_COM_URL: IP_API_DO})
    got = await fetch_exit_ip(None)
    assert got.source == "ipapi.is" and asked == [IPAPI_URL]


async def test_fetch_falls_back_to_ip_api_com(fake_http):
    asked = fake_http({IPAPI_URL: TimeoutError(), IP_API_COM_URL: IP_API_VIVO})
    got = await fetch_exit_ip(None)
    assert got.source == "ip-api.com" and asked == [IPAPI_URL, IP_API_COM_URL]
    assert not blocks_connection(got)


async def test_fetch_falls_back_when_ipapi_is_has_no_ip(fake_http):
    fake_http({IPAPI_URL: {"ip": ""}, IP_API_COM_URL: IP_API_DO})
    assert blocks_connection(await fetch_exit_ip(None))


async def test_fetch_both_down_raises_unknown(fake_http):
    fake_http({IPAPI_URL: TimeoutError(), IP_API_COM_URL: {"status": "fail", "message": "quota"}})
    with pytest.raises(ExitIpUnknown) as err:
        await fetch_exit_ip(None)
    assert "ipapi.is" in str(err.value) and "ip-api.com" in str(err.value)


# --- trava dos downloads do jogo ---------------------------------------------------------


def guard_with(*answers, **kw) -> tuple[ExitGuard, list[str | None]]:
    calls: list[str | None] = []
    queue = list(answers)

    async def fetch(proxy, wait_s):
        calls.append(proxy)
        got = queue.pop(0)
        if isinstance(got, Exception):
            raise got
        return got

    return ExitGuard("socks5://p", fetch=fetch, **kw), calls


async def test_guard_confirms_once_per_ttl():
    guard, calls = guard_with(parse(ISP), parse(ISP))
    await guard.ensure()
    await guard.ensure()
    assert calls == ["socks5://p"]  # a segunda vale pelo cache


async def test_guard_rechecks_after_ttl():
    guard, calls = guard_with(parse(ISP), parse(DIGITALOCEAN), ttl_s=0)
    await guard.ensure()
    with pytest.raises(ExitIpBlocked):
        await guard.ensure()
    assert len(calls) == 2


async def test_guard_blocks_download_on_datacenter_or_unknown():
    downloads: list[str] = []

    async def get(url, etag):
        downloads.append(url)
        return 200, None, b""

    for answer, error in (
        (parse(DIGITALOCEAN), ExitIpBlocked),
        (ExitIpUnknown("x"), ExitIpUnknown),
    ):
        guard, _ = guard_with(answer)
        with pytest.raises(error):
            await guard.wrap(get)("https://pokeidle.io/assets/items.json", None)
    assert downloads == []  # o jogo não viu nada


async def test_guard_failure_is_not_cached():
    guard, calls = guard_with(ExitIpUnknown("x"), parse(ISP))
    with pytest.raises(ExitIpUnknown):
        await guard.ensure()
    await guard.ensure()
    assert len(calls) == 2


async def test_guard_disabled_skips_check():
    guard, calls = guard_with(parse(DIGITALOCEAN), enabled=False)
    await guard.ensure()
    assert calls == []
