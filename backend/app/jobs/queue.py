"""Fila de jobs sobre o PostgreSQL.

- `enqueue` é idempotente quando recebe `dedupe_key` (um job ativo por chave).
- `claim` usa FOR UPDATE SKIP LOCKED: vários workers podem rodar em paralelo
  sem pegar o mesmo job.
- Falhas fazem retry com backoff exponencial; esgotadas as tentativas, o job
  vai para 'dead' e aparece no dashboard para revisão humana.
"""

from datetime import datetime
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

BACKOFF_BASE_SECONDS = 30
# V2.6: teto de prioridade (menor = antes) para tarefas que alimentam a operação. Sem isto, milhares de pesquisas e
# verificações enfileiradas (prioridade 60-90) deixavam a releitura da RPI parada por dias, sem erro visível.
PRIORIDADE_TETO = {
    "rpi.semana": 5,
    "rpi.discover": 10,
    "rpi.collect": 10,
    "rpi.parse": 10,
    "rpi.historico": 15,
    "leads.build": 20,
    "servicos.analisar": 20,
}
BACKOFF_MAX_SECONDS = 6 * 3600


def enqueue(
    conn: Connection,
    tipo: str,
    payload: dict[str, Any] | None = None,
    *,
    dedupe_key: str | None = None,
    prioridade: int = 100,
    max_tentativas: int = 5,
    run_after: datetime | None = None,
    parent_id: int | None = None,
) -> dict | None:
    """Enfileira um job. Retorna o job criado, ou o job ativo já existente com
    a mesma `dedupe_key` (cuja prioridade sobe, se a nova for mais urgente)."""
    prioridade = min(prioridade, PRIORIDADE_TETO.get(tipo, prioridade))
    row = conn.execute(
        """
        insert into jobs (tipo, payload, dedupe_key, prioridade, max_tentativas,
                          run_after, parent_id)
        values (%s, %s, %s, %s, %s, coalesce(%s, now()), %s)
        on conflict (dedupe_key) where dedupe_key is not null
                                   and status in ('queued','running')
        do nothing
        returning *
        """,
        (tipo, Jsonb(payload or {}), dedupe_key, prioridade, max_tentativas, run_after, parent_id),
    ).fetchone()
    if row is None and dedupe_key is not None:
        row = (
            conn.execute(
                "update jobs set prioridade = %s where dedupe_key = %s and status = 'queued' and prioridade > %s returning *",
                (prioridade, dedupe_key, prioridade),
            ).fetchone()
            or conn.execute(
                "select * from jobs where dedupe_key = %s and status in ('queued','running')",
                (dedupe_key,),
            ).fetchone()
        )
    return row


def claim(conn: Connection, worker_id: str, tipos: list[str] | None = None) -> dict | None:
    """Reserva o próximo job disponível (ou None)."""
    return conn.execute(
        """
        with next_job as (
          select id from jobs
          where status = 'queued' and run_after <= now()
            and (%(tipos)s::text[] is null or tipo = any(%(tipos)s::text[]))
          order by prioridade, run_after, id
          for update skip locked
          limit 1
        )
        update jobs j
           set status = 'running', locked_by = %(worker)s, locked_at = now(),
               iniciado_em = coalesce(j.iniciado_em, now()), tentativas = j.tentativas + 1
          from next_job
         where j.id = next_job.id
        returning j.*
        """,
        {"tipos": tipos, "worker": worker_id},
    ).fetchone()


def complete(conn: Connection, job_id: int, resultado: dict[str, Any] | None = None) -> None:
    conn.execute(
        """
        update jobs set status = 'succeeded', resultado = %s, finalizado_em = now(),
                        locked_at = null, ultimo_erro = null
         where id = %s and status = 'running'
        """,
        (Jsonb(resultado or {}), job_id),
    )


def fail(conn: Connection, job_id: int, erro: str, *, retryable: bool = True, delay_seconds: int | None = None) -> str:
    """Registra falha. Retorna o novo status ('queued' para retry ou 'dead')."""
    row = conn.execute(
        """
        update jobs
           set status = case when %(retry)s and tentativas < max_tentativas
                             then 'queued' else 'dead' end,
               run_after = now() + make_interval(secs => coalesce(%(delay)s,
                   least(%(base)s * power(2, greatest(tentativas - 1, 0)), %(max)s))),
               ultimo_erro = left(%(erro)s, 4000),
               locked_at = null,
               finalizado_em = case when %(retry)s and tentativas < max_tentativas
                                    then null else now() end
         where id = %(id)s
        returning status
        """,
        {
            "retry": retryable,
            "base": BACKOFF_BASE_SECONDS,
            "max": BACKOFF_MAX_SECONDS,
            "erro": erro,
            "id": job_id,
            "delay": delay_seconds,
        },
    ).fetchone()
    return row["status"] if row else "unknown"


def retry(conn: Connection, job_id: int) -> dict | None:
    """Reenfileira manualmente um job 'dead' ou 'failed' (ação humana)."""
    return conn.execute(
        """
        update jobs set status = 'queued', run_after = now(), finalizado_em = null,
                        max_tentativas = greatest(max_tentativas, tentativas + 1)
         where id = %s and status in ('dead','failed','cancelled')
        returning *
        """,
        (job_id,),
    ).fetchone()


def requeue_stale(conn: Connection, timeout_minutes: int) -> int:
    """Devolve à fila jobs presos em 'running' (worker morreu)."""
    cur = conn.execute(
        """
        update jobs set status = 'queued', locked_by = null, locked_at = null,
                        ultimo_erro = 'lock expirado: worker não respondeu'
         where status = 'running' and locked_at < now() - make_interval(mins => %s)
        """,
        (timeout_minutes,),
    )
    return cur.rowcount
