"""Painel executivo (UX V2.2): indicadores, séries diárias, pendências priorizadas e desempenho dos agentes.

Somente leitura. Tudo é calculado sobre os dados reais; nenhuma tabela é alterada.
"""

from datetime import UTC, datetime

# Severidade das pendências: critico > aviso > oportunidade > info
ORDEM = {"critico": 0, "aviso": 1, "oportunidade": 2, "info": 3}


def series(conn, dias: int) -> list[dict]:
    return conn.execute(
        """with d as (select generate_series(current_date - (%(n)s - 1), current_date, interval '1 day')::date as dia)
           select d.dia,
                  (select count(*) from leads l where l.created_at::date = d.dia) as leads,
                  (select count(*) from contacts c where c.created_at::date = d.dia) as contatos,
                  (select count(*) from contacts c where c.created_at::date = d.dia and c.tipo = 'whatsapp') as whatsapp,
                  (select count(*) from jobs j where j.finalizado_em::date = d.dia and j.status = 'succeeded') as tarefas_ok,
                  (select count(*) from jobs j where j.finalizado_em::date = d.dia and j.status = 'dead') as tarefas_falha
             from d order by d.dia""",
        {"n": dias},
    ).fetchall()


def agent_stats(conn, dias: int = 7) -> dict[str, dict]:
    """Desempenho por tipo de job (agente real) nos últimos N dias."""
    rows = conn.execute(
        """select tipo,
                  count(*) filter (where status in ('succeeded','dead')) as execucoes,
                  count(*) filter (where status = 'succeeded') as sucesso,
                  count(*) filter (where status = 'dead') as falhas,
                  round(avg(extract(epoch from finalizado_em - iniciado_em))
                        filter (where status = 'succeeded' and iniciado_em is not null)::numeric, 1) as duracao_media_s,
                  max(finalizado_em) as ultima_execucao
             from jobs where coalesce(finalizado_em, criado_em) >= now() - make_interval(days => %s)
            group by tipo""",
        (dias,),
    ).fetchall()
    out = {}
    for r in rows:
        ex = r["execucoes"] or 0
        out[r["tipo"]] = r | {"taxa_sucesso": round(100 * r["sucesso"] / ex, 1) if ex else None}
    return out


def pendencias(conn) -> list[dict]:
    """O que pede atenção agora, da mais grave para a menos grave. Só aparece o que tem quantidade > 0."""
    q = conn.execute(
        """select
             (select count(*) from schedules where ativo and proximo_em < now() - interval '10 minutes') as atrasados,
             (select count(*) from jobs where status = 'dead' and finalizado_em >= now() - interval '24 hours') as falhas_24h,
             (select count(*) from review_tasks where status = 'aberta') as revisoes,
             (select count(*) from leads where mesclado_em is null and pipeline_stage = 'resposta_recebida') as respostas,
             (select count(*) from leads where mesclado_em is null and pipeline_stage = 'elegivel_primeiro_contato') as elegiveis,
             (select count(*) from leads where mesclado_em is null and pipeline_stage = 'aguardando_autorizacao') as aguardando_aut,
             (select count(*) from leads where mesclado_em is null and status in ('qualificado','em_revisao')
                 and precisa_revisao) as aprovar,
             (select count(distinct c.holder_id) from contacts c join leads l on l.holder_id = c.holder_id
               where c.tipo = 'whatsapp' and c.wa_nivel = 'candidate' and l.mesclado_em is null
                 and l.status not in ('descartado')) as wa_candidatos,
             (select count(*) from wa_messages where direcao = 'saida' and status = 'falhou'
                 and coalesce(falhou_em, criado_em) >= now() - interval '7 days') as msg_falhas,
             (select count(*) from consent_requests where status = 'enviado' and criado_em < now() - interval '7 days')
                 as pedidos_sem_resposta,
             (select not ativo from schedules where nome = 'cnpj-receita') as receita_desligada"""
    ).fetchone()
    itens = [
        ("worker", "critico", q["atrasados"], "Agentes parados: agendamentos atrasados", "/operacao",
         "O worker não está executando a agenda. Verifique o serviço worker no servidor."),
        ("falhas", "critico", q["falhas_24h"], "Tarefas com falha nas últimas 24 h", "/jobs?status=dead",
         "Tarefas que esgotaram as tentativas e precisam de revisão."),
        ("respostas", "oportunidade", q["respostas"], "Respostas de WhatsApp para tratar", "/pipeline?etapa=resposta_recebida",
         "Leads que responderam: classifique como interessado, reunião ou perdido."),
        ("elegiveis", "oportunidade", q["elegiveis"], "Leads prontos para o primeiro contato", "/pipeline?etapa=elegivel_primeiro_contato",
         "Contato validado e autorização registrada."),
        ("revisoes", "aviso", q["revisoes"], "Revisões humanas abertas", "/revisoes",
         "Dúvidas que os agentes deixaram para uma pessoa decidir."),
        ("aprovar", "aviso", q["aprovar"], "Leads qualificados aguardando aprovação", "/leads?revisao=true",
         "Aprovar libera o contato e a preparação da mensagem."),
        ("msg_falhas", "aviso", q["msg_falhas"], "Mensagens de WhatsApp com falha (7 dias)", "/whatsapp",
         "Recusadas pela Meta ou com resultado incerto."),
        ("aguardando_aut", "info", q["aguardando_aut"], "Leads aguardando autorização", "/pipeline?etapa=aguardando_autorizacao",
         "Peça a autorização por e-mail ou registre a que já recebeu."),
        ("wa_candidatos", "info", q["wa_candidatos"], "WhatsApp candidatos para confirmar", "/contatos?filtro=wa_candidato",
         "Celulares sem prova de WhatsApp: confirme antes de usar."),
        ("pedidos", "info", q["pedidos_sem_resposta"], "Pedidos de autorização sem resposta há 7+ dias", "/contatos",
         "Encerre como sem resposta ou registre a autorização."),
        ("receita", "aviso", 1 if q["receita_desligada"] else 0, "Base CNPJ da Receita desligada", "/operacao",
         "Sem ela não há CNPJ, telefones nem e-mails cadastrais dos titulares."),
    ]
    out = [
        {"chave": k, "severidade": sev, "quantidade": int(n or 0), "titulo": t, "href": h, "descricao": d}
        for k, sev, n, t, h, d in itens
        if n
    ]
    return sorted(out, key=lambda x: (ORDEM[x["severidade"]], -x["quantidade"]))


def overview(conn, dias: int = 14) -> dict:
    kpi = conn.execute(
        """select
             (select count(*) from processes) as processos,
             (select count(*) from opportunities where status = 'elegivel') as oportunidades,
             (select count(*) from leads where mesclado_em is null and status <> 'descartado') as leads,
             (select count(*) from leads where mesclado_em is null and status <> 'descartado'
                and created_at >= now() - interval '7 days') as leads_7d,
             (select count(distinct holder_id) from contacts where verificacao <> 'invalido') as titulares_com_contato,
             (select count(*) from contacts where verificacao in ('dominio_ok','verificado_humano')) as contatos_validados,
             (select count(*) from contacts where tipo = 'whatsapp' and verificacao <> 'invalido') as whatsapp_total,
             (select count(*) from contacts where tipo = 'whatsapp' and wa_nivel in ('company_evidence','human_confirmed'))
                as whatsapp_validado,
             (select count(*) from consents where status = 'ativo') as autorizacoes,
             (select count(*) from wa_messages where direcao = 'saida' and modo = 'real' and aceita_em is not null) as enviadas,
             (select count(*) from wa_messages where direcao = 'saida' and modo = 'real'
                 and (entregue_em is not null or lida_em is not null)) as entregues,
             (select count(*) from wa_messages where direcao = 'entrada') as respostas,
             (select count(*) from outreach_log) as contatos_manuais,
             (select count(*) from leads where mesclado_em is null and pipeline_stage in
                 ('interessado','reuniao','proposta_enviada','negociacao')) as em_negociacao,
             (select count(*) from leads where mesclado_em is null and pipeline_stage = 'fechado') as fechados,
             (select coalesce(sum(custo_usd), 0) from llm_calls where criado_em >= date_trunc('week', now())) as custo_ia_semana,
             (select count(*) from jobs where status = 'running') as executando,
             (select count(*) from jobs where status = 'queued') as na_fila"""
    ).fetchone()
    abordados = (kpi["enviadas"] or 0) + (kpi["contatos_manuais"] or 0)
    kpi = kpi | {"taxa_conversao": round(100 * kpi["fechados"] / abordados, 1) if abordados else None}

    def grupo(sql: str) -> list[dict]:
        return conn.execute(sql).fetchall()

    return {
        "gerado_em": datetime.now(UTC),
        "kpis": kpi,
        "series": series(conn, dias),
        "pipeline": grupo("select pipeline_stage as chave, count(*) n from leads where mesclado_em is null group by 1"),
        "whatsapp_niveis": grupo(
            "select wa_nivel as chave, count(*) n from contacts where tipo = 'whatsapp' and wa_nivel is not null group by 1"
        ),
        "contatos_tipo": grupo(
            "select tipo as chave, count(*) n from contacts where verificacao <> 'invalido' group by 1 order by 2 desc"
        ),
        "categorias": grupo(
            """select coalesce(categoria_principal, 'outro') as chave, count(*) n from leads
                where mesclado_em is null and status <> 'descartado' group by 1 order by 2 desc"""
        ),
        "prioridades": grupo(
            """select coalesce(prioridade, 'sem') as chave, count(*) n from leads
                where mesclado_em is null and status <> 'descartado' group by 1"""
        ),
        "ufs": grupo(
            """select coalesce(h.uf, '?') as chave, count(*) n from leads l join holders h on h.id = l.holder_id
                where l.mesclado_em is null and l.status <> 'descartado' group by 1 order by 2 desc limit 8"""
        ),
        "edicoes": grupo(
            "select numero, data_publicacao, status, processada_em, stats->>'processos_importados' as processos"
            " from rpi_editions order by numero desc limit 5"
        ),
        "agentes": agent_stats(conn, 7),
        "pendencias": pendencias(conn),
    }
