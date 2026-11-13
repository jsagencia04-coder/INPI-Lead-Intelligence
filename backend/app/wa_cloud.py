"""WhatsApp Business Platform — Cloud API oficial da Meta (V2.0, Fase 7).

Princípios:
  * Só a API oficial. Nenhuma automação do WhatsApp Web.
  * Credenciais só no backend; nunca são devolvidas por rota alguma nem escritas em log.
  * Chave geral WHATSAPP_ENVIO_ATIVO: desligada = simulação (nada sai do sistema).
  * Status não é inventado: 'aceita' vem da resposta da API; 'enviada/entregue/lida/falhou' só do webhook.
  * Sem duplicidade: chave de idempotência por contato + processo + template.
  * Retry seguro: só repete quando é certo que a Meta NÃO recebeu o pedido (falha de conexão ou limite de taxa).
    Resultado incerto (timeout de leitura, erro 5xx) não é reenviado sozinho.
"""

import hashlib
import hmac
import re
import time
import unicodedata
from datetime import UTC, datetime

import httpx
from psycopg.types.json import Jsonb

from app import consent
from app.config import Settings, get_settings
from app.jobs import queue

transport: httpx.BaseTransport | None = None  # testes
REGRA_VERSAO = "v1"  # mudar só com nova regra aprovada (permite um novo envio ao mesmo contato/processo)

RANK = {"na_fila": 0, "aceita": 1, "enviada": 2, "entregue": 3, "lida": 4}
STATUS_META = {"sent": "enviada", "delivered": "entregue", "read": "lida", "failed": "falhou"}
# códigos da Meta que significam "devagar": o pedido não foi aceito e pode ser repetido
CODIGOS_LIMITE = {4, 80007, 130429, 131048, 131056}

_OPTOUT_EXATO = {"SAIR", "PARAR", "PARE", "STOP", "CANCELAR", "DESCADASTRAR", "REMOVER", "SAIA", "UNSUBSCRIBE"}
_OPTOUT_TRECHO = ("NAO QUERO RECEBER", "NAO ME MANDE", "NAO MANDE MAIS", "PARE DE ENVIAR", "PARE DE MANDAR", "ME REMOVA",
                  "ME TIRE", "NAO ENVIE MAIS", "NAO QUERO MAIS")  # fmt: skip


class ErroDeRegra(Exception):
    """Pedido recusado por regra de negócio (vira 409 na API)."""


def configurado(s: Settings | None = None) -> bool:
    s = s or get_settings()
    return bool(s.whatsapp_phone_number_id and s.whatsapp_access_token and s.whatsapp_template_name)


def numeros_teste(s: Settings | None = None) -> set[str]:
    s = s or get_settings()
    return {n.strip() for n in s.whatsapp_numeros_teste.split(",") if n.strip()}


def hash_numero(e164: str) -> str:
    return hashlib.sha256(e164.encode()).hexdigest()


def eh_optout(texto: str | None) -> bool:
    t = "".join(c for c in unicodedata.normalize("NFKD", texto or "") if not unicodedata.combining(c)).upper()
    t = re.sub(r"[^A-Z0-9 ]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t in _OPTOUT_EXATO or any(p in t for p in _OPTOUT_TRECHO)


# ------------------------------------------------------------------ cliente HTTP
def _client() -> httpx.Client:
    s = get_settings()
    return httpx.Client(
        base_url=s.whatsapp_api_url.rstrip("/"),
        headers={"Authorization": f"Bearer {s.whatsapp_access_token}"},
        timeout=httpx.Timeout(20, connect=8),
        transport=transport,
    )


def _erro_meta(resp: httpx.Response) -> tuple[str, str]:
    try:
        e = resp.json().get("error", {})
        return str(e.get("code", resp.status_code)), str(e.get("message", ""))[:300]
    except ValueError:
        return str(resp.status_code), ""


_template_cache: dict[str, tuple[float, dict]] = {}


def template_status(force: bool = False) -> dict:
    """Consulta na Meta se o template configurado existe e está APPROVED (cache de 10 min)."""
    s = get_settings()
    if not (s.whatsapp_business_account_id and s.whatsapp_access_token and s.whatsapp_template_name):
        return {"ok": False, "status": None, "motivo": "template ou conta (WABA) não configurados"}
    chave = f"{s.whatsapp_business_account_id}:{s.whatsapp_template_name}:{s.whatsapp_template_language}"
    if not force and chave in _template_cache and time.time() - _template_cache[chave][0] < 600:
        return _template_cache[chave][1]
    try:
        with _client() as c:
            r = c.get(
                f"/{s.whatsapp_business_account_id}/message_templates",
                params={"name": s.whatsapp_template_name, "fields": "name,status,language,category"},
            )
    except httpx.HTTPError as exc:
        return {"ok": False, "status": None, "motivo": f"não foi possível consultar a Meta ({type(exc).__name__})"}
    if r.status_code != 200:
        cod, msg = _erro_meta(r)
        return {"ok": False, "status": None, "motivo": f"Meta respondeu erro {cod}: {msg}"}
    achados = [t for t in r.json().get("data", []) if t.get("name") == s.whatsapp_template_name]
    t = next((t for t in achados if t.get("language") == s.whatsapp_template_language), None)
    if t is None:
        out = {"ok": False, "status": None, "motivo": "template não encontrado nesse idioma"}
    else:
        out = {
            "ok": t.get("status") == "APPROVED",
            "status": t.get("status"),
            "categoria": t.get("category"),
            "motivo": None if t.get("status") == "APPROVED" else "template ainda não aprovado pela Meta",
        }
    _template_cache[chave] = (time.time(), out)
    return out


# ------------------------------------------------------------------ criação (fila)
def parametros_padrao(conn, numero_processo: str) -> list[str]:
    """Variáveis do template, só com fatos oficiais: marca, processo, despacho, nº e data da RPI."""
    r = conn.execute(
        """select p.marca_nome, pub.despacho_nome, pub.despacho_codigo, e.numero as rpi, e.data_publicacao
             from processes p
             left join lateral (select * from publications x where x.numero_processo = p.numero_processo
                                 order by x.edition_id desc limit 1) pub on true
             left join rpi_editions e on e.id = pub.edition_id
            where p.numero_processo = %s""",
        (numero_processo,),
    ).fetchone()
    if r is None:
        raise ErroDeRegra("Processo não encontrado")
    data = r["data_publicacao"].strftime("%d/%m/%Y") if r["data_publicacao"] else "—"
    return [
        r["marca_nome"] or "—",
        numero_processo,
        r["despacho_nome"] or r["despacho_codigo"] or "—",
        str(r["rpi"] or "—"),
        data,
    ]


def criar_saida(conn, *, lead_id: int, contact_id: int, numero_processo: str | None, params: list[str] | None) -> dict:
    """Cria a mensagem de saída. Modo real entra na fila; modo simulação só registra o que seria enviado."""
    s = get_settings()
    lead = conn.execute("select * from leads where id = %s", (lead_id,)).fetchone()
    if lead is None:
        raise ErroDeRegra("Lead não encontrado")
    if lead["status"] not in ("aprovado", "contatado", "convertido"):
        raise ErroDeRegra("Aprove o lead antes de preparar a mensagem")
    c = conn.execute("select * from contacts where id = %s and holder_id = %s", (contact_id, lead["holder_id"])).fetchone()
    if c is None or c["tipo"] != "whatsapp":
        raise ErroDeRegra("O contato precisa ser um WhatsApp deste lead")
    if c["verificacao"] == "invalido":
        raise ErroDeRegra("Contato inválido ou em opt-out")
    if conn.execute("select 1 from suppression_list where valor_hash = %s", (hash_numero(c["valor_normalizado"]),)).fetchone():
        raise ErroDeRegra("Contato na lista de opt-out (LGPD)")
    if numero_processo is None:
        p = conn.execute(
            "select numero_processo from lead_processes where lead_id = %s order by numero_processo desc limit 1", (lead_id,)
        ).fetchone()
        numero_processo = p["numero_processo"] if p else None
    elif not conn.execute(
        "select 1 from lead_processes where lead_id = %s and numero_processo = %s", (lead_id, numero_processo)
    ).fetchone():
        raise ErroDeRegra("O processo não pertence a este lead")
    if numero_processo is None:
        raise ErroDeRegra("Lead sem processo vinculado")

    modo = "real" if (s.whatsapp_envio_ativo and configurado(s)) else "simulacao"
    template = s.whatsapp_template_name or "(template não configurado)"
    chave = hashlib.sha256(f"{modo}|{contact_id}|{numero_processo}|{template}|{REGRA_VERSAO}".encode()).hexdigest()
    existente = conn.execute("select * from wa_messages where idempotency_key = %s", (chave,)).fetchone()
    if existente:
        return existente | {"duplicada": True}
    params = params if params is not None else parametros_padrao(conn, numero_processo)
    row = conn.execute(
        """insert into wa_messages (direcao, modo, contact_id, lead_id, numero_processo, numero, tipo, template_nome,
                                    template_idioma, template_params, corpo, idempotency_key, status)
           values ('saida', %s, %s, %s, %s, %s, 'template', %s, %s, %s, %s, %s, %s) returning *""",
        (modo, contact_id, lead_id, numero_processo, c["valor_normalizado"], template, s.whatsapp_template_language,
         Jsonb(params), " | ".join(params), chave, "na_fila" if modo == "real" else "simulada"),
    ).fetchone()  # fmt: skip
    if modo == "real":
        queue.enqueue(conn, "whatsapp.send", {"message_id": row["id"]}, dedupe_key=f"whatsapp.send:{row['id']}")
    return row | {"duplicada": False}


# ------------------------------------------------------------------ envio (worker)
def bloqueio(conn, msg: dict) -> str | None:
    """Motivo pelo qual a mensagem NÃO pode sair agora (None = pode). Negar é o padrão."""
    s = get_settings()
    if s.mensageria_provedor != "meta":
        return f"Cloud API da Meta desativada: o provedor de envio é '{s.mensageria_provedor}'"
    if not s.whatsapp_envio_ativo:
        return "envio desligado (WHATSAPP_ENVIO_ATIVO=false)"
    if not configurado(s):
        return "integração não configurada"
    if s.auth_mode == "dev":
        return "envio real exige login obrigatório (AUTH_MODE=supabase)"
    if conn.execute("select 1 from suppression_list where valor_hash = %s", (hash_numero(msg["numero"]),)).fetchone():
        return "opt-out (lista de supressão)"
    if msg["contact_id"]:
        c = conn.execute("select verificacao from contacts where id = %s", (msg["contact_id"],)).fetchone()
        if c is None or c["verificacao"] == "invalido":
            return "contato inválido"
    t = template_status()
    if not t["ok"]:
        return f"template não aprovado: {t['motivo']}"
    # Exceção só para homologação: seus próprios números de teste, nunca em produção.
    if s.app_env != "producao" and msg["numero"] in numeros_teste(s):
        return None
    if not msg["contact_id"]:
        return "mensagem sem contato vinculado"
    e = consent.elegibilidade(conn, msg["contact_id"])
    if not e["elegivel"]:
        falhas = "; ".join(r["detalhe"] for r in e["regras"] if not r["ok"])
        return f"regra de consentimento: {falhas}"
    return None


def limite_atingido(conn) -> int | None:
    """Segundos a esperar se o limite de envio foi atingido; None se há folga."""
    s = get_settings()
    r = conn.execute(
        """select count(*) filter (where aceita_em > now() - interval '1 minute') as minuto,
                  count(*) filter (where aceita_em > date_trunc('day', now())) as dia
             from wa_messages where direcao = 'saida' and modo = 'real' and aceita_em is not null"""
    ).fetchone()
    if r["dia"] >= s.whatsapp_limite_por_dia:
        return 3600
    if r["minuto"] >= s.whatsapp_limite_por_minuto:
        return 60
    return None


def chamar_api(msg: dict) -> httpx.Response:
    s = get_settings()
    corpo = {
        "messaging_product": "whatsapp",
        "to": msg["numero"].lstrip("+"),
        "type": "template",
        "template": {
            "name": msg["template_nome"],
            "language": {"code": msg["template_idioma"]},
            "components": [{"type": "body", "parameters": [{"type": "text", "text": str(p)} for p in msg["template_params"]]}]
            if msg["template_params"]
            else [],
        },
    }
    with _client() as c:
        return c.post(f"/{s.whatsapp_phone_number_id}/messages", json=corpo)


# ------------------------------------------------------------------ recebimento (webhook)
def assinatura_valida(corpo: bytes, cabecalho: str | None, segredo: str) -> bool:
    if not cabecalho or not cabecalho.startswith("sha256="):
        return False
    esperado = hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, cabecalho.removeprefix("sha256="))


def _ts(v) -> datetime:
    try:
        return datetime.fromtimestamp(int(v), UTC)
    except (TypeError, ValueError):
        return datetime.now(UTC)


def aplicar_optout(conn, numero: str, origem: str, motivo: str) -> None:
    """Opt-out imediato: bloqueia, registra data e origem, revoga consentimentos e cancela pendentes."""
    conn.execute(
        """insert into suppression_list (tipo, valor_hash, motivo, origem) values ('telefone', %s, %s, %s)
           on conflict do nothing""",
        (hash_numero(numero), motivo, origem),
    )
    ids = [
        r["id"]
        for r in conn.execute(
            """update contacts set verificacao = 'invalido', observacao = 'opt-out (LGPD)'
                where valor_normalizado = %s and tipo in ('telefone','whatsapp') returning id""",
            (numero,),
        ).fetchall()
    ]
    if ids:
        conn.execute(
            """update consents set status = 'revogado', revogado_em = now(), revogacao_origem = %s
                where contact_id = any(%s) and status = 'ativo'""",
            (origem, ids),
        )
    conn.execute(
        "update wa_messages set status = 'cancelada', motivo = 'opt-out do destinatário' where numero = %s and status = 'na_fila'",
        (numero,),
    )


def _novo_evento(conn, chave: str, tipo: str, wa_id: str | None, payload: dict) -> bool:
    return (
        conn.execute(
            """insert into wa_webhook_events (event_key, tipo, wa_message_id, payload) values (%s, %s, %s, %s)
               on conflict (event_key) do nothing returning id""",
            (chave, tipo, wa_id, Jsonb(payload)),
        ).fetchone()
        is not None
    )


def processar_webhook(conn, payload: dict) -> dict:
    """Aplica um webhook da Meta. Idempotente: evento repetido é ignorado."""
    res = {"status": 0, "mensagens": 0, "optouts": 0, "repetidos": 0, "desconhecidos": 0}
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            v = change.get("value", {})
            for st in v.get("statuses", []):
                wa_id, nome = st.get("id"), st.get("status")
                if not _novo_evento(conn, f"status:{wa_id}:{nome}:{st.get('timestamp')}", "status", wa_id, st):
                    res["repetidos"] += 1
                    continue
                novo = STATUS_META.get(nome)
                msg = conn.execute("select * from wa_messages where wa_message_id = %s for update", (wa_id,)).fetchone()
                if novo is None or msg is None:
                    res["desconhecidos"] += 1  # guardado em wa_webhook_events, mas não altera nada
                    continue
                quando = _ts(st.get("timestamp"))
                if novo == "falhou":
                    if RANK.get(msg["status"], 9) < RANK["entregue"]:
                        err = (st.get("errors") or [{}])[0]
                        conn.execute(
                            "update wa_messages set status = 'falhou', falhou_em = %s, erro_codigo = %s, motivo = %s where id = %s",
                            (
                                quando,
                                str(err.get("code", "")),
                                str(err.get("title") or err.get("message") or "")[:300],
                                msg["id"],
                            ),
                        )
                else:
                    # grava o horário do evento; o status só avança, nunca regride (eventos chegam fora de ordem)
                    coluna = {"enviada": "enviada_em", "entregue": "entregue_em", "lida": "lida_em"}[novo]
                    avanca = msg["status"] in RANK and RANK[novo] > RANK[msg["status"]]
                    conn.execute(
                        f"update wa_messages set {coluna} = coalesce({coluna}, %s), status = %s where id = %s",
                        (quando, novo if avanca else msg["status"], msg["id"]),
                    )
                res["status"] += 1
            for m in v.get("messages", []):
                wa_id = m.get("id")
                if not _novo_evento(conn, f"msg:{wa_id}", "mensagem", wa_id, m):
                    res["repetidos"] += 1
                    continue
                numero = "+" + re.sub(r"\D", "", m.get("from", ""))
                texto = (m.get("text") or {}).get("body") or (m.get("button") or {}).get("text")
                c = conn.execute(
                    """select c.id, l.id as lead_id from contacts c left join leads l on l.holder_id = c.holder_id
                        where c.valor_normalizado = %s and c.tipo = 'whatsapp' order by c.id limit 1""",
                    (numero,),
                ).fetchone()
                conn.execute(
                    """insert into wa_messages (direcao, modo, contact_id, lead_id, numero, tipo, corpo, wa_message_id,
                                                status, recebida_em)
                       values ('entrada', 'real', %s, %s, %s, %s, %s, %s, 'recebida', %s)
                       on conflict (wa_message_id) do nothing""",
                    (c["id"] if c else None, c["lead_id"] if c else None, numero,
                     "texto" if m.get("type") == "text" else "outro", texto, wa_id, _ts(m.get("timestamp"))),
                )  # fmt: skip
                res["mensagens"] += 1
                if eh_optout(texto):
                    aplicar_optout(conn, numero, "whatsapp:resposta", f"respondeu: {(texto or '')[:60]}")
                    res["optouts"] += 1
    return res
