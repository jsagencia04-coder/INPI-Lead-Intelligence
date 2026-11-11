"""Vínculo titular -> CNPJ usando os dados abertos da Receita (parte do Agente 04/05).

    cnpj.sync  baixa (ou reaproveita do cache) os zips do mês, varre só os nomes
               dos titulares pendentes e grava empresas/estabelecimentos encontrados;
               depois tenta o vínculo de cada titular.

Critério de vínculo (regra 5, não confundir homônimos):
  * nome normalizado idêntico (ignorando acentos, pontuação e prefixo de MEI)
  * mesma UF da RPI, quando a RPI informa UF
  * exatamente 1 candidato matriz ativo -> 'encontrado' (confiança 0,9)
  * mais de 1 -> 'ambiguo' + tarefa de revisão humana (nada é escolhido sozinho)
  * nenhum   -> 'nao_encontrado'
Telefone e e-mail cadastrais viram contatos com fonte 'receita', ainda não verificados.
"""

from psycopg.types.json import Jsonb

from app.cnpj.receita import ensure_files, nome_chave, scan_empresas, scan_estabelecimentos
from app.config import get_settings
from app.jobs import queue
from app.jobs.registry import JobContext, handler
from app.validation import normalize_contact

ATIVA = "02"


def pending_holders(conn, mes: str) -> list[dict]:
    return conn.execute(
        """select distinct h.* from holders h
             join process_holders ph on ph.holder_id = h.id
             join opportunities o on o.numero_processo = ph.numero_processo and o.status = 'elegivel'
            where h.cnpj is null and coalesce(h.pais, 'BR') = 'BR'
              and h.cnpj_status in ('pendente', 'nao_encontrado')
              and h.cnpj_mes_verificado is distinct from %s""",
        (mes,),
    ).fetchall()


def _upsert(conn, empresas: list[dict], estabs: list[dict], mes: str):
    with conn.cursor() as cur:
        cur.executemany(
            """insert into cnpj_empresas (cnpj_basico, razao_social, nome_normalizado, natureza_juridica,
                                          capital_social, porte, mes_referencia)
               values (%(cnpj_basico)s, %(razao_social)s, %(nome_normalizado)s, %(natureza_juridica)s,
                       %(capital_social)s, %(porte)s, %(mes)s)
               on conflict (cnpj_basico) do update set razao_social = excluded.razao_social,
                 nome_normalizado = excluded.nome_normalizado, natureza_juridica = excluded.natureza_juridica,
                 capital_social = excluded.capital_social, porte = excluded.porte,
                 mes_referencia = excluded.mes_referencia, updated_at = now()""",
            [e | {"mes": mes} for e in empresas],
        )
        cols = [
            "cnpj",
            "cnpj_basico",
            "matriz",
            "nome_fantasia",
            "situacao_cadastral",
            "data_situacao",
            "data_inicio",
            "cnae_principal",
            "logradouro",
            "numero",
            "bairro",
            "cep",
            "uf",
            "municipio_codigo",
            "telefone1",
            "telefone2",
            "email",
        ]
        cur.executemany(
            f"""insert into cnpj_estabelecimentos ({", ".join(cols)}, mes_referencia)
                values ({", ".join(f"%({c})s" for c in cols)}, %(mes)s)
                on conflict (cnpj) do update set {", ".join(f"{c} = excluded.{c}" for c in cols[2:])},
                  mes_referencia = excluded.mes_referencia, updated_at = now()""",
            [e | {"mes": mes} for e in estabs],
        )


def match_holder(conn, h: dict, mes: str, fonte_url: str) -> str:
    chave = nome_chave(h["nome_original"])
    cands = conn.execute(
        """select e.*, emp.razao_social, emp.natureza_juridica, emp.porte from cnpj_estabelecimentos e
             join cnpj_empresas emp on emp.cnpj_basico = e.cnpj_basico
            where emp.nome_normalizado = %s and e.matriz
              and (%s::text is null or e.uf = %s)""",
        (chave, h["uf"], h["uf"]),
    ).fetchall()
    ativos = [c for c in cands if c["situacao_cadastral"] == ATIVA]
    escolhidos = ativos or cands
    resumo = [
        {
            "cnpj": c["cnpj"],
            "razao_social": c["razao_social"],
            "uf": c["uf"],
            "situacao": c["situacao_cadastral"],
            "fantasia": c["nome_fantasia"],
        }
        for c in cands
    ]

    if len(escolhidos) == 1:
        c = escolhidos[0]
        conf = 0.9 if c["situacao_cadastral"] == ATIVA else 0.7
        conn.execute(
            """update holders set cnpj = %s, cnpj_confianca = %s, cnpj_fonte = %s, cnpj_status = 'encontrado',
                      cnpj_mes_verificado = %s, cnpj_candidatos = %s, tipo_provavel = 'PJ' where id = %s""",
            (c["cnpj"], conf, f"Receita Federal, dados abertos CNPJ {mes}", mes, Jsonb(resumo), h["id"]),
        )
        trecho = (
            f"CNPJ {c['cnpj']} | {c['razao_social']} | fantasia: {c['nome_fantasia'] or '-'} | "
            f"UF {c['uf']} | situação {c['situacao_cadastral']} | tel {c['telefone1'] or '-'} | "
            f"e-mail {c['email'] or '-'}"
        )
        ev = conn.execute(
            """insert into evidences (url, titulo, trecho, fonte_tipo) values (%s, %s, %s, 'receita')
               returning id""",
            (fonte_url, f"Cadastro CNPJ {c['cnpj']} (Receita, {mes})", trecho),
        ).fetchone()
        for tipo, valor in (("telefone", c["telefone1"]), ("telefone", c["telefone2"]), ("email", c["email"])):
            if not valor:
                continue
            norm = normalize_contact(tipo, valor)
            if not norm:
                continue
            conn.execute(
                """insert into contacts (holder_id, tipo, valor, valor_normalizado, evidence_id, fonte_tipo,
                                         confianca, observacao)
                   values (%s, %s, %s, %s, %s, 'receita', 0.5, %s)
                   on conflict (holder_id, tipo, valor_normalizado) do update set ultima_vez_visto = now()""",
                (
                    h["id"],
                    tipo,
                    valor,
                    norm,
                    ev["id"],
                    "Dado cadastral da Receita: pode ser do contador ou estar desatualizado.",
                ),
            )
        return "encontrado"

    status = "ambiguo" if len(escolhidos) > 1 else "nao_encontrado"
    conn.execute(
        """update holders set cnpj_status = %s, cnpj_mes_verificado = %s, cnpj_candidatos = %s where id = %s""",
        (status, mes, Jsonb(resumo), h["id"]),
    )
    if status == "ambiguo":
        conn.execute(
            "insert into review_tasks (entidade, entidade_id, motivo) values ('holder', %s, %s)",
            (
                str(h["id"]),
                f"Homônimos: {len(escolhidos)} empresas com o nome '{h['nome_original']}'"
                f"{' na UF ' + h['uf'] if h['uf'] else ''}. Escolha o CNPJ correto ou descarte.",
            ),
        )
    return status


@handler("cnpj.sync")
def sync(conn, ctx: JobContext) -> dict:
    mes, empresas_zip, estab_zip = ensure_files(ctx.payload.get("mes"))
    holders = pending_holders(conn, mes)
    if not holders:
        return {"mes": mes, "titulares_pendentes": 0}
    chaves = {nome_chave(h["nome_original"]) for h in holders}
    empresas = scan_empresas(empresas_zip, chaves)
    estabs = scan_estabelecimentos(estab_zip, {e["cnpj_basico"] for e in empresas})
    _upsert(conn, empresas, estabs, mes)

    from app.config import get_settings

    fonte = f"{get_settings().cnpj_webdav_url.rstrip('/')}/{mes}/"
    contagem: dict[str, int] = {}
    for h in holders:
        st = match_holder(conn, h, mes, fonte)
        contagem[st] = contagem.get(st, 0) + 1
    queue.enqueue(conn, "leads.build", {}, dedupe_key="leads.build", prioridade=80)
    return {
        "mes": mes,
        "titulares_pendentes": len(holders),
        "empresas_candidatas": len(empresas),
        "estabelecimentos": len(estabs),
        "resultado": contagem,
    }


@handler("cnpj.recontatos")
def cnpj_recontatos(conn, ctx: JobContext) -> dict:
    """Reaproveita o que já está na base local da Receita: grava telefones/e-mails que ficaram de fora.

    Corrige os celulares cadastrados no formato antigo (DDD + 8 dígitos), antes descartados como inválidos.
    Não baixa nada. Idempotente: contato já existente não é duplicado.
    """
    rows = conn.execute(
        """select h.id as holder_id, e.cnpj, e.telefone1, e.telefone2, e.email, e.mes_referencia,
                  (select c.evidence_id from contacts c where c.holder_id = h.id and c.fonte_tipo = 'receita' limit 1) as ev
             from holders h join cnpj_estabelecimentos e on e.cnpj = h.cnpj
            where h.cnpj_status in ('encontrado', 'manual')"""
    ).fetchall()
    novos = celulares = 0
    for r in rows:
        ev = r["ev"]
        for tipo, valor in (("telefone", r["telefone1"]), ("telefone", r["telefone2"]), ("email", r["email"])):
            norm = normalize_contact(tipo, valor) if valor else None
            if not norm:
                continue
            if conn.execute(
                "select 1 from contacts where holder_id = %s and tipo = %s and valor_normalizado = %s", (r["holder_id"], tipo, norm)
            ).fetchone():
                continue
            if ev is None:
                ev = conn.execute(
                    """insert into evidences (url, titulo, trecho, fonte_tipo) values (%s, %s, %s, 'receita') returning id""",
                    (
                        get_settings().cnpj_webdav_url,
                        f"Cadastro CNPJ {r['cnpj']} (Receita, {r['mes_referencia']})",
                        f"tel {r['telefone1'] or '-'} / {r['telefone2'] or '-'} | e-mail {r['email'] or '-'}",
                    ),
                ).fetchone()["id"]
            conn.execute(
                """insert into contacts (holder_id, tipo, valor, valor_normalizado, evidence_id, fonte_tipo, confianca, observacao)
                   values (%s, %s, %s, %s, %s, 'receita', 0.5, %s) on conflict (holder_id, tipo, valor_normalizado) do nothing""",
                (r["holder_id"], tipo, valor, norm, ev, "Dado cadastral da Receita: pode ser do contador ou estar desatualizado."),
            )
            novos += 1
            celulares += 1 if tipo == "telefone" and norm[5:6] == "9" and len(norm) == 14 else 0
    if novos:
        queue.enqueue(conn, "leads.build", {}, dedupe_key="leads.build", prioridade=80)
    return {"titulares_conferidos": len(rows), "contatos_novos": novos, "celulares_novos": celulares}
