"""Agendador portável: a tabela `schedules` diz o que enfileirar e a cada quanto tempo.

Qualquer worker pode chamar `tick`; o SKIP LOCKED garante que cada agendamento
dispare uma vez só, mesmo com vários workers.

Janela opcional (V2.3): `dias_semana` (ISO, 1=segunda), `hora_inicio`/`hora_fim` e `fuso`
(padrão America/Sao_Paulo). Fora da janela nada é enfileirado e o próximo disparo vai para o
início da próxima janela. Ex.: a RPI sai às terças; às terças e quartas a verificação é a cada 10 min.
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from psycopg import Connection

from app.jobs import queue


def _na_janela(s: dict, local: datetime) -> bool:
    if s.get("dias_semana") and local.isoweekday() not in s["dias_semana"]:
        return False
    ini, fim = s.get("hora_inicio") or time(0, 0), s.get("hora_fim") or time(23, 59, 59)
    return ini <= local.time().replace(tzinfo=None) <= fim


def proxima_janela(s: dict, agora: datetime) -> datetime:
    """Primeiro instante >= agora dentro da janela do agendamento (no fuso dele)."""
    tz = ZoneInfo(s.get("fuso") or "America/Sao_Paulo")
    local = agora.astimezone(tz)
    if _na_janela(s, local):
        return agora
    ini = s.get("hora_inicio") or time(0, 0)
    for d in range(0, 8):
        dia = (local + timedelta(days=d)).date()
        candidato = datetime.combine(dia, ini, tzinfo=tz)
        if candidato >= local and _na_janela(s, candidato):
            return candidato
    return agora + timedelta(days=1)


def proximo_disparo(s: dict, agora: datetime) -> datetime:
    alvo = agora + timedelta(minutes=s["intervalo_minutos"])
    if not (s.get("dias_semana") or s.get("hora_inicio") or s.get("hora_fim")):
        return alvo
    return proxima_janela(s, alvo)


def tick(conn: Connection) -> list[int]:
    due = conn.execute(
        """select * from schedules where ativo and proximo_em <= now()
           order by proximo_em for update skip locked"""
    ).fetchall()
    agora = conn.execute("select now() as n").fetchone()["n"]
    criados = []
    for s in due:
        tem_janela = bool(s.get("dias_semana") or s.get("hora_inicio") or s.get("hora_fim"))
        if tem_janela and proxima_janela(s, agora) != agora:
            # fora da janela: não enfileira, só reagenda para o início da próxima janela
            conn.execute("update schedules set proximo_em = %s where nome = %s", (proxima_janela(s, agora), s["nome"]))
            continue
        job = queue.enqueue(conn, s["tipo"], s["payload"], dedupe_key=f"schedule:{s['nome']}", prioridade=40)
        conn.execute(
            "update schedules set ultimo_job_id = %s, proximo_em = %s where nome = %s",
            (job["id"], proximo_disparo(s, agora), s["nome"]),
        )
        criados.append(job["id"])
    return criados
