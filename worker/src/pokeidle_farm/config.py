"""Configuração do worker, lida do ambiente (.env).

A mesma imagem roda local ou no droplet; só o .env muda.
"""

from __future__ import annotations

import socket

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Supabase. Sem estes dois, o worker roda em modo memória (desenvolvimento).
    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None

    # Jogo
    ws_url: str = "wss://pokeidle.io"

    # Identificação desta instância no lease das contas (ex.: "notebook", "droplet-1").
    worker_holder: str = Field(default_factory=socket.gethostname)

    # Sessão
    welcome_timeout_s: float = 15.0
    ping_interval_s: float = 30.0
    ping_timeout_s: float = 60.0  # 30 s de intervalo + 60 s de espera ≈ 90 s sem resposta
    reconnect_min_s: float = 10.0
    reconnect_max_s: float = 300.0
    online_limit_retry_s: float = 30.0
    online_limit_max_retries: int = 10

    # Lease
    lease_ttl_s: int = 90
    lease_renew_s: float = 30.0
    lease_busy_retry_s: float = 60.0

    # Telemetria
    telemetry_batch_size: int = 100
    telemetry_flush_s: float = 2.0
    telemetry_buffer_path: str = "data/telemetry-buffer.jsonl"

    # Comandos do painel (fase 4b): intervalo da busca por pendentes.
    commands_poll_s: float = 5.0

    # Ações. Na fase 2 o gateway só observa.
    action_mode: str = "observe_only"

    log_level: str = "INFO"

    # Modo memória: uma conta vinda do .env (ACCOUNT_1_*).
    account_1_nick: str | None = None
    account_1_token: SecretStr | None = None
    account_1_device_id: str | None = None

    @property
    def uses_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)
