"""Pipeline comercial (V2.0, Fase 6): funil de 17 etapas e a jornada de cada lead."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app import db
from app.auth import User, current_user

router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])

ETAPAS: list[tuple[str, str, bool]] = [  # (id, nome, automática?)
    ("lead_novo", "Lead novo", True),
    ("investigando", "Investigando", True),
    ("contato_identificado", "Contato identificado", True),
    ("contato_validado", "Contato validado", True),
    ("aguardando_autorizacao", "Aguardando autorização", True),
    ("elegivel_primeiro_contato", "Elegível para primeiro contato", True),
    ("mensagem_programada", "Mensagem programada", True),
    ("mensagem_enviada", "Mensagem enviada", True),
    ("mensagem_entregue", "Mensagem entregue", True),
    ("resposta_recebida", "Resposta recebida", True),
    ("interessado", "Interessado", False),
    ("reuniao", "Reunião", False),
    ("proposta_enviada", "Proposta enviada", False),
    ("negociacao", "Negociação", False),
    ("fechado", "Fechado", False),
    ("perdido", "Perdido", False),
    ("opt_out", "Opt-out", True),
]
NOMES = {e[0]: e[1] for e in ETAPAS}
MANUAIS = [e[0] for e in ETAPAS if not e[2]]


@router.get("/pipeline")
def funil() -> dict:
    with db.get_pool().connection() as conn:
        cont = {
            r["pipeline_stage"]: r["n"]
            for r in conn.execute(
                "select pipeline_stage, count(*) n from leads where mesclado_em is null group by 1"
            ).fetchall()
        }
    return {
        "total": sum(cont.values()),
        "etapas": [{"id": i, "nome": n, "automatica": a, "leads": cont.get(i, 0), "ordem": k + 1} for k, (i, n, a) in enumerate(ETAPAS)],
    }


@router.get("/pipeline/leads")
def leads_da_etapa(
    etapa: str,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    if etapa not in NOMES:
        raise HTTPException(422, "Etapa desconhecida")
    p = {"e": etapa, "q": (q or "").strip() or None, "l": limit, "o": offset}
    filtro = """ from leads l join holders h on h.id = l.holder_id
                where l.mesclado_em is null and l.pipeline_stage = %(e)s
                  and (%(q)s::text is null or h.nome_original ilike '%%' || %(q)s || '%%' or h.cnpj = %(q)s)"""
    with db.get_pool().connection() as conn:
        total = conn.execute(f"select count(*) n {filtro}", p).fetchone()["n"]
        rows = conn.execute(
            f"""select l.id, h.nome_original as titular, h.uf, h.cnpj, l.status, l.prioridade, l.score, l.whatsapp,
                       l.whatsapp_status, l.categoria_principal, l.pipeline_stage, l.pipeline_manual, l.pipeline_desde,
                       (select string_agg(distinct p.marca_nome, ', ') from lead_processes lp
                          join processes p on p.numero_processo = lp.numero_processo where lp.lead_id = l.id) as marcas
                {filtro}
                order by case l.prioridade when 'alta' then 1 when 'media' then 2 else 3 end, l.score desc nulls last, l.id
                limit %(l)s offset %(o)s""",
            p,
        ).fetchall()
    return {"total": total, "items": rows}


@router.get("/leads/{lead_id}/jornada")
def jornada(lead_id: int) -> dict:
    with db.get_pool().connection() as conn:
        lead = conn.execute(
            "select id, pipeline_stage, pipeline_manual, pipeline_desde, pipeline_auto(id) as etapa_pelos_fatos from leads where id = %s",
            (lead_id,),
        ).fetchone()
        if lead is None:
            raise HTTPException(404, "Lead não encontrado")
        hist = conn.execute("select * from lead_stage_history where lead_id = %s order by id", (lead_id,)).fetchall()
    return lead | {"historico": hist, "nomes": NOMES}


class MoverIn(BaseModel):
    etapa: Literal["interessado", "reuniao", "proposta_enviada", "negociacao", "fechado", "perdido", "automatico"]
    motivo: str = Field(min_length=3, max_length=500)


@router.post("/leads/{lead_id}/pipeline")
def mover(lead_id: int, body: MoverIn, user: User = Depends(current_user)) -> dict:
    """Decisão humana sobre a etapa comercial. 'automatico' devolve o lead à etapa indicada pelos fatos."""
    with db.transaction(user.actor) as conn:
        lead = conn.execute("select * from leads where id = %s and mesclado_em is null for update", (lead_id,)).fetchone()
        if lead is None:
            raise HTTPException(404, "Lead não encontrado")
        if lead["pipeline_stage"] == "opt_out":
            raise HTTPException(409, "Lead em opt-out: não pode voltar ao funil")
        if body.etapa == "automatico":
            conn.execute("update leads set pipeline_manual = false where id = %s", (lead_id,))
            conn.execute("select pipeline_sync(%s, %s)", (lead_id, f"voltou ao automático: {body.motivo}"))
        elif body.etapa != lead["pipeline_stage"]:
            conn.execute(
                "update leads set pipeline_stage = %s, pipeline_manual = true, pipeline_desde = now() where id = %s",
                (body.etapa, lead_id),
            )
            conn.execute(
                "insert into lead_stage_history (lead_id, de, para, origem, motivo, ator) values (%s, %s, %s, 'manual', %s, %s)",
                (lead_id, lead["pipeline_stage"], body.etapa, body.motivo, user.actor),
            )
        return conn.execute(
            "select id, pipeline_stage, pipeline_manual, pipeline_desde from leads where id = %s", (lead_id,)
        ).fetchone()
