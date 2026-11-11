"""Agente 04 — Web Researcher (Claude + busca web).

    research.batch   escolhe os leads que valem a pesquisa (prioridade, procurador
                     confirmado, dentro do orçamento) e enfileira research.holder
    research.holder  pesquisa 1 titular e grava contatos com evidência

Proteções contra informação inventada (regras 2, 3 e 4):
  * Claude só pode registrar contatos com URL de origem e trecho literal da página.
  * O valor do contato precisa aparecer no trecho citado; senão é descartado.
  * Tudo entra como 'encontrado'. A validação (Agente 05) confere a página de novo.
LGPD: o prompt proíbe dados pessoais (CPF, endereço residencial, família, perfis
pessoais) e restringe a busca a dados comerciais públicos.
"""

import json
import logging

from psycopg.types.json import Jsonb

from app import db, llm
from app.config import get_settings
from app.jobs import queue
from app.jobs.registry import JobContext, handler
from app.validation import normalize_contact, value_in_text

log = logging.getLogger("agent.research")

TIPOS = ["site", "email", "telefone", "whatsapp", "instagram", "linkedin", "facebook", "tiktok", "youtube"]

SYSTEM = """Você é um pesquisador comercial que encontra dados PÚBLICOS de contato COMERCIAL de \
titulares de marcas registradas no INPI (Brasil).

Regras obrigatórias:
1. Nunca invente nada. Só registre um dado se ele estiver escrito numa página que você encontrou.
2. Para cada contato, informe a URL exata da página e copie o trecho LITERAL (até 200 caracteres) \
em que o valor aparece. O valor precisa estar dentro do trecho.
3. Confirme o vínculo com o titular: a página deve mencionar o titular, a marca, o CNPJ ou dados \
que coincidam (cidade/UF, ramo). Explique o vínculo em uma frase. Na dúvida, não registre, ou registre \
com confiança baixa e explique.
4. Cuidado com homônimos: empresas ou pessoas com nome parecido em outra cidade ou ramo NÃO são o titular.
5. Proibido coletar: CPF, RG, endereço residencial, dados de familiares, perfis pessoais sem relação \
com a atividade comercial, dados de saúde ou qualquer dado sensível.
6. Prefira: site oficial, página de contato, perfis comerciais da marca, diretórios empresariais.
7. PRIORIDADE MÁXIMA: o WhatsApp comercial da empresa (o primeiro contato será por WhatsApp). Procure \
links wa.me / api.whatsapp.com, botões "Fale pelo WhatsApp" e números indicados como WhatsApp no site oficial, \
na página de contato e em perfis comerciais. Registre como tipo "whatsapp" SOMENTE se a página indicar que o \
número é WhatsApp, e inclua essa indicação no trecho. Celular sem indicação de WhatsApp é tipo "telefone".
8. Ao terminar, chame a ferramenta registrar_resultado exatamente uma vez. Se nada for encontrado, \
chame-a com a lista de contatos vazia."""

RESULT_TOOL = {
    "name": "registrar_resultado",
    "description": "Registra o resultado final da pesquisa. Chamar uma única vez, ao final.",
    "input_schema": {
        "type": "object",
        "properties": {
            "titular_identificado": {
                "type": "boolean",
                "description": "Encontrou presença online que é claramente do titular?",
            },
            "contatos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "tipo": {"type": "string", "enum": TIPOS},
                        "valor": {"type": "string"},
                        "url_fonte": {"type": "string"},
                        "trecho": {"type": "string", "description": "Trecho literal da página contendo o valor"},
                        "vinculo": {"type": "string", "description": "Por que este dado é do titular"},
                        "confianca": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["tipo", "valor", "url_fonte", "trecho", "vinculo", "confianca"],
                },
            },
            "homonimos_encontrados": {"type": "boolean"},
            "segmento_observado": {"type": "string"},
            "observacoes": {"type": "string"},
        },
        "required": ["titular_identificado", "contatos", "homonimos_encontrados", "observacoes"],
    },
}


def holder_context(conn, holder_id: int) -> dict:
    h = conn.execute("select * from holders where id = %s", (holder_id,)).fetchone()
    procs = conn.execute(
        """select p.numero_processo, p.marca_nome, p.classes_nice, p.nice_detalhes, p.situacao_atual
             from processes p join process_holders ph on ph.numero_processo = p.numero_processo
            where ph.holder_id = %s order by p.numero_processo""",
        (holder_id,),
    ).fetchall()
    est = None
    if h["cnpj"]:
        est = conn.execute(
            """select e.nome_fantasia, e.cnae_principal, e.uf, e.municipio_codigo, e.situacao_cadastral,
                      emp.razao_social from cnpj_estabelecimentos e
                 join cnpj_empresas emp on emp.cnpj_basico = e.cnpj_basico where e.cnpj = %s""",
            (h["cnpj"],),
        ).fetchone()
    return {
        "titular": h["nome_original"],
        "uf": h["uf"],
        "pais": h["pais"],
        "tipo_provavel": h["tipo_provavel"],
        "cnpj": h["cnpj"],
        "cadastro_receita": est,
        "marcas": [
            {
                "processo": p["numero_processo"],
                "marca": p["marca_nome"],
                "classes_nice": p["classes_nice"],
                "especificacao": "; ".join((d.get("especificacao") or "")[:150] for d in p["nice_detalhes"])[:300],
            }
            for p in procs
        ],
    }


def _prompt(ctx: dict) -> str:
    return (
        "Encontre os contatos comerciais públicos deste titular de marca. Dados oficiais (RPI/INPI e "
        "Receita) abaixo, use-os para confirmar o vínculo e evitar homônimos:\n\n"
        + json.dumps(ctx, ensure_ascii=False, default=str, indent=1)
    )


@handler("research.holder")
def research_holder(conn, ctx: JobContext) -> dict:
    s = get_settings()
    holder_id = int(ctx.payload["holder_id"])
    if not s.anthropic_api_key:
        return {"ignorado": "ANTHROPIC_API_KEY não configurada"}
    try:
        llm.ensure_budget(conn, estimativa=0.15)
    except llm.BudgetExceeded as exc:
        return {"ignorado": str(exc)}

    contexto = holder_context(conn, holder_id)
    run = conn.execute(
        """insert into research_runs (holder_id, agente, modelo, job_id) values (%s, 'research.holder', %s, %s)
           returning id""",
        (holder_id, s.modelo_pesquisa, ctx.job["id"]),
    ).fetchone()
    tools = [
        {
            "type": s.web_search_tool,
            "name": "web_search",
            "max_uses": s.pesquisa_max_buscas,
            "user_location": {"type": "approximate", "country": "BR", "timezone": "America/Sao_Paulo"},
        },
        RESULT_TOOL,
    ]
    messages = [{"role": "user", "content": _prompt(contexto)}]
    res = llm.call(model=s.modelo_pesquisa, system=SYSTEM, messages=messages, tools=tools, max_tokens=3000)
    resultado = next(
        (b["input"] for b in res.content if b.get("type") == "tool_use" and b.get("name") == "registrar_resultado"),
        None,
    )
    if resultado is None:  # pede o registro explicitamente, sem nova busca
        messages += [
            {"role": "assistant", "content": res.content},
            {"role": "user", "content": "Registre agora o resultado com a ferramenta registrar_resultado."},
        ]
        extra = llm.call(
            model=s.modelo_pesquisa,
            system=SYSTEM,
            messages=messages,
            tools=[RESULT_TOOL],
            tool_choice={"type": "tool", "name": "registrar_resultado"},
            max_tokens=2000,
        )
        for k in ("tokens_in", "tokens_out", "buscas", "custo_usd"):
            setattr(res, k, getattr(res, k) + getattr(extra, k))
        resultado = next((b["input"] for b in extra.content if b.get("type") == "tool_use"), None) or {}

    # custo registrado fora da transação do job: não se perde se algo falhar depois
    with db.transaction(ctx.actor) as c2:
        llm.record(c2, res, proposito="research", modelo=s.modelo_pesquisa, job_id=None, holder_id=holder_id)

    aceitos, rejeitados = 0, []
    for item in resultado.get("contatos", []):
        tipo, valor = item.get("tipo"), (item.get("valor") or "").strip()
        url, trecho = (item.get("url_fonte") or "").strip(), (item.get("trecho") or "").strip()
        norm = normalize_contact(tipo, valor) if tipo in TIPOS else None
        motivo = None
        if not norm:
            motivo = "formato inválido"
        elif not url.startswith("http") or not trecho:
            motivo = "sem URL ou trecho de origem"
        elif tipo in ("email", "telefone", "whatsapp") and not value_in_text(tipo, norm, trecho):
            motivo = "valor não aparece no trecho citado"
        if motivo:
            rejeitados.append({"tipo": tipo, "valor": valor, "motivo": motivo})
            continue
        ev = conn.execute(
            "insert into evidences (research_run_id, url, trecho, fonte_tipo) values (%s, %s, %s, 'web') returning id",
            (run["id"], url, trecho[:1000]),
        ).fetchone()
        conn.execute(
            """insert into contacts (holder_id, tipo, valor, valor_normalizado, evidence_id, fonte_tipo, confianca,
                                     observacao)
               values (%s, %s, %s, %s, %s, 'web', %s, %s)
               on conflict (holder_id, tipo, valor_normalizado) do update set ultima_vez_visto = now()""",
            (
                holder_id,
                tipo,
                valor,
                norm,
                ev["id"],
                min(max(float(item.get("confianca") or 0), 0), 1),
                (item.get("vinculo") or "")[:500],
            ),
        )
        aceitos += 1

    status = "needs_review" if resultado.get("homonimos_encontrados") else "succeeded"
    conn.execute(
        """update research_runs set status = %s, consultas = %s, tokens_in = %s, tokens_out = %s, buscas_web = %s,
                  custo_usd = %s, finalizado_em = now(), erro = %s where id = %s""",
        (
            status,
            Jsonb(res.consultas),
            res.tokens_in,
            res.tokens_out,
            res.buscas,
            res.custo_usd,
            json.dumps(
                {
                    "rejeitados": rejeitados,
                    "observacoes": resultado.get("observacoes"),
                    "segmento_observado": resultado.get("segmento_observado"),
                },
                ensure_ascii=False,
            ),
            run["id"],
        ),
    )
    conn.execute("update leads set pesquisado_em = now() where holder_id = %s", (holder_id,))
    if resultado.get("homonimos_encontrados"):
        conn.execute(
            "insert into review_tasks (entidade, entidade_id, motivo) values ('holder', %s, %s)",
            (str(holder_id), "Pesquisa web encontrou homônimos. Confira os contatos antes de usar."),
        )
    queue.enqueue(
        conn,
        "lead.validate_contacts",
        {"holder_id": holder_id},
        dedupe_key=f"lead.validate_contacts:{holder_id}",
        prioridade=70,
    )
    return {
        "holder_id": holder_id,
        "aceitos": aceitos,
        "rejeitados": len(rejeitados),
        "buscas": res.buscas,
        "custo_usd": round(res.custo_usd, 4),
    }


@handler("research.batch")
def research_batch(conn, ctx: JobContext) -> dict:
    s = get_settings()
    if not s.anthropic_api_key:
        return {"ignorado": "ANTHROPIC_API_KEY não configurada"}
    gasto = llm.week_spend(conn)
    if gasto >= s.ia_orcamento_semanal_usd:
        return {"ignorado": f"orçamento semanal atingido (US$ {gasto:.2f})"}
    rows = conn.execute(
        """select l.holder_id from leads l
            where l.status in ('novo', 'qualificado', 'sem_contato') and l.mesclado_em is null
              and l.prioridade in ('alta', 'media') and l.procurador_confirmado
              and (l.pesquisado_em is null or l.pesquisado_em < now() - make_interval(days => %s))
              and not exists (select 1 from jobs j where j.tipo = 'research.holder'
                                and j.status in ('queued', 'running')
                                and (j.payload->>'holder_id')::bigint = l.holder_id)
            order by (l.whatsapp_status in ('confirmado', 'validado')) nulls first,
                     case l.prioridade when 'alta' then 1 else 2 end, l.score desc nulls last
            limit %s""",
        (s.pesquisa_refazer_dias, s.pesquisa_lote_por_execucao),
    ).fetchall()
    for r in rows:
        queue.enqueue(
            conn,
            "research.holder",
            {"holder_id": r["holder_id"]},
            dedupe_key=f"research.holder:{r['holder_id']}",
            prioridade=90,
        )
    return {"enfileirados": len(rows), "gasto_semana_usd": round(gasto, 2)}
