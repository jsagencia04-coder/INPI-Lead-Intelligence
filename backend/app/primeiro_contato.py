"""Primeiro contato supervisionado (V2.5).

Fluxo: rascunho (IA ou modelo) → edição livre → aprovação humana presa ao conteúdo, número, canal e versão →
verificações no backend → UM envio pela Evolution (ou simulação) → registro → fim da automação daquela conversa.
Respostas: só pela pessoa, no app WhatsApp Business. Não há chatbot, resposta automática, follow-up nem envio em massa.

Aprovação humana NÃO substitui a autorização do destinatário: sem consentimento ativo (tabela consents), não sai.
A IA só escreve texto; não aprova, não envia e não tem acesso ao serviço de envio.
"""

import hashlib
import json
import re

from psycopg.types.json import Jsonb

from app import consent, db, evolution, llm
from app.config import get_settings
from app.jobs import queue

ROTULO_SERVICO = {"manifestacao_oposicao": "manifestação à oposição", "recurso_indeferimento": "recurso contra o indeferimento"}
PLACEHOLDER = re.compile(r"\[[^\]]{2,40}\]")  # ex.: [seu nome] — impede aprovar texto com lacunas
LINHA_SAIR = "Se preferir não receber mensagens, responda SAIR."
PAPEIS_APROVAR = ("revisor", "admin")


class Recusado(Exception):
    """Ação recusada por regra (vira HTTP 409)."""


def sha(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()


def hash_aprovacao(r: dict) -> str:
    return sha(f"{r['conteudo']}|{r['numero']}|{r['canal']}|{r['versao']}")


def auditar(conn, acao: str, lead_id: int | None, **detalhes) -> None:
    conn.execute("insert into wa_auditoria (lead_id, acao, detalhes) values (%s, %s, %s)",
                 (lead_id, acao, Jsonb(json.loads(json.dumps(detalhes, default=str)))))  # fmt: skip


def envio_bloqueado(conn) -> bool:
    r = conn.execute("select valor from app_config where chave = 'whatsapp_envio_bloqueado'").fetchone()
    return bool(r and r["valor"] == "true")


# ------------------------------------------------------------------ fatos do lead (só dados verificados)
def fatos(conn, lead_id: int) -> dict:
    lead = conn.execute(
        """select l.*, h.nome_original as titular, h.tipo_provavel, h.geo_uf, h.geo_municipio from leads l
             join holders h on h.id = l.holder_id where l.id = %s""",
        (lead_id,),
    ).fetchone()
    if lead is None:
        raise Recusado("Lead não encontrado")
    op = conn.execute(
        """select os.*, p.marca_nome from oportunidades_servico os
             join processes p on p.numero_processo = os.numero_processo
             join lead_processes lp on lp.numero_processo = os.numero_processo
            where lp.lead_id = %s and os.situacao_processual = 'aberta'
            order by case os.classificacao when 'quente' then 0 when 'morno' then 1 else 2 end, os.prazo_fim nulls last limit 1""",
        (lead_id,),
    ).fetchone()
    return {"lead": lead, "oportunidade": op}


def modelo_padrao(f: dict) -> str:
    s = get_settings()
    rem = s.primeiro_contato_remetente or "[seu nome]"
    op = f["oportunidade"]
    if op:
        marca = f'"{op["marca_nome"]}"' if op["marca_nome"] else "da sua marca"
        evento = "recebeu uma oposição de terceiro" if op["servico"] == "manifestacao_oposicao" else (
            "foi deferido parcialmente" if op["tipo_decisao"] == "deferimento_parcial" else "foi indeferido")  # fmt: skip
        prazo = f" O prazo legal estimado vai até {op['prazo_fim']:%d/%m/%Y} (vale confirmar no processo)." if op["prazo_fim"] else ""
        corpo = (
            f"Olá! Aqui é {rem}. Vi na Revista da Propriedade Industrial (RPI nº {op['rpi_numero']}) que o pedido de "
            f"registro {marca}, processo {op['numero_processo']}, {evento}.{prazo}\n\n"
            f"Trabalho com {ROTULO_SERVICO[op['servico']]} e posso explicar como funciona, sem compromisso. Podemos conversar?"
        )
    else:
        corpo = f"Olá! Aqui é {rem}. Acompanho publicações de marcas no INPI e vi um andamento no seu processo. Podemos conversar?"
    return f"{corpo}\n\n{LINHA_SAIR}"


SISTEMA_IA = """Você escreve, em português do Brasil, UMA primeira mensagem curta de WhatsApp (até 600 caracteres) para o \
titular de um pedido de marca no INPI. Use SOMENTE os fatos fornecidos. Não invente nomes, valores, prazos, resultados \
nem urgência. Não prometa resultado nem diga que o titular "vai perder a marca". Prazos são estimativas: diga isso. \
Apresente quem escreve usando exatamente o texto de "remetente". Tom cordial e profissional, sem emojis em excesso, \
sem links. Termine com uma pergunta simples. Responda chamando a ferramenta registrar_mensagem."""
FERRAMENTA = {
    "name": "registrar_mensagem",
    "description": "Registra a mensagem final.",
    "input_schema": {"type": "object", "required": ["mensagem"], "properties": {"mensagem": {"type": "string"}}},
}


def gerar_texto(conn, f: dict) -> tuple[str, str]:
    """IA (quando configurada e com orçamento) ou modelo fixo. A IA nunca aprova nem envia."""
    s = get_settings()
    base = modelo_padrao(f)
    if not s.anthropic_api_key:
        return base, "modelo-padrao"
    op = f["oportunidade"]
    dados = {
        "remetente": s.primeiro_contato_remetente or "[seu nome]",
        "titular": f["lead"]["titular"],
        "servico_oferecido": ROTULO_SERVICO.get(op["servico"]) if op else None,
        "ocorrencia": (op["tipo_decisao"] if op else None),
        "marca": op["marca_nome"] if op else None,
        "processo": op["numero_processo"] if op else None,
        "rpi": op["rpi_numero"] if op else None,
        "data_publicacao": op["data_publicacao"] if op else None,
        "prazo_estimado": op["prazo_fim"] if op else None,
        "mensagem_base": base,
    }
    try:
        llm.ensure_budget(conn, 0.01)
        res = llm.call(model=s.modelo_resumo, system=SISTEMA_IA, tools=[FERRAMENTA],
                       tool_choice={"type": "tool", "name": "registrar_mensagem"}, max_tokens=500,
                       messages=[{"role": "user", "content": json.dumps(dados, ensure_ascii=False, default=str)}])  # fmt: skip
        with db.transaction("agent:primeiro-contato") as c2:
            llm.record(c2, res, proposito="primeiro_contato", modelo=s.modelo_resumo, job_id=None, holder_id=f["lead"]["holder_id"])
        out = next((b["input"] for b in res.content if b.get("type") == "tool_use"), None)
        texto = (out or {}).get("mensagem", "").strip()
    except (llm.BudgetExceeded, llm.LLMNotConfigured, RuntimeError):
        texto = ""
    if not texto or len(texto) > 900 or "http" in texto.lower():
        return base, "modelo-padrao"
    if "SAIR" not in texto.upper():
        texto = f"{texto}\n\n{LINHA_SAIR}"
    return texto, f"ia:{s.modelo_resumo}"


# ------------------------------------------------------------------ rascunho
def contato_whatsapp(conn, lead_id: int, contact_id: int | None) -> dict:
    c = conn.execute(
        """select c.* from contacts c join leads l on l.holder_id = c.holder_id
            where l.id = %s and c.tipo = 'whatsapp' and c.verificacao <> 'invalido' and (%s::bigint is null or c.id = %s)
            order by (c.wa_nivel = 'human_confirmed') desc, (c.wa_nivel = 'company_evidence') desc, c.confianca desc nulls last limit 1""",
        (lead_id, contact_id, contact_id),
    ).fetchone()
    if c is None:
        raise Recusado("O lead não tem WhatsApp encontrado para este contato")
    return c


def criar_rascunho(conn, lead_id: int, contact_id: int | None, ator: str) -> dict:
    c = contato_whatsapp(conn, lead_id, contact_id)
    aberto = conn.execute(
        "select * from wa_rascunhos where lead_id = %s and contact_id = %s and status in ('rascunho','aprovado')", (lead_id, c["id"])
    ).fetchone()
    f = fatos(conn, lead_id)
    texto, autor = gerar_texto(conn, f)
    if aberto:  # gerar de novo = nova versão; qualquer aprovação anterior deixa de valer
        r = conn.execute(
            """update wa_rascunhos set conteudo = %s, conteudo_hash = %s, versao = versao + 1, status = 'rascunho',
                      gerado_por = %s, aprovado_por = null, aprovado_em = null, aprovacao_hash = null where id = %s returning *""",
            (texto, sha(texto), autor, aberto["id"]),
        ).fetchone()
    else:
        r = conn.execute(
            """insert into wa_rascunhos (lead_id, contact_id, numero_processo, numero, canal, conteudo, conteudo_hash, gerado_por)
               values (%s,%s,%s,%s,%s,%s,%s,%s) returning *""",
            (lead_id, c["id"], f["oportunidade"]["numero_processo"] if f["oportunidade"] else None, c["valor_normalizado"],
             "evolution" if get_settings().mensageria_provedor == "evolution" else "manual", texto, sha(texto), autor),
        ).fetchone()  # fmt: skip
    auditar(conn, "rascunho_gerado", lead_id, rascunho_id=r["id"], versao=r["versao"], gerado_por=autor)
    return r


def _aberto(conn, rid: int) -> dict:
    r = conn.execute("select * from wa_rascunhos where id = %s for update", (rid,)).fetchone()
    if r is None:
        raise Recusado("Rascunho não encontrado")
    return r


def editar(conn, rid: int, conteudo: str, versao: int, ator: str) -> dict:
    r = _aberto(conn, rid)
    if r["status"] not in ("rascunho", "aprovado"):
        raise Recusado(f"Rascunho {r['status']}: não pode ser editado")
    if r["versao"] != versao:
        raise Recusado("Outra pessoa alterou este rascunho. Recarregue para ver a versão atual.")
    conteudo = conteudo.strip()
    if not conteudo:
        raise Recusado("A mensagem não pode ficar vazia")
    r = conn.execute(
        """update wa_rascunhos set conteudo = %s, conteudo_hash = %s, versao = versao + 1, status = 'rascunho',
                  gerado_por = case when conteudo = %s then gerado_por else %s end,
                  aprovado_por = null, aprovado_em = null, aprovacao_hash = null where id = %s returning *""",
        (conteudo, sha(conteudo), conteudo, f"editado:{ator}", rid),
    ).fetchone()
    auditar(conn, "rascunho_editado", r["lead_id"], rascunho_id=rid, versao=r["versao"])
    return r


def rejeitar(conn, rid: int, motivo: str, ator: str) -> dict:
    r = _aberto(conn, rid)
    if r["status"] not in ("rascunho", "aprovado"):
        raise Recusado(f"Rascunho {r['status']}")
    r = conn.execute(
        """update wa_rascunhos set status = 'rejeitado', rejeitado_por = %s, rejeitado_em = now(), motivo = %s,
                  aprovado_por = null, aprovado_em = null, aprovacao_hash = null where id = %s returning *""",
        (ator, motivo, rid),
    ).fetchone()
    auditar(conn, "rascunho_rejeitado", r["lead_id"], rascunho_id=rid, motivo=motivo)
    return r


def aprovar(conn, rid: int, versao: int, conteudo_hash: str, numero: str, canal: str, ator: str, papel: str) -> dict:
    if papel not in PAPEIS_APROVAR:
        raise Recusado("Só revisor ou administrador aprova mensagens")
    r = _aberto(conn, rid)
    if r["status"] != "rascunho":
        raise Recusado(f"Rascunho {r['status']}: só um rascunho em revisão pode ser aprovado")
    # a pessoa aprova exatamente o que viu: versão, texto, número e canal
    if (r["versao"], r["conteudo_hash"], r["numero"], r["canal"]) != (versao, conteudo_hash, numero, canal):
        raise Recusado("O rascunho mudou depois que você abriu (texto, número ou canal). Revise de novo antes de aprovar.")
    if PLACEHOLDER.search(r["conteudo"]):
        raise Recusado("Preencha as lacunas entre colchetes (ex.: [seu nome]) antes de aprovar")
    r = conn.execute(
        "update wa_rascunhos set status = 'aprovado', aprovado_por = %s, aprovado_em = now(), aprovacao_hash = %s where id = %s returning *",
        (ator, hash_aprovacao(r), rid),
    ).fetchone()
    auditar(conn, "rascunho_aprovado", r["lead_id"], rascunho_id=rid, versao=r["versao"], numero=r["numero"], canal=r["canal"])
    return r


# ------------------------------------------------------------------ verificações de envio (negar é o padrão)
def verificacoes(conn, r: dict, *, papel: str | None = None, conexao: dict | None = None, mensagem_atual: int | None = None) -> list[dict]:
    s = get_settings()
    real = evolution.modo(s) == "real"
    ok = lambda regra, cond, sim, nao: {"regra": regra, "ok": bool(cond), "detalhe": sim if cond else nao}  # noqa: E731
    v = [
        ok("provedor", s.mensageria_provedor == "evolution" and r["canal"] == "evolution",
           "Envio pela Evolution (instância " + s.evolution_instance_name + ")",
           f"Provedor selecionado: {s.mensageria_provedor}. Use 'Abrir no WhatsApp' para o envio manual."),
        ok("envio_liberado", not envio_bloqueado(conn), "Envios liberados", "Envios desativados pelo botão de emergência"),
        ok("aprovado", r["status"] == "aprovado" and r["aprovacao_hash"] == hash_aprovacao(r),
           f"Aprovado por {r['aprovado_por']}", "Mensagem ainda não aprovada (ou mudou depois da aprovação)"),
    ]  # fmt: skip
    c = conn.execute("select * from contacts where id = %s", (r["contact_id"],)).fetchone()
    v.append(ok("numero_atual", c and c["valor_normalizado"] == r["numero"] and c["verificacao"] != "invalido",
                "Número confere com o contato", "O número do contato mudou ou foi invalidado"))  # fmt: skip
    e = consent.elegibilidade(conn, r["contact_id"])
    for regra in e["regras"]:
        v.append({"regra": f"consentimento:{regra['regra']}", "ok": regra["ok"], "detalhe": regra["detalhe"]})
    anterior = conn.execute(
        """select 1 from wa_messages where direcao = 'saida' and (rascunho_id = %s or contact_id = %s)
              and status not in ('falhou','simulada','bloqueada','cancelada') and id is distinct from %s limit 1""",
        (r["id"], r["contact_id"], mensagem_atual),
    ).fetchone()
    v.append(ok("sem_envio_anterior", anterior is None, "Nenhum envio anterior para este contato",
                "Já houve envio para este contato: o primeiro contato é único (sem follow-up automático)"))  # fmt: skip
    if papel is not None:
        v.append(ok("usuario", papel in PAPEIS_APROVAR, "Usuário com permissão comercial", "Só revisor ou administrador envia"))
    if real:
        teste = evolution.numeros_teste(s)
        if teste:
            v.append(ok("numero_teste", r["numero"] in teste, "Número na lista do teste controlado",
                        "Teste controlado: só os números de teste autorizados podem receber"))  # fmt: skip
        if conexao is not None:
            v.append(ok("instancia_conectada", conexao.get("status") == "conectado", "Instância conectada",
                        f"Instância: {conexao.get('status')} {conexao.get('detalhe') or ''}".strip()))  # fmt: skip
            v.append(ok("numero_remetente", conexao.get("numero_confere"), "Número remetente é o autorizado do INPI Agent",
                        "O número conectado não é o número autorizado (EVOLUTION_NUMERO_AUTORIZADO)"))  # fmt: skip
    return v


def bloqueios(v: list[dict]) -> list[str]:
    return [x["detalhe"] for x in v if not x["ok"]]


# ------------------------------------------------------------------ envio
def solicitar_envio(conn, rid: int, ator: str, papel: str) -> dict:
    """Valida tudo e cria UM registro de envio. Em simulação, nada sai do sistema."""
    r = _aberto(conn, rid)
    s = get_settings()
    real = evolution.modo(s) == "real"
    conexao = evolution.verificar_conexao(conn) if real else None
    falhas = bloqueios(verificacoes(conn, r, papel=papel, conexao=conexao))
    if falhas:
        auditar(conn, "envio_bloqueado", r["lead_id"], rascunho_id=rid, motivos=falhas)
        raise Recusado("Envio bloqueado: " + "; ".join(falhas))
    tentativa = conn.execute("select count(*) n from wa_messages where rascunho_id = %s", (rid,)).fetchone()["n"] + 1
    dados = (r["contact_id"], r["lead_id"], r["numero_processo"], r["numero"], r["conteudo"], s.evolution_instance_name, rid)
    if not real:
        m = conn.execute(
            """insert into wa_messages (direcao, modo, provedor, contact_id, lead_id, numero_processo, numero, tipo, corpo,
                                        instancia, rascunho_id, idempotency_key, status, motivo, criado_por)
               values ('saida','simulacao','evolution',%s,%s,%s,%s,'texto',%s,%s,%s,%s,'simulada',%s,%s) returning *""",
            (*dados, f"evo:sim:{rid}:{tentativa}", "simulação: nada foi enviado (EVOLUTION_SIMULATION ou envio desligado)", ator),
        ).fetchone()
        auditar(conn, "envio_simulado", r["lead_id"], rascunho_id=rid, mensagem_id=m["id"])
        return m
    m = conn.execute(
        """insert into wa_messages (direcao, modo, provedor, contact_id, lead_id, numero_processo, numero, tipo, corpo,
                                    instancia, rascunho_id, idempotency_key, status, criado_por)
           values ('saida','real','evolution',%s,%s,%s,%s,'texto',%s,%s,%s,%s,'na_fila',%s) returning *""",
        (*dados, f"evo:{rid}:{tentativa}", ator),
    ).fetchone()
    queue.enqueue(conn, "whatsapp.evolution_send", {"message_id": m["id"]}, dedupe_key=f"whatsapp.evolution_send:{m['id']}", prioridade=5)
    auditar(conn, "envio_solicitado", r["lead_id"], rascunho_id=rid, mensagem_id=m["id"])
    return m


def executar_envio(conn, message_id: int) -> dict:
    """Worker: confere tudo de novo e faz UMA chamada. Nunca repete sozinho."""
    msg = conn.execute("select * from wa_messages where id = %s", (message_id,)).fetchone()
    if msg is None or msg["status"] != "na_fila" or msg["provedor"] != "evolution":
        return {"ignorado": "mensagem não está na fila"}
    r = conn.execute("select * from wa_rascunhos where id = %s", (msg["rascunho_id"],)).fetchone()
    conexao = evolution.verificar_conexao(conn)
    falhas = ["simulação/envio desligado"] if evolution.modo() != "real" else []
    falhas += bloqueios(verificacoes(conn, r, conexao=conexao, mensagem_atual=message_id)) if r else ["rascunho não encontrado"]
    if r and msg["corpo"] != r["conteudo"]:
        falhas.append("o texto mudou depois do pedido de envio")
    if falhas:
        conn.execute("update wa_messages set status = 'bloqueada', motivo = %s where id = %s", ("; ".join(falhas)[:500], message_id))
        auditar(conn, "envio_bloqueado_worker", msg["lead_id"], mensagem_id=message_id, motivos=falhas)
        return {"status": "bloqueada", "motivos": falhas}
    # Marca "em andamento" numa transação já confirmada ANTES de chamar a Evolution: se o worker cair no meio,
    # a mensagem fica para reconciliação humana e nunca é enviada duas vezes.
    with db.transaction("agent:whatsapp.evolution_send") as c2:
        ok = c2.execute(
            "update wa_messages set status = 'reconciliar', motivo = 'envio em andamento' where id = %s and status = 'na_fila' returning id",
            (message_id,),
        ).fetchone()
    if not ok:
        return {"ignorado": "outro processo já pegou esta mensagem"}
    res = evolution.enviar_texto(msg["numero"], msg["corpo"])
    if res.status == "aceita":
        conn.execute(
            """update wa_messages set status = 'aceita', wa_message_id = %s, aceita_em = now(), motivo = null,
                      tentativas = tentativas + 1 where id = %s""",
            (res.message_id, message_id),
        )
        conn.execute("update wa_rascunhos set status = 'enviado' where id = %s", (r["id"],))
    else:
        conn.execute(
            f"""update wa_messages set status = %s, motivo = %s, erro_codigo = %s, tentativas = tentativas + 1
                {", falhou_em = now()" if res.status == "falhou" else ""} where id = %s""",
            (res.status, res.motivo, res.codigo, message_id),
        )
    auditar(conn, f"envio_{res.status}", msg["lead_id"], mensagem_id=message_id, motivo=res.motivo)
    return {"status": res.status, "motivo": res.motivo}


def reconciliar(conn, message_id: int, resultado: str, ator: str) -> dict:
    """Uma pessoa conferiu no celular se a mensagem saiu. Nada é reenviado automaticamente."""
    m = conn.execute("select * from wa_messages where id = %s for update", (message_id,)).fetchone()
    if m is None or m["status"] != "reconciliar":
        raise Recusado("Esta mensagem não está aguardando conferência")
    if resultado == "enviada":
        m = conn.execute("update wa_messages set status = 'enviada', enviada_em = now(), motivo = %s where id = %s returning *",
                         (f"confirmada no celular por {ator}", message_id)).fetchone()  # fmt: skip
        conn.execute("update wa_rascunhos set status = 'enviado' where id = %s", (m["rascunho_id"],))
    else:
        m = conn.execute("update wa_messages set status = 'falhou', falhou_em = now(), motivo = %s where id = %s returning *",
                         (f"não saiu (conferido por {ator})", message_id)).fetchone()  # fmt: skip
    auditar(conn, "envio_reconciliado", m["lead_id"], mensagem_id=message_id, resultado=resultado)
    return m
