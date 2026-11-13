"""Comercial → Primeiro Contato e Integração WhatsApp (V2.5).

Nenhuma rota devolve credenciais. O navegador nunca fala com a Evolution: só o backend (e o worker) têm a chave.
"""

import hmac
import json
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app import db, evolution, evolution_webhook, primeiro_contato, security
from app.auth import User, current_user
from app.config import get_settings
from app.primeiro_contato import Recusado

router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])
webhook = APIRouter(prefix="/webhooks/evolution")  # público: a Evolution chama; protegido por token na URL
MAX_WEBHOOK = 256_000


def _rec(fn):
    try:
        return fn()
    except Recusado as exc:
        raise HTTPException(409, str(exc)) from exc


# ------------------------------------------------------------------ lista e detalhe
@router.get("/primeiro-contato")
def listar(classificacao: Literal["quente", "morno", "pendente", "historico"] | None = None,
           situacao: Literal["sem_rascunho", "rascunho", "aprovado", "enviado", "rejeitado"] | None = None,
           uf: str | None = None, q: str | None = None, limite: int = 100) -> list[dict]:  # fmt: skip
    """Leads das duas frentes que têm WhatsApp encontrado, com a situação do rascunho e do consentimento."""
    with db.get_pool().connection() as conn:
        return conn.execute(
            """with base as (
                 select l.id as lead_id, h.nome_original as titular, h.geo_uf, h.geo_municipio, l.pipeline_stage, l.status as lead_status,
                        coalesce(l.classificacao_oposicao, l.classificacao_recurso) as classe_principal, l.servico_principal,
                        l.classificacao_oposicao, l.classificacao_recurso,
                        os.numero_processo, os.servico, os.tipo_decisao, os.data_publicacao, os.prazo_fim, p.marca_nome,
                        c.id as contact_id, c.valor_normalizado as whatsapp, c.wa_nivel, c.fonte_tipo as origem_tipo,
                        (select e.url from evidences e where e.id = c.evidence_id) as origem_url,
                        (select k.status from consents k where k.contact_id = c.id and k.canal = 'whatsapp' order by k.id desc limit 1) as consentimento,
                        (select row_to_json(r) from (select r.id, r.status, r.versao, r.aprovado_por, r.updated_at from wa_rascunhos r
                           where r.lead_id = l.id order by r.id desc limit 1) r) as rascunho,
                        (select m.status from wa_messages m where m.lead_id = l.id and m.direcao = 'saida' and m.provedor = 'evolution'
                           order by m.id desc limit 1) as contato_status
                   from leads l join holders h on h.id = l.holder_id
                   join lateral (select * from contacts c where c.holder_id = l.holder_id and c.tipo = 'whatsapp' and c.verificacao <> 'invalido'
                                  order by (c.wa_nivel = 'human_confirmed') desc, (c.wa_nivel = 'company_evidence') desc, c.confianca desc nulls last
                                  limit 1) c on true
                   left join lateral (select os.* from oportunidades_servico os join lead_processes lp on lp.numero_processo = os.numero_processo
                                      where lp.lead_id = l.id order by (os.situacao_processual = 'aberta') desc, os.prazo_fim nulls last limit 1) os on true
                   left join processes p on p.numero_processo = os.numero_processo
                  where l.mesclado_em is null and l.status <> 'descartado' and l.servico_principal is not null)
               select * from base
                where (%(cl)s::text is null or classe_principal = %(cl)s)
                  and (%(uf)s::text is null or geo_uf = %(uf)s)
                  and (%(q)s::text is null or titular ilike '%%' || %(q)s || '%%' or marca_nome ilike '%%' || %(q)s || '%%'
                       or numero_processo = %(q)s)
                  and (%(sit)s::text is null or (%(sit)s = 'sem_rascunho' and rascunho is null) or rascunho->>'status' = %(sit)s)
                order by case classe_principal when 'quente' then 0 when 'morno' then 1 when 'pendente' then 2 else 3 end,
                         prioridade_fila_uf(geo_uf), prazo_fim nulls last
                limit %(lim)s""",
            {"cl": classificacao, "uf": uf, "q": q, "sit": situacao, "lim": min(limite, 300)},
        ).fetchall()


@router.get("/primeiro-contato/{lead_id}")
def detalhe(lead_id: int, user: User = Depends(current_user)) -> dict:
    with db.get_pool().connection() as conn:
        f = _rec(lambda: primeiro_contato.fatos(conn, lead_id))
        contatos = conn.execute(
            """select c.id, c.valor_normalizado as numero, c.wa_nivel, c.verificacao, c.fonte_tipo, e.url as fonte_url
                 from contacts c join leads l on l.holder_id = c.holder_id left join evidences e on e.id = c.evidence_id
                where l.id = %s and c.tipo = 'whatsapp' order by c.id""",
            (lead_id,),
        ).fetchall()
        r = conn.execute("select * from wa_rascunhos where lead_id = %s order by id desc limit 1", (lead_id,)).fetchone()
        consentimentos = conn.execute(
            """select k.id, k.contact_id, k.status, k.metodo, k.finalidade, k.empresa_identificada, k.obtido_em, k.fonte_evidencia,
                      k.revogado_em from consents k join contacts c on c.id = k.contact_id join leads l on l.holder_id = c.holder_id
                where l.id = %s and k.canal = 'whatsapp' order by k.id desc""",
            (lead_id,),
        ).fetchall()
        envios = conn.execute(
            """select id, direcao, modo, status, motivo, numero, criado_por, criado_em, aceita_em, entregue_em, lida_em, recebida_em
                 from wa_messages where lead_id = %s and provedor = 'evolution' order by id desc""",
            (lead_id,),
        ).fetchall()
        verifs = primeiro_contato.verificacoes(conn, r, papel=user.papel) if r else []
        historico = conn.execute("select * from wa_auditoria where lead_id = %s order by id desc limit 50", (lead_id,)).fetchall()
    return {"lead": f["lead"], "oportunidade": f["oportunidade"], "contatos": contatos, "rascunho": r,
            "consentimentos": consentimentos, "envios": envios, "verificacoes": verifs, "historico": historico,
            "modo": evolution.modo(), "provedor": get_settings().mensageria_provedor}  # fmt: skip


# ------------------------------------------------------------------ rascunho
class GerarIn(BaseModel):
    contact_id: int | None = None


@router.post("/primeiro-contato/{lead_id}/rascunho", status_code=201)
def gerar(lead_id: int, body: GerarIn, user: User = Depends(current_user)) -> dict:
    with db.transaction(user.actor) as conn:
        return _rec(lambda: primeiro_contato.criar_rascunho(conn, lead_id, body.contact_id, user.actor))


class EditarIn(BaseModel):
    conteudo: str = Field(min_length=1, max_length=1500)
    versao: int


@router.patch("/rascunhos/{rid}")
def editar(rid: int, body: EditarIn, user: User = Depends(current_user)) -> dict:
    with db.transaction(user.actor) as conn:
        return _rec(lambda: primeiro_contato.editar(conn, rid, body.conteudo, body.versao, user.actor))


class RejeitarIn(BaseModel):
    motivo: str = Field(min_length=3, max_length=300)


@router.post("/rascunhos/{rid}/rejeitar")
def rejeitar(rid: int, body: RejeitarIn, user: User = Depends(current_user)) -> dict:
    with db.transaction(user.actor) as conn:
        return _rec(lambda: primeiro_contato.rejeitar(conn, rid, body.motivo, user.actor))


class AprovarIn(BaseModel):
    versao: int
    conteudo_hash: str = Field(min_length=64, max_length=64)
    numero: str
    canal: Literal["evolution", "manual", "meta"]


@router.post("/rascunhos/{rid}/aprovar")
def aprovar(rid: int, body: AprovarIn, user: User = Depends(current_user)) -> dict:
    with db.transaction(user.actor) as conn:
        return _rec(lambda: primeiro_contato.aprovar(conn, rid, body.versao, body.conteudo_hash, body.numero, body.canal,
                                                     user.actor, user.papel))  # fmt: skip


@router.post("/rascunhos/{rid}/enviar", status_code=202)
def enviar(rid: int, user: User = Depends(current_user)) -> dict:
    with db.transaction(user.actor) as conn:
        return _rec(lambda: primeiro_contato.solicitar_envio(conn, rid, user.actor, user.papel))


@router.post("/rascunhos/{rid}/abrir-whatsapp")
def abrir(rid: int, user: User = Depends(current_user)) -> dict:
    """Envio manual: devolve o link wa.me com o texto. NÃO marca como enviada."""
    with db.transaction(user.actor) as conn:
        r = conn.execute("select * from wa_rascunhos where id = %s", (rid,)).fetchone()
        if r is None:
            raise HTTPException(404, "Rascunho não encontrado")
        primeiro_contato.auditar(conn, "abrir_whatsapp", r["lead_id"], rascunho_id=rid, versao=r["versao"])
    return {"url": f"https://wa.me/{evolution.digitos(r['numero'])}?text={quote(r['conteudo'])}",
            "aviso": "Abrir o link não registra envio. Depois de enviar pelo celular, registre a prospecção no lead."}  # fmt: skip


class ReconciliarIn(BaseModel):
    resultado: Literal["enviada", "nao_enviada"]


@router.post("/wa-mensagens/{mid}/reconciliar")
def reconciliar(mid: int, body: ReconciliarIn, user: User = Depends(current_user)) -> dict:
    with db.transaction(user.actor) as conn:
        return _rec(lambda: primeiro_contato.reconciliar(conn, mid, body.resultado, user.actor))


# ------------------------------------------------------------------ Integração WhatsApp (sem credenciais)
@router.get("/integracao-whatsapp")
def integracao() -> dict:
    s = get_settings()
    with db.get_pool().connection() as conn:
        conta = conn.execute("select provedor, instancia, numero, status_conexao, verificado_em, detalhes from wa_contas"
                             " where provedor = 'evolution' and instancia = %s", (s.evolution_instance_name,)).fetchone()  # fmt: skip
        n = conn.execute(
            """select (select count(*) from wa_rascunhos where status = 'rascunho') as rascunhos,
                      (select count(*) from wa_rascunhos where status = 'aprovado') as aprovados,
                      (select count(*) from wa_rascunhos where status = 'rascunho' and conteudo is not null) as aguardando_aprovacao,
                      (select count(*) from wa_messages where provedor = 'evolution' and direcao = 'saida' and modo = 'real'
                         and status in ('aceita','enviada','entregue','lida')) as enviados,
                      (select count(*) from wa_messages where provedor = 'evolution' and direcao = 'saida' and status = 'simulada') as simulados,
                      (select count(*) from wa_messages where provedor = 'evolution' and direcao = 'saida' and status = 'falhou') as falhas,
                      (select count(*) from wa_messages where provedor = 'evolution' and status = 'reconciliar') as a_conferir,
                      (select count(*) from wa_messages where provedor = 'evolution' and direcao = 'entrada') as respostas,
                      (select count(*) from suppression_list) as bloqueados"""
        ).fetchone()
        bloqueado = primeiro_contato.envio_bloqueado(conn)
    return {
        "provedor": s.mensageria_provedor,
        "instancia": s.evolution_instance_name,
        "configurada": evolution.configurada(s),
        "simulacao": s.evolution_simulation,
        "envio_habilitado": s.evolution_send_enabled,
        "modo": evolution.modo(s),
        "envio_bloqueado": bloqueado,
        "numero_autorizado": s.evolution_numero_autorizado,
        "numeros_teste": len(evolution.numeros_teste(s)),
        "webhook": f"/webhooks/evolution/{s.evolution_instance_name}?token=<EVOLUTION_WEBHOOK_TOKEN>",
        "webhook_configurado": bool(s.evolution_webhook_token),
        "remetente_configurado": bool(s.primeiro_contato_remetente),
        "meta_cloud_api": "desativada" if s.mensageria_provedor != "meta" else "ativa",
        "conta": conta,
        "contadores": n,
    }


@router.post("/integracao-whatsapp/testar")
def testar(user: User = Depends(current_user)) -> dict:
    """Só verifica a conexão (estado e número). Não envia mensagem."""
    with db.transaction(user.actor) as conn:
        r = evolution.verificar_conexao(conn)
        primeiro_contato.auditar(conn, "testar_conexao", None, status=r["status"], numero_confere=r["numero_confere"])
    return r


@router.post("/integracao-whatsapp/desativar-envios")
def desativar(user: User = Depends(current_user)) -> dict:
    """Emergência: bloqueia novos envios no backend e no worker imediatamente; cancela os que estão na fila."""
    with db.transaction(user.actor) as conn:
        conn.execute("update app_config set valor = 'true', atualizado_em = now() where chave = 'whatsapp_envio_bloqueado'")
        n = conn.execute("""update wa_messages set status = 'cancelada', motivo = 'envios desativados (emergência)'
                             where provedor = 'evolution' and status = 'na_fila' returning id""").fetchall()  # fmt: skip
        primeiro_contato.auditar(conn, "envios_desativados", None, cancelados=len(n))
    return {"envio_bloqueado": True, "cancelados": len(n)}


@router.post("/integracao-whatsapp/reativar-envios")
def reativar(user: User = Depends(current_user)) -> dict:
    with db.transaction(user.actor) as conn:
        conn.execute("update app_config set valor = 'false', atualizado_em = now() where chave = 'whatsapp_envio_bloqueado'")
        primeiro_contato.auditar(conn, "envios_reativados", None)
    return {"envio_bloqueado": False}


# ------------------------------------------------------------------ webhook exclusivo da instância
@webhook.post("/{instancia}")
@webhook.post("/{instancia}/{evento}")
async def receber(instancia: str, request: Request, evento: str | None = None) -> dict:
    s = get_settings()
    if not security.limite_webhook.permite(request.client.host if request.client else "?"):
        raise HTTPException(429, "Muitas requisições")
    if not s.evolution_webhook_token:
        raise HTTPException(503, "Webhook da Evolution não configurado")
    token = request.query_params.get("token") or request.headers.get("x-webhook-token") or ""
    if not hmac.compare_digest(token, s.evolution_webhook_token):
        raise HTTPException(403, "Token inválido")
    if instancia != s.evolution_instance_name:
        raise HTTPException(403, "Instância não autorizada")
    corpo = await request.body()
    if len(corpo) > MAX_WEBHOOK:
        raise HTTPException(413, "Payload grande demais")
    try:
        payload = json.loads(corpo or b"{}")
    except ValueError as exc:
        raise HTTPException(400, "JSON inválido") from exc
    if not isinstance(payload, dict):
        raise HTTPException(400, "Formato inesperado")
    if payload.get("instance") not in (None, s.evolution_instance_name):
        raise HTTPException(403, "Evento de outra instância")
    chave = payload.get("apikey")
    if chave and s.evolution_api_key and not hmac.compare_digest(str(chave), s.evolution_api_key):
        raise HTTPException(403, "Evento com chave de outra instância")
    if s.mensageria_provedor != "evolution":
        return {"ignorado": "provedor Evolution não está selecionado"}
    with db.transaction("webhook:evolution") as conn:
        return evolution_webhook.processar(conn, evento or payload.get("event") or "", payload)
