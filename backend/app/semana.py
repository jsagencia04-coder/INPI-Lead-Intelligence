"""Operação semanal da RPI (V2.3): etapas, prioridade territorial e relatório executivo.

Etapas: RPI detectada → Dados extraídos → SC → RS → PR → Demais estados.
O status de cada etapa é calculado a partir dos fatos (fila de jobs, verificações, pesquisas), nunca simulado:
  sem_dados    nenhum lead da edição nesse grupo de estados
  pendente     há leads, mas o trabalho ainda não começou
  em_execucao  há tarefas na fila ou rodando para esses titulares/processos
  concluida    todos os leads tiveram verificação no INPI tentada e pesquisa de contatos feita
  erro         alguma tarefa desse grupo falhou definitivamente
"""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

GRUPOS = [("SC", ["SC"]), ("RS", ["RS"]), ("PR", ["PR"])]
SP = ZoneInfo("America/Sao_Paulo")


def edicao(conn, numero: int | None) -> dict | None:
    if numero:
        return conn.execute("select * from rpi_editions where numero = %s", (numero,)).fetchone()
    return conn.execute("select * from rpi_editions order by numero desc limit 1").fetchone()


# leads e processos de uma edição, com a UF (confirmada ou estimada) do titular
_BASE = """
  with lp as (
    select distinct l.id as lead_id, l.holder_id, l.temperatura, l.pipeline_stage, l.status,
           o.numero_processo, o.categoria, h.geo_uf, h.geo_status
      from opportunities o
      join process_holders ph on ph.numero_processo = o.numero_processo
      join leads l on l.holder_id = ph.holder_id and l.mesclado_em is null
      join holders h on h.id = l.holder_id
     where o.edition_id = %(ed)s and o.status = 'elegivel'
  )
"""


def por_uf(conn, ed_id: int) -> dict[str, dict]:
    rows = conn.execute(
        _BASE
        + """
        select coalesce(lp.geo_uf, 'PENDENTE') as uf,
               count(distinct lp.lead_id) as leads,
               count(distinct lp.numero_processo) as processos,
               count(distinct lp.numero_processo) filter (where lp.categoria = 'oposicao_apresentada') as oposicoes,
               count(distinct lp.numero_processo) filter (where lp.categoria = 'oposicao') as publicados_oposicao,
               count(distinct lp.numero_processo) filter (where p.verificado_inpi_em is not null) as verificados_inpi,
               count(distinct lp.lead_id) filter (where lp.temperatura = 'quente') as quentes,
               count(distinct lp.lead_id) filter (where lp.temperatura = 'morno') as mornos,
               count(distinct lp.lead_id) filter (where exists (
                    select 1 from contacts c where c.holder_id = lp.holder_id
                       and c.verificacao in ('dominio_ok','verificado_humano'))) as com_contato_validado,
               count(distinct lp.lead_id) filter (where exists (
                    select 1 from research_runs r where r.holder_id = lp.holder_id and r.agente = 'research.free'
                       and r.iniciado_em >= e.processada_em - interval '7 days')) as pesquisados,
               count(distinct lp.lead_id) filter (where exists (
                    select 1 from contacts c where c.holder_id = lp.holder_id and c.verificacao in ('encontrado','formato_ok'))) as pendencias_validacao,
               count(distinct j.id) filter (where j.status in ('queued','running')) as tarefas_ativas,
               count(distinct j.id) filter (where j.status = 'dead') as falhas
          from lp
          join rpi_editions e on e.id = %(ed)s
          join processes p on p.numero_processo = lp.numero_processo
          left join jobs j on (
                 (j.tipo in ('research.free','lead.validate_contacts') and (j.payload->>'holder_id')::bigint = lp.holder_id)
              or (j.tipo = 'inpi.verify' and j.payload->>'numero' = lp.numero_processo))
             and j.criado_em >= e.processada_em - interval '1 minute'
         group by 1""",
        {"ed": ed_id},
    ).fetchall()
    return {r["uf"]: r for r in rows}


def _status(g: dict | None) -> str:
    if not g or not g["leads"]:
        return "sem_dados"
    if g["falhas"]:
        return "erro"
    if g["tarefas_ativas"]:
        return "em_execucao"
    if g["pesquisados"] >= g["leads"] and g["verificados_inpi"] >= g["processos"]:
        return "concluida"
    return "em_execucao" if g["pesquisados"] or g["verificados_inpi"] else "pendente"


def _soma(gs: list[dict]) -> dict | None:
    gs = [g for g in gs if g]
    if not gs:
        return None
    return {k: sum(g[k] for g in gs) for k in gs[0] if k != "uf"}


def status_operacao(conn, numero: int | None = None) -> dict | None:
    ed = edicao(conn, numero)
    if ed is None:
        return None
    op = conn.execute("select * from rpi_operacoes where edition_id = %s", (ed["id"],)).fetchone()
    ufs = por_uf(conn, ed["id"]) if ed["status"] == "parsed" else {}
    etapas = [
        {"chave": "detectada", "nome": "RPI detectada", "status": "concluida", "em": ed["detectada_em"]},
        {"chave": "extraida", "nome": "Dados extraídos",
         "status": {"parsed": "concluida", "error": "erro", "parsing": "em_execucao"}.get(ed["status"], "pendente"),
         "em": ed["processada_em"]},
    ]
    usados: set[str] = set()
    for nome, lista in GRUPOS:
        g = _soma([ufs.get(u) for u in lista])
        usados.update(lista)
        etapas.append({"chave": nome, "nome": nome, "status": _status(g) if ed["status"] == "parsed" else "pendente", "dados": g})
    demais = _soma([v for k, v in ufs.items() if k not in usados and k != "PENDENTE"])
    etapas.append({"chave": "demais", "nome": "Demais estados", "status": _status(demais) if ed["status"] == "parsed" else "pendente",
                   "dados": demais})
    atual = next((e["nome"] for e in etapas[2:] if e["status"] in ("em_execucao", "pendente")), None)
    ordem = {r["uf"]: r["ordem"] for r in conn.execute("select uf, ordem from uf_prioridade")}
    ultima_busca = conn.execute(
        "select max(finalizado_em) as m from jobs where tipo = 'rpi.discover' and status = 'succeeded'"
    ).fetchone()["m"]
    return {
        "edicao": {k: ed[k] for k in ("numero", "data_publicacao", "status", "detectada_em", "coletada_em", "processada_em")},
        "operacao": op,
        "etapas": etapas,
        "trabalhando_em": atual,
        "ufs": sorted(ufs.values(), key=lambda r: ordem.get(r["uf"], 99)),
        "ultima_verificacao_rpi": ultima_busca,
        "atraso": rpi_atrasada(conn),
    }


def rpi_atrasada(conn, agora: datetime | None = None) -> dict | None:
    """A RPI sai às terças. Depois das 14h de terça (horário de Brasília), sem a edição da semana = atraso."""
    agora = (agora or datetime.now(UTC)).astimezone(SP)
    terca = agora.date() - timedelta(days=(agora.isoweekday() - 2) % 7)
    limite = datetime.combine(terca, time(14, 0), tzinfo=SP)
    if agora < limite:
        return None
    if not conn.execute("select 1 from rpi_editions limit 1").fetchone():
        return None  # sistema ainda sem nenhuma edição: não há "atraso" a acusar
    tem = conn.execute(
        "select numero from rpi_editions where data_publicacao >= %s or detectada_em >= %s order by numero desc limit 1",
        (terca, limite - timedelta(hours=9)),
    ).fetchone()
    if tem:
        return None
    return {"desde": limite, "terca": terca, "horas": round((agora - limite).total_seconds() / 3600, 1)}


def relatorio(conn, numero: int | None = None, uf: str = "SC") -> dict | None:
    """Relatório executivo de um estado para a edição (SC é o primeiro da terça-feira)."""
    st = status_operacao(conn, numero)
    if st is None:
        return None
    ed = edicao(conn, numero)
    g = next((r for r in st["ufs"] if r["uf"] == uf), None)
    quentes = conn.execute(
        _BASE
        + """
        select distinct on (l.id) l.id, h.nome_original as titular, h.geo_municipio as municipio, l.score, l.whatsapp,
               l.whatsapp_status, l.categoria_principal, l.temperatura_motivos,
               (select string_agg(distinct p.marca_nome, ', ') from lead_processes x join processes p using (numero_processo)
                 where x.lead_id = l.id) as marcas
          from lp join leads l on l.id = lp.lead_id join holders h on h.id = l.holder_id
         where lp.geo_uf = %(uf)s and lp.temperatura = 'quente'
         order by l.id, l.score desc nulls last""",
        {"ed": ed["id"], "uf": uf},
    ).fetchall()
    quentes.sort(key=lambda r: -(r["score"] or 0))
    pend = []
    if g:
        if g["pendencias_validacao"]:
            pend.append(f"{g['pendencias_validacao']} lead(s) com contatos aguardando validação")
        if g["leads"] - g["pesquisados"] > 0:
            pend.append(f"{g['leads'] - g['pesquisados']} lead(s) ainda sem pesquisa de contatos")
        if g["processos"] - g["verificados_inpi"] > 0:
            pend.append(f"{g['processos'] - g['verificados_inpi']} processo(s) ainda sem verificação no INPI")
        if g["falhas"]:
            pend.append(f"{g['falhas']} tarefa(s) com falha")
    etapa = next((e for e in st["etapas"] if e["chave"] == uf), None)
    return {
        "uf": uf,
        "edicao": st["edicao"],
        "situacao": etapa["status"] if etapa else ("concluida" if g else "sem_dados"),
        "oposicoes": g["oposicoes"] if g else 0,
        "publicados_oposicao": g["publicados_oposicao"] if g else 0,
        "novas_oportunidades": g["leads"] if g else 0,
        "contatos_validados": g["com_contato_validado"] if g else 0,
        "leads_quentes": quentes[:20],
        "total_quentes": len(quentes),
        "pendencias": pend,
        "gerado_em": datetime.now(UTC),
    }
