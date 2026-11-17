"""V2.13 · JULIO (TI): monitora o sistema 24 h, de uma Revista à outra, e corrige o que é seguro corrigir sozinho.

    sistema.saude  a cada 5 min: banco, worker e agendador, fila, tarefas travadas, falhas, WhatsApp, RPI da semana,
                   última importação e disco. Grava em system_health; quando o estado muda (ok → atenção/falha e
                   de volta), registra um evento para o painel e, em falha, uma tarefa de revisão.

Correções automáticas (só as seguras): devolver à fila tarefas travadas por worker que caiu. Nada é apagado e
nenhuma mensagem é enviada.
"""

import os
import shutil
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from app import evolution
from app.config import get_settings
from app.jobs import queue
from app.jobs.registry import JobContext, handler

SP = ZoneInfo("America/Sao_Paulo")
NIVEL = {"ok": 0, "atencao": 1, "falha": 2}


def _c(nome: str, status: str, detalhe: str, **extra) -> dict:
    return {"nome": nome, "status": status, "detalhe": detalhe, **extra}


def verificar(conn, agora: datetime | None = None, whatsapp: bool = True) -> tuple[list[dict], list[dict]]:
    agora = agora or datetime.now(UTC)
    s = get_settings()
    checks, acoes = [], []

    conn.execute("select 1")
    checks.append(_c("banco", "ok", "Banco de dados respondendo"))

    atrasados = [r["nome"] for r in conn.execute(
        "select nome from schedules where ativo and proximo_em < now() - interval '15 minutes' order by nome").fetchall()]  # fmt: skip
    checks.append(_c("agendador", "falha" if atrasados else "ok",
                     f"Rotinas atrasadas: {', '.join(atrasados)}" if atrasados else "Rotinas automáticas em dia"))  # fmt: skip

    devolvidas = queue.requeue_stale(conn, max(30, s.job_lock_timeout_minutes))
    if devolvidas:
        acoes.append({"acao": "tarefas_travadas_devolvidas", "quantidade": devolvidas})
    checks.append(_c("tarefas_travadas", "atencao" if devolvidas else "ok",
                     f"{devolvidas} tarefa(s) travada(s) devolvida(s) à fila" if devolvidas else "Nenhuma tarefa travada"))  # fmt: skip

    f = conn.execute(
        """select count(*) n, string_agg(distinct tipo, ', ') tipos from jobs
            where status = 'dead' and finalizado_em > now() - interval '24 hours'"""
    ).fetchone()
    criticas = conn.execute(
        """select count(*) n from jobs where status = 'dead' and finalizado_em > now() - interval '24 hours'
              and tipo in ('rpi.discover', 'rpi.collect', 'rpi.parse', 'rpi.pdf', 'rpi.pdf_importar', 'rpi.semana')"""
    ).fetchone()["n"]
    checks.append(_c("falhas_24h", "falha" if criticas else ("atencao" if f["n"] else "ok"),
                     f"{f['n']} tarefa(s) com falha definitiva nas últimas 24 h ({f['tipos']})" if f["n"] else "Sem falhas definitivas em 24 h",
                     quantidade=f["n"]))  # fmt: skip

    q = conn.execute(
        """select count(*) n, extract(epoch from now() - min(run_after)) / 60 as espera_min
             from jobs where status = 'queued' and run_after <= now()"""
    ).fetchone()
    espera = round(q["espera_min"] or 0)
    checks.append(_c("fila", "atencao" if espera > 180 else "ok",
                     f"{q['n']} tarefa(s) na fila; a mais antiga espera há {espera} min", pendentes=q["n"]))  # fmt: skip

    imp = {r["chave"]: r["valor"] for r in conn.execute(
        "select chave, valor from app_config where chave in ('last_import_status', 'last_publication_id', 'system_status')")}  # fmt: skip
    if imp.get("last_import_status") == "failed":
        checks.append(
            _c("importacao", "falha", f"A última importação da RPI falhou (edição {imp.get('last_publication_id') or '—'})")
        )
    else:
        checks.append(_c("importacao", "ok", "Última importação concluída" if imp.get("last_import_status") == "success"
                         else "Aguardando a próxima Revista"))  # fmt: skip

    local = agora.astimezone(SP)
    terca = local.date() - timedelta(days=(local.isoweekday() - 2) % 7)
    # só cobra a Revista na terça (após 14 h) e na quarta; no resto da semana a da terça anterior já foi tratada
    if local.date() - terca <= timedelta(days=1) and local >= datetime.combine(terca, time(14, 0), tzinfo=SP):
        tem = conn.execute(
            "select 1 from rpi_editions where detectada_em >= %s and numero >= rpi_edicao_minima() limit 1",
            (datetime.combine(terca, time(0, 0), tzinfo=SP),),
        ).fetchone()
        checks.append(_c("rpi_semana", "ok" if tem else "atencao",
                         "Revista desta semana recebida" if tem else "Revista desta semana ainda não detectada (após 14 h de terça)"))  # fmt: skip
    else:
        checks.append(_c("rpi_semana", "ok", "Dentro do horário esperado da Revista"))

    if whatsapp and s.mensageria_provedor == "evolution" and evolution.configurada(s):
        w = evolution.verificar_conexao(conn)
        ok = w.get("status") in ("conectado", "open")
        checks.append(_c("whatsapp", "ok" if ok else "falha",
                         "WhatsApp conectado" if ok else f"WhatsApp: {w.get('status')} {w.get('detalhe') or ''}".strip()))  # fmt: skip

    try:
        d = shutil.disk_usage(s.storage_local_dir if os.path.isdir(s.storage_local_dir) else ".")
        livre = d.free / d.total * 100
        checks.append(_c("disco", "falha" if livre < 5 else ("atencao" if livre < 12 else "ok"),
                         f"{livre:.0f}% livre ({d.free / 2**30:.1f} GB)", livre_pct=round(livre, 1)))  # fmt: skip
    except OSError:
        pass
    return checks, acoes


def status_geral(checks: list[dict]) -> str:
    return max((c["status"] for c in checks), key=NIVEL.__getitem__, default="ok")


@handler("sistema.saude")
def saude(conn, ctx: JobContext) -> dict:
    checks, acoes = verificar(conn)
    st = status_geral(checks)
    anterior = conn.execute("select status from system_health order by id desc limit 1").fetchone()
    conn.execute("insert into system_health (status, checks, acoes) values (%s, %s, %s)", (st, Jsonb(checks), Jsonb(acoes)))
    conn.execute("delete from system_health where criado_em < now() - interval '14 days'")
    problemas = [c["detalhe"] for c in checks if c["status"] != "ok"]
    if anterior is None or anterior["status"] != st:
        desc = "Sistema operando normalmente" if st == "ok" else "; ".join(problemas)
        conn.execute(
            "insert into agent_events (tipo, agente, job_id, referencia, descricao, resultado) values (%s, 'sistema.saude', %s, 'ti', %s, %s)",
            (f"ti.{st}", ctx.job["id"], f"TI: {desc}"[:500], Jsonb({"status": st, "anterior": anterior and anterior["status"]})),
        )
        if st == "falha":
            conn.execute(
                "insert into review_tasks (entidade, entidade_id, motivo) values ('sistema', 'saude', %s)",
                (f"TI (Julio) detectou falha: {'; '.join(problemas)}"[:900],),
            )
    return {"status": st, "problemas": problemas, "acoes": acoes}
