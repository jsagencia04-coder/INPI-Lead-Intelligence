"""Leads, contatos, prospecção, LGPD, exportação, relatórios e métricas (Fases 5 a 7)."""

import csv
import hashlib
import io
import json
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app import db
from app.agents.leads import holder_hash, weekly_report_data
from app.agents.research import TIPOS
from app.auth import User, current_user
from app.jobs import queue
from app.validation import normalize_contact

router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])

LEAD_FILTER = """
  from leads l join holders h on h.id = l.holder_id
 where l.mesclado_em is null
   and (%(st)s::text is null or l.status = %(st)s)
   and (%(pr)s::text is null or l.prioridade = %(pr)s)
   and (%(cat)s::text is null or l.categoria_principal = %(cat)s)
   and (%(uf)s::text is null or h.uf = %(uf)s)
   and (%(guf)s::text is null or coalesce(h.geo_uf, 'PENDENTE') = %(guf)s)
   and (%(temp)s::text is null or l.temperatura = %(temp)s)
   and (%(serv)s::text is null
        or (%(serv)s = 'manifestacao_oposicao' and l.classificacao_oposicao is not null)
        or (%(serv)s = 'recurso_indeferimento' and l.classificacao_recurso is not null)
        or (%(serv)s = 'outros' and l.classificacao_oposicao is null and l.classificacao_recurso is null))
   and (%(cls)s::text is null
        or (%(serv)s = 'manifestacao_oposicao' and l.classificacao_oposicao = %(cls)s)
        or (%(serv)s = 'recurso_indeferimento' and l.classificacao_recurso = %(cls)s)
        or (%(serv)s is distinct from 'manifestacao_oposicao' and %(serv)s is distinct from 'recurso_indeferimento'
            and %(cls)s in (l.classificacao_oposicao, l.classificacao_recurso)))
   and (%(ed)s::int is null or exists (select 1 from lead_processes lp2 join opportunities o2 on o2.numero_processo = lp2.numero_processo
                                        join rpi_editions e2 on e2.id = o2.edition_id
                                       where lp2.lead_id = l.id and e2.numero = %(ed)s and o2.status = 'elegivel'))
   and (%(rev)s::boolean is null or l.precisa_revisao = %(rev)s)
   and (%(op)s::boolean is not true or exists (
        select 1 from lead_processes lpo join opportunities oo on oo.numero_processo = lpo.numero_processo
         where lpo.lead_id = l.id and oo.status = 'elegivel'))
   and (%(wa)s::text is null
        or (%(wa)s = 'validado' and l.whatsapp_status in ('confirmado', 'validado'))
        or (%(wa)s = 'candidato' and l.whatsapp_status = 'candidato')
        or (%(wa)s = 'nenhum' and l.whatsapp_status is null))
   and (%(q)s::text is null or h.nome_original ilike '%%' || %(q)s || '%%' or h.cnpj = %(q)s
        or exists (select 1 from lead_processes lp join processes p on p.numero_processo = lp.numero_processo
                    where lp.lead_id = l.id and (p.numero_processo = %(q)s or p.marca_nome ilike '%%' || %(q)s || '%%')))
"""


def _filters(status, prioridade, categoria, uf, revisao, q, whatsapp=None, geo_uf=None, temperatura=None, edicao=None,
             servico=None, classificacao=None, operacional=None) -> dict:  # fmt: skip
    return {"st": status, "pr": prioridade, "cat": categoria, "uf": uf, "rev": revisao, "q": q, "wa": whatsapp,
            "guf": geo_uf, "temp": temperatura, "ed": edicao, "serv": servico, "cls": classificacao, "op": operacional}  # fmt: skip


# V2.6 · ordem comercial: oposição antes de indeferimento, depois SC, RS, PR e demais (sem UF por último), publicação
ORDEM_COMERCIAL = """(select min(prioridade_categoria(oo.categoria)) from lead_processes lpo
                        join opportunities oo on oo.numero_processo = lpo.numero_processo
                       where lpo.lead_id = l.id and oo.status = 'elegivel') nulls last,
                     (select u.ordem from uf_prioridade u where u.uf = h.geo_uf) nulls last,
                     ultima_publicacao desc nulls last, l.id"""
ORDEM_PADRAO = "case l.prioridade when 'alta' then 1 when 'media' then 2 else 3 end, l.score desc nulls last, l.id desc"


ServicoF = Literal["manifestacao_oposicao", "recurso_indeferimento", "outros"]
ClasseF = Literal["quente", "morno", "historico", "pendente"]
TempF = Literal["quente", "morno", "em_pesquisa", "historico"]


@router.get("/leads")
def list_leads(
    status: str | None = None,
    prioridade: str | None = None,
    categoria: str | None = None,
    uf: str | None = None,
    revisao: bool | None = None,
    q: str | None = None,
    whatsapp: Literal["validado", "candidato", "nenhum"] | None = None,
    geo_uf: str | None = Query(None, pattern=r"^([A-Z]{2}|PENDENTE)$"),
    temperatura: TempF | None = None,
    edicao: int | None = None,
    servico: ServicoF | None = None,
    classificacao: ClasseF | None = None,
    operacional: bool | None = None,
    ordem: Literal["padrao", "comercial"] = "padrao",
    limit: int = Query(50, le=200),
    offset: int = 0,
) -> dict:
    p = _filters(status, prioridade, categoria, uf, revisao, q, whatsapp, geo_uf, temperatura, edicao, servico, classificacao,
                 operacional) | {"l": limit, "o": offset}  # fmt: skip
    with db.get_pool().connection() as conn:
        total = conn.execute(f"select count(*) n {LEAD_FILTER}", p).fetchone()["n"]
        rows = conn.execute(
            f"""select l.*, h.nome_original as titular, h.uf, h.tipo_provavel, h.cnpj, h.cnpj_status,
                       h.geo_uf, h.geo_municipio, h.geo_status, h.geo_fonte,
                       (select max(e.data_publicacao) from lead_processes lp join opportunities o on o.numero_processo = lp.numero_processo
                          join rpi_editions e on e.id = o.edition_id where lp.lead_id = l.id) as ultima_publicacao,
                       (select string_agg(distinct p.marca_nome, ', ') from lead_processes lp join processes p on p.numero_processo = lp.numero_processo
                         where lp.lead_id = l.id) as marcas,
                       (select string_agg(lp.numero_processo, ', ') from lead_processes lp where lp.lead_id = l.id) as processos,
                       (select count(*) from lead_processes lp where lp.lead_id = l.id) as n_processos,
                       (select count(*) from contacts c where c.holder_id = l.holder_id and c.verificacao <> 'invalido')
                         as n_contatos,
                       (select count(*) from contacts c where c.holder_id = l.holder_id
                          and c.verificacao in ('dominio_ok','verificado_humano')) as n_validados
                {LEAD_FILTER}
                order by {ORDEM_COMERCIAL if ordem == "comercial" else ORDEM_PADRAO}
                limit %(l)s offset %(o)s""",
            p,
        ).fetchall()
    return {"total": total, "items": rows}


@router.get("/leads/{lead_id}")
def get_lead(lead_id: int) -> dict:
    with db.get_pool().connection() as conn:
        lead = conn.execute("select * from leads where id = %s", (lead_id,)).fetchone()
        if lead is None:
            raise HTTPException(404, "Lead não encontrado")
        hid = lead["holder_id"]
        lead["titular"] = conn.execute("select * from holders where id = %s", (hid,)).fetchone()
        lead["cadastro_cnpj"] = (
            conn.execute(
                """select e.*, emp.razao_social, emp.natureza_juridica, emp.porte, emp.capital_social
                 from cnpj_estabelecimentos e join cnpj_empresas emp using (cnpj_basico)
                where e.cnpj = %s""",
                (lead["titular"]["cnpj"],),
            ).fetchone()
            if lead["titular"]["cnpj"]
            else None
        )
        lead["processos"] = conn.execute(
            """select p.*,
                      (select row_to_json(x) from (
                          select pub.despacho_codigo, pub.despacho_nome, pub.texto_complementar, e.numero as rpi,
                                 e.data_publicacao
                            from publications pub join rpi_editions e on e.id = pub.edition_id
                           where pub.numero_processo = p.numero_processo
                           order by e.numero desc limit 1) x) as ultimo_despacho,
                      (select row_to_json(v) from (
                          select iv.id, iv.consultado_em, iv.fonte_url, iv.resultado, iv.situacao, iv.procurador
                            from inpi_verifications iv where iv.numero_processo = p.numero_processo
                           order by iv.consultado_em desc limit 1) v) as ultima_verificacao
                 from processes p join lead_processes lp on lp.numero_processo = p.numero_processo
                where lp.lead_id = %s order by p.numero_processo""",
            (lead_id,),
        ).fetchall()
        lead["contatos"] = conn.execute(
            """select c.*, e.url as fonte_url, e.trecho as fonte_trecho, e.obtido_em as fonte_data,
                      e.fonte_tipo as evidencia_tipo
                 from contacts c join evidences e on e.id = c.evidence_id
                where c.holder_id = %s
                order by case c.verificacao when 'verificado_humano' then 1 when 'dominio_ok' then 2
                         when 'formato_ok' then 3 when 'encontrado' then 4 else 5 end, c.tipo""",
            (hid,),
        ).fetchall()
        lead["pesquisas"] = conn.execute(
            "select * from research_runs where holder_id = %s order by iniciado_em desc", (hid,)
        ).fetchall()
        lead["prospeccao"] = conn.execute(
            """select o.*, c.tipo as contato_tipo, c.valor as contato_valor from outreach_log o
                 left join contacts c on c.id = o.contact_id where o.lead_id = %s order by o.executado_em desc""",
            (lead_id,),
        ).fetchall()
        lead["notas"] = conn.execute("select * from lead_notes where lead_id = %s order by em desc", (lead_id,)).fetchall()
        # V2.4: oportunidades de serviço (manifestação à oposição / recurso) com prazo, medida, opositor e fontes
        lead["servicos"] = conn.execute(
            """select os.*, p.marca_nome from oportunidades_servico os
                 join processes p on p.numero_processo = os.numero_processo
                 join lead_processes lp on lp.numero_processo = os.numero_processo
                where lp.lead_id = %s
                order by case os.classificacao when 'quente' then 0 when 'morno' then 1 when 'pendente' then 2 else 3 end,
                         os.prazo_fim nulls last""",
            (lead_id,),
        ).fetchall()
        lead["peticoes"] = conn.execute(
            """select pt.* from process_peticoes pt join lead_processes lp on lp.numero_processo = pt.numero_processo
                where lp.lead_id = %s order by pt.data desc nulls last""",
            (lead_id,),
        ).fetchall()
        lead["revisoes"] = conn.execute(
            """select * from review_tasks where status = 'aberta' and (
                 (entidade = 'holder' and entidade_id = %s) or (entidade = 'process' and entidade_id in
                   (select numero_processo from lead_processes where lead_id = %s)))""",
            (str(hid), lead_id),
        ).fetchall()
        lead["historico"] = conn.execute(
            """select id, acao, ator, em, antes->>'status' as status_antes, depois->>'status' as status_depois,
                      depois->>'prioridade' as prioridade
                 from audit_log where tabela = 'leads' and registro_id = %s order by em desc limit 100""",
            (str(lead_id),),
        ).fetchall()
    return lead


class LeadPatch(BaseModel):
    status: (
        Literal["novo", "qualificado", "sem_contato", "em_revisao", "aprovado", "contatado", "convertido", "descartado"] | None
    ) = None
    motivo_descarte: str | None = None
    revisado: bool | None = None


@router.patch("/leads/{lead_id}")
def update_lead(lead_id: int, body: LeadPatch, user: User = Depends(current_user)) -> dict:
    if body.status == "descartado" and not body.motivo_descarte:
        raise HTTPException(422, "Informe o motivo do descarte")
    with db.transaction(user.actor) as conn:
        row = conn.execute(
            """update leads set status = coalesce(%s, status),
                      motivo_descarte = case when %s::text is not null then %s else motivo_descarte end,
                      revisado_por = case when %s then %s else revisado_por end,
                      revisado_em = case when %s then now() else revisado_em end,
                      precisa_revisao = case when %s then false else precisa_revisao end
                where id = %s returning *""",
            (
                body.status,
                body.motivo_descarte,
                body.motivo_descarte,
                bool(body.revisado),
                user.actor,
                bool(body.revisado),
                bool(body.revisado),
                lead_id,
            ),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Lead não encontrado")
        if body.revisado:
            conn.execute(
                """update review_tasks set status = 'resolvida', resolvido_em = now(), resolucao = %s
                    where status = 'aberta' and entidade = 'holder' and entidade_id = %s""",
                (f"revisado por {user.actor}", str(row["holder_id"])),
            )
    return row


class NoteIn(BaseModel):
    texto: str = Field(min_length=1, max_length=4000)


@router.post("/leads/{lead_id}/notes", status_code=201)
def add_note(lead_id: int, body: NoteIn, user: User = Depends(current_user)) -> dict:
    with db.transaction(user.actor) as conn:
        return conn.execute(
            "insert into lead_notes (lead_id, texto, autor) values (%s, %s, %s) returning *",
            (lead_id, body.texto, user.actor),
        ).fetchone()


class OutreachIn(BaseModel):
    canal: Literal["email", "telefone", "whatsapp", "presencial", "outro"]
    contact_id: int | None = None
    resultado: str | None = None
    observacoes: str | None = None


@router.post("/leads/{lead_id}/outreach", status_code=201)
def register_outreach(lead_id: int, body: OutreachIn, user: User = Depends(current_user)) -> dict:
    """Registra uma prospecção feita POR UMA PESSOA. O sistema não envia nada (regra 8)."""
    with db.transaction(user.actor) as conn:
        lead = conn.execute("select * from leads where id = %s", (lead_id,)).fetchone()
        if lead is None:
            raise HTTPException(404, "Lead não encontrado")
        if lead["status"] not in ("aprovado", "contatado", "convertido"):
            raise HTTPException(409, "Aprove o lead antes de registrar a prospecção")
        if body.contact_id:
            c = conn.execute(
                "select * from contacts where id = %s and holder_id = %s", (body.contact_id, lead["holder_id"])
            ).fetchone()
            if c is None:
                raise HTTPException(404, "Contato não pertence ao lead")
            h = hashlib.sha256(c["valor_normalizado"].encode()).hexdigest()
            if conn.execute("select 1 from suppression_list where valor_hash = %s", (h,)).fetchone():
                raise HTTPException(409, "Contato na lista de opt-out (LGPD)")
            if c["verificacao"] == "invalido":
                raise HTTPException(409, "Contato marcado como inválido")
        row = conn.execute(
            """insert into outreach_log (lead_id, canal, contact_id, aprovado_por, executado_por, resultado, observacoes)
               values (%s, %s, %s, %s, %s, %s, %s) returning *""",
            (
                lead_id,
                body.canal,
                body.contact_id,
                lead["revisado_por"] or user.actor,
                user.actor,
                body.resultado,
                body.observacoes,
            ),
        ).fetchone()
        conn.execute("update leads set status = 'contatado' where id = %s and status = 'aprovado'", (lead_id,))
    return row


class ContactVerify(BaseModel):
    verificacao: Literal["verificado_humano", "invalido"]
    observacao: str | None = None


@router.post("/contacts/{contact_id}/verify")
def verify_contact(contact_id: int, body: ContactVerify, user: User = Depends(current_user)) -> dict:
    with db.transaction(user.actor) as conn:
        row = conn.execute(
            """update contacts set verificacao = %s, observacao = coalesce(%s, observacao), checado_em = now(),
                      checagem = checagem || %s where id = %s returning *""",
            (body.verificacao, body.observacao, Jsonb({"humano": user.actor}), contact_id),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Contato não encontrado")
        queue.enqueue(conn, "leads.build", {}, dedupe_key="leads.build", prioridade=80)
    return row


class ContactIn(BaseModel):
    tipo: str
    valor: str
    fonte_url: str = Field(min_length=4, description="Onde o dado foi obtido (regra 3)")
    trecho: str | None = None


@router.post("/leads/{lead_id}/contacts", status_code=201)
def add_contact(lead_id: int, body: ContactIn, user: User = Depends(current_user)) -> dict:
    if body.tipo not in TIPOS:
        raise HTTPException(422, f"Tipo inválido. Use: {', '.join(TIPOS)}")
    norm = normalize_contact(body.tipo, body.valor)
    if not norm:
        raise HTTPException(422, "Formato inválido")
    with db.transaction(user.actor) as conn:
        lead = conn.execute("select holder_id from leads where id = %s", (lead_id,)).fetchone()
        if lead is None:
            raise HTTPException(404, "Lead não encontrado")
        ev = conn.execute(
            "insert into evidences (url, trecho, fonte_tipo) values (%s, %s, 'manual') returning id",
            (body.fonte_url, body.trecho or f"Informado por {user.actor}"),
        ).fetchone()
        return conn.execute(
            """insert into contacts (holder_id, tipo, valor, valor_normalizado, evidence_id, fonte_tipo, verificacao,
                                     confianca, observacao)
               values (%s, %s, %s, %s, %s, 'manual', 'verificado_humano', 1, %s)
               on conflict (holder_id, tipo, valor_normalizado) do update set verificacao = 'verificado_humano'
               returning *""",
            (lead["holder_id"], body.tipo, body.valor, norm, ev["id"], f"cadastrado por {user.actor}"),
        ).fetchone()


class CnpjChoice(BaseModel):
    cnpj: str | None = Field(None, pattern=r"^\d{14}$")
    nenhum: bool = False


@router.post("/holders/{holder_id}/cnpj")
def choose_cnpj(holder_id: int, body: CnpjChoice, user: User = Depends(current_user)) -> dict:
    """Resolução humana de homônimos (escolhe o CNPJ ou declara que nenhum serve)."""
    with db.transaction(user.actor) as conn:
        h = conn.execute("select * from holders where id = %s", (holder_id,)).fetchone()
        if h is None:
            raise HTTPException(404, "Titular não encontrado")
        if body.nenhum:
            row = conn.execute(
                "update holders set cnpj = null, cnpj_status = 'nao_aplicavel' where id = %s returning *", (holder_id,)
            ).fetchone()
        else:
            if not body.cnpj:
                raise HTTPException(422, "Informe o CNPJ ou nenhum=true")
            row = conn.execute(
                """update holders set cnpj = %s, cnpj_status = 'manual', cnpj_confianca = 1, cnpj_fonte = %s,
                          tipo_provavel = 'PJ' where id = %s returning *""",
                (body.cnpj, f"escolhido por {user.actor}", holder_id),
            ).fetchone()
        conn.execute(
            """update review_tasks set status = 'resolvida', resolvido_em = now(), resolucao = %s
                         where status = 'aberta' and entidade = 'holder' and entidade_id = %s""",
            (f"CNPJ definido por {user.actor}", str(holder_id)),
        )
        queue.enqueue(conn, "leads.build", {}, dedupe_key="leads.build", prioridade=80)
    return row


class OptOut(BaseModel):
    tipo: Literal["email", "telefone", "titular"]
    valor: str | None = None
    lead_id: int | None = None
    motivo: str | None = None


@router.post("/optout", status_code=201)
def optout(body: OptOut, user: User = Depends(current_user)) -> dict:
    """LGPD: inclui na lista de supressão (só o hash é guardado) e descarta o lead."""
    with db.transaction(user.actor) as conn:
        if body.tipo == "titular":
            if not body.lead_id:
                raise HTTPException(422, "Informe lead_id")
            h = conn.execute(
                "select h.* from holders h join leads l on l.holder_id = h.id where l.id = %s", (body.lead_id,)
            ).fetchone()
            if h is None:
                raise HTTPException(404, "Lead não encontrado")
            valor_hash = holder_hash(h)
            conn.execute(
                "update leads set status = 'descartado', motivo_descarte = 'opt-out (LGPD)',"
                " revisado_por = %s, revisado_em = now() where holder_id = %s",
                (user.actor, h["id"]),
            )
        else:
            norm = normalize_contact(body.tipo, body.valor or "")
            if not norm:
                raise HTTPException(422, "Valor inválido")
            valor_hash = hashlib.sha256(norm.encode()).hexdigest()
            conn.execute(
                "update contacts set verificacao = 'invalido', observacao = 'opt-out (LGPD)' where valor_normalizado = %s",
                (norm,),
            )
        conn.execute(
            """insert into suppression_list (tipo, valor_hash, motivo, criado_por) values (%s, %s, %s, %s)
                        on conflict do nothing""",
            (body.tipo, valor_hash, body.motivo, user.actor),
        )
    return {"ok": True, "hash": valor_hash}


@router.post("/leads/{lead_id}/research", status_code=202)
def research_now(lead_id: int, user: User = Depends(current_user)) -> dict:
    with db.transaction(user.actor) as conn:
        lead = conn.execute("select holder_id from leads where id = %s", (lead_id,)).fetchone()
        if lead is None:
            raise HTTPException(404, "Lead não encontrado")
        return queue.enqueue(
            conn,
            "research.holder",
            {"holder_id": lead["holder_id"]},
            dedupe_key=f"research.holder:{lead['holder_id']}",
            prioridade=30,
        )


@router.post("/leads/{lead_id}/summary", status_code=202)
def summarize_now(lead_id: int, user: User = Depends(current_user)) -> dict:
    with db.transaction(user.actor) as conn:
        conn.execute("update leads set resumo = null where id = %s", (lead_id,))
        return queue.enqueue(
            conn,
            "sales.summarize_batch",
            {"lead_id": lead_id, "limite": 1},
            dedupe_key=f"sales.summary:{lead_id}",
            prioridade=30,
        )


# ------------------------------------------------------------------ exportação
EXPORT_COLS = [
    "lead_id",
    "prioridade",
    "score",
    "whatsapp",
    "whatsapp_status",
    "temperatura",
    "motivos_temperatura",
    "status",
    "titular",
    "tipo",
    "uf",
    "uf_localizacao",
    "municipio",
    "localizacao",
    "fonte_localizacao",
    "cnpj",
    "segmento",
    "categoria",
    "prazo_estimado",
    "processos",
    "marcas",
    "procurador_confirmado_inpi",
    "contatos_validados",
    "fontes",
    "precisa_revisao",
    "servico_principal",
    "classificacao_manifestacao",
    "classificacao_recurso",
]


def _export_rows(conn, p: dict) -> list[dict]:
    rows = conn.execute(
        f"""select l.id as lead_id, l.prioridade, l.score, l.status, h.nome_original as titular,
                   h.tipo_provavel as tipo, h.uf, h.cnpj, l.segmento, l.whatsapp, l.whatsapp_status,
                   h.geo_uf as uf_localizacao, h.geo_municipio as municipio, h.geo_status as localizacao,
                   case h.geo_fonte when 'receita' then 'Receita Federal (CNPJ)' when 'rpi' then 'Declarada na RPI'
                        when 'manual' then 'Informada manualmente' end as fonte_localizacao,
                   l.temperatura, (select string_agg(m, '; ') from jsonb_array_elements_text(l.temperatura_motivos) m) as motivos_temperatura,
                   case l.servico_principal when 'manifestacao_oposicao' then 'Manifestação à oposição'
                        when 'recurso_indeferimento' then 'Recurso contra indeferimento' end as servico_principal,
                   l.classificacao_oposicao as classificacao_manifestacao, l.classificacao_recurso,
                   l.categoria_principal as categoria,
                   l.prazo_ate as prazo_estimado, l.procurador_confirmado as procurador_confirmado_inpi,
                   l.precisa_revisao,
                   (select string_agg(lp.numero_processo, ', ') from lead_processes lp where lp.lead_id = l.id)
                     as processos,
                   (select string_agg(distinct p.marca_nome, ', ') from lead_processes lp
                      join processes p on p.numero_processo = lp.numero_processo where lp.lead_id = l.id) as marcas,
                   (select string_agg(c.tipo || ': ' || c.valor, ' | ') from contacts c
                     where c.holder_id = l.holder_id and c.verificacao in ('dominio_ok','verificado_humano'))
                     as contatos_validados,
                   (select string_agg(distinct e.url, ' | ') from contacts c join evidences e on e.id = c.evidence_id
                     where c.holder_id = l.holder_id and c.verificacao in ('dominio_ok','verificado_humano'))
                     as fontes
            {LEAD_FILTER} and l.status <> 'descartado'
            order by case l.prioridade when 'alta' then 1 when 'media' then 2 else 3 end, l.score desc nulls last""",
        p,
    ).fetchall()
    # opt-out: o titular fica 'descartado' e o contato 'invalido', então nenhum dos dois sai aqui
    return rows


@router.get("/leads-export")
def export_leads(
    formato: Literal["csv", "xlsx"] = "xlsx",
    status: str | None = None,
    prioridade: str | None = None,
    categoria: str | None = None,
    uf: str | None = None,
    whatsapp: Literal["validado", "candidato", "nenhum"] | None = None,
    geo_uf: str | None = Query(None, pattern=r"^([A-Z]{2}|PENDENTE)$"),
    temperatura: TempF | None = None,
    edicao: int | None = None,
    servico: ServicoF | None = None,
    classificacao: ClasseF | None = None,
    user: User = Depends(current_user),
) -> Response:
    p = _filters(status, prioridade, categoria, uf, None, None, whatsapp, geo_uf, temperatura, edicao, servico, classificacao)
    with db.transaction(user.actor) as conn:
        rows = _export_rows(conn, p)
        conn.execute(
            "insert into exports_log (formato, filtros, linhas, criado_por) values (%s, %s, %s, %s)",
            (formato, Jsonb({k: v for k, v in p.items() if v is not None}), len(rows), user.actor),
        )
    nome = f"leads_{datetime.now(UTC):%Y%m%d_%H%M}"
    if formato == "csv":
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=EXPORT_COLS, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
        return Response(
            ("﻿" + buf.getvalue()).encode("utf-8"),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{nome}.csv"'},
        )
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Leads"
    ws.append(EXPORT_COLS)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append([r.get(k) if not isinstance(r.get(k), (list, dict)) else json.dumps(r.get(k)) for k in EXPORT_COLS])
    ws.freeze_panes = "A2"
    for col, w in zip("ABCDEFGHIJKLMNOPQ", [8, 10, 7, 12, 40, 10, 5, 16, 28, 18, 14, 30, 30, 12, 50, 50, 10], strict=False):
        ws.column_dimensions[col].width = w
    aviso = wb.create_sheet("Leia-me")
    for linha in [
        "Exportação do INPI Lead Intelligence.",
        "Contatos listados: apenas os validados (automaticamente ou por pessoa), com a URL de origem.",
        "Prazos são estimativas (60 dias da publicação na RPI); confirme no INPI.",
        "Contatos e titulares em opt-out (LGPD) foram excluídos. Não use para envio automático em massa.",
        f"Gerado em {datetime.now(UTC):%d/%m/%Y %H:%M} UTC por {user.actor}.",
    ]:
        aviso.append([linha])
    out = io.BytesIO()
    wb.save(out)
    return Response(
        out.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nome}.xlsx"'},
    )


# ------------------------------------------------------------------ relatórios e métricas
@router.get("/reports")
def list_reports() -> list[dict]:
    with db.get_pool().connection() as conn:
        return conn.execute(
            "select id, tipo, referencia, criado_em, criado_por from reports order by criado_em desc limit 100"
        ).fetchall()


@router.get("/reports/preview")
def report_preview(edicao: int | None = None) -> dict:
    with db.get_pool().connection() as conn:
        d = weekly_report_data(conn, edicao)
    if d is None:
        raise HTTPException(404, "Nenhuma edição processada")
    return d


@router.get("/reports/{report_id}")
def get_report(report_id: int) -> dict:
    with db.get_pool().connection() as conn:
        r = conn.execute("select * from reports where id = %s", (report_id,)).fetchone()
    if r is None:
        raise HTTPException(404, "Relatório não encontrado")
    return r


@router.post("/reports", status_code=202)
def create_report(edicao: int | None = None, user: User = Depends(current_user)) -> dict:
    with db.transaction(user.actor) as conn:
        return queue.enqueue(conn, "reports.weekly", {"edicao": edicao} if edicao else {}, dedupe_key="reports.weekly:manual")


@router.get("/metrics")
def metrics() -> dict:
    """Saúde operacional: fila, últimos resultados por agente, custo de IA e agendamentos."""
    from app.config import get_settings

    s = get_settings()
    with db.get_pool().connection() as conn:
        return {
            "ia_configurada": bool(s.anthropic_api_key),
            "orcamento_semanal_usd": s.ia_orcamento_semanal_usd,
            "fila": conn.execute(
                "select tipo, status, count(*) n from jobs group by tipo, status order by tipo, status"
            ).fetchall(),
            "ultimo_por_agente": conn.execute(
                """select distinct on (tipo) tipo, status, finalizado_em, left(ultimo_erro, 200) as erro
                     from jobs where status in ('succeeded','dead') order by tipo, id desc"""
            ).fetchall(),
            "falhas_24h": conn.execute(
                "select count(*) n from jobs where status = 'dead' and finalizado_em > now() - interval '24 hours'"
            ).fetchone()["n"],
            "custo_ia": conn.execute(
                """select proposito, count(*) chamadas, sum(buscas_web) buscas, round(sum(custo_usd), 2) usd
                     from llm_calls where criado_em >= date_trunc('week', now()) group by proposito"""
            ).fetchall(),
            "agendamentos": conn.execute(
                "select nome, tipo, ativo, intervalo_minutos, proximo_em from schedules order by nome"
            ).fetchall(),
        }


class ScheduleIn(BaseModel):
    ativo: bool


@router.patch("/schedules/{nome}")
def toggle_schedule(nome: str, body: ScheduleIn, user: User = Depends(current_user)) -> dict:
    with db.transaction(user.actor) as conn:
        row = conn.execute("update schedules set ativo = %s where nome = %s returning *", (body.ativo, nome)).fetchone()
    if row is None:
        raise HTTPException(404, "Agendamento não encontrado")
    return row


@router.get("/reviews")
def list_reviews(status: str = "aberta", limit: int = Query(100, le=500)) -> list[dict]:
    with db.get_pool().connection() as conn:
        return conn.execute(
            """select r.*, (select l.id from leads l where r.entidade = 'holder' and l.holder_id::text = r.entidade_id)
                      as lead_id from review_tasks r where r.status = %s order by r.criado_em desc limit %s""",
            (status, limit),
        ).fetchall()


@router.post("/reviews/{review_id}/resolve")
def resolve_review(review_id: int, body: NoteIn, user: User = Depends(current_user)) -> dict:
    with db.transaction(user.actor) as conn:
        row = conn.execute(
            """update review_tasks set status = 'resolvida', resolucao = %s, resolvido_em = now(),
                                     atribuido_a = %s where id = %s returning *""",
            (body.texto, user.actor, review_id),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Revisão não encontrada")
    return row
