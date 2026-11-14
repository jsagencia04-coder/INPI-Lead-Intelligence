"""Comercial → Primeiro Contato e Integração WhatsApp (V2.5).

Nenhuma rota devolve credenciais. O navegador nunca fala com a Evolution: só o backend (e o worker) têm a chave.
"""

import hmac
import json
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app import db, evolution, evolution_webhook, modelos, primeiro_contato, security
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
            """select m.id, m.direcao, m.modo, m.status, m.motivo, m.numero, m.numero_processo, m.criado_por, m.criado_em, m.aceita_em,
                      m.enviada_em, m.entregue_em, m.lida_em, m.recebida_em, m.falhou_em, m.wa_message_id, m.erro_codigo, m.visto_em,
                      case when m.direcao = 'saida' then m.corpo end as corpo, md.codigo as modelo_codigo, md.nome as modelo_nome,
                      r.aprovado_por, r.aprovado_em, r.finalidade
                 from wa_messages m left join wa_modelos md on md.id = m.modelo_id left join wa_rascunhos r on r.id = m.rascunho_id
                where m.lead_id = %s and m.provedor = 'evolution' order by m.id desc""",
            (lead_id,),
        ).fetchall()
        lista_modelos = [
            {k: m[k] for k in ("codigo", "nome", "descricao", "tipo_oportunidade", "finalidade", "ativo", "versao")}
            | {"compativel": modelos.compativel(m["codigo"], f["oportunidade"])}
            for m in modelos.listar(conn)
        ]
        modelo_rascunho = conn.execute("select codigo, nome, versao from wa_modelos where id = %s", (r["modelo_id"],)).fetchone() if r and r.get("modelo_id") else None
        verifs = primeiro_contato.verificacoes(conn, r, papel=user.papel) if r else []
        historico = conn.execute("select * from wa_auditoria where lead_id = %s order by id desc limit 50", (lead_id,)).fetchall()
    return {"lead": f["lead"], "oportunidade": f["oportunidade"], "contatos": contatos, "rascunho": r,
            "consentimentos": consentimentos, "envios": envios, "verificacoes": verifs, "historico": historico,
            "modo": evolution.modo(), "provedor": get_settings().mensageria_provedor,
            "modelos": lista_modelos, "modelo_sugerido": modelos.sugerido(f["oportunidade"]), "modelo_rascunho": modelo_rascunho}  # fmt: skip


# ------------------------------------------------------------------ rascunho
class GerarIn(BaseModel):
    contact_id: int | None = None
    modelo: Literal["MODELO_01", "MODELO_02", "MODELO_03"] | None = None  # vazio = sugerido pela oportunidade


@router.post("/primeiro-contato/{lead_id}/rascunho", status_code=201)
def gerar(lead_id: int, body: GerarIn, user: User = Depends(current_user)) -> dict:
    with db.transaction(user.actor) as conn:
        return _rec(lambda: primeiro_contato.criar_rascunho(conn, lead_id, body.contact_id, user.actor, body.modelo))


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


class EnviarIn(BaseModel):
    chave: str | None = Field(None, min_length=8, max_length=64, pattern=r"^[A-Za-z0-9-]+$")  # idempotência do clique


@router.post("/rascunhos/{rid}/enviar")
def enviar(rid: int, body: EnviarIn | None = None, user: User = Depends(current_user)) -> dict:
    """Envio direto pelo backend (V2.7): valida, registra e faz UMA chamada à Evolution nesta mesma requisição.
    O navegador não abre nada nem fala com a Evolution. Repetir o mesmo clique (mesma chave) devolve o mesmo envio.
    Se a chamada não terminar (tempo esgotado), o resultado fica "conferir no celular" e nada é reenviado sozinho."""
    with db.transaction(user.actor) as conn:
        m = _rec(lambda: primeiro_contato.solicitar_envio(conn, rid, user.actor, user.papel, body.chave if body else None))
    if m["status"] == "na_fila":
        with db.transaction("agent:whatsapp.evolution_send") as conn:
            primeiro_contato.executar_envio(conn, m["id"])
    return mensagem(m["id"])


class UmCliqueIn(BaseModel):
    contact_id: int | None = None
    texto: str | None = Field(None, max_length=1500)
    chave: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9-]+$")


@router.post("/primeiro-contato/{lead_id}/enviar")
def enviar_um_clique(lead_id: int, body: UmCliqueIn, user: User = Depends(current_user)) -> dict:
    """V2.8 · Botão "Enviar" do card do lead: aprova o texto mostrado e envia na hora, pelo backend (Evolution).
    Todas as regras continuam valendo (autorização do destinatário, opt-out, limites, número de teste...)."""
    try:
        with db.transaction(user.actor) as conn:
            m = primeiro_contato.enviar_um_clique(conn, lead_id, body.contact_id, body.texto, user.actor, user.papel, body.chave)
    except Recusado as exc:
        with db.transaction(user.actor) as conn:  # a recusa fica registrada mesmo com a transação desfeita
            primeiro_contato.auditar(conn, "envio_um_clique_recusado", lead_id, motivo=str(exc))
        raise HTTPException(409, str(exc)) from exc
    if m["status"] == "na_fila":
        with db.transaction("agent:whatsapp.evolution_send") as conn:
            primeiro_contato.executar_envio(conn, m["id"])
    return mensagem(m["id"])


@router.get("/wa-mensagens/{mid}")
def mensagem(mid: int) -> dict:
    """Situação de um envio, para a tela acompanhar sem recarregar (aceita → entregue/lida pelo webhook)."""
    with db.get_pool().connection() as conn:
        m = conn.execute(
            """select id, lead_id, rascunho_id, status, modo, motivo, wa_message_id, criado_em, aceita_em, enviada_em, entregue_em,
                      lida_em, falhou_em, erro_codigo from wa_messages where id = %s and provedor = 'evolution'""",
            (mid,),
        ).fetchone()
    if m is None:
        raise HTTPException(404, "Envio não encontrado")
    return m


# ------------------------------------------------------------------ respostas recebidas (aviso na tela; nada é respondido)
@router.get("/primeiro-contato-respostas")
def respostas() -> dict:
    with db.get_pool().connection() as conn:
        itens = conn.execute(
            """select m.id, m.lead_id, m.numero, m.recebida_em, m.criado_em, h.nome_original as titular
                 from wa_messages m join leads l on l.id = m.lead_id join holders h on h.id = l.holder_id
                where m.provedor = 'evolution' and m.direcao = 'entrada' and m.visto_em is null order by m.id desc limit 50"""
        ).fetchall()
    return {"novas": len(itens), "itens": itens}


@router.post("/primeiro-contato-respostas/vistas")
def marcar_vistas(user: User = Depends(current_user)) -> dict:
    with db.transaction(user.actor) as conn:
        n = conn.execute("update wa_messages set visto_em = now() where provedor = 'evolution' and direcao = 'entrada' and visto_em is null")
        return {"marcadas": n.rowcount}


# ------------------------------------------------------------------ V2.7 · modelos de mensagem (textos no banco)
@router.get("/wa-modelos")
def listar_modelos() -> dict:
    with db.get_pool().connection() as conn:
        return {"modelos": modelos.listar(conn), "remetente": modelos.remetente(conn), "variaveis": modelos.VARIAVEIS}


class ModeloIn(BaseModel):
    nome: str = Field(min_length=3, max_length=80)
    descricao: str = Field(min_length=3, max_length=300)
    texto: str = Field(min_length=20, max_length=1500)
    ativo: bool
    versao: int


@router.put("/wa-modelos/{codigo}")
def salvar_modelo(codigo: Literal["MODELO_01", "MODELO_02", "MODELO_03"], body: ModeloIn, user: User = Depends(current_user)) -> dict:
    with db.transaction(user.actor) as conn:
        try:
            return modelos.salvar(conn, codigo, nome=body.nome, descricao=body.descricao, texto=body.texto, ativo=body.ativo,
                                  versao=body.versao, ator=user.actor)  # fmt: skip
        except modelos.ModeloInvalido as exc:
            raise HTTPException(409, str(exc)) from exc


@router.get("/wa-modelos/{codigo}/historico")
def historico_modelo(codigo: str) -> list[dict]:
    with db.get_pool().connection() as conn:
        return conn.execute(
            """select h.* from wa_modelos_historico h join wa_modelos m on m.id = h.modelo_id where m.codigo = %s
                order by h.versao desc""",
            (codigo,),
        ).fetchall()


class PreviaIn(BaseModel):
    texto: str | None = Field(None, max_length=1500)  # texto ainda não salvo (testar antes de salvar)
    lead_id: int | None = None                         # lead real para a prévia (nada é gravado)


@router.post("/wa-modelos/{codigo}/previa")
def previa(codigo: Literal["MODELO_01", "MODELO_02", "MODELO_03"], body: PreviaIn) -> dict:
    with db.get_pool().connection() as conn:
        m = modelos.obter(conn, codigo)
        if body.lead_id:
            f = _rec(lambda: primeiro_contato.fatos(conn, body.lead_id))
            lead, op = f["lead"], f["oportunidade"]
        else:  # exemplo fictício, claramente marcado
            lead = {"titular": "EMPRESA EXEMPLO LTDA (exemplo)", "geo_uf": "SC"}
            op = {"marca_nome": "MARCA EXEMPLO", "numero_processo": "900000000", "tipo_decisao": m["tipo_oportunidade"]
                  if m["tipo_oportunidade"] != "institucional" else None, "rpi_numero": 2914}  # fmt: skip
        texto, alertas, usadas = modelos.renderizar(body.texto or m["texto"], modelos.valores(conn, lead, op))
    return {"texto": texto, "alertas": alertas, "variaveis": usadas, "exemplo": not body.lead_id,
            "compativel": modelos.compativel(codigo, op) if body.lead_id else True}  # fmt: skip


class RemetenteIn(BaseModel):
    nome_atendente: str = Field(max_length=80)
    empresa: str = Field(max_length=120)


@router.put("/wa-modelos-remetente")
def salvar_remetente(body: RemetenteIn, user: User = Depends(current_user)) -> dict:
    with db.transaction(user.actor) as conn:
        return modelos.salvar_remetente(conn, body.nome_atendente, body.empresa)


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
