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


# Etapas de negociação só com evidência de que houve conversa (resposta recebida ou contato registrado por pessoa).
EXIGEM_EVIDENCIA = {"interessado", "reuniao", "proposta_enviada", "negociacao"}


def _tem_evidencia(conn, lead_id: int) -> bool:
    return conn.execute(
        """select exists (select 1 from wa_messages m where m.lead_id = %(l)s and m.direcao = 'entrada')
               or exists (select 1 from outreach_log o where o.lead_id = %(l)s) as ok""",
        {"l": lead_id},
    ).fetchone()["ok"]


@router.get("/pipeline")
def funil(adicionados: bool = False) -> dict:
    with db.get_pool().connection() as conn:
        cont = {
            r["pipeline_stage"]: r["n"]
            for r in conn.execute(
                """select pipeline_stage, count(*) n from leads
                    where mesclado_em is null and (not %s or pipeline_incluido_em is not null) group by 1""",
                (adicionados,),
            ).fetchall()
        }
        info = {r["id"]: r for r in conn.execute("select * from pipeline_etapas").fetchall()}
        n_adicionados = conn.execute(
            "select count(*) n from leads where mesclado_em is null and pipeline_incluido_em is not null"
        ).fetchone()["n"]
    return {
        "total": sum(cont.values()),
        "adicionados": n_adicionados,
        "etapas": [
            {"id": i, "nome": n, "automatica": a, "leads": cont.get(i, 0), "ordem": k + 1}
            | {c: (info.get(i) or {}).get(c) for c in ("fase", "cor", "descricao", "regra")}
            for k, (i, n, a) in enumerate(ETAPAS)
        ],
    }


@router.get("/pipeline/leads")
def leads_da_etapa(
    etapa: str,
    q: str | None = None,
    lead_id: int | None = None,
    adicionados: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    if etapa not in NOMES:
        raise HTTPException(422, "Etapa desconhecida")
    p = {"e": etapa, "q": (q or "").strip() or None, "l": limit, "o": offset, "lid": lead_id, "ad": adicionados}
    filtro = """ from leads l join holders h on h.id = l.holder_id
                where l.mesclado_em is null and l.pipeline_stage = %(e)s
                  and (%(lid)s::bigint is null or l.id = %(lid)s)
                  and (not %(ad)s or l.pipeline_incluido_em is not null)
                  and (%(q)s::text is null or h.nome_original ilike '%%' || %(q)s || '%%' or h.cnpj = %(q)s)"""
    with db.get_pool().connection() as conn:
        total = conn.execute(f"select count(*) n {filtro}", p).fetchone()["n"]
        rows = conn.execute(
            f"""select l.id, h.nome_original as titular, h.uf, h.cnpj, l.status, l.prioridade, l.score, l.whatsapp,
                       l.whatsapp_status, l.categoria_principal, l.pipeline_stage, l.pipeline_manual, l.pipeline_desde,
                       l.pipeline_incluido_em, h.geo_uf,
                       (select string_agg(pp.numero_processo, ', ' order by pp.id) from pipeline_processos pp
                         where pp.lead_id = l.id) as processos_no_pipeline,
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
        if body.etapa in EXIGEM_EVIDENCIA and not _tem_evidencia(conn, lead_id):
            raise HTTPException(
                409,
                "Sem evidência de conversa (resposta recebida ou contato registrado): o lead ainda não pode ser marcado como interessado ou em negociação",
            )
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


# ------------------------------------------------------------------ V2.6 · mapa → pipeline (por processo do INPI)
def _ficha(conn, numero: str) -> dict | None:
    """Dados do processo para a janela 'Adicionar ao Pipeline'. O lead é o 1º titular do processo (lead por titular);
    o vínculo processo → lead fica em pipeline_processos, então o mesmo titular pode ter várias oportunidades."""
    return conn.execute(
        """select p.numero_processo, p.marca_nome, p.procurador_status, procurador_situacao(p.procurador_status) as procurador_situacao,
                  p.procurador_nome, h.id as holder_id, h.nome_original as titular, h.geo_uf, h.geo_municipio, h.cnpj,
                  coalesce(l.mesclado_em, l.id) as lead_id,
                  os.id as oportunidade_servico_id, os.servico, os.tipo_decisao, os.despacho_codigo, os.rpi_numero,
                  os.data_publicacao, os.prazo_fim, os.prazo_status, os.elegivel, os.motivo_descarte,
                  dt.nome as despacho_nome, prioridade_servico(os.servico) as prioridade
             from processes p
             join process_holders ph on ph.numero_processo = p.numero_processo
              and ph.ordem = (select min(ordem) from process_holders x where x.numero_processo = p.numero_processo)
             join holders h on h.id = ph.holder_id
             left join leads l on l.holder_id = h.id
             left join lateral (select * from oportunidades_servico s where s.numero_processo = p.numero_processo
                                 order by (s.rpi_numero >= rpi_edicao_minima()) desc, s.elegivel desc,
                                          prioridade_servico(s.servico), s.rpi_numero desc limit 1) os on true
             left join despacho_types dt on dt.codigo = os.despacho_codigo
            where p.numero_processo = %s""",
        (numero,),
    ).fetchone()


def _detalhes_lead(conn, lead_id: int) -> dict:
    return conn.execute(
        """select l.id, l.pipeline_stage, l.pipeline_manual, l.pipeline_incluido_em, l.status, l.whatsapp, l.whatsapp_status,
                  pipeline_auto(l.id) as etapa_pelos_fatos,
                  (select count(*) from contacts c where c.holder_id = l.holder_id and c.verificacao <> 'invalido') as contatos,
                  (select count(*) from contacts c where c.holder_id = l.holder_id
                     and c.verificacao in ('dominio_ok','verificado_humano')) as contatos_validados,
                  (select k.status from consents k join contacts c on c.id = k.contact_id
                    where c.holder_id = l.holder_id and k.canal = 'whatsapp' order by k.id desc limit 1) as consentimento,
                  exists (select 1 from suppression_list s join contacts c
                            on s.valor_hash = encode(sha256(convert_to(c.valor_normalizado, 'UTF8')), 'hex')
                           where c.holder_id = l.holder_id) as opt_out
             from leads l where l.id = %s""",
        (lead_id,),
    ).fetchone()


@router.get("/pipeline/processo/{numero}")
def ficha_processo(numero: str) -> dict:
    with db.get_pool().connection() as conn:
        f = _ficha(conn, numero)
        if f is None:
            raise HTTPException(404, "Processo não encontrado na base (ou sem titular)")
        vinculo = conn.execute("select * from pipeline_processos where numero_processo = %s", (numero,)).fetchone()
        lead = _detalhes_lead(conn, f["lead_id"]) if f["lead_id"] else None
        evidencia = _tem_evidencia(conn, f["lead_id"]) if f["lead_id"] else False
        outros = (
            conn.execute(
                """select lp.numero_processo, pr.marca_nome,
                      exists (select 1 from pipeline_processos pp where pp.numero_processo = lp.numero_processo) as no_pipeline
                 from lead_processes lp join processes pr using (numero_processo)
                where lp.lead_id = %s and lp.numero_processo <> %s order by lp.numero_processo limit 20""",
                (f["lead_id"], numero),
            ).fetchall()
            if f["lead_id"]
            else []
        )
    etapas = [{"id": "automatico", "nome": f"Etapa pelos fatos: {NOMES.get((lead or {}).get('etapa_pelos_fatos'), '—')}"}]
    etapas += [
        {"id": e, "nome": NOMES[e], "bloqueada": e in EXIGEM_EVIDENCIA and not evidencia}
        for e in MANUAIS
        if e not in ("fechado", "perdido")
    ]
    return {
        "processo": f,
        "lead": lead,
        "ja_no_pipeline": vinculo is not None,
        "vinculo": vinculo,
        "outros_processos_do_titular": outros,
        "etapas_iniciais": etapas,
        "aviso": None
        if f["procurador_situacao"] == "SEM_PROCURADOR_CONFIRMADO"
        else "Processo fora da lista de prospecção (representação: " + f["procurador_situacao"] + ")",
    }


class AdicionarIn(BaseModel):
    etapa: Literal["automatico", "interessado", "reuniao", "proposta_enviada", "negociacao"] = "automatico"
    motivo: str | None = Field(None, max_length=500)


@router.post("/pipeline/processo/{numero}")
def adicionar_processo(numero: str, body: AdicionarIn, user: User = Depends(current_user)) -> dict:
    """Inclui o processo no pipeline (idempotente). Se já estiver, não cria nada: devolve o lead existente.
    Notas, histórico, responsáveis e etapa atual são preservados; a etapa só muda por escolha explícita."""
    with db.transaction(user.actor) as conn:
        f = _ficha(conn, numero)
        if f is None:
            raise HTTPException(404, "Processo não encontrado na base (ou sem titular)")
        if not f["lead_id"]:
            raise HTTPException(409, "O titular deste processo ainda não virou lead (aguarde a montagem dos leads)")
        lead = conn.execute("select * from leads where id = %s for update", (f["lead_id"],)).fetchone()
        existente = conn.execute("select * from pipeline_processos where numero_processo = %s", (numero,)).fetchone()
        if existente:
            return {"ja_existia": True, "lead_id": existente["lead_id"], "etapa": lead["pipeline_stage"],
                    "mensagem": "Este processo já está cadastrado no Pipeline."}  # fmt: skip
        if lead["pipeline_stage"] == "opt_out":
            raise HTTPException(409, "Lead em opt-out: não pode entrar no funil")
        if body.etapa in EXIGEM_EVIDENCIA and not _tem_evidencia(conn, lead["id"]):
            raise HTTPException(409, "Sem evidência de conversa (resposta ou contato registrado): escolha a etapa pelos fatos")
        conn.execute(
            """insert into pipeline_processos (lead_id, numero_processo, oportunidade_servico_id, servico, rpi_numero,
                                               etapa_inicial, adicionado_por)
               values (%s, %s, %s, %s, %s, %s, %s)""",
            (lead["id"], numero, f["oportunidade_servico_id"], f["servico"], f["rpi_numero"],
             lead["pipeline_stage"] if body.etapa == "automatico" else body.etapa, user.actor),
        )  # fmt: skip
        novo_no_funil = lead["pipeline_incluido_em"] is None
        if novo_no_funil:
            conn.execute("update leads set pipeline_incluido_em = now(), pipeline_incluido_por = %s where id = %s",
                         (user.actor, lead["id"]))  # fmt: skip
        if body.etapa == "automatico":
            if novo_no_funil and not lead["pipeline_manual"]:
                conn.execute("select pipeline_sync(%s, %s)", (lead["id"], f"adicionado ao pipeline pelo processo {numero}"))
        elif body.etapa != lead["pipeline_stage"]:
            conn.execute("update leads set pipeline_stage = %s, pipeline_manual = true, pipeline_desde = now() where id = %s",
                         (body.etapa, lead["id"]))  # fmt: skip
            conn.execute(
                "insert into lead_stage_history (lead_id, de, para, origem, motivo, ator) values (%s, %s, %s, 'manual', %s, %s)",
                (lead["id"], lead["pipeline_stage"], body.etapa,
                 body.motivo or f"etapa escolhida ao adicionar o processo {numero}", user.actor),
            )  # fmt: skip
        atual = conn.execute("select pipeline_stage from leads where id = %s", (lead["id"],)).fetchone()["pipeline_stage"]
    return {"ja_existia": False, "lead_id": lead["id"], "etapa": atual, "mensagem": "Lead adicionado ao Pipeline com sucesso."}
