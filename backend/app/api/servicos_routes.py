"""Oportunidades de serviço (V2.4): pipeline 1 · manifestação à oposição; pipeline 2 · recurso contra indeferimento.

Os números das duas frentes nunca se misturam: cada consulta é por serviço, e o consolidado só soma no fim.
"""

import csv
import io
from datetime import UTC, date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from psycopg.types.json import Jsonb

from app import db
from app.auth import User, current_user
from app.servicos import ROTULO_SERVICO

router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])

Servico = Literal["manifestacao_oposicao", "recurso_indeferimento"]
Classe = Literal["quente", "morno", "historico", "pendente"]
TRABALHADOS = ["mensagem_programada", "mensagem_enviada", "mensagem_entregue", "resposta_recebida", "interessado", "reuniao",
               "proposta_enviada", "negociacao", "fechado", "perdido", "opt_out"]  # fmt: skip

# Uma linha por oportunidade de serviço, com o titular (1º titular do processo) e o resumo dos contatos
_BASE = """
  with base as (
    select os.*, p.marca_nome, p.classes_nice, p.situacao_atual, p.verificado_inpi_em,
           h.id as holder_id, h.nome_original as titular, h.tipo_provavel, h.cnpj, h.geo_uf, h.geo_municipio, h.geo_status,
           h.geo_fonte, coalesce(l.mesclado_em, l.id) as lead_id, l.pipeline_stage, l.status as lead_status, l.score,
           prioridade_fila_uf(h.geo_uf) as pfila,
           prioridade_servico(os.servico) as prioridade,
           (select u.ordem from uf_prioridade u where u.uf = h.geo_uf) as uf_ordem,
           p.procurador_status, procurador_situacao(p.procurador_status) as procurador_situacao, p.procurador_nome,
           exists (select 1 from pipeline_processos pp where pp.numero_processo = os.numero_processo) as no_pipeline,
           (select count(*) from contacts c where c.holder_id = h.id and c.verificacao <> 'invalido') as contatos,
           (select count(*) from contacts c where c.holder_id = h.id
              and c.verificacao in ('dominio_ok','verificado_humano')) as contatos_validados,
           case os.classificacao when 'quente' then 0 when 'morno' then 1 when 'pendente' then 2 when 'historico' then 3 else 4 end as ordem_classe
      from oportunidades_servico os
      join processes p on p.numero_processo = os.numero_processo
      join process_holders ph on ph.numero_processo = os.numero_processo
      join holders h on h.id = ph.holder_id
      left join leads l on l.holder_id = h.id
     where (%(todas)s or (os.elegivel and procurador_situacao(p.procurador_status) = 'SEM_PROCURADOR_CONFIRMADO'))
       and (%(todas)s or os.rpi_numero >= rpi_edicao_minima())
       and ph.ordem = (select min(ordem) from process_holders x where x.numero_processo = os.numero_processo)
  ),
  f as (
    select * from base
     where (%(servico)s::text is null or servico = %(servico)s)
       and (%(classe)s::text is null or classificacao = %(classe)s)
       and (%(uf)s::text is null or coalesce(geo_uf, 'PENDENTE') = %(uf)s)
       and (%(cidade)s::text is null or geo_municipio ilike '%%' || %(cidade)s || '%%')
       and (%(edicao)s::int is null or rpi_numero = %(edicao)s)
       and (%(desde)s::date is null or data_publicacao >= %(desde)s)
       and (%(ate)s::date is null or data_publicacao <= %(ate)s)
       and (%(situacao)s::text is null or situacao_processual = %(situacao)s)
       and (%(prazo)s::text is null or prazo_status = %(prazo)s
            or (%(prazo)s = 'validacao_juridica' and validacao_juridica))
       and (%(tipo)s::text is null or tipo_decisao = %(tipo)s)
       and (%(contato)s::text is null
            or (%(contato)s = 'validado' and contatos_validados > 0)
            or (%(contato)s = 'encontrado' and contatos > 0 and contatos_validados = 0)
            or (%(contato)s = 'sem' and contatos = 0))
       and (%(q)s::text is null or titular ilike '%%' || %(q)s || '%%' or marca_nome ilike '%%' || %(q)s || '%%'
            or numero_processo like %(q)s || '%%' or coalesce(cnpj, '') like %(q)s || '%%')
  )
"""
# V2.6: 1º prioridade do despacho (oposição antes de indeferimento, sempre), 2º estado (SC, RS, PR, demais; sem UF por
# último), 3º data da publicação, 4º edição, 5º desempate estável.
_ORDEM = "order by prioridade, uf_ordem nulls last, data_publicacao desc nulls last, rpi_numero desc, numero_processo, servico"


def _params(**kw) -> dict:
    base = dict.fromkeys(["servico", "classe", "uf", "cidade", "edicao", "desde", "ate", "situacao", "prazo", "tipo", "contato", "q"])
    return base | {"todas": False} | {k: v for k, v in kw.items() if v is not None}


_INDICADORES = """
  count(*) as identificadas,
  count(distinct holder_id) as titulares,
  count(*) filter (where situacao_processual = 'aberta') as abertas,
  count(*) filter (where medida_status = 'protocolada') as protocoladas,
  count(*) filter (where situacao_processual = 'historico') as historico,
  count(*) filter (where classificacao = 'quente') as quentes,
  count(*) filter (where classificacao = 'morno') as mornos,
  count(*) filter (where classificacao = 'pendente') as pendentes,
  count(*) filter (where classificacao in ('quente','morno')) as qualificados,
  count(distinct holder_id) filter (where contatos > 0) as contatos_encontrados,
  count(distinct holder_id) filter (where pipeline_stage = any(%(trab)s)) as abordados,
  count(*) filter (where situacao_processual = 'aberta' and prazo_status = 'proximo_fim') as proximos_fim,
  count(*) filter (where validacao_juridica and situacao_processual <> 'historico') as validacao_juridica,
  count(*) filter (where tipo_decisao = 'deferimento_parcial') as parciais,
  min(prazo_fim) filter (where situacao_processual = 'aberta') as proximo_vencimento
"""


def indicadores(conn, **filtros) -> dict:
    p = _params(**filtros) | {"trab": TRABALHADOS}
    out = {}
    for s in ("manifestacao_oposicao", "recurso_indeferimento"):
        out[s] = conn.execute(_BASE + f"select {_INDICADORES} from f", p | {"servico": s}).fetchone()
    soma = {k: out["manifestacao_oposicao"][k] + out["recurso_indeferimento"][k]
            for k in out["manifestacao_oposicao"] if k != "proximo_vencimento"}  # fmt: skip
    return out | {"consolidado": soma}


def _linhas(conn, p: dict, limite: int, offset: int = 0) -> list[dict]:
    return conn.execute(_BASE + f"select * from f {_ORDEM} limit %(lim)s offset %(off)s", p | {"lim": limite, "off": offset}).fetchall()


@router.get("/servicos/painel")
def painel(uf: str | None = None, edicao: int | None = None) -> dict:
    with db.get_pool().connection() as conn:
        ind = indicadores(conn, uf=uf, edicao=edicao)
        melhores = _linhas(conn, _params(uf=uf, edicao=edicao), 20)
    melhores = [m for m in melhores if m["classificacao"] in ("quente", "morno")][:10]
    return ind | {"melhores": melhores, "gerado_em": datetime.now(UTC)}


@router.get("/servicos")
def listar(
    servico: Servico | None = None,
    classificacao: Classe | None = None,
    uf: str | None = Query(None, pattern=r"^([A-Z]{2}|PENDENTE)$"),
    cidade: str | None = None,
    edicao: int | None = None,
    desde: date | None = None,
    ate: date | None = None,
    situacao: Literal["aberta", "historico", "pendente"] | None = None,
    prazo: Literal["em_andamento", "proximo_fim", "encerrado", "validar", "validacao_juridica"] | None = None,
    tipo: Literal["oposicao", "indeferimento", "deferimento_parcial"] | None = None,
    contato: Literal["validado", "encontrado", "sem"] | None = None,
    q: str | None = None,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(50, ge=1, le=200),
) -> dict:
    p = _params(servico=servico, classe=classificacao, uf=uf, cidade=cidade, edicao=edicao, desde=desde, ate=ate,
                situacao=situacao, prazo=prazo, tipo=tipo, contato=contato, q=q)  # fmt: skip
    with db.get_pool().connection() as conn:
        total = conn.execute(_BASE + "select count(*) n from f", p).fetchone()["n"]
        items = _linhas(conn, p, por_pagina, (pagina - 1) * por_pagina)
    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "items": items}


@router.get("/servicos/processo/{numero}")
def do_processo(numero: str) -> dict:
    with db.get_pool().connection() as conn:
        ops = conn.execute(_BASE + "select * from base where numero_processo = %(n)s order by rpi_numero desc",
                           _params() | {"todas": True, "n": numero}).fetchall()  # fmt: skip
        pets = conn.execute("select * from process_peticoes where numero_processo = %s order by data desc", (numero,)).fetchall()
    return {"oportunidades": ops, "peticoes": pets}


# ------------------------------------------------------------------ exportação
EXPORT_COLS = [
    "servico", "classificacao", "motivos", "numero_processo", "marca", "titular", "tipo_titular", "cnpj", "uf", "municipio",
    "fonte_localizacao", "classes_nice", "rpi", "data_publicacao", "despacho", "fundamentacao", "opositor", "fonte_opositor",
    "situacao_inpi", "medida_ja_apresentada", "fonte_medida", "prazo_inicio", "prazo_final_estimado", "situacao_prazo",
    "validacao_juridica", "fonte_prazo", "whatsapp", "telefone", "email", "site", "fontes_contatos", "etapa_crm", "lead_id",
]  # fmt: skip
_MEDIDA = {"protocolada": "Sim", "nao_identificada": "Não identificada no pePI", "nao_verificada": "Ainda não verificada"}
_PRAZO = {"em_andamento": "Em andamento", "proximo_fim": "Próximo do encerramento", "encerrado": "Encerrado", "validar": "Validar"}


def _contatos(conn, holder_ids: list[int]) -> dict[int, dict]:
    rows = conn.execute(
        """select distinct on (c.holder_id, c.tipo) c.holder_id, c.tipo, c.valor_normalizado, c.verificacao, e.url
             from contacts c left join evidences e on e.id = c.evidence_id
            where c.holder_id = any(%s) and c.verificacao <> 'invalido'
              and c.tipo in ('whatsapp','telefone','email','site')
            order by c.holder_id, c.tipo, (c.verificacao in ('dominio_ok','verificado_humano')) desc, c.confianca desc nulls last""",
        (holder_ids,),
    ).fetchall()
    out: dict[int, dict] = {}
    for r in rows:
        d = out.setdefault(r["holder_id"], {"fontes": []})
        d[r["tipo"]] = r["valor_normalizado"] + ("" if r["verificacao"] in ("dominio_ok", "verificado_humano") else " (não validado)")
        if r["url"]:
            d["fontes"].append(f"{r['tipo']}: {r['url']}")
    return out


def _br(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


@router.get("/servicos/export")
def exportar(
    formato: Literal["csv", "xlsx"] = "xlsx",
    servico: Servico | None = None,
    classificacao: Classe | None = None,
    uf: str | None = Query(None, pattern=r"^([A-Z]{2}|PENDENTE)$"),
    cidade: str | None = None,
    edicao: int | None = None,
    situacao: Literal["aberta", "historico", "pendente"] | None = None,
    prazo: Literal["em_andamento", "proximo_fim", "encerrado", "validar", "validacao_juridica"] | None = None,
    user: User = Depends(current_user),
) -> Response:
    p = _params(servico=servico, classe=classificacao, uf=uf, cidade=cidade, edicao=edicao, situacao=situacao, prazo=prazo)
    with db.transaction(user.actor) as conn:
        rows = _linhas(conn, p, 20000)
        cont = _contatos(conn, list({r["holder_id"] for r in rows}))
        conn.execute(
            "insert into exports_log (formato, filtros, linhas, criado_por) values (%s, %s, %s, %s)",
            (formato, Jsonb({"tipo": "servicos"} | {k: str(v) for k, v in p.items() if v not in (None, False)}), len(rows), user.actor),
        )
    linhas = []
    for r in rows:
        c = cont.get(r["holder_id"], {})
        linhas.append({
            "servico": ROTULO_SERVICO[r["servico"]], "classificacao": (r["classificacao"] or "").upper(),
            "motivos": " | ".join(r["classificacao_motivos"] or []), "numero_processo": r["numero_processo"],
            "marca": r["marca_nome"] or "", "titular": r["titular"], "tipo_titular": r["tipo_provavel"], "cnpj": r["cnpj"] or "",
            "uf": r["geo_uf"] or "", "municipio": r["geo_municipio"] or "",
            "fonte_localizacao": {"receita": "Receita Federal (CNPJ)", "rpi": "Declarada na RPI", "manual": "Correção manual"}.get(r["geo_fonte"] or "", ""),
            "classes_nice": ", ".join(r["classes_nice"] or []), "rpi": r["rpi_numero"], "data_publicacao": _br(r["data_publicacao"]),
            "despacho": r["despacho_codigo"], "fundamentacao": r["fundamentacao"] or "",
            "opositor": r["opositor_nome"] or ("" if r["servico"] != "manifestacao_oposicao" else "não informado na RPI"),
            "fonte_opositor": r["opositor_fonte"] or "", "situacao_inpi": r["situacao_atual"] or "",
            "medida_ja_apresentada": _MEDIDA[r["medida_status"]], "fonte_medida": r["medida_fonte"] or "",
            "prazo_inicio": _br(r["prazo_inicio"]), "prazo_final_estimado": _br(r["prazo_fim"]),
            "situacao_prazo": _PRAZO[r["prazo_status"]], "validacao_juridica": r["validacao_motivo"] or "",
            "fonte_prazo": r["prazo_fonte"] or "", "whatsapp": c.get("whatsapp", ""), "telefone": c.get("telefone", ""),
            "email": c.get("email", ""), "site": c.get("site", ""), "fontes_contatos": " | ".join(c.get("fontes", [])),
            "etapa_crm": r["pipeline_stage"] or "", "lead_id": r["lead_id"] or "",
        })  # fmt: skip
    nome = f"oportunidades_{servico or 'servicos'}_{datetime.now(UTC):%Y%m%d_%H%M}"
    if formato == "csv":
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=EXPORT_COLS, delimiter=";")
        w.writeheader()
        w.writerows(linhas)
        return Response(("﻿" + buf.getvalue()).encode("utf-8"), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{nome}.csv"'})  # fmt: skip
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Oportunidades"
    ws.append(EXPORT_COLS)
    for cel in ws[1]:
        cel.font = Font(bold=True)
    for linha in linhas:
        ws.append([linha[k] for k in EXPORT_COLS])
    ws.freeze_panes = "A2"
    leia = wb.create_sheet("Leia-me")
    for t in [
        "Oportunidades de serviço do INPI Lead Intelligence: manifestação à oposição e recurso contra indeferimento.",
        "O lead é o TITULAR do pedido que sofreu a oposição ou o indeferimento. O opositor é só informação complementar.",
        "Prazos são estimativas conservadoras (60 dias; 1º dia útil após a publicação na RPI). Confirme no INPI antes do contato.",
        "Abordagem só após validação humana e autorização da equipe. Nada é enviado automaticamente.",
        f"Gerado em {datetime.now(UTC):%d/%m/%Y %H:%M} UTC por {user.actor}.",
    ]:
        leia.append([t])
    out = io.BytesIO()
    wb.save(out)
    return Response(out.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nome}.xlsx"'})  # fmt: skip


# ------------------------------------------------------------------ SILVANE: resumo executivo
def resumo_executivo(conn) -> dict:
    por_uf = conn.execute(
        _BASE
        + """select coalesce(geo_uf, 'PENDENTE') as uf, min(pfila) as pfila,
                    count(*) filter (where servico = 'manifestacao_oposicao' and situacao_processual = 'aberta') as manifestacoes_abertas,
                    count(*) filter (where servico = 'recurso_indeferimento' and situacao_processual = 'aberta') as recursos_abertos,
                    count(*) filter (where servico = 'manifestacao_oposicao' and classificacao = 'quente') as manifestacoes_quentes,
                    count(*) filter (where servico = 'recurso_indeferimento' and classificacao = 'quente') as recursos_quentes,
                    count(*) filter (where situacao_processual = 'aberta' and prazo_status = 'proximo_fim') as prazos_curtos
               from f group by 1 order by 2, 1""",
        _params(),
    ).fetchall()
    destaques = [u for u in por_uf if u["manifestacoes_abertas"] or u["recursos_abertos"]]
    partes = []
    for u in destaques[:4]:
        partes.append(
            f"{u['uf']}: {u['manifestacoes_abertas']} manifestação(ões) à oposição e {u['recursos_abertos']} recurso(s) com prazo aberto"
            f" ({u['manifestacoes_quentes'] + u['recursos_quentes']} quente(s){', ' + str(u['prazos_curtos']) + ' perto do vencimento' if u['prazos_curtos'] else ''})"
        )
    texto = ("Prioridade SC → RS → PR. " + "; ".join(partes) + ".") if partes else "Nenhuma oportunidade de serviço com prazo aberto no momento."
    melhores = [m for m in _linhas(conn, _params(situacao="aberta"), 30) if m["classificacao"] in ("quente", "morno")][:8]
    return {"texto": texto, "destaques": destaques, "melhores": melhores, "gerado_em": datetime.now(UTC)}


@router.get("/servicos/resumo-executivo")
def get_resumo() -> dict:
    with db.get_pool().connection() as conn:
        return resumo_executivo(conn) | {"indicadores": indicadores(conn)}


def por_estado(conn, uf: str) -> dict:
    """Bloco do painel do estado no mapa: as duas categorias comerciais lado a lado."""
    p = _params(uf=uf)
    r = conn.execute(
        _BASE
        + """select count(*) filter (where servico = 'manifestacao_oposicao') as oposicoes_sofridas,
                    count(*) filter (where servico = 'manifestacao_oposicao' and situacao_processual = 'aberta') as manifestacoes_cabiveis,
                    count(*) filter (where servico = 'manifestacao_oposicao' and medida_status = 'protocolada') as manifestacoes_protocoladas,
                    count(*) filter (where servico = 'recurso_indeferimento') as indeferimentos,
                    count(*) filter (where servico = 'recurso_indeferimento' and situacao_processual = 'aberta') as recursos_cabiveis,
                    count(*) filter (where servico = 'recurso_indeferimento' and medida_status = 'protocolada') as recursos_protocolados,
                    count(distinct holder_id) filter (where contatos > 0) as contatos_encontrados,
                    count(distinct holder_id) filter (where classificacao = 'quente') as leads_quentes
               from f""",
        p,
    ).fetchone()
    tops = {s: [x for x in _linhas(conn, p | {"servico": s, "situacao": "aberta"}, 8)] for s in ("manifestacao_oposicao", "recurso_indeferimento")}
    cidades = conn.execute(
        _BASE + """select coalesce(geo_municipio, 'Município não informado') as municipio,
                          count(*) filter (where servico = 'manifestacao_oposicao') as oposicoes,
                          count(*) filter (where servico = 'recurso_indeferimento') as indeferimentos
                     from f group by 1 order by count(*) desc limit 12""",
        p,
    ).fetchall()
    return dict(r) | {"melhores": tops, "municipios": cidades}


def contagem_por_uf(conn, **filtros) -> dict[str, dict]:
    rows = conn.execute(
        _BASE
        + """select coalesce(geo_uf, 'PENDENTE') as uf,
                    count(*) filter (where servico = 'manifestacao_oposicao') as oposicoes_sofridas,
                    count(*) filter (where servico = 'manifestacao_oposicao' and situacao_processual = 'aberta') as manifestacoes_cabiveis,
                    count(*) filter (where servico = 'recurso_indeferimento') as indeferimentos,
                    count(*) filter (where servico = 'recurso_indeferimento' and situacao_processual = 'aberta') as recursos_cabiveis,
                    count(*) filter (where classificacao = 'quente') as servicos_quentes
               from f group by 1""",
        _params(**filtros),
    ).fetchall()
    return {r["uf"]: r for r in rows}
