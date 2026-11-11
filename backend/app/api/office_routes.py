"""INPI AI Office: estado real dos agentes, eventos e WebSocket.

O estado de cada agente é DERIVADO da fila real (tabela jobs), nunca simulado:
  * running                      -> working (ou thinking, para agentes que usam IA)
  * falha definitiva < 15 min    -> error
  * jobs prontos na fila         -> waiting
  * concluiu algo < 2 min        -> completed
  * caso contrário               -> idle
Os eventos vêm da tabela agent_events, preenchida por triggers no banco
(migration 20261111000005). O WebSocket avisa a tela a cada evento novo.
"""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from psycopg.rows import dict_row

from app import db
from app.auth import current_user, usuario_do_token
from app.config import get_settings

log = logging.getLogger("office")
router = APIRouter(prefix="/api/office", dependencies=[Depends(current_user)])
ws_router = APIRouter()

IA = {"research.holder", "sales.summarize_batch"}


def describe_job(tipo: str, payload: dict | None) -> str:
    p = payload or {}
    if tipo == "rpi.discover":
        return "Verificando o índice da RPI"
    if tipo in ("rpi.collect", "rpi.parse") and "numero" in p:
        return f"{'Baixando' if tipo == 'rpi.collect' else 'Interpretando'} a RPI {p['numero']}"
    if tipo == "inpi.verify" and "numero" in p:
        return f"Consultando o processo {p['numero']} no INPI"
    if tipo == "inpi.verify_pending":
        return "Selecionando processos para consultar no INPI"
    if tipo == "cnpj.sync":
        return "Cruzando titulares com a base CNPJ da Receita"
    if tipo in ("research.free", "research.holder") and "holder_id" in p:
        return f"Pesquisando contatos do titular #{p['holder_id']}" + (" com IA" if tipo == "research.holder" else "")
    if tipo in ("research.free_batch", "research.batch"):
        return "Escolhendo titulares para pesquisar"
    if tipo == "lead.validate_contacts" and "holder_id" in p:
        return f"Validando contatos do titular #{p['holder_id']}"
    if tipo == "leads.build":
        return "Montando e pontuando os leads"
    if tipo == "sales.summarize_batch":
        return "Escrevendo resumos e abordagens"
    if tipo == "reports.weekly":
        return "Consolidando o relatório semanal"
    return tipo


def office_state(conn) -> dict:
    agora = datetime.now(UTC)
    contagem = {
        r["tipo"]: r
        for r in conn.execute(
            """select tipo,
                  count(*) filter (where status = 'queued' and run_after <= now()) as pendentes,
                  count(*) filter (where status = 'queued' and run_after > now()) as agendados,
                  count(*) filter (where status = 'running') as executando,
                  count(*) filter (where status = 'succeeded' and finalizado_em >= date_trunc('day', now())) as concluidos_hoje,
                  count(*) filter (where status = 'dead' and finalizado_em >= date_trunc('day', now())) as falhas_hoje
             from jobs where status in ('queued', 'running')
                or finalizado_em >= date_trunc('day', now()) group by tipo"""
        ).fetchall()
    }
    rodando = {
        r["tipo"]: r
        for r in conn.execute(
            "select distinct on (tipo) tipo, id, payload, iniciado_em from jobs where status = 'running' order by tipo, id"
        )
    }
    ultimo = {
        r["tipo"]: r
        for r in conn.execute(
            """select distinct on (tipo) tipo, id, status, payload, finalizado_em, resultado,
                  split_part(coalesce(ultimo_erro, ''), E'\\n', 1) as erro
             from jobs where status in ('succeeded', 'dead') order by tipo, finalizado_em desc nulls last"""
        )
    }

    tipos = {}
    for t in sorted(set(contagem) | set(ultimo) | set(rodando)):
        c = contagem.get(t, {})
        u, r = ultimo.get(t), rodando.get(t)
        idade = (agora - u["finalizado_em"]).total_seconds() if u and u["finalizado_em"] else None
        if r:
            state, tarefa, desde = ("thinking" if t in IA else "working"), describe_job(t, r["payload"]), r["iniciado_em"]
        elif u and u["status"] == "dead" and idade is not None and idade < 900:
            state, tarefa, desde = "error", u["erro"] or "Falha definitiva", u["finalizado_em"]
        elif c.get("pendentes"):
            state, tarefa, desde = "waiting", f"{c['pendentes']} tarefa(s) na fila", None
        elif u and u["status"] == "succeeded" and idade is not None and idade < 120:
            state, tarefa, desde = "completed", describe_job(t, u["payload"]), u["finalizado_em"]
        else:
            state, tarefa, desde = "idle", None, u["finalizado_em"] if u else None
        tipos[t] = {
            "state": state,
            "tarefa": tarefa,
            "desde": desde,
            "pendentes": c.get("pendentes", 0),
            "agendados": c.get("agendados", 0),
            "executando": c.get("executando", 0),
            "concluidos_hoje": c.get("concluidos_hoje", 0),
            "falhas_hoje": c.get("falhas_hoje", 0),
            "ultimo": {
                "job_id": u["id"],
                "status": u["status"],
                "em": u["finalizado_em"],
                "resultado": u["resultado"],
                "erro": u["erro"] or None,
                "tarefa": describe_job(t, u["payload"]),
            }
            if u
            else None,
        }

    # Coordenação (agendador): saudável se nenhum agendamento ativo está atrasado
    atrasados = conn.execute(
        "select nome from schedules where ativo and proximo_em < now() - interval '10 minutes' order by nome"
    ).fetchall()
    disparo = conn.execute("select max(updated_at) as m from schedules").fetchone()["m"]
    worker_ok = not atrasados
    tipos["scheduler"] = {
        "state": "error" if not worker_ok else ("completed" if disparo and (agora - disparo).total_seconds() < 120 else "idle"),
        "tarefa": ("Worker parado: agendamentos atrasados (" + ", ".join(r["nome"] for r in atrasados) + ")")
        if not worker_ok
        else None,
        "desde": disparo,
        "pendentes": 0,
        "agendados": 0,
        "executando": 0,
        "concluidos_hoje": 0,
        "falhas_hoje": 0,
        "ultimo": None,
    }

    k = conn.execute(
        """select (select count(*) from jobs where status = 'queued') as pendentes,
                  (select count(*) from jobs where status = 'running') as executando,
                  (select count(*) from jobs where status = 'succeeded' and finalizado_em >= date_trunc('day', now()))
                    as concluidas_hoje,
                  (select count(*) from jobs where status = 'dead' and finalizado_em >= date_trunc('day', now()))
                    as falhas_hoje,
                  (select count(*) from leads where status <> 'descartado' and mesclado_em is null) as leads,
                  (select count(*) from leads where status <> 'descartado' and mesclado_em is null
                      and whatsapp_status in ('confirmado', 'validado')) as leads_whatsapp,
                  (select coalesce(sum(tokens_in + tokens_out), 0) from llm_calls
                    where criado_em >= date_trunc('week', now())) as tokens_semana,
                  (select coalesce(sum(custo_usd), 0) from llm_calls
                    where criado_em >= date_trunc('week', now())) as custo_semana_usd,
                  (select coalesce(max(id), 0) from agent_events) as ultimo_evento_id"""
    ).fetchone()
    return {
        "gerado_em": agora,
        "tipos": tipos,
        "kpis": k,
        "sistema": {
            "worker_ok": worker_ok,
            "agendamentos_atrasados": [r["nome"] for r in atrasados],
            "ia_configurada": bool(get_settings().anthropic_api_key),
        },
    }


def list_events(conn, after: int = 0, limit: int = 100) -> list[dict]:
    rows = conn.execute(
        """select * from (select * from agent_events where id > %s order by id desc limit %s) e order by id""", (after, limit)
    ).fetchall()
    return rows


@router.get("/state")
def state() -> dict:
    with db.get_pool().connection() as conn:
        return office_state(conn)


@router.get("/events")
def events(after: int = 0, limit: int = Query(100, le=500)) -> list[dict]:
    with db.get_pool().connection() as conn:
        return list_events(conn, after, limit)


@router.get("/history")
def history(tipos: str, limit: int = Query(10, le=50)) -> list[dict]:
    """Últimas execuções reais dos tipos de job de um personagem."""
    lista = [t for t in tipos.split(",") if t]
    with db.get_pool().connection() as conn:
        rows = conn.execute(
            """select id, tipo, status, payload, tentativas, criado_em, iniciado_em, finalizado_em, resultado,
                      split_part(coalesce(ultimo_erro, ''), E'\\n', 1) as erro
                 from jobs where tipo = any(%s) order by id desc limit %s""",
            (lista, limit),
        ).fetchall()
    for r in rows:
        r["tarefa"] = describe_job(r["tipo"], r["payload"])
    return rows


# ------------------------------------------------------------------ WebSocket
def _ws_autorizado(token: str | None) -> bool:
    s = get_settings()
    try:
        usuario_do_token(token, s)  # mesmo critério das rotas: token válido E usuário ativo em app_users
        return True
    except HTTPException:
        return False


@ws_router.websocket("/ws/office")
async def office_ws(ws: WebSocket):
    """Envia {estado, eventos} na conexão e a cada evento novo (via LISTEN/NOTIFY do Postgres)."""
    if not _ws_autorizado(ws.query_params.get("token")):
        await ws.close(code=4401)
        return
    await ws.accept()
    s = get_settings()
    ultimo = int(ws.query_params.get("after") or 0)

    async def snapshot(conn) -> dict:
        def run():
            with db.get_pool().connection() as c:
                st = office_state(c)
                ev = list_events(c, ultimo, 200)
            return st, ev

        st, ev = await asyncio.to_thread(run)
        return {"estado": st, "eventos": ev}

    try:
        async with await psycopg.AsyncConnection.connect(s.database_url, autocommit=True, row_factory=dict_row) as conn:
            await conn.execute("listen agent_events")
            msg = await snapshot(conn)
            if msg["eventos"]:
                ultimo = msg["eventos"][-1]["id"]
            await ws.send_json(jsonable_encoder({"tipo": "snapshot", **msg}))

            fechou = asyncio.Event()

            async def ouvir_cliente():
                with contextlib.suppress(WebSocketDisconnect, RuntimeError):
                    while True:
                        await ws.receive_text()  # ping do cliente
                fechou.set()

            leitor = asyncio.create_task(ouvir_cliente())
            try:
                while not fechou.is_set():
                    houve = False
                    gen = conn.notifies(timeout=5.0)
                    async for _ in gen:
                        houve = True
                        break  # agrupa rajadas: busca tudo de uma vez abaixo
                    if houve:
                        await asyncio.sleep(0.3)
                    msg = await snapshot(conn)
                    if msg["eventos"]:
                        ultimo = msg["eventos"][-1]["id"]
                    if houve or msg["eventos"]:
                        await ws.send_json(jsonable_encoder({"tipo": "update", **msg}))
                    else:
                        await ws.send_json(jsonable_encoder({"tipo": "estado", "estado": msg["estado"]}))
            finally:
                leitor.cancel()
    except (WebSocketDisconnect, RuntimeError):
        return
    except Exception:  # noqa: BLE001
        log.exception("erro no WebSocket do escritório")
        with contextlib.suppress(Exception):
            await ws.close(code=1011)
