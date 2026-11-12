"""Agente 03 — INPI Verifier.

    inpi.verify_pending  escolhe processos elegíveis ainda não verificados e enfileira 1 job por processo
    inpi.verify          consulta 1 processo no pePI e atualiza marca, situação, titular e procurador

Regras:
  * Ausência de procurador só vira 'sem_confirmado' quando a seção "Representante
    Legal" existe e está vazia na base do INPI. Página incompleta = 'desconhecido'.
  * Divergências (procurador na RPI x INPI sem procurador, titular diferente) não
    são resolvidas automaticamente: geram tarefa de revisão humana.
  * Toda consulta guarda o HTML original (hash SHA-256), a URL e a data.
"""

import logging
from datetime import UTC, datetime

from psycopg.types.json import Jsonb

from app import db
from app.config import get_settings
from app.inpi.pepi import PepiBlocked, PepiClient
from app.jobs import queue
from app.jobs.registry import JobContext, RetryLater, handler
from app.rpi.normalize import normalize_name
from app.storage import get_storage, sha256_of

log = logging.getLogger("agent.inpi")
_client: PepiClient | None = None

URGENCIA = {"indeferimento": 1, "exigencia": 2, "oposicao": 3, "extincao_prorrogacao": 4}


def _pepi() -> PepiClient:
    global _client
    if _client is None:
        _client = PepiClient()
    return _client


def reset_client():
    global _client
    if _client is not None:
        _client.http.close()
    _client = None


@handler("inpi.verify_pending")
def verify_pending(conn, ctx: JobContext) -> dict:
    s = get_settings()
    rows = conn.execute(
        """
        select p.numero_processo, min(case o.categoria when 'oposicao_apresentada' then 0 when 'indeferimento' then 1
                                       when 'exigencia' then 2 when 'oposicao' then 3 else 4 end) as urg, max(e.numero) as rpi,
               min(prioridade_fila_uf(h.geo_uf)) as pfila
          from processes p
          join opportunities o on o.numero_processo = p.numero_processo and o.status = 'elegivel'
          join rpi_editions e on e.id = o.edition_id
          left join process_holders ph on ph.numero_processo = p.numero_processo
          left join holders h on h.id = ph.holder_id
         where p.procurador_status <> 'com_procurador'
           and (p.verificado_inpi_em is null or p.verificado_inpi_em < now() - make_interval(days => %s))
           and not exists (select 1 from jobs j where j.tipo = 'inpi.verify' and j.status in ('queued','running')
                             and j.payload->>'numero' = p.numero_processo)
         group by p.numero_processo
         order by min(prioridade_fila_uf(h.geo_uf)), rpi desc, urg, p.numero_processo
         limit %s
        """,
        (s.pepi_reverificar_dias, ctx.payload.get("limite", s.pepi_lote_por_execucao)),
    ).fetchall()
    for r in rows:
        queue.enqueue(
            conn,
            "inpi.verify",
            {"numero": r["numero_processo"]},
            dedupe_key=f"inpi.verify:{r['numero_processo']}",
            prioridade=r["pfila"] + 50 + r["urg"],
        )
    return {"enfileirados": len(rows)}


def _pause_queue(minutos: int, motivo: str):
    with db.transaction("agent:inpi.verify") as c:
        c.execute(
            """update jobs set run_after = now() + make_interval(mins => %s)
                where tipo = 'inpi.verify' and status = 'queued'""",
            (minutos,),
        )
        c.execute(
            "insert into review_tasks (entidade, entidade_id, motivo) "
            "select 'sistema', 'pepi', %s where not exists (select 1 from review_tasks "
            "where entidade = 'sistema' and entidade_id = 'pepi' and status = 'aberta')",
            (f"Consulta ao INPI pausada por {minutos} min: {motivo}",),
        )


@handler("inpi.verify")
def verify(conn, ctx: JobContext) -> dict:
    numero = str(ctx.payload["numero"])
    proc = conn.execute("select * from processes where numero_processo = %s for update", (numero,)).fetchone()
    if proc is None:
        return {"ignorado": "processo não existe"}

    try:
        res = _pepi().consultar(numero)
    except PepiBlocked as exc:
        reset_client()
        _pause_queue(120, str(exc))
        raise RetryLater(f"pePI indisponível: {exc}", delay_seconds=120 * 60) from exc

    agora = datetime.now(UTC)
    snap_path = snap_sha = None
    if res.html:
        snap_sha = sha256_of(res.html)
        snap_path = f"inpi/{numero}/{agora:%Y%m%dT%H%M%S}_{snap_sha[:12]}.html"
        get_storage().put_immutable(snap_path, res.html, "text/html")

    status_inpi = res.procurador_status if res.resultado == "ok" else None
    resultado = res.resultado if (res.resultado != "ok" or status_inpi != "desconhecido") else "indisponivel"
    v = conn.execute(
        """insert into inpi_verifications (numero_processo, fonte_url, resultado, titular, marca, situacao,
                                           procurador, procurador_status, snapshot_path, snapshot_sha256, job_id,
                                           titulares, publicacoes, cod_pedido)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
        (
            numero,
            res.fonte_url,
            resultado,
            "; ".join(res.titulares) or None,
            res.marca,
            res.situacao,
            "; ".join(res.procuradores) or None,
            status_inpi,
            snap_path,
            snap_sha,
            ctx.job["id"],
            Jsonb(res.titulares),
            Jsonb(res.publicacoes),
            res.cod_pedido,
        ),
    ).fetchone()
    fonte = f"inpi:{v['id']}"

    if res.resultado == "nao_encontrado":
        conn.execute("update processes set verificado_inpi_em = now() where numero_processo = %s", (numero,))
        return {"numero": numero, "resultado": "nao_encontrado"}

    novo_status, revisao = proc["procurador_status"], None
    if status_inpi == "com_procurador":
        novo_status = "com_procurador"
    elif status_inpi == "sem_confirmado":
        if proc["procurador_status"] == "com_procurador":
            revisao = (
                f"Divergência: a RPI ({proc['procurador_fonte']}) mostrou o procurador "
                f"'{proc['procurador_nome']}', mas a base do INPI não lista representante."
            )
        else:
            novo_status = "sem_confirmado"

    conn.execute(
        """update processes set
             marca_nome = coalesce(%(marca)s, marca_nome),
             situacao_atual = coalesce(%(sit)s, situacao_atual),
             apresentacao = coalesce(apresentacao, %(apres)s),
             natureza = coalesce(natureza, %(nat)s),
             data_deposito = coalesce(data_deposito, %(dep)s),
             data_concessao = coalesce(%(conc)s, data_concessao),
             data_vigencia = coalesce(%(vig)s, data_vigencia),
             procurador_status = %(ps)s,
             procurador_nome = case when %(ps)s = 'com_procurador' and %(pn)s::text is not null
                                    then %(pn)s else procurador_nome end,
             procurador_fonte = case when %(ps)s is distinct from procurador_status
                                       or (%(ps)s = 'com_procurador' and %(pn)s::text is not null)
                                     then %(fonte)s else procurador_fonte end,
             inpi_cod_pedido = %(cod)s,
             verificado_inpi_em = now()
           where numero_processo = %(num)s""",
        {
            "marca": res.marca,
            "sit": res.situacao,
            "apres": res.apresentacao,
            "nat": res.natureza,
            "dep": res.data_deposito,
            "conc": res.data_concessao,
            "vig": res.data_vigencia,
            "ps": novo_status,
            "pn": "; ".join(res.procuradores) or None,
            "fonte": fonte,
            "cod": res.cod_pedido,
            "num": numero,
        },
    )

    if novo_status == "com_procurador":
        conn.execute(
            """update opportunities set status = 'descartada', motivo_descarte = 'procurador identificado no INPI'
                where numero_processo = %s and status = 'elegivel'""",
            (numero,),
        )

    # Titular divergente (possível transferência) -> revisão humana
    atuais = {
        r["nome_normalizado"]
        for r in conn.execute(
            """select h.nome_normalizado from process_holders ph join holders h on h.id = ph.holder_id
            where ph.numero_processo = %s""",
            (numero,),
        ).fetchall()
    }
    inpi_tit = {normalize_name(t) for t in res.titulares}
    if inpi_tit and atuais and inpi_tit != atuais:
        revisao = (revisao + " " if revisao else "") + (
            f"Titular no INPI ({'; '.join(res.titulares)}) difere do titular da RPI. Possível transferência."
        )

    if revisao:
        conn.execute("insert into review_tasks (entidade, entidade_id, motivo) values ('process', %s, %s)", (numero, revisao))
    queue.enqueue(conn, "leads.build", {}, dedupe_key="leads.build", prioridade=80)
    return {
        "numero": numero,
        "resultado": resultado,
        "procurador": novo_status,
        "marca": res.marca,
        "situacao": res.situacao,
        "revisao": bool(revisao),
    }
