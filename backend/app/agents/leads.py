"""Agentes 05 (Lead Validator) e 06 (Sales Intelligence).

    leads.build              monta/atualiza 1 lead por titular, deduplica por CNPJ, calcula score e prioridade
    lead.validate_contacts   valida os contatos de um titular (formato, página, MX)
    sales.summarize_batch    gera resumo e sugestão de abordagem (Claude Haiku ou modelo fixo)
    reports.weekly           guarda o relatório da última edição processada

Nada aqui envia mensagens: a prospecção só é registrada por uma pessoa (regra 8).
"""

import hashlib
import json
from datetime import date, timedelta

from psycopg.types.json import Jsonb

from app import db, llm
from app.config import get_settings
from app.jobs import queue
from app.jobs.registry import JobContext, handler
from app.validation import check_contact, host_of
from app.whatsapp import CANDIDATO_OBS, best_whatsapp, derive_candidates, evidencia_indica_whatsapp

# Oposição apresentada (categoria A) é a oportunidade principal; pedido publicado para oposição é a categoria B.
CAT_PESO = {"oposicao_apresentada": 45, "indeferimento": 40, "exigencia": 35, "extincao_prorrogacao": 30, "oposicao": 20}
CAT_ORDEM = ["oposicao_apresentada", "indeferimento", "exigencia", "extincao_prorrogacao", "oposicao"]
# LPI: prazos de 60 dias (estimativa; confirmar no INPI)
PRAZO_DIAS = {"oposicao_apresentada": 60, "indeferimento": 60, "exigencia": 60, "oposicao": 60}
# Peso comercial por UF, pela ordem configurada em uf_prioridade (SC, RS, PR...)
UF_PESO = {1: 15, 2: 10, 3: 8}
STATUS_HUMANOS = ("aprovado", "contatado", "convertido")

# Setores por classe de Nice (agrupamento comercial simplificado)
NICE_SETOR = {
    **dict.fromkeys(["01", "02", "04"], "Química e insumos industriais"),
    "03": "Cosméticos, higiene e limpeza",
    "05": "Farmacêutico e veterinário",
    **dict.fromkeys(
        ["06", "07", "08", "12", "17", "19", "20", "22", "23", "24", "26", "27", "28", "34"],
        "Indústria e bens de consumo",
    ),
    "09": "Tecnologia e eletrônicos",
    "10": "Saúde (equipamentos)",
    "11": "Equipamentos e utilidades",
    "13": "Indústria e bens de consumo",
    "14": "Joias e acessórios",
    "15": "Instrumentos musicais",
    "16": "Papelaria e gráfica",
    "18": "Couro, bolsas e acessórios",
    "21": "Utilidades domésticas",
    "25": "Moda e vestuário",
    **dict.fromkeys(["29", "30", "31", "32", "33"], "Alimentos e bebidas"),
    "35": "Comércio, varejo e serviços empresariais",
    "36": "Finanças, seguros e imóveis",
    "37": "Construção e manutenção",
    "38": "Telecomunicações",
    "39": "Transporte e logística",
    "40": "Tratamento de materiais",
    "41": "Educação, cultura e entretenimento",
    "42": "Tecnologia e ciência (serviços)",
    "43": "Alimentação e hospedagem",
    "44": "Saúde, estética e bem-estar",
    "45": "Serviços jurídicos, pessoais e segurança",
}
CNAE_SECAO = [  # (início da divisão, fim, setor) — seções da CNAE 2.0
    (1, 3, "Agropecuária"),
    (5, 9, "Indústria extrativa"),
    (10, 33, "Indústria"),
    (35, 39, "Utilidades"),
    (41, 43, "Construção"),
    (45, 47, "Comércio e varejo"),
    (49, 53, "Transporte e logística"),
    (55, 56, "Alimentação e hospedagem"),
    (58, 63, "Tecnologia, mídia e comunicação"),
    (64, 66, "Finanças e seguros"),
    (68, 68, "Imóveis"),
    (69, 75, "Serviços profissionais"),
    (77, 82, "Serviços administrativos"),
    (84, 84, "Administração pública"),
    (85, 85, "Educação"),
    (86, 88, "Saúde e assistência"),
    (90, 93, "Cultura, esporte e lazer"),
    (94, 96, "Outros serviços"),
]


def setor(cnae: str | None, classes: list[str]) -> str | None:
    if cnae and cnae[:2].isdigit():
        d = int(cnae[:2])
        for ini, fim, nome in CNAE_SECAO:
            if ini <= d <= fim:
                return nome
    for c in classes:
        if c.zfill(2) in NICE_SETOR:
            return NICE_SETOR[c.zfill(2)]
    return None


def holder_hash(holder: dict) -> str:
    return hashlib.sha256(holder["holder_key"].encode()).hexdigest()


def compute_score(
    *,
    categoria: str | None,
    dias_restantes: int | None,
    n_proc: int,
    contatos_validados: int,
    contatos_total: int,
    tipo: str,
    procurador_confirmado: bool,
    cnpj_status: str,
    whatsapp_status: str | None = None,
    uf_ordem: int | None = None,
    dias_publicacao: int | None = None,
    abordado: bool = False,
    geo_status: str | None = None,
) -> tuple[float, dict]:
    det = {"categoria": CAT_PESO.get(categoria or "", 0)}
    if dias_restantes is not None:
        det["urgencia"] = 20 if dias_restantes <= 15 else 10 if dias_restantes <= 30 else 0
        if dias_restantes < 0:
            det["urgencia"] = -15  # prazo estimado vencido
    det["processos"] = min(5 * (n_proc - 1), 15)
    det["contatos"] = 20 if contatos_validados else 8 if contatos_total else 0
    # WhatsApp é o canal do primeiro contato: pesa forte
    det["whatsapp"] = 25 if whatsapp_status in ("confirmado", "validado") else 8 if whatsapp_status == "candidato" else 0
    det["pessoa_juridica"] = 5 if tipo == "PJ" else 0
    det["procurador_confirmado"] = 10 if procurador_confirmado else -10
    det["cnpj_ambiguo"] = -10 if cnpj_status == "ambiguo" else 0
    # V2.3: território, recência, abordagem anterior e confiabilidade da localização
    det["estado"] = UF_PESO.get(uf_ordem or 0, 0)
    if dias_publicacao is not None:
        det["recencia"] = 10 if dias_publicacao <= 7 else 5 if dias_publicacao <= 30 else 0
    det["sem_abordagem"] = 0 if abordado else 5
    det["localizacao"] = 5 if geo_status == "confirmada" else 0 if geo_status == "estimada" else -5
    return float(sum(det.values())), det


ROTULO_CAT = {
    "oposicao_apresentada": "oposição apresentada por terceiro",
    "oposicao": "pedido publicado para oposição",
    "indeferimento": "indeferimento",
    "exigencia": "exigência",
    "extincao_prorrogacao": "extinção por falta de prorrogação",
}


def temperatura(
    *, categoria: str | None, dias_publicacao: int | None, contato_validado: bool, contatos_total: int,
    whatsapp_status: str | None, geo_status: str, cnpj_status: str, abordado: bool, procurador_confirmado: bool,
    uf: str | None,
) -> tuple[str, list[str]]:
    """Quente / morno / em pesquisa, com os motivos. Oposição sozinha NÃO torna o lead validado."""
    motivos: list[str] = []
    relevante = categoria == "oposicao_apresentada" or (dias_publicacao is not None and dias_publicacao <= 30)
    motivos.append(f"Despacho: {ROTULO_CAT.get(categoria or '', categoria or '—')}")
    if dias_publicacao is not None:
        motivos.append(f"Publicado há {dias_publicacao} dia(s)")
    motivos.append(
        f"Localização {geo_status}" + (f" ({uf})" if uf else "") if geo_status != "pendente" else "Localização pendente"
    )
    if contato_validado:
        motivos.append("Contato comercial validado")
    elif whatsapp_status == "candidato":
        motivos.append("WhatsApp ainda candidato (sem prova)")
    elif contatos_total:
        motivos.append("Contatos encontrados, ainda sem validação")
    else:
        motivos.append("Nenhum contato encontrado")
    if cnpj_status == "ambiguo":
        motivos.append("CNPJ ambíguo (homônimos)")
    motivos.append("Ausência de procurador confirmada no INPI" if procurador_confirmado else "Procurador ausente só na RPI")
    if abordado:
        motivos.append("Já houve abordagem")

    if contatos_total == 0 or geo_status == "pendente" or (cnpj_status == "ambiguo" and not contato_validado):
        return "em_pesquisa", motivos
    if relevante and contato_validado and not abordado:
        return "quente", motivos
    return "morno", motivos


def prioridade(score: float) -> str:
    return "alta" if score >= 60 else "media" if score >= 40 else "baixa"


@handler("leads.build")
def build(conn, ctx: JobContext) -> dict:
    hoje = date.today()
    conn.execute("select geo_atualizar()")  # localização: Receita (confirmada) > RPI (estimada) > pendente
    ordem_uf = {r["uf"]: r["ordem"] for r in conn.execute("select uf, ordem from uf_prioridade where ativo")}
    supr = {r["valor_hash"] for r in conn.execute("select valor_hash from suppression_list where tipo = 'titular'")}

    # Titulares com oportunidade elegível
    base = conn.execute(
        """select h.*, o.numero_processo, o.categoria, e.data_publicacao, p.procurador_status, p.classes_nice
             from holders h
             join process_holders ph on ph.holder_id = h.id
             join opportunities o on o.numero_processo = ph.numero_processo and o.status = 'elegivel'
             join rpi_editions e on e.id = o.edition_id
             join processes p on p.numero_processo = o.numero_processo
            where not p.descartado"""
    ).fetchall()
    por_holder: dict[int, dict] = {}
    for r in base:
        g = por_holder.setdefault(r["id"], {"holder": r, "procs": {}, "cats": [], "pubs": [], "conf": [], "classes": []})
        g["procs"][r["numero_processo"]] = True
        g["cats"].append(r["categoria"])
        if r["categoria"] in PRAZO_DIAS and r["data_publicacao"]:
            g["pubs"].append(r["data_publicacao"] + timedelta(days=PRAZO_DIAS[r["categoria"]]))
        g["conf"].append(r["procurador_status"] == "sem_confirmado")
        if r["data_publicacao"]:
            g.setdefault("datas", []).append(r["data_publicacao"])
        g["classes"] += r["classes_nice"] or []

    # Deduplicação: titulares diferentes com o mesmo CNPJ viram um lead só (o de menor id)
    principal_por_cnpj: dict[str, int] = {}
    for hid, g in sorted(por_holder.items()):
        cnpj = g["holder"]["cnpj"]
        if cnpj:
            principal_por_cnpj.setdefault(cnpj, hid)

    criados = atualizados = mesclados = 0
    ativos: set[int] = set()
    for hid, g in sorted(por_holder.items()):
        h = g["holder"]
        cnpj = h["cnpj"]
        principal = principal_por_cnpj.get(cnpj, hid) if cnpj else hid
        lead = conn.execute("select * from leads where holder_id = %s", (hid,)).fetchone()
        if lead is None:
            lead = conn.execute("insert into leads (holder_id) values (%s) returning *", (hid,)).fetchone()
            criados += 1
        ativos.add(lead["id"])

        if principal != hid:
            alvo = conn.execute("select id from leads where holder_id = %s", (principal,)).fetchone()
            if alvo is None:
                alvo = conn.execute("insert into leads (holder_id) values (%s) returning id", (principal,)).fetchone()
            conn.execute(
                """update leads set status = 'descartado', mesclado_em = %s,
                          motivo_descarte = 'duplicado: mesmo CNPJ do lead ' || %s
                    where id = %s and mesclado_em is distinct from %s""",
                (alvo["id"], alvo["id"], lead["id"], alvo["id"]),
            )
            for num in g["procs"]:
                conn.execute("insert into lead_processes values (%s, %s) on conflict do nothing", (alvo["id"], num))
            mesclados += 1
            continue

        for num in g["procs"]:
            conn.execute("insert into lead_processes values (%s, %s) on conflict do nothing", (lead["id"], num))
        # processos mesclados de outros titulares com o mesmo CNPJ contam aqui
        n_proc = conn.execute("select count(*) n from lead_processes where lead_id = %s", (lead["id"],)).fetchone()["n"]
        derive_candidates(conn, hid)
        wa_num, wa_status = best_whatsapp(conn, hid)
        cont = conn.execute(
            """select count(*) filter (where verificacao in ('dominio_ok','verificado_humano')) as val,
                      count(*) filter (where verificacao <> 'invalido') as tot
                 from contacts where holder_id = %s""",
            (hid,),
        ).fetchone()
        categoria = min(g["cats"], key=lambda c: CAT_ORDEM.index(c) if c in CAT_ORDEM else 99)
        prazo = min((p for p in g["pubs"] if p >= hoje), default=max(g["pubs"], default=None))
        dias = (prazo - hoje).days if prazo else None
        confirmado = any(g["conf"])
        recente = max(g.get("datas", []), default=None)
        dias_pub = (hoje - recente).days if recente else None
        hg = conn.execute("select geo_uf, geo_status from holders where id = %s", (hid,)).fetchone()
        abordado = (
            conn.execute("select 1 from outreach_log where lead_id = %s limit 1", (lead["id"],)).fetchone() is not None
            or conn.execute(
                "select 1 from wa_messages where lead_id = %s and direcao = 'saida' and modo = 'real' limit 1", (lead["id"],)
            ).fetchone()
            is not None
        )
        score, det = compute_score(
            categoria=categoria,
            dias_restantes=dias,
            n_proc=n_proc,
            contatos_validados=cont["val"],
            contatos_total=cont["tot"],
            tipo=h["tipo_provavel"],
            procurador_confirmado=confirmado,
            cnpj_status=h["cnpj_status"],
            whatsapp_status=wa_status,
            uf_ordem=ordem_uf.get(hg["geo_uf"]),
            dias_publicacao=dias_pub,
            abordado=abordado,
            geo_status=hg["geo_status"],
        )
        temp, motivos_temp = temperatura(
            categoria=categoria,
            dias_publicacao=dias_pub,
            contato_validado=bool(cont["val"]) or wa_status in ("confirmado", "validado"),
            contatos_total=cont["tot"],
            whatsapp_status=wa_status,
            geo_status=hg["geo_status"],
            cnpj_status=h["cnpj_status"],
            abordado=abordado,
            procurador_confirmado=confirmado,
            uf=hg["geo_uf"],
        )
        cnae = None
        if cnpj:
            est = conn.execute("select cnae_principal from cnpj_estabelecimentos where cnpj = %s", (cnpj,)).fetchone()
            cnae = est["cnae_principal"] if est else None
        seg = setor(cnae, g["classes"])

        status = lead["status"]
        motivo = lead["motivo_descarte"]
        if holder_hash(h) in supr:
            status, motivo = "descartado", "opt-out (LGPD)"
        elif status not in STATUS_HUMANOS and not (status == "descartado" and lead["revisado_por"]):
            if lead["pesquisado_em"] is None and cont["tot"] == 0:
                status = "novo"
            elif cont["tot"] == 0:
                status = "sem_contato"
            else:
                status = "qualificado"
            motivo = None
        abertas = conn.execute(
            """select count(*) n from review_tasks where status = 'aberta' and (
                 (entidade = 'holder' and entidade_id = %s) or
                 (entidade = 'process' and entidade_id in (select numero_processo from lead_processes where lead_id = %s)))""",
            (str(hid), lead["id"]),
        ).fetchone()["n"]
        conn.execute(
            """update leads set status = %s, motivo_descarte = %s, score = %s, score_detalhes = %s, prioridade = %s,
                      segmento = %s, categoria_principal = %s, prazo_ate = %s, procurador_confirmado = %s,
                      precisa_revisao = (revisado_por is null or %s > 0), whatsapp = %s, whatsapp_status = %s,
                      temperatura = %s, temperatura_motivos = %s
                where id = %s""",
            (
                status,
                motivo,
                score,
                Jsonb(det),
                prioridade(score),
                seg,
                categoria,
                prazo,
                confirmado,
                abertas,
                wa_num,
                wa_status,
                temp,
                Jsonb(motivos_temp),
                lead["id"],
            ),
        )
        atualizados += 1

    # Leads que perderam todas as oportunidades elegíveis (ex.: procurador apareceu)
    sem_op = conn.execute(
        """update leads set status = 'descartado', motivo_descarte = 'sem oportunidade elegível (procurador identificado)'
            where status not in ('descartado', 'aprovado', 'contatado', 'convertido')
              and not (id = any(%s)) returning id""",
        (list(ativos) or [0],),
    ).fetchall()
    return {"criados": criados, "atualizados": atualizados, "mesclados": mesclados, "descartados": len(sem_op)}


@handler("lead.validate_contacts")
def validate_contacts(conn, ctx: JobContext) -> dict:
    hid = int(ctx.payload["holder_id"])
    contatos = conn.execute(
        """select c.*, e.url, e.trecho from contacts c join evidences e on e.id = c.evidence_id
            where c.holder_id = %s and c.verificacao in ('encontrado', 'formato_ok')""",
        (hid,),
    ).fetchall()
    site = next(
        (
            c["valor_normalizado"]
            for c in conn.execute(
                "select valor_normalizado from contacts where holder_id = %s and tipo = 'site' and verificacao <> 'invalido'"
                " order by confianca desc nulls last limit 1",
                (hid,),
            )
        ),
        None,
    )
    resumo: dict[str, int] = {}
    for c in contatos:
        nivel, checagem = check_contact(c, {"url": c["url"]}, host_of(site))
        # WhatsApp só é "validado" se a empresa indicou o número como WhatsApp; candidatos nunca sobem sozinhos
        sem_indicacao = c["observacao"] == CANDIDATO_OBS or not evidencia_indica_whatsapp(c["trecho"], c["url"])
        if c["tipo"] == "whatsapp" and nivel == "dominio_ok" and sem_indicacao:
            nivel = "formato_ok"
            checagem["whatsapp"] = "sem indicação de WhatsApp na fonte: confirme abrindo a conversa"
        if c["fonte_tipo"] == "receita" and nivel == "dominio_ok" and not checagem.get("dominio_igual_site"):
            nivel = "formato_ok"  # e-mail cadastral (pode ser do contador): só sobe com o site oficial
        conn.execute(
            "update contacts set verificacao = %s, checagem = %s, checado_em = now() where id = %s",
            (nivel, Jsonb(checagem), c["id"]),
        )
        resumo[nivel] = resumo.get(nivel, 0) + 1
    queue.enqueue(conn, "leads.build", {}, dedupe_key="leads.build", prioridade=80)
    return {"holder_id": hid, "resultado": resumo}


# ------------------------------------------------------------------ Agente 06
ABORDAGEM = {
    "indeferimento": "O pedido foi indeferido em {data}. Cabe recurso em até 60 dias (prazo estimado: {prazo}). "
    "Abordagem: oferecer análise do indeferimento e elaboração do recurso.",
    "exigencia": "Há uma exigência publicada em {data}, com prazo estimado de cumprimento até {prazo}. "
    "Abordagem: oferecer o cumprimento da exigência antes do arquivamento.",
    "oposicao": "O pedido foi publicado para oposição em {data} (prazo estimado de oposição até {prazo}). "
    "Abordagem: oferecer acompanhamento do processo e vigilância de marcas colidentes.",
    "extincao_prorrogacao": "O registro foi extinto em {data} por fim da vigência sem prorrogação: a marca está "
    "sem proteção. Abordagem: oferecer busca de anterioridade e novo depósito.",
}


def lead_facts(conn, lead_id: int) -> dict:
    lead = conn.execute("select * from leads where id = %s", (lead_id,)).fetchone()
    h = conn.execute("select * from holders where id = %s", (lead["holder_id"],)).fetchone()
    procs = conn.execute(
        """select p.numero_processo, p.marca_nome, p.classes_nice, p.situacao_atual, o.categoria,
                  e.data_publicacao, e.numero as rpi
             from lead_processes lp join processes p on p.numero_processo = lp.numero_processo
             left join lateral (select o.categoria, o.edition_id from opportunities o
                                 where o.numero_processo = p.numero_processo and o.status = 'elegivel'
                                 order by o.id desc limit 1) o on true
             left join rpi_editions e on e.id = o.edition_id
            where lp.lead_id = %s order by p.numero_processo""",
        (lead_id,),
    ).fetchall()
    return {"lead": lead, "holder": h, "processos": procs}


def template_summary(f: dict) -> tuple[str, str]:
    lead, h, procs = f["lead"], f["holder"], f["processos"]
    marcas = ", ".join(sorted({p["marca_nome"] for p in procs if p["marca_nome"]})) or "marca não informada"
    resumo = (
        f"{h['nome_original']} ({h['tipo_provavel']}, {h['uf'] or 'UF não informada'}) tem "
        f"{len(procs)} processo(s) sem procurador ({marcas}). Segmento: {lead['segmento'] or 'não identificado'}. "
        f"Prioridade {lead['prioridade']} (score {lead['score']})."
    )
    cat = lead["categoria_principal"]
    pub = next((p for p in procs if p["categoria"] == cat), procs[0] if procs else None)
    data = pub["data_publicacao"].strftime("%d/%m/%Y") if pub and pub["data_publicacao"] else "data não informada"
    prazo = lead["prazo_ate"].strftime("%d/%m/%Y") if lead["prazo_ate"] else "-"
    abordagem = ABORDAGEM.get(cat, "Abordagem: apresentar os serviços de registro e acompanhamento de marcas.")
    abordagem = abordagem.format(data=data, prazo=prazo) + " Confirme os prazos no INPI antes do contato."
    return resumo, abordagem


SUMMARY_SYSTEM = """Você escreve, em português do Brasil, um resumo comercial curto (até 3 frases) e uma \
sugestão de abordagem (até 3 frases) para um lead de serviços de registro de marcas. Use SOMENTE os fatos \
fornecidos. Não invente nomes, valores, prazos ou dados. Prazos são estimativas: diga isso. Tom profissional, \
sem promessas de resultado. Responda chamando a ferramenta registrar_texto."""

SUMMARY_TOOL = {
    "name": "registrar_texto",
    "description": "Registra o texto final.",
    "input_schema": {
        "type": "object",
        "required": ["resumo", "abordagem"],
        "properties": {"resumo": {"type": "string"}, "abordagem": {"type": "string"}},
    },
}


@handler("sales.summarize_batch")
def summarize_batch(conn, ctx: JobContext) -> dict:
    s = get_settings()
    refazer = bool(ctx.payload.get("refazer"))
    leads = conn.execute(
        """select id from leads where status <> 'descartado' and mesclado_em is null
              and (%s or resumo is null or (%s::int is not null and id = %s))
            order by case prioridade when 'alta' then 1 when 'media' then 2 else 3 end, score desc nulls last
            limit %s""",
        (refazer, ctx.payload.get("lead_id"), ctx.payload.get("lead_id"), ctx.payload.get("limite", 50)),
    ).fetchall()
    usou_ia = 0
    for row in leads:
        f = lead_facts(conn, row["id"])
        resumo, abordagem = template_summary(f)
        autor = "modelo-padrao"
        if s.anthropic_api_key and f["lead"]["prioridade"] in ("alta", "media"):
            try:
                llm.ensure_budget(conn, 0.01)
                fatos = {
                    "titular": f["holder"]["nome_original"],
                    "tipo": f["holder"]["tipo_provavel"],
                    "uf": f["holder"]["uf"],
                    "segmento": f["lead"]["segmento"],
                    "prazo_estimado": f["lead"]["prazo_ate"],
                    "categoria": f["lead"]["categoria_principal"],
                    "processos": f["processos"],
                    "resumo_base": resumo,
                    "abordagem_base": abordagem,
                }
                res = llm.call(
                    model=s.modelo_resumo,
                    system=SUMMARY_SYSTEM,
                    tools=[SUMMARY_TOOL],
                    tool_choice={"type": "tool", "name": "registrar_texto"},
                    max_tokens=600,
                    messages=[{"role": "user", "content": json.dumps(fatos, ensure_ascii=False, default=str)}],
                )
                with db.transaction(ctx.actor) as c2:
                    llm.record(c2, res, proposito="summary", modelo=s.modelo_resumo, job_id=None, holder_id=f["holder"]["id"])
                out = next((b["input"] for b in res.content if b.get("type") == "tool_use"), None)
                if out and out.get("resumo") and out.get("abordagem"):
                    resumo, abordagem, autor = out["resumo"], out["abordagem"], s.modelo_resumo
                    usou_ia += 1
            except (llm.BudgetExceeded, llm.LLMNotConfigured, RuntimeError):
                pass  # mantém o texto do modelo fixo
        conn.execute(
            "update leads set resumo = %s, sugestao_abordagem = %s, resumo_gerado_por = %s where id = %s",
            (resumo, abordagem, autor, row["id"]),
        )
    return {"leads": len(leads), "com_ia": usou_ia}


# ------------------------------------------------------------------ relatório semanal
def weekly_report_data(conn, edicao: int | None = None) -> dict | None:
    ed = conn.execute(
        "select * from rpi_editions where status = 'parsed' and (%s::int is null or numero = %s) order by numero desc limit 1",
        (edicao, edicao),
    ).fetchone()
    if ed is None:
        return None
    por_cat = conn.execute(
        """select categoria, count(*) filter (where status = 'elegivel') as elegiveis,
                  count(*) filter (where status = 'descartada') as descartadas
             from opportunities where edition_id = %s group by categoria order by categoria""",
        (ed["id"],),
    ).fetchall()
    leads = conn.execute(
        """select l.id, h.nome_original as titular, h.uf, l.prioridade, l.score, l.categoria_principal, l.prazo_ate,
                  l.status, l.segmento,
                  (select count(*) from contacts c where c.holder_id = l.holder_id
                     and c.verificacao in ('dominio_ok','verificado_humano')) as contatos_validados
             from leads l join holders h on h.id = l.holder_id
            where l.mesclado_em is null and l.status <> 'descartado' and exists (
              select 1 from lead_processes lp join opportunities o on o.numero_processo = lp.numero_processo
               where lp.lead_id = l.id and o.edition_id = %s)
            order by l.score desc nulls last limit 50""",
        (ed["id"],),
    ).fetchall()
    custo = llm.week_spend(conn)
    return {
        "edicao": ed["numero"],
        "data_publicacao": ed["data_publicacao"],
        "estatisticas_rpi": ed["stats"],
        "oportunidades_por_categoria": por_cat,
        "leads_por_prioridade": conn.execute(
            "select prioridade, count(*) n from leads where status <> 'descartado' and mesclado_em is null group by prioridade"
        ).fetchall(),
        "procurador_confirmado_inpi": conn.execute(
            "select count(*) n from processes where procurador_status = 'sem_confirmado'"
        ).fetchone()["n"],
        "revisoes_abertas": conn.execute("select count(*) n from review_tasks where status = 'aberta'").fetchone()["n"],
        "custo_ia_semana_usd": round(custo, 2),
        "top_leads": leads,
    }


@handler("reports.weekly")
def weekly(conn, ctx: JobContext) -> dict:
    # retenção dos eventos do escritório (30 dias)
    conn.execute("delete from agent_events where criado_em < now() - interval '30 days'")
    dados = weekly_report_data(conn, ctx.payload.get("edicao"))
    if dados is None:
        return {"ignorado": "nenhuma edição processada"}
    ref = f"RPI {dados['edicao']}"
    conn.execute(
        """insert into reports (tipo, referencia, dados) values ('semanal', %s, %s)
           on conflict (tipo, referencia) do update set dados = excluded.dados, criado_em = now()""",
        (ref, Jsonb(json.loads(json.dumps(dados, default=str)))),
    )
    return {"referencia": ref, "top_leads": len(dados["top_leads"])}
