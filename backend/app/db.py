"""Acesso ao PostgreSQL (psycopg 3 + pool).

Toda transação de escrita deve passar um `actor`, que vai para a trilha de
auditoria (audit_log) via `set_config('app.actor', ..., true)`.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import get_settings

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            get_settings().database_url,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row, "autocommit": False},
            open=True,
        )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def transaction(actor: str) -> Iterator[Connection]:
    """Abre uma transação com o ator registrado para auditoria."""
    with get_pool().connection() as conn, conn.transaction():
        conn.execute("select set_config('app.actor', %s, true)", (actor,))
        yield conn
