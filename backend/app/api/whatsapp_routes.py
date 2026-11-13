"""WhatsApp Business Platform: configuração, histórico, criação de mensagem e webhooks da Meta."""

import hmac
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from app import db, security, wa_cloud
from app.auth import User, current_user
from app.config import get_settings

router = APIRouter(prefix="/api/whatsapp", dependencies=[Depends(current_user)])
webhook = APIRouter(prefix="/webhooks/whatsapp")  # público: a Meta chama; protegido por token e assinatura

MAX_WEBHOOK = 1_000_000


@router.get("/status")
def status() -> dict:
    """Situação da integração. Só indica SE cada credencial existe; nunca devolve o valor."""
    s = get_settings()
    with db.get_pool().connection() as conn:
        hoje = conn.execute(
            """select count(*) filter (where direcao = 'saida' and modo = 'real' and aceita_em > date_trunc('day', now())) as enviadas_hoje,
                      count(*) filter (where status = 'na_fila') as na_fila,
                      count(*) filter (where direcao = 'entrada' and recebida_em > date_trunc('day', now())) as recebidas_hoje
                 from wa_messages"""
        ).fetchone()
    credenciais = {
        "WHATSAPP_PHONE_NUMBER_ID": bool(s.whatsapp_phone_number_id),
        "WHATSAPP_BUSINESS_ACCOUNT_ID": bool(s.whatsapp_business_account_id),
        "WHATSAPP_ACCESS_TOKEN": bool(s.whatsapp_access_token),
        "WHATSAPP_VERIFY_TOKEN": bool(s.whatsapp_verify_token),
        "WHATSAPP_APP_SECRET": bool(s.whatsapp_app_secret),
        "WHATSAPP_TEMPLATE_NAME": bool(s.whatsapp_template_name),
    }
    pendencias = [k for k, ok in credenciais.items() if not ok]
    if s.auth_mode == "dev":
        pendencias.append("login obrigatório (AUTH_MODE=supabase)")
    return {
        "configurado": wa_cloud.configurado(s),
        "envio_ativo": s.whatsapp_envio_ativo,
        "modo": "real" if (s.whatsapp_envio_ativo and wa_cloud.configurado(s)) else "simulacao",
        "credenciais": credenciais,
        "pendencias_para_envio_real": pendencias,
        "template": {"nome": s.whatsapp_template_name, "idioma": s.whatsapp_template_language},
        "numeros_teste": len(wa_cloud.numeros_teste(s)),
        "limites": {"por_minuto": s.whatsapp_limite_por_minuto, "por_dia": s.whatsapp_limite_por_dia},
        "webhook": "/webhooks/whatsapp",
    } | hoje


@router.post("/template/verificar")
def verificar_template() -> dict:
    return wa_cloud.template_status(force=True)


@router.get("/messages")
def list_messages(
    lead_id: int | None = None,
    direcao: Literal["saida", "entrada"] | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    p = {"lead": lead_id, "dir": direcao, "st": status, "l": limit, "o": offset}
    filtro = """ from wa_messages m
                where (%(lead)s::bigint is null or m.lead_id = %(lead)s)
                  and (%(dir)s::text is null or m.direcao = %(dir)s)
                  and (%(st)s::text is null or m.status = %(st)s)"""
    with db.get_pool().connection() as conn:
        total = conn.execute(f"select count(*) n {filtro}", p).fetchone()["n"]
        rows = conn.execute(
            f"""select m.*, h.nome_original as titular
                {
                filtro.replace(
                    "from wa_messages m",
                    "from wa_messages m left join leads l on l.id = m.lead_id left join holders h on h.id = l.holder_id",
                )
            }
                order by m.id desc limit %(l)s offset %(o)s""",
            p,
        ).fetchall()
    return {"total": total, "items": rows}


class MensagemIn(BaseModel):
    lead_id: int
    contact_id: int
    numero_processo: str | None = None
    params: list[str] | None = Field(default=None, max_length=10)


@router.post("/messages", status_code=201)
def create_message(body: MensagemIn, user: User = Depends(current_user)) -> dict:
    """Prepara UMA mensagem para UM contato. Com o envio desligado, fica como simulação."""
    try:
        with db.transaction(user.actor) as conn:
            return wa_cloud.criar_saida(
                conn, lead_id=body.lead_id, contact_id=body.contact_id, numero_processo=body.numero_processo, params=body.params
            )
    except wa_cloud.ErroDeRegra as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/messages/{message_id}/cancel")
def cancel_message(message_id: int, user: User = Depends(current_user)) -> dict:
    with db.transaction(user.actor) as conn:
        row = conn.execute(
            "update wa_messages set status = 'cancelada', motivo = %s where id = %s and status = 'na_fila' returning *",
            (f"cancelada por {user.actor}", message_id),
        ).fetchone()
    if row is None:
        raise HTTPException(409, "Só é possível cancelar mensagens que ainda estão na fila")
    return row


# ------------------------------------------------------------------ webhooks (Meta)
@webhook.get("")
def verify(request: Request) -> Response:
    """Verificação do webhook: a Meta envia o token que você cadastrou e espera o desafio de volta."""
    s = get_settings()
    q = request.query_params
    token = q.get("hub.verify_token") or ""
    if (
        s.whatsapp_verify_token
        and q.get("hub.mode") == "subscribe"
        and hmac.compare_digest(token.encode(), s.whatsapp_verify_token.encode())
    ):
        return Response(q.get("hub.challenge") or "", media_type="text/plain")
    raise HTTPException(403, "Verificação recusada")


@webhook.post("")
async def receive(request: Request) -> dict:
    s = get_settings()
    if not security.limite_webhook.permite(request.client.host if request.client else "?"):
        raise HTTPException(429, "Muitas requisições")
    if not s.whatsapp_app_secret:
        # sem o segredo não há como saber se o aviso veio mesmo da Meta: não aceitamos
        raise HTTPException(503, "Webhook não configurado")
    corpo = await request.body()
    if len(corpo) > MAX_WEBHOOK:
        raise HTTPException(413, "Corpo grande demais")
    if not wa_cloud.assinatura_valida(corpo, request.headers.get("X-Hub-Signature-256"), s.whatsapp_app_secret):
        raise HTTPException(401, "Assinatura inválida")
    try:
        payload = json.loads(corpo)
    except ValueError as exc:
        raise HTTPException(400, "JSON inválido") from exc
    if not isinstance(payload, dict):
        raise HTTPException(400, "JSON inválido")
    if s.mensageria_provedor != "meta":
        return {"ignorado": "Cloud API da Meta desativada (um provedor por vez)"}
    with db.transaction("webhook:whatsapp") as conn:
        return wa_cloud.processar_webhook(conn, payload)
