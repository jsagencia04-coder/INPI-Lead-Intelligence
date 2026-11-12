"""SILVANE (Diretoria) · operação semanal da RPI.

rpi.semana        disparado ao fim da leitura da RPI: monta os leads e distribui o trabalho por estado,
                  com prioridade real na fila (SC primeiro, depois RS, PR e os demais na ordem configurada).
rpi.semana_check  a cada 10 min: registra os marcos (primeiros leads quentes de SC, conclusão) e emite eventos.
"""

from datetime import UTC, datetime

from psycopg.types.json import Jsonb

from app import semana
from app.agents.leads import build as leads_build
from app.jobs import queue
from app.jobs.registry import JobContext, PermanentError, handler


def _enfileirar(conn, tipo: str, payload: dict, chave: str, prioridade: int) -> bool:
    """Enfileira ou, se já estiver na fila com prioridade menor, adianta. Nunca duplica."""
    ativo = conn.execute(
        "select id, prioridade from jobs where dedupe_key = %s and status in ('queued','running')", (chave,)
    ).fetchone()
    if ativo:
        if ativo["prioridade"] > prioridade:
            conn.execute("update jobs set prioridade = %s where id = %s and status = 'queued'", (prioridade, ativo["id"]))
        return False
    queue.enqueue(conn, tipo, payload, dedupe_key=chave, prioridade=prioridade)
    return True


@handler("rpi.semana")
def rpi_semana(conn, ctx: JobContext) -> dict:
    numero = int(ctx.payload["numero"])
    ed = conn.execute("select * from rpi_editions where numero = %s", (numero,)).fetchone()
    if ed is None or ed["status"] != "parsed":
        raise PermanentError(f"Edição {numero} ainda não foi processada")
    conn.execute(
        """insert into rpi_operacoes (edition_id) values (%s)
           on conflict (edition_id) do update set execucoes = rpi_operacoes.execucoes + 1""",
        (ed["id"],),
    )
    # 1. leads e localização na hora (não espera a agenda de hora em hora)
    montagem = leads_build(conn, ctx)
    # 1b. com a base da Receita ligada, cruza os titulares novos antes da pesquisa (traz CNPJ, UF confirmada e domínio)
    if conn.execute("select 1 from schedules where nome = 'cnpj-receita' and ativo").fetchone():
        _enfileirar(conn, "cnpj.sync", {}, "cnpj.sync:semana", 8)

    # 2. trabalho por estado, na ordem de prioridade
    alvos = conn.execute(
        """select distinct l.holder_id, o.numero_processo, h.geo_uf, prioridade_fila_uf(h.geo_uf) as pfila,
                  p.verificado_inpi_em is not null and p.verificado_inpi_em > now() - interval '30 days' as verificado,
                  exists (select 1 from research_runs r where r.holder_id = l.holder_id and r.agente = 'research.free'
                            and r.iniciado_em > now() - interval '7 days'
                            and (h.geo_fonte is distinct from 'receita' or r.iniciado_em > h.geo_atualizado_em)) as pesquisado
             from opportunities o
             join process_holders ph on ph.numero_processo = o.numero_processo
             join leads l on l.holder_id = ph.holder_id and l.mesclado_em is null and l.status <> 'descartado'
             join holders h on h.id = l.holder_id
             join processes p on p.numero_processo = o.numero_processo
            where o.edition_id = %s and o.status = 'elegivel' and p.procurador_status <> 'com_procurador'
            order by pfila""",
        (ed["id"],),
    ).fetchall()
    por_uf: dict[str, dict] = {}
    for a in alvos:
        uf = a["geo_uf"] or "PENDENTE"
        c = por_uf.setdefault(uf, {"verificacoes": 0, "pesquisas": 0, "prioridade": a["pfila"]})
        if not a["verificado"] and _enfileirar(
            conn, "inpi.verify", {"numero": a["numero_processo"]}, f"inpi.verify:{a['numero_processo']}", a["pfila"]
        ):
            c["verificacoes"] += 1
        if not a["pesquisado"] and _enfileirar(
            conn, "research.free", {"holder_id": a["holder_id"]}, f"research.free:{a['holder_id']}", a["pfila"] + 1
        ):
            c["pesquisas"] += 1
    conn.execute(
        "update rpi_operacoes set priorizada_em = now(), detalhes = detalhes || %s where edition_id = %s",
        (Jsonb({"distribuicao": por_uf, "montagem": montagem}), ed["id"]),
    )
    conn.execute(
        "select office_emit('operacao.priorizada', 'rpi.semana', %s, %s, %s, %s)",
        (ctx.job["id"], f"rpi:{numero}", f"RPI {numero}: trabalho distribuído por estado, começando por SC",
         Jsonb({k: v["verificacoes"] + v["pesquisas"] for k, v in por_uf.items()})),
    )  # fmt: skip
    return {"numero": numero, "leads": montagem, "por_uf": por_uf}


@handler("rpi.semana_check")
def rpi_semana_check(conn, ctx: JobContext) -> dict:
    st = semana.status_operacao(conn)
    if st is None or st["edicao"]["status"] != "parsed":
        return {"ignorado": "nenhuma edição processada"}
    ed = conn.execute("select id from rpi_editions where numero = %s", (st["edicao"]["numero"],)).fetchone()
    op = conn.execute("select * from rpi_operacoes where edition_id = %s", (ed["id"],)).fetchone()
    if op is None:
        return {"ignorado": "operação ainda não iniciada"}
    marcos = {}
    sc = next((u for u in st["ufs"] if u["uf"] == "SC"), None)
    if sc and sc["quentes"] and not op["sc_primeiros_quentes_em"]:
        conn.execute("update rpi_operacoes set sc_primeiros_quentes_em = now() where edition_id = %s", (ed["id"],))
        conn.execute(
            "select office_emit('operacao.sc_pronto', 'rpi.semana', %s, %s, %s, %s)",
            (ctx.job["id"], f"rpi:{st['edicao']['numero']}",
             f"Primeiros {sc['quentes']} lead(s) quentes de SC disponíveis (RPI {st['edicao']['numero']})", Jsonb({"quentes": sc["quentes"]})),
        )  # fmt: skip
        marcos["sc_pronto"] = sc["quentes"]
    terminou = all(e["status"] in ("concluida", "sem_dados") for e in st["etapas"])
    if terminou and not op["concluida_em"]:
        conn.execute("update rpi_operacoes set concluida_em = now() where edition_id = %s", (ed["id"],))
        marcos["concluida"] = True
    conn.execute("update rpi_operacoes set ultima_verificacao_em = %s where edition_id = %s", (datetime.now(UTC), ed["id"]))
    return {"numero": st["edicao"]["numero"], "trabalhando_em": st["trabalhando_em"], "marcos": marcos}
