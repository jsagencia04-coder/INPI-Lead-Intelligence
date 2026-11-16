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


# ------------------------------------------------------------------ V2.9 · extração paralela PDF + XML
@router.get("/rpi-fontes")
def rpi_fontes(numero: int | None = None) -> dict:
    """Indicadores da edição (a mais recente, se não informada): publicação, detecção e processamento de cada arquivo,
    registros por fonte, divergências PDF × XML, leads qualificados e o estado sendo processado agora."""
    with db.get_pool().connection() as conn:
        ed = conn.execute(
            "select * from rpi_editions where (%(n)s::int is null or numero = %(n)s) order by numero desc limit 1",
            {"n": numero},
        ).fetchone()
        if ed is None:
            if numero is not None:
                raise HTTPException(404, "Edição não encontrada")
            return {"edicao": None, "fontes": []}
        fontes = conn.execute(
            """select fonte, url, status, detectado_em, baixado_em, processamento_inicio, processado_em,
                      tempo_download_s, tempo_processamento_s, paginas, registros, registros_alvo, tentativas,
                      ultimo_erro, etapa, uf_em_processamento, detalhes
                 from rpi_fontes where edition_id = %s order by array_position(array['pdf_i','xml','pdf_ii'], fonte)""",
            (ed["id"],),
        ).fetchall()
        conc = {
            r["situacao"]: r["n"]
            for r in conn.execute(
                "select situacao, count(*) n from rpi_reconciliacao where edition_id = %s group by 1", (ed["id"],)
            ).fetchall()
        }
        por_fonte = {
            r["fonte"]: r["n"]
            for r in conn.execute(
                "select fonte, count(*) n from publications where edition_id = %s group by 1", (ed["id"],)
            ).fetchall()
        }
        leads = conn.execute(
            """select coalesce(h.geo_uf, 'PENDENTE') uf, count(distinct l.id) n,
                      count(distinct l.id) filter (where pb.fonte = 'pdf') as pelo_pdf
                 from opportunities o
                 join publications pb on pb.numero_processo = o.numero_processo and pb.edition_id = o.edition_id
                                     and pb.despacho_codigo = o.despacho_codigo
                 join process_holders ph on ph.numero_processo = o.numero_processo
                 join leads l on l.holder_id = ph.holder_id and l.mesclado_em is null and l.status <> 'descartado'
                 join holders h on h.id = l.holder_id
                where o.edition_id = %s and o.status = 'elegivel'
                group by 1 order by prioridade_fila_uf(min(h.geo_uf)) nulls last, 1""",
            (ed["id"],),
        ).fetchall()
        divergencias = conn.execute(
            """select numero_processo, despacho_codigo, situacao, diferencas from rpi_reconciliacao
                where edition_id = %s and situacao <> 'confere' and revisado_em is null
                order by situacao, numero_processo limit 50""",
            (ed["id"],),
        ).fetchall()
    em_proc = next((f for f in fontes if f["status"] in ("baixando", "processando")), None)
    return {
        "edicao": {k: ed[k] for k in ("numero", "data_publicacao", "status", "detectada_em", "coletada_em", "processada_em")},
        "fontes": fontes,
        "publicacoes_por_fonte": por_fonte,
        "conciliacao": conc,
        "divergencias": divergencias,
        "leads_qualificados": leads,
        "em_processamento": {"fonte": em_proc["fonte"], "etapa": em_proc["etapa"], "uf": em_proc["uf_em_processamento"]}
        if em_proc
        else None,
    }


@router.get("/sistema/status")
def sistema_status() -> dict:
    """V2.11: situação da operação (aguardando a próxima Revista, última importação, próxima execução)."""
    from app import reset

    with db.get_pool().connection() as conn:
        st = reset.status_sistema(conn)
        st["ultima_limpeza"] = conn.execute(
            "select executado_em, executado_por from system_resets order by id desc limit 1"
        ).fetchone()
    return st
