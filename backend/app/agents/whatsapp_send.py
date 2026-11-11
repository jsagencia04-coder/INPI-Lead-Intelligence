"""Agente de envio do WhatsApp (Cloud API oficial). Um job por mensagem; nunca envia em massa."""

import httpx

from app import wa_cloud
from app.jobs.registry import JobContext, RetryLater, handler

INCERTO = "resultado incerto: a Meta pode ter recebido. Não reenviado automaticamente para evitar duplicidade"


@handler("whatsapp.send")
def whatsapp_send(conn, ctx: JobContext) -> dict:
    msg = conn.execute("select * from wa_messages where id = %s for update", (int(ctx.payload["message_id"]),)).fetchone()
    if msg is None or msg["status"] != "na_fila" or msg["direcao"] != "saida":
        return {"ignorado": "mensagem não está na fila"}

    def fim(status: str, motivo: str | None, codigo: str | None = None) -> dict:
        conn.execute(
            f"""update wa_messages set status = %s, motivo = %s, erro_codigo = %s, tentativas = tentativas + 1
                {", falhou_em = now()" if status == "falhou" else ""} where id = %s""",
            (status, motivo, codigo, msg["id"]),
        )
        return {"status": status, "motivo": motivo}

    motivo = wa_cloud.bloqueio(conn, msg)
    if motivo:
        return fim("bloqueada", motivo)
    espera = wa_cloud.limite_atingido(conn)
    if espera:
        raise RetryLater("limite de envio atingido", espera)

    try:
        resp = wa_cloud.chamar_api(msg)
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise RetryLater(f"sem conexão com a Meta ({type(exc).__name__})", 120) from exc  # pedido não chegou a sair
    except httpx.HTTPError as exc:
        return fim("falhou", f"{INCERTO} ({type(exc).__name__})")

    if resp.status_code == 200:
        try:
            wa_id = resp.json()["messages"][0]["id"]
        except (ValueError, KeyError, IndexError):
            return fim("falhou", INCERTO + " (resposta sem id)")
        conn.execute(
            "update wa_messages set status = 'aceita', wa_message_id = %s, aceita_em = now(), tentativas = tentativas + 1"
            " where id = %s",
            (wa_id, msg["id"]),
        )
        # a partir daqui, 'enviada', 'entregue' e 'lida' só chegam pelo webhook
        return {"status": "aceita", "wa_message_id": wa_id}

    codigo, texto = wa_cloud._erro_meta(resp)
    if resp.status_code == 429 or (codigo.isdigit() and int(codigo) in wa_cloud.CODIGOS_LIMITE):
        raise RetryLater(f"Meta pediu para reduzir o ritmo (código {codigo})", 300)
    if resp.status_code >= 500:
        return fim("falhou", f"{INCERTO} (HTTP {resp.status_code})", codigo)
    return fim("falhou", f"recusada pela Meta: {texto}", codigo)
