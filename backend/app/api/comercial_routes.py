"""V2.6 · Indicadores comerciais e auditoria da coleta, com a mesma lógica dos filtros operacionais.

Nada aqui conta registro descartado como oportunidade: a base é a mesma de /api/servicos (elegível, sem procurador
confirmado e edição ≥ mínima). Prioridade comercial ≠ elegibilidade de envio: são indicadores separados.
"""

from fastapi import APIRouter, Depends, HTTPException

from app import comercial, db
from app.api.servicos_routes import _BASE, _params
from app.auth import current_user

router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])

_POR_UF = """
  count(*) filter (where servico = 'manifestacao_oposicao') as oposicoes,
  count(*) filter (where servico = 'recurso_indeferimento') as indeferimentos,
  count(distinct holder_id) as titulares,
  count(*) filter (where no_pipeline) as no_pipeline,
  count(distinct holder_id) filter (where contatos > 0) as com_contato
"""


@router.get("/comercial/indicadores")
def indicadores() -> dict:
    with db.get_pool().connection() as conn:
        minimo = conn.execute("select rpi_edicao_minima() m").fetchone()["m"]
        edicoes = conn.execute(
            """select numero, data_publicacao, status, auditoria, catalogo_versao is not distinct from catalogo_versao() as catalogo_atual
                 from rpi_editions where numero >= %s order by numero desc""",
            (minimo,),
        ).fetchall()
        base = conn.execute(_BASE + f"select {_POR_UF} from f", _params()).fetchone()
        uf = {
            r["uf"]: r
            for r in conn.execute(
                _BASE + f"select coalesce(geo_uf, 'PENDENTE') as uf, {_POR_UF} from f group by 1", _params()
            ).fetchall()
        }
        # representação: todos os processos de oposição/indeferimento das edições operacionais (não só os elegíveis)
        rep = {
            r["s"]: r["n"]
            for r in conn.execute(
                """select procurador_situacao(p.procurador_status) s, count(distinct os.numero_processo) n
                     from oportunidades_servico os join processes p using (numero_processo)
                    where os.rpi_numero >= rpi_edicao_minima() group by 1"""
            ).fetchall()
        }
        leads = conn.execute(
            _BASE
            + """, ls as (select distinct lead_id from f where lead_id is not null)
               select count(*) as leads,
                      count(*) filter (where l.pipeline_incluido_em is not null) as no_pipeline,
                      count(*) filter (where l.precisa_revisao) as aguardando_revisao,
                      count(*) filter (where exists (select 1 from contacts c where c.holder_id = l.holder_id
                                                        and c.verificacao <> 'invalido')) as com_contato,
                      count(*) filter (where exists (select 1 from contacts c join consents k on k.contact_id = c.id
                                                      where c.holder_id = l.holder_id and k.status = 'ativo')) as com_autorizacao,
                      count(*) filter (where l.pipeline_stage = 'elegivel_primeiro_contato') as elegiveis_primeiro_contato
                 from ls join leads l on l.id = ls.lead_id""",
            _params(),
        ).fetchone()
        duplicados = conn.execute("select count(*) n from leads where mesclado_em is not null").fetchone()["n"]
    zero = {"oposicoes": 0, "indeferimentos": 0, "titulares": 0, "no_pipeline": 0, "com_contato": 0}
    return {
        "edicao_minima": minimo,
        "rpis_processadas": sum(1 for e in edicoes if e["status"] == "parsed"),
        "edicoes": [
            {
                "numero": e["numero"],
                "data_publicacao": e["data_publicacao"],
                "status": e["status"],
                "completa": e["status"] == "parsed" and e["catalogo_atual"] and (e["auditoria"] or {}).get("completa", False),
                "alerta": _alerta(e),
                "auditoria": e["auditoria"],
            }
            for e in edicoes
        ],  # fmt: skip
        "oportunidades": base,
        "representacao": {
            k: rep.get(k, 0)
            for k in ("SEM_PROCURADOR_CONFIRMADO", "COM_PROCURADOR", "PROCURADOR_DESCONHECIDO", "ERRO_NA_IDENTIFICACAO")
        },
        "por_uf": uf,
        "sul": [
            {"uf": u, "ordem": o} | {k: v for k, v in (uf.get(u) or zero).items() if k != "uf"}
            for u, o in comercial.UF_PRIORIDADE.items()
        ],
        "sem_uf": uf.get("PENDENTE") or zero,
        "leads": leads | {"duplicados_mesclados": duplicados},
    }


def _alerta(e: dict) -> str | None:
    if e["status"] != "parsed":
        return f"Processamento incompleto (situação: {e['status']})"
    if not e["catalogo_atual"]:
        return "Releitura pendente: o catálogo de despachos mudou depois da leitura desta edição"
    erros = (e["auditoria"] or {}).get("erros_de_extracao") or []
    if erros:
        return "Divergência na extração: " + "; ".join(erros)
    if not e["auditoria"]:
        return "Sem relatório de auditoria (edição lida antes da V2.6): será relida"
    return None


@router.get("/rpi/{numero}/auditoria")
def auditoria(numero: int) -> dict:
    with db.get_pool().connection() as conn:
        e = conn.execute(
            """select numero, data_publicacao, status, auditoria, stats, catalogo_versao is not distinct from catalogo_versao() as catalogo_atual,
                      numero >= rpi_edicao_minima() as operacional
                 from rpi_editions where numero = %s""",
            (numero,),
        ).fetchone()
    if e is None:
        raise HTTPException(404, "Edição não encontrada")
    return e | {"alerta": _alerta(e)}
