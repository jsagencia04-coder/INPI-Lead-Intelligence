"""Mapa de oportunidades (Brasil) e Central RPI · operação semanal (V2.3)."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app import db, semana
from app.api.servicos_routes import contagem_por_uf, por_estado
from app.auth import User, current_user
from app.jobs import queue

router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])

UFS = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
       "RS", "RO", "RR", "SC", "SP", "SE", "TO"]  # fmt: skip
TRABALHADOS = ("mensagem_programada", "mensagem_enviada", "mensagem_entregue", "resposta_recebida", "interessado", "reuniao",
               "proposta_enviada", "negociacao", "fechado", "perdido", "opt_out")  # fmt: skip

# leads no escopo dos filtros: lead ativo com oportunidade elegível que atende edição, período e categoria
_ESCOPO = """
  with ult as (select id, numero from rpi_editions where status = 'parsed' order by numero desc limit 1),
  esc as (
    select l.id, l.holder_id, l.temperatura, l.pipeline_stage, l.score, l.prioridade, h.geo_uf, h.geo_status, h.tipo_provavel,
           bool_or(o.categoria = 'oposicao_apresentada') as tem_a,
           bool_or(o.categoria = 'oposicao') as tem_b,
           bool_or(o.edition_id = (select id from ult)) as da_ultima
      from leads l
      join holders h on h.id = l.holder_id
      join lead_processes lp on lp.lead_id = l.id
      join opportunities o on o.numero_processo = lp.numero_processo and o.status = 'elegivel'
      join rpi_editions e on e.id = o.edition_id
     where l.mesclado_em is null and l.status <> 'descartado'
       and (%(ed)s::int is null or e.numero = %(ed)s)
       and (%(desde)s::date is null or e.data_publicacao >= %(desde)s)
       and (%(ate)s::date is null or e.data_publicacao <= %(ate)s)
       and (%(cat)s::text is null or o.categoria = %(cat)s)
     group by l.id, h.id
  )
"""

_CONTAGEM = """
  count(*) as leads,
  count(*) filter (where tem_a) as oposicoes_apresentadas,
  count(*) filter (where tem_b) as publicados_oposicao,
  count(*) filter (where exists (select 1 from contacts c where c.holder_id = esc.holder_id
                                  and c.verificacao in ('dominio_ok','verificado_humano'))) as com_contato_validado,
  count(*) filter (where temperatura = 'quente') as quentes,
  count(*) filter (where temperatura = 'morno') as mornos,
  count(*) filter (where temperatura = 'em_pesquisa' or temperatura is null) as em_pesquisa,
  count(*) filter (where da_ultima) as novos_ultima_rpi,
  count(*) filter (where pipeline_stage <> all(%(trab)s)) as em_analise,
  count(*) filter (where pipeline_stage = any(%(trab)s)) as trabalhados,
  count(*) filter (where geo_status = 'confirmada') as localizacao_confirmada,
  count(*) filter (where geo_status = 'estimada') as localizacao_estimada
"""


def _params(edicao, desde, ate, categoria, temperatura) -> dict:
    return {"ed": edicao, "desde": desde, "ate": ate, "cat": categoria, "temp": temperatura, "trab": list(TRABALHADOS)}


def _filtro_temp(p: dict) -> str:
    return " where (%(temp)s::text is null or temperatura = %(temp)s)"


Cat = Literal["oposicao_apresentada", "oposicao", "indeferimento", "deferimento_parcial", "exigencia", "extincao_prorrogacao"]


Temp = Literal["quente", "morno", "em_pesquisa", "historico"]
Servico = Literal["manifestacao_oposicao", "recurso_indeferimento"]
Prazo = Literal["em_andamento", "proximo_fim", "encerrado", "validar", "validacao_juridica"]
SERV_ZERO = dict.fromkeys(["oposicoes_sofridas", "manifestacoes_cabiveis", "indeferimentos", "recursos_cabiveis", "servicos_quentes"], 0)


@router.get("/mapa")
def mapa(
    edicao: int | None = None,
    desde: date | None = None,
    ate: date | None = None,
    categoria: Cat | None = None,
    temperatura: Temp | None = None,
    servico: Servico | None = None,
    prazo: Prazo | None = None,
) -> dict:
    p = _params(edicao, desde, ate, categoria, temperatura)
    with db.get_pool().connection() as conn:
        rows = conn.execute(
            _ESCOPO + f"select coalesce(geo_uf, 'PENDENTE') as uf, {_CONTAGEM} from esc {_filtro_temp(p)} group by 1", p
        ).fetchall()
        processadas = conn.execute(
            "select count(*) n, max(numero) ultima, max(processada_em) em from rpi_editions where status = 'parsed'"
        ).fetchone()
        ordem = {r["uf"]: r["ordem"] for r in conn.execute("select uf, ordem from uf_prioridade where ativo")}
        # V2.4: as duas categorias comerciais (oposição sofrida × indeferimento), por estado
        serv = contagem_por_uf(conn, edicao=edicao, desde=desde, ate=ate, servico=servico, prazo=prazo)
    por = {r["uf"]: r for r in rows}
    vazio = {k: 0 for k in rows[0] if k != "uf"} if rows else None

    def linha(uf: str) -> dict:
        r = por.get(uf)
        base = r if r else ({"uf": uf} | (vazio or {}))
        sv = {k: v for k, v in (serv.get(uf) or SERV_ZERO).items() if k != "uf"}
        return dict(base) | sv | {"uf": uf, "ordem_prioridade": ordem.get(uf), "taxa_qualificacao": (
            round(100 * base.get("quentes", 0) / base["leads"], 1) if base.get("leads") else None)}  # fmt: skip

    return {
        # sem nenhuma edição processada não há dado: a tela mostra "sem dados", nunca zero
        "processado": processadas["n"] > 0,
        "ultima_edicao": processadas["ultima"],
        "processado_em": processadas["em"],
        "estados": [linha(u) for u in UFS],
        "pendente": linha("PENDENTE"),
        "total": sum(r["leads"] for r in rows),
        "total_servicos": {k: sum(r[k] for r in serv.values()) for k in SERV_ZERO},
    }


@router.get("/mapa/{uf}")
def mapa_uf(
    uf: str,
    edicao: int | None = None,
    desde: date | None = None,
    ate: date | None = None,
    categoria: Cat | None = None,
    temperatura: Temp | None = None,
) -> dict:
    uf = uf.upper()
    if uf not in UFS and uf != "PENDENTE":
        raise HTTPException(404, "UF desconhecida")
    p = _params(edicao, desde, ate, categoria, temperatura) | {"uf": uf}
    cond = "coalesce(esc.geo_uf, 'PENDENTE') = %(uf)s and (%(temp)s::text is null or esc.temperatura = %(temp)s)"
    with db.get_pool().connection() as conn:
        tot = conn.execute(
            _ESCOPO + f"""select {_CONTAGEM},
                    count(distinct holder_id) as titulares,
                    count(distinct holder_id) filter (where tipo_provavel = 'PJ') as empresas
               from esc where {cond}""",
            p,
        ).fetchone()
        prioritarios = conn.execute(
            _ESCOPO + f"""select esc.id, h.nome_original as titular, h.geo_municipio as municipio, h.geo_status, esc.score,
                    esc.temperatura, l.temperatura_motivos, l.whatsapp, l.whatsapp_status, l.categoria_principal, esc.tem_a,
                    (select string_agg(distinct pr.marca_nome, ', ') from lead_processes x join processes pr using (numero_processo)
                      where x.lead_id = esc.id) as marcas
               from esc join leads l on l.id = esc.id join holders h on h.id = esc.holder_id
              where {cond}
              order by case esc.temperatura when 'quente' then 1 when 'morno' then 2 else 3 end, esc.tem_a desc,
                       esc.score desc nulls last
              limit 10""",
            p,
        ).fetchall()
        municipios = conn.execute(
            _ESCOPO + f"""select coalesce(h.geo_municipio, 'Município não informado') as chave, count(*) n
               from esc join holders h on h.id = esc.holder_id where {cond} group by 1 order by 2 desc limit 8""",
            p,
        ).fetchall()
        historico = conn.execute(
            """select e.numero, e.data_publicacao,
                      count(distinct l.id) as leads,
                      count(distinct l.id) filter (where o.categoria = 'oposicao_apresentada') as oposicoes_apresentadas,
                      count(distinct l.id) filter (where o.categoria = 'oposicao') as publicados_oposicao,
                      count(distinct l.id) filter (where l.temperatura = 'quente') as quentes,
                      count(distinct ol.id) as abordagens
                 from rpi_editions e
                 join opportunities o on o.edition_id = e.id and o.status = 'elegivel'
                 join lead_processes lp on lp.numero_processo = o.numero_processo
                 join leads l on l.id = lp.lead_id and l.mesclado_em is null
                 join holders h on h.id = l.holder_id
                 left join outreach_log ol on ol.lead_id = l.id
                where coalesce(h.geo_uf, 'PENDENTE') = %(uf)s
                group by e.id order by e.numero desc limit 10""",
            p,
        ).fetchall()
        pipeline = conn.execute(
            _ESCOPO + f"select pipeline_stage as chave, count(*) n from esc where {cond} group by 1", p
        ).fetchall()
        info = conn.execute("select * from uf_prioridade where uf = %s", (uf,)).fetchone()
        servicos = por_estado(conn, uf)
    return {"uf": uf, "info": info, "indicadores": tot, "prioritarios": prioritarios, "municipios": municipios,
            "historico": historico, "pipeline": pipeline, "servicos": servicos}  # fmt: skip


# ------------------------------------------------------------------ Central RPI · operação semanal
@router.get("/rpi-semana")
def operacao(numero: int | None = None) -> dict:
    with db.get_pool().connection() as conn:
        st = semana.status_operacao(conn, numero)
        edicoes = conn.execute(
            "select numero, data_publicacao, status from rpi_editions order by numero desc limit 20"
        ).fetchall()
        agenda = conn.execute(
            "select nome, ativo, proximo_em, intervalo_minutos, dias_semana, hora_inicio, hora_fim, fuso from schedules"
            " where nome in ('rpi-terca', 'rpi-descoberta', 'operacao-semanal', 'cnpj-receita') order by nome"
        ).fetchall()
        execs = conn.execute(
            """select id, tipo, status, criado_em, iniciado_em, finalizado_em, tentativas, resultado,
                      split_part(coalesce(ultimo_erro, ''), E'\\n', 1) as erro
                 from jobs where tipo in ('rpi.discover','rpi.collect','rpi.parse','rpi.semana','rpi.semana_check')
                order by id desc limit 15"""
        ).fetchall()
    return {"status": st, "edicoes": edicoes, "agenda": agenda, "execucoes": execs}


@router.get("/rpi-semana/relatorio")
def relatorio(numero: int | None = None, uf: str = Query("SC", pattern=r"^[A-Z]{2}$")) -> dict:
    with db.get_pool().connection() as conn:
        r = semana.relatorio(conn, numero, uf)
    if r is None:
        raise HTTPException(404, "Nenhuma edição da RPI importada ainda")
    return r


@router.get("/rpi-semana/comparativo")
def comparativo(uf: str | None = Query(None, pattern=r"^([A-Z]{2}|PENDENTE)$"), limite: int = Query(8, ge=2, le=26)) -> list[dict]:
    """Semana a semana: leads novos (primeira aparição) × recorrentes, oposições, quentes e contatos validados."""
    with db.get_pool().connection() as conn:
        return conn.execute(
            """with pub as (
                 select o.edition_id, l.id as lead_id, l.holder_id, l.temperatura, o.categoria,
                        min(o.edition_id) over (partition by l.id) as primeira
                   from opportunities o
                   join lead_processes lp on lp.numero_processo = o.numero_processo
                   join leads l on l.id = lp.lead_id and l.mesclado_em is null
                   join holders h on h.id = l.holder_id
                  where o.status = 'elegivel' and (%(uf)s::text is null or coalesce(h.geo_uf, 'PENDENTE') = %(uf)s))
               select e.numero, e.data_publicacao,
                      count(distinct pub.lead_id) as leads,
                      count(distinct pub.lead_id) filter (where pub.primeira = e.id) as novos,
                      count(distinct pub.lead_id) filter (where pub.primeira < e.id) as recorrentes,
                      count(distinct pub.lead_id) filter (where pub.categoria = 'oposicao_apresentada') as oposicoes_apresentadas,
                      count(distinct pub.lead_id) filter (where pub.categoria = 'oposicao') as publicados_oposicao,
                      count(distinct pub.lead_id) filter (where pub.temperatura = 'quente') as quentes,
                      count(distinct pub.lead_id) filter (where exists (select 1 from contacts c where c.holder_id = pub.holder_id
                             and c.verificacao in ('dominio_ok','verificado_humano'))) as com_contato_validado
                 from rpi_editions e join pub on pub.edition_id = e.id
                group by e.id order by e.numero desc limit %(lim)s""",
            {"uf": uf, "lim": limite},
        ).fetchall()


@router.post("/rpi-semana/{numero}/priorizar", status_code=202)
def priorizar(numero: int, user: User = Depends(current_user)) -> dict:
    """Reprocessa a priorização da edição (idempotente: não duplica leads nem tarefas)."""
    with db.transaction(user.actor) as conn:
        ed = conn.execute("select status from rpi_editions where numero = %s", (numero,)).fetchone()
        if ed is None or ed["status"] != "parsed":
            raise HTTPException(409, "A edição ainda não foi processada")
        return queue.enqueue(conn, "rpi.semana", {"numero": numero}, dedupe_key=f"rpi.semana:{numero}", prioridade=5)


# ------------------------------------------------------------------ localização e prioridade territorial
class LocalIn(BaseModel):
    uf: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    municipio: str | None = Field(default=None, max_length=120)


@router.post("/holders/{holder_id}/localizacao")
def definir_localizacao(holder_id: int, body: LocalIn, user: User = Depends(current_user)) -> dict:
    """Uma pessoa confirma a UF do titular (ex.: localização pendente). uf vazio = volta ao cálculo automático."""
    if body.uf and body.uf not in UFS:
        raise HTTPException(422, "UF inválida")
    with db.transaction(user.actor) as conn:
        if not conn.execute("select 1 from holders where id = %s", (holder_id,)).fetchone():
            raise HTTPException(404, "Titular não encontrado")
        if body.uf:
            conn.execute(
                """update holders set geo_uf = %s, geo_municipio = %s, geo_fonte = 'manual', geo_status = 'confirmada',
                          geo_atualizado_em = now() where id = %s""",
                (body.uf, body.municipio, holder_id),
            )
        else:
            conn.execute("update holders set geo_fonte = null where id = %s", (holder_id,))
            conn.execute("select geo_atualizar(%s)", (holder_id,))
        queue.enqueue(conn, "leads.build", {}, dedupe_key="leads.build", prioridade=30)
        return conn.execute(
            "select id, geo_uf, geo_municipio, geo_fonte, geo_status, geo_atualizado_em from holders where id = %s", (holder_id,)
        ).fetchone()


@router.get("/uf-prioridade")
def listar_prioridade() -> list[dict]:
    with db.get_pool().connection() as conn:
        return conn.execute("select * from uf_prioridade order by ordem").fetchall()


class OrdemIn(BaseModel):
    ufs: list[str] = Field(min_length=24, max_length=24)


@router.put("/uf-prioridade")
def ordenar(body: OrdemIn, user: User = Depends(current_user)) -> list[dict]:
    """Ordem dos demais estados (4ª posição em diante). SC, RS e PR ficam sempre nas três primeiras."""
    fixos = ["SC", "RS", "PR"]
    resto = [u.upper() for u in body.ufs]
    if sorted(resto) != sorted(u for u in UFS if u not in fixos):
        raise HTTPException(422, "Informe os 24 estados restantes (sem SC, RS e PR), cada um uma vez")
    with db.transaction(user.actor) as conn:
        for i, u in enumerate(fixos + resto, start=1):
            conn.execute("update uf_prioridade set ordem = %s where uf = %s and ordem <> %s", (i, u, i))
        return conn.execute("select * from uf_prioridade order by ordem").fetchall()
