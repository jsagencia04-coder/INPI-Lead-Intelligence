"""Agendador portável: a tabela `schedules` diz o que enfileirar e a cada quanto tempo.

Qualquer worker pode chamar `tick`; o SKIP LOCKED garante que cada agendamento
dispare uma vez só, mesmo com vários workers.
"""

from psycopg import Connection

from app.jobs import queue


def tick(conn: Connection) -> list[int]:
    due = conn.execute(
        """select * from schedules where ativo and proximo_em <= now()
           order by proximo_em for update skip locked"""
    ).fetchall()
    criados = []
    for s in due:
        job = queue.enqueue(conn, s["tipo"], s["payload"], dedupe_key=f"schedule:{s['nome']}", prioridade=40)
        conn.execute(
            """update schedules set ultimo_job_id = %s,
                      proximo_em = now() + make_interval(mins => intervalo_minutos)
                where nome = %s""",
            (job["id"], s["nome"]),
        )
        criados.append(job["id"])
    return criados
