"""Registro de handlers: cada tipo de job aponta para a função de um agente."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from psycopg import Connection


class PermanentError(Exception):
    """Erro que não adianta repetir (ex.: arquivo inválido). Vai direto para 'dead'."""


class RetryLater(Exception):
    """Falha temporária com espera definida pelo agente (ex.: site bloqueou: tentar em 2 h)."""

    def __init__(self, message: str, delay_seconds: int):
        super().__init__(message)
        self.delay_seconds = delay_seconds


@dataclass
class JobContext:
    job: dict
    worker_id: str

    @property
    def payload(self) -> dict[str, Any]:
        return self.job["payload"]

    @property
    def actor(self) -> str:
        return f"agent:{self.job['tipo']}#{self.job['id']}"


Handler = Callable[[Connection, JobContext], dict[str, Any] | None]
# Chamado quando o job esgota as tentativas (ex.: marcar a edição como 'error').
OnDead = Callable[[Connection, dict, str], None]
_HANDLERS: dict[str, Handler] = {}
_ON_DEAD: dict[str, OnDead] = {}


def handler(tipo: str, on_dead: OnDead | None = None) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        if tipo in _HANDLERS:
            raise ValueError(f"Handler duplicado para {tipo}")
        _HANDLERS[tipo] = fn
        if on_dead:
            _ON_DEAD[tipo] = on_dead
        return fn

    return deco


def get_handler(tipo: str) -> Handler | None:
    return _HANDLERS.get(tipo)


def get_on_dead(tipo: str) -> OnDead | None:
    return _ON_DEAD.get(tipo)


def registered_types() -> list[str]:
    return sorted(_HANDLERS)


def load_agents() -> None:
    """Importa os módulos de agentes para que registrem seus handlers."""
    from app.agents import cnpj, inpi, leads, research, rpi, semana, site_crawler, system, whatsapp_send  # noqa: F401
