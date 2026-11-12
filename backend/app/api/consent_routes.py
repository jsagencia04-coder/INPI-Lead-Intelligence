"""Consentimentos: registrar, revogar, pedir por outro canal e conferir a elegibilidade de um contato."""

from datetime import datetime
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import consent, db, wa_cloud
from app.auth import User, current_user

router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])


def _contato(conn, contact_id: int) -> dict:
    c = conn.execute("select * from contacts where id = %s", (contact_id,)).fetchone()
    if c is None:
        raise HTTPException(404, "Contato não encontrado")
    return c


@router.get("/contacts/{contact_id}/consents")
def list_consents(contact_id: int) -> dict:
    with db.get_pool().connection() as conn:
        _contato(conn, contact_id)
        return {
            "consentimentos": conn.execute("select * from consents where contact_id = %s order by id desc", (contact_id,)).fetchall(),
            "pedidos": conn.execute("select * from consent_requests where contact_id = %s order by id desc", (contact_id,)).fetchall(),
            "aviso_versao": consent.AVISO_VERSAO,
            "finalidade_padrao": consent.FINALIDADE_PADRAO,
        }


@router.get("/contacts/{contact_id}/elegibilidade")
def get_elegibilidade(contact_id: int) -> dict:
    """Mostra regra por regra por que um contato pode (ou não) receber WhatsApp."""
    tpl = wa_cloud.template_status() if wa_cloud.configurado() else {"ok": False, "motivo": "integração com a Meta não configurada"}
    with db.get_pool().connection() as conn:
        return consent.elegibilidade(conn, contact_id, template=tpl)


class ConsentIn(BaseModel):
    canal: Literal["whatsapp", "email", "telefone"] = "whatsapp"
    finalidade: str = Field(default=consent.FINALIDADE_PADRAO, min_length=5, max_length=300)
    empresa_identificada: str = Field(min_length=2, max_length=200)
    obtido_em: datetime
    metodo: Literal["resposta_whatsapp", "email", "formulario", "telefone", "presencial", "contrato", "outro"]
    fonte_evidencia: str = Field(min_length=3, max_length=500)
    texto_autorizacao: str = Field(min_length=2, max_length=2000)
    numero_fornecido: bool = False
    pedido_id: int | None = None


@router.post("/contacts/{contact_id}/consents", status_code=201)
def create_consent(contact_id: int, body: ConsentIn, user: User = Depends(current_user)) -> dict:
    """Registra uma autorização REAL, com a prova. Quem registra responde por ela (fica na auditoria)."""
    with db.transaction(user.actor) as conn:
        c = _contato(conn, contact_id)
        if c["verificacao"] == "invalido":
            raise HTTPException(409, "Contato inválido ou em opt-out")
        if conn.execute("select 1 from suppression_list where valor_hash = %s", (consent._hash(c["valor_normalizado"]),)).fetchone():
            raise HTTPException(409, "Contato na lista de opt-out: não é possível registrar autorização")
        if body.obtido_em.timestamp() > datetime.now().timestamp() + 300:
            raise HTTPException(422, "A data da autorização não pode estar no futuro")
        if conn.execute(
            "select 1 from consents where contact_id = %s and canal = %s and finalidade = %s and status = 'ativo'",
            (contact_id, body.canal, body.finalidade),
        ).fetchone():
            raise HTTPException(409, "Já existe autorização ativa para este contato, canal e finalidade")
        row = conn.execute(
            """insert into consents (contact_id, canal, finalidade, empresa_identificada, obtido_em, metodo, fonte_evidencia,
                                     texto_autorizacao, versao_aviso, numero_fornecido, registrado_por)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning *""",
            (contact_id, body.canal, body.finalidade, body.empresa_identificada, body.obtido_em, body.metodo,
             body.fonte_evidencia, body.texto_autorizacao, consent.AVISO_VERSAO, body.numero_fornecido, user.actor),
        ).fetchone()  # fmt: skip
        if body.pedido_id:
            conn.execute(
                "update consent_requests set status = 'autorizado', consent_id = %s, respondido_em = now()"
                " where id = %s and contact_id = %s",
                (row["id"], body.pedido_id, contact_id),
            )
    return row


class RevokeIn(BaseModel):
    origem: str = Field(min_length=3, max_length=200)


@router.post("/consents/{consent_id}/revoke")
def revoke_consent(consent_id: int, body: RevokeIn, user: User = Depends(current_user)) -> dict:
    with db.transaction(user.actor) as conn:
        row = conn.execute(
            """update consents set status = 'revogado', revogado_em = now(), revogacao_origem = %s
                where id = %s and status = 'ativo' returning *""",
            (f"{body.origem} (por {user.actor})", consent_id),
        ).fetchone()
        if row is None:
            raise HTTPException(409, "Autorização não encontrada ou já revogada")
        # sem autorização, nada pendente pode sair
        c = conn.execute("select valor_normalizado from contacts where id = %s", (row["contact_id"],)).fetchone()
        conn.execute(
            "update wa_messages set status = 'cancelada', motivo = 'autorização revogada' where numero = %s and status = 'na_fila'",
            (c["valor_normalizado"],),
        )
    return row


class PedidoIn(BaseModel):
    via_contact_id: int
    empresa_identificada: str = Field(min_length=2, max_length=200)


@router.post("/contacts/{contact_id}/consent-requests", status_code=201)
def create_request(contact_id: int, body: PedidoIn, user: User = Depends(current_user)) -> dict:
    """Prepara o pedido de autorização por e-mail. O sistema NÃO envia: devolve o texto e o link para você enviar."""
    with db.transaction(user.actor) as conn:
        c = _contato(conn, contact_id)
        via = conn.execute(
            "select * from contacts where id = %s and holder_id = %s and tipo = 'email' and verificacao <> 'invalido'",
            (body.via_contact_id, c["holder_id"]),
        ).fetchone()
        if via is None:
            raise HTTPException(409, "Escolha um e-mail válido do mesmo titular para fazer o pedido")
        for alvo in (c, via):
            if conn.execute("select 1 from suppression_list where valor_hash = %s", (consent._hash(alvo["valor_normalizado"]),)).fetchone():
                raise HTTPException(409, "Contato na lista de opt-out")
        if conn.execute(
            "select 1 from consent_requests where contact_id = %s and status = 'enviado' and criado_em > now() - interval '30 days'",
            (contact_id,),
        ).fetchone():
            raise HTTPException(409, "Já existe um pedido de autorização em aberto para este contato (últimos 30 dias)")
        p = conn.execute(
            """select p.numero_processo, p.marca_nome from process_holders ph join processes p using (numero_processo)
                where ph.holder_id = %s order by p.numero_processo desc limit 1""",
            (c["holder_id"],),
        ).fetchone()
        texto = consent.PEDIDO_TEXTO.format(
            empresa=body.empresa_identificada, processo=p["numero_processo"] if p else "—", marca=(p or {}).get("marca_nome") or "—"
        )
        row = conn.execute(
            """insert into consent_requests (contact_id, via_contact_id, canal_pedido, finalidade, texto, versao_aviso, criado_por)
               values (%s, %s, 'email', %s, %s, %s, %s) returning *""",
            (contact_id, via["id"], consent.FINALIDADE_PADRAO, texto, consent.AVISO_VERSAO, user.actor),
        ).fetchone()
    assunto = "Publicação do INPI sobre a sua marca"
    return row | {"para": via["valor_normalizado"], "mailto": f"mailto:{via['valor_normalizado']}?subject={quote(assunto)}&body={quote(texto)}"}


class PedidoPatch(BaseModel):
    status: Literal["recusado", "sem_resposta"]


@router.post("/consent-requests/{request_id}/close")
def close_request(request_id: int, body: PedidoPatch, user: User = Depends(current_user)) -> dict:
    with db.transaction(user.actor) as conn:
        row = conn.execute(
            "update consent_requests set status = %s, respondido_em = now() where id = %s and status = 'enviado' returning *",
            (body.status, request_id),
        ).fetchone()
    if row is None:
        raise HTTPException(409, "Pedido não encontrado ou já encerrado")
    return row
