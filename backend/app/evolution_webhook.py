"""Webhook exclusivo da instância do INPI Agent na Evolution API (V2.5).

Só registra o necessário. NUNCA envia nada nem responde automaticamente.
  CONNECTION_UPDATE  atualiza o estado da conexão da instância.
  MESSAGES_UPDATE    avança o status de mensagens que o INPI Agent enviou (servidor, entregue, lida).
  MESSAGES_UPSERT    resposta de um contato que o INPI Agent abordou: marca "respondeu" (sem guardar o texto) e
                     aplica opt-out se a pessoa pedir para sair. Conversas de outros números são ignoradas e não são
                     gravadas.
  SEND_MESSAGE       apenas confirma ids conhecidos.
Eventos repetidos são ignorados (deduplicação).
"""

import hashlib
import json
from datetime import UTC, datetime

from psycopg.types.json import Jsonb

from app import evolution, wa_cloud

STATUS = {"SERVER_ACK": "enviada", "DELIVERY_ACK": "entregue", "READ": "lida", "PLAYED": "lida", "ERROR": "falhou"}
STATUS_NUM = {2: "enviada", 3: "entregue", 4: "lida", 5: "lida", 0: "falhou"}  # alguns builds mandam números
COLUNA = {"enviada": "enviada_em", "entregue": "entregue_em", "lida": "lida_em"}


def normalizar_evento(nome: str | None) -> str:
    return (nome or "").strip().upper().replace(".", "_").replace("-", "_")


def _lista(data) -> list[dict]:
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    return [data] if isinstance(data, dict) else []


def _novo(conn, chave: str, tipo: str, wa_id: str | None, payload: dict) -> bool:
    return (
        conn.execute(
            """insert into wa_webhook_events (event_key, tipo, wa_message_id, payload, provedor)
               values (%s, %s, %s, %s, 'evolution') on conflict (event_key) do nothing returning id""",
            (chave, tipo, wa_id, Jsonb(payload)),
        ).fetchone()
        is not None
    )


def _texto(msg: dict) -> str | None:
    m = msg.get("message") or {}
    return m.get("conversation") or (m.get("extendedTextMessage") or {}).get("text") or (m.get("buttonsResponseMessage") or {}).get(
        "selectedDisplayText"
    )


def processar(conn, evento: str, payload: dict) -> dict:
    ev = normalizar_evento(evento)
    res = {"evento": ev, "aplicados": 0, "ignorados": 0, "repetidos": 0, "optouts": 0}
    agora = datetime.now(UTC)
    if ev == "CONNECTION_UPDATE":
        d = payload.get("data") or {}
        estado = d.get("state") or d.get("status")
        chave = f"evo:conn:{estado}:{payload.get('date_time') or agora.isoformat()}"
        if not _novo(conn, chave, "outro", None, {"event": ev, "state": estado, "statusReason": d.get("statusReason")}):
            res["repetidos"] += 1
            return res
        conn.execute(
            """insert into wa_contas (provedor, instancia, status_conexao, verificado_em) values ('evolution', %s, %s, %s)
               on conflict (provedor, instancia) do update set status_conexao = excluded.status_conexao, verificado_em = excluded.verificado_em""",
            (payload.get("instance"), evolution.ESTADO.get(estado, estado or "desconhecido"), agora),
        )
        res["aplicados"] += 1
        return res

    if ev in ("MESSAGES_UPDATE", "SEND_MESSAGE"):
        for d in _lista(payload.get("data")):
            mid = d.get("keyId") or d.get("messageId") or (d.get("key") or {}).get("id")
            st = d.get("status")
            novo = STATUS.get(st) if isinstance(st, str) else STATUS_NUM.get(st)
            if ev == "SEND_MESSAGE":
                novo = "enviada"
            msg = conn.execute(
                "select * from wa_messages where wa_message_id = %s and provedor = 'evolution' for update", (mid,)
            ).fetchone() if mid else None  # fmt: skip
            if msg is None or novo is None:
                res["ignorados"] += 1  # mensagem que não é do INPI Agent: nada é gravado
                continue
            if not _novo(conn, f"evo:st:{mid}:{novo}", "status", mid, {"event": ev, "keyId": mid, "status": st}):
                res["repetidos"] += 1
                continue
            if novo == "falhou":
                if wa_cloud.RANK.get(msg["status"], 9) < wa_cloud.RANK["entregue"]:
                    conn.execute("update wa_messages set status = 'falhou', falhou_em = %s, motivo = 'erro informado pela Evolution' where id = %s",
                                 (agora, msg["id"]))  # fmt: skip
            else:
                avanca = msg["status"] in wa_cloud.RANK and wa_cloud.RANK[novo] > wa_cloud.RANK[msg["status"]]
                col = COLUNA[novo]
                conn.execute(f"update wa_messages set {col} = coalesce({col}, %s), status = %s where id = %s",
                             (agora, novo if avanca else msg["status"], msg["id"]))  # fmt: skip
            res["aplicados"] += 1
        return res

    if ev == "MESSAGES_UPSERT":
        for d in _lista(payload.get("data")):
            key = d.get("key") or {}
            if key.get("fromMe") or "@g.us" in (key.get("remoteJid") or ""):
                res["ignorados"] += 1  # enviada pelo próprio celular ou grupo: não é resposta
                continue
            numero = evolution.jid_para_e164(key.get("remoteJid"))
            # só contatos que o INPI Agent abordou de verdade; os demais nem são gravados
            abordado = conn.execute(
                """select contact_id, lead_id from wa_messages where provedor = 'evolution' and direcao = 'saida' and modo = 'real'
                      and numero = %s and status in ('aceita','enviada','entregue','lida') order by id desc limit 1""",
                (numero,),
            ).fetchone()
            if abordado is None:
                res["ignorados"] += 1
                continue
            mid = key.get("id") or hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()
            if not _novo(conn, f"evo:in:{mid}", "mensagem", mid, {"event": ev, "keyId": mid, "numero": numero}):
                res["repetidos"] += 1
                continue
            texto = _texto(d)
            conn.execute(
                """insert into wa_messages (direcao, modo, provedor, contact_id, lead_id, numero, tipo, corpo, wa_message_id,
                                            status, recebida_em, instancia)
                   values ('entrada','real','evolution',%s,%s,%s,'outro',null,%s,'recebida',%s,%s) on conflict (wa_message_id) do nothing""",
                (abordado["contact_id"], abordado["lead_id"], numero, mid, agora, payload.get("instance")),
            )  # o texto NÃO é guardado: a conversa continua só no celular
            if wa_cloud.eh_optout(texto):
                wa_cloud.aplicar_optout(conn, numero, "whatsapp:evolution", "pediu para sair")
                res["optouts"] += 1
            res["aplicados"] += 1
        return res

    res["ignorados"] += 1
    return res
