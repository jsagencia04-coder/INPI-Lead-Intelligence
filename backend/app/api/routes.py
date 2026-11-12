"""Endpoints gerais da API: saúde, dashboard, jobs, processos, leads e auditoria."""

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app import db, overview
from app.auth import User, current_user
from app.jobs import queue
from app.jobs.registry import registered_types

public = APIRouter()
router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])


@public.get("/health")
def health() -> dict:
    with db.get_pool().connection() as conn:
        conn.execute("select 1")
        versao = conn.execute("select max(versao) as v from schema_migrations").fetchone()["v"]
    return {"status": "ok", "schema": versao}


# ------------------------------------------------------------------ dashboard
@router.get("/dashboard/summary")
def dashboard_summary() -> dict:
    with db.get_pool().connection() as conn:
        return conn.execute("select * from v_dashboard_summary").fetchone()


@router.get("/dashboard/overview")
def dashboard_overview(dias: int = Query(14, ge=7, le=90)) -> dict:
    """Painel executivo: indicadores, séries diárias, distribuição, pendências e desempenho dos agentes."""
    with db.get_pool().connection() as conn:
        return overview.overview(conn, dias)


@router.get("/alerts")
def alerts() -> list[dict]:
    """Pendências priorizadas (sino de notificações e contadores do menu)."""
    with db.get_pool().connection() as conn:
        return overview.pendencias(conn)


@router.get("/dashboard/history")
def dashboard_history(limit: int = Query(20, le=100)) -> dict:
    with db.get_pool().connection() as conn:
        edicoes = conn.execute(
            """select numero, data_publicacao, status, detectada_em, processada_em
                 from rpi_editions order by numero desc limit %s""",
            (limit,),
        ).fetchall()
        jobs = conn.execute(
            """select id, tipo, status, tentativas, criado_em, iniciado_em, finalizado_em,
                      locked_by, left(ultimo_erro, 300) as ultimo_erro
                 from jobs order by id desc limit %s""",
            (limit,),
        ).fetchall()
    return {"edicoes": edicoes, "jobs": jobs}


# ------------------------------------------------------------------ jobs
class EnqueueIn(BaseModel):
    tipo: str
    payload: dict[str, Any] = Field(default_factory=dict)
    dedupe_key: str | None = None
    prioridade: int = 100


@router.get("/jobs")
def list_jobs(
    status: Literal["queued", "running", "succeeded", "failed", "dead", "cancelled"] | None = None,
    tipo: str | None = None,
    limit: int = Query(50, le=200),
) -> list[dict]:
    with db.get_pool().connection() as conn:
        return conn.execute(
            """select * from jobs
                where (%(s)s::text is null or status = %(s)s)
                  and (%(t)s::text is null or tipo = %(t)s)
                order by id desc limit %(l)s""",
            {"s": status, "t": tipo, "l": limit},
        ).fetchall()


@router.get("/jobs/types")
def job_types() -> list[str]:
    return registered_types()


@router.post("/jobs", status_code=201)
def create_job(body: EnqueueIn, user: User = Depends(current_user)) -> dict:
    if body.tipo not in registered_types():
        raise HTTPException(422, f"Tipo de job desconhecido: {body.tipo}")
    with db.transaction(user.actor) as conn:
        return queue.enqueue(conn, body.tipo, body.payload, dedupe_key=body.dedupe_key, prioridade=body.prioridade)


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: int, user: User = Depends(current_user)) -> dict:
    with db.transaction(user.actor) as conn:
        job = queue.retry(conn, job_id)
    if job is None:
        raise HTTPException(409, "Job não existe ou não está em estado reprocessável")
    return job


# ------------------------------------------------------------------ processos
@router.get("/processes")
def list_processes(
    procurador_status: str | None = None,
    oportunidade: Literal["elegivel", "descartada"] | None = None,
    categoria: str | None = None,
    edicao: int | None = None,
    q: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
) -> dict:
    """Lista processos. `oportunidade` filtra pela última oportunidade do processo."""
    ps = procurador_status.split(",") if procurador_status else None
    params = {"ps": ps, "op": oportunidade, "cat": categoria, "ed": edicao, "q": q, "l": limit, "o": offset}
    base = """
      from processes p
      left join lateral (
        select o.categoria, o.despacho_codigo, o.status, o.motivo_descarte, e.numero as rpi
          from opportunities o join rpi_editions e on e.id = o.edition_id
         where o.numero_processo = p.numero_processo
         order by e.numero desc, o.id desc limit 1) op on true
      left join lateral (
        select string_agg(h.nome_original, '; ' order by ph.ordem) as titulares
          from process_holders ph join holders h on h.id = ph.holder_id
         where ph.numero_processo = p.numero_processo) t on true
     where (%(ps)s::text[] is null or p.procurador_status = any(%(ps)s::text[]))
       and (%(op)s::text is null or op.status = %(op)s)
       and (%(cat)s::text is null or op.categoria = %(cat)s)
       and (%(ed)s::int is null or op.rpi = %(ed)s)
       and (%(q)s::text is null or p.numero_processo = %(q)s
            or p.marca_nome ilike '%%' || %(q)s || '%%' or t.titulares ilike '%%' || %(q)s || '%%')"""
    with db.get_pool().connection() as conn:
        total = conn.execute(f"select count(*) as n {base}", params).fetchone()
        rows = conn.execute(
            f"""select p.*, t.titulares, op.categoria, op.despacho_codigo, op.status as oportunidade_status,
                       op.motivo_descarte, op.rpi {base}
                 order by op.rpi desc nulls last, p.numero_processo limit %(l)s offset %(o)s""",
            params,
        ).fetchall()
    return {"total": total["n"], "items": rows}


@router.get("/processes/{numero}")
def get_process(numero: str) -> dict:
    with db.get_pool().connection() as conn:
        proc = conn.execute("select * from processes where numero_processo = %s", (numero,)).fetchone()
        if proc is None:
            raise HTTPException(404, "Processo não encontrado")
        proc["publicacoes"] = conn.execute(
            """select p.*, e.numero as rpi_numero, e.data_publicacao
                 from publications p join rpi_editions e on e.id = p.edition_id
                where p.numero_processo = %s order by e.numero desc""",
            (numero,),
        ).fetchall()
        proc["titulares"] = conn.execute(
            """select h.* from holders h join process_holders ph on ph.holder_id = h.id
                where ph.numero_processo = %s order by ph.ordem""",
            (numero,),
        ).fetchall()
        proc["oportunidades"] = conn.execute(
            """select o.*, e.numero as rpi from opportunities o join rpi_editions e on e.id = o.edition_id
                where o.numero_processo = %s order by e.numero desc""",
            (numero,),
        ).fetchall()
        proc["verificacoes_inpi"] = conn.execute(
            "select * from inpi_verifications where numero_processo = %s order by consultado_em desc",
            (numero,),
        ).fetchall()
    return proc


# ------------------------------------------------------------------ auditoria
@router.get("/audit")
def audit(tabela: str, registro_id: str, limit: int = Query(100, le=500)) -> list[dict]:
    with db.get_pool().connection() as conn:
        return conn.execute(
            """select * from audit_log where tabela = %s and registro_id = %s
                order by em desc limit %s""",
            (tabela, registro_id, limit),
        ).fetchall()
