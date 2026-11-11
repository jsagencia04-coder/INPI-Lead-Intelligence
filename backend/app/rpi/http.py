"""Cliente HTTP para o site da RPI. Os testes trocam `transport` por um mock."""

import httpx

from app.config import get_settings

transport: httpx.BaseTransport | None = None  # sobrescrito nos testes


def client() -> httpx.Client:
    s = get_settings()
    return httpx.Client(
        headers={"User-Agent": s.rpi_user_agent},
        timeout=httpx.Timeout(s.http_timeout_seconds, connect=30),
        follow_redirects=True,
        transport=transport,
    )
