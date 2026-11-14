"""V2.5 · Primeiro contato supervisionado pela Evolution API — os 20 cenários da simulação (Fase 11).

Nada sai do sistema: a Evolution é simulada (httpx.MockTransport). O lead é real (944040470 · TELEVAULT, CEI, SC,
oposição sofrida na RPI 2914); o contato e a autorização são fictícios, criados só para o teste.
"""

import json
import os

import httpx
import pytest
from fastapi.testclient import TestClient

from app import evolution, evolution_webhook, primeiro_contato, wa_cloud
from app.config import get_settings
from app.main import app
from app.primeiro_contato import Recusado
from tests.test_fases3a7 import drain
from tests.test_servicos_reais import importar_tudo, lead_do, real, validar_contato  # noqa: F401

NUM_INPI = "+554931913301"  # número do INPI Agent (autorizado)
DEST = "+5547999990001"  # destinatário de teste (fictício)
TOKEN = "t" * 32


class FakeEvolution:
    def __init__(self):
        self.estado, self.dono = "open", "554931913301@s.whatsapp.net"
        self.envio = "ok"  # ok | timeout | conexao | 401 | 500 | sem_id
        self.auth_estado = 200
        self.envios: list[dict] = []
        self.chamadas: list[str] = []

    def handler(self, req: httpx.Request) -> httpx.Response:
        self.chamadas.append(f"{req.method} {req.url.path}")
        assert req.headers.get("apikey") == "chave-da-instancia"
        if req.url.path.startswith("/instance/connectionState/"):
            if self.auth_estado != 200:
                return httpx.Response(self.auth_estado, json={"error": "Unauthorized"})
            return httpx.Response(200, json={"instance": {"instanceName": "inpi-agent", "state": self.estado}})
        if req.url.path == "/instance/fetchInstances":
            return httpx.Response(200, json=[{"name": "inpi-agent", "ownerJid": self.dono, "connectionStatus": self.estado}])
        if req.url.path.startswith("/message/sendText/"):
            if self.envio == "conexao":
                raise httpx.ConnectError("recusada", request=req)
            self.envios.append({"path": req.url.path, **json.loads(req.content)})
            if self.envio == "timeout":
                raise httpx.ReadTimeout("demorou", request=req)
            if self.envio == "401":
                return httpx.Response(401, json={"error": "Unauthorized"})
            if self.envio == "500":
                return httpx.Response(500, text="erro")
            if self.envio == "sem_id":
                return httpx.Response(201, json={"status": "PENDING"})
            return httpx.Response(201, json={"key": {"remoteJid": "x@s.whatsapp.net", "fromMe": True, "id": f"BAE{len(self.envios)}"},
                                             "status": "PENDING"})  # fmt: skip
        return httpx.Response(404)


def configurar(monkeypatch, *, real_mode: bool, **extra):
    env = {"MENSAGERIA_PROVEDOR": "evolution", "EVOLUTION_BASE_URL": "https://evo.exemplo", "EVOLUTION_API_KEY": "chave-da-instancia",
           "EVOLUTION_WEBHOOK_TOKEN": TOKEN, "EVOLUTION_NUMERO_AUTORIZADO": NUM_INPI,
           "EVOLUTION_SEND_ENABLED": "true" if real_mode else "false", "EVOLUTION_SIMULATION": "false" if real_mode else "true",
           "PRIMEIRO_CONTATO_REMETENTE": "Julio, consultor em registro de marcas"} | extra  # fmt: skip
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()


@pytest.fixture
def evo(monkeypatch, conn, real):  # noqa: F811
    fe = FakeEvolution()
    monkeypatch.setattr(evolution, "transport", httpx.MockTransport(fe.handler))
    importar_tudo(conn)
    validar_contato(conn, "944040470", "(47) 99999-0001")
    configurar(monkeypatch, real_mode=False)
    conn.execute("update app_config set valor = 'Marcas Exemplo' where chave = 'primeiro_contato_empresa'")
    yield fe
    for k in list(os.environ):
        if k.startswith(("EVOLUTION_", "MENSAGERIA_", "PRIMEIRO_CONTATO_")):
            monkeypatch.delenv(k, raising=False)
    get_settings.cache_clear()


def preparar(conn, *, consentimento=True, aprovar_lead=True):
    lead = lead_do(conn, "944040470")
    c = conn.execute("select * from contacts where holder_id = %s and tipo = 'whatsapp'", (lead["holder_id"],)).fetchone()
    conn.execute("update contacts set verificacao = 'verificado_humano' where id = %s", (c["id"],))
    if aprovar_lead:
        conn.execute("update leads set status = 'aprovado', revisado_por = 'teste' where id = %s", (lead["id"],))
    if consentimento:
        conn.execute(
            """insert into consents (contact_id, canal, finalidade, empresa_identificada, obtido_em, metodo, fonte_evidencia,
                                     texto_autorizacao, versao_aviso, numero_fornecido)
               values (%s, 'whatsapp', 'Contato comercial sobre o processo de marca no INPI', 'Julio', now(), 'email',
                       'e-mail de 12/11/2026', 'Autorizo', '2026-11-v1', true)""",
            (c["id"],),
        )
    return lead, c


def aprovar(conn, r, papel="revisor"):
    return primeiro_contato.aprovar(conn, r["id"], r["versao"], r["conteudo_hash"], r["numero"], r["canal"], "user:revisor", papel)


def rascunho_aprovado(conn):
    lead, c = preparar(conn)
    r = primeiro_contato.criar_rascunho(conn, lead["id"], c["id"], "user:op")
    return lead, c, aprovar(conn, r)


# 1, 2, 3, 4, 5 ------------------------------------------------------------------------------------
def test_gerar_editar_rejeitar_aprovar_e_alterar_depois(conn, evo, monkeypatch):
    lead, c = preparar(conn)
    r = primeiro_contato.criar_rascunho(conn, lead["id"], c["id"], "user:op")  # 1. geração (sem chave de IA: modelo)
    assert r["status"] == "rascunho" and r["gerado_por"] == "modelo:MODELO_01:v1" and r["canal"] == "evolution"
    assert "944040470" in r["conteudo"] and "TELEVAULT" in r["conteudo"] and "oposição" in r["conteudo"] and "SAIR" in r["conteudo"]
    assert "Julio, consultor" in r["conteudo"] and "Marcas Exemplo" in r["conteudo"] and "{{" not in r["conteudo"]
    with pytest.raises(Recusado, match="Só revisor"):  # 4. operador não aprova
        aprovar(conn, r, papel="operador")
    r2 = primeiro_contato.editar(conn, r["id"], r["conteudo"] + " Obrigado.", r["versao"], "user:op")  # 2. edição
    assert r2["versao"] == r["versao"] + 1 and r2["conteudo_hash"] != r["conteudo_hash"]
    with pytest.raises(Recusado, match="mudou"):  # aprovação do texto antigo não vale
        aprovar(conn, r)
    a = aprovar(conn, r2)  # 4. aprovação
    assert a["status"] == "aprovado" and a["aprovacao_hash"] == primeiro_contato.hash_aprovacao(a)
    r3 = primeiro_contato.editar(conn, r2["id"], "Olá, texto novo.\n\nResponda SAIR para não receber.", a["versao"], "user:op")
    assert r3["status"] == "rascunho" and r3["aprovado_por"] is None  # 5. alterou depois de aprovar: precisa aprovar de novo
    with pytest.raises(Recusado, match="não aprovada"):
        primeiro_contato.solicitar_envio(conn, r3["id"], "user:rev", "revisor")
    rj = primeiro_contato.rejeitar(conn, r3["id"], "texto fraco", "user:rev")  # 3. rejeição
    assert rj["status"] == "rejeitado"
    with pytest.raises(Recusado):
        primeiro_contato.solicitar_envio(conn, r3["id"], "user:rev", "revisor")
    # lacuna [seu nome] impede a aprovação
    monkeypatch.delenv("PRIMEIRO_CONTATO_REMETENTE")
    get_settings.cache_clear()
    n = primeiro_contato.criar_rascunho(conn, lead["id"], c["id"], "user:op")
    assert "[nome atendente]" in n["conteudo"]
    with pytest.raises(Recusado, match="lacunas"):
        aprovar(conn, n)


# 6, 7 -------------------------------------------------------------------------------------------------------------
def test_sem_consentimento_e_opt_out_bloqueiam(conn, evo):
    lead, c = preparar(conn, consentimento=False)
    r = aprovar(conn, primeiro_contato.criar_rascunho(conn, lead["id"], c["id"], "user:op"))
    with pytest.raises(Recusado, match="Sem autorização registrada"):  # 6. aprovação humana não substitui autorização
        primeiro_contato.solicitar_envio(conn, r["id"], "user:rev", "revisor")
    conn.execute(
        """insert into consents (contact_id, canal, finalidade, empresa_identificada, obtido_em, metodo, fonte_evidencia,
                                 texto_autorizacao, versao_aviso, numero_fornecido)
           values (%s,'whatsapp','x','Julio',now(),'email','e-mail','Autorizo','v1',true)""",
        (c["id"],),
    )
    wa_cloud.aplicar_optout(conn, c["valor_normalizado"], "teste", "pediu para sair")  # 7. opt-out revoga e bloqueia
    with pytest.raises(Recusado, match="opt-out|Em opt-out|invalidado"):
        primeiro_contato.solicitar_envio(conn, r["id"], "user:rev", "revisor")
    assert conn.execute("select status from consents where contact_id = %s", (c["id"],)).fetchone()["status"] == "revogado"


# simulação + 8, 20 -----------------------------------------------------------------------------------------------
def test_simulacao_nao_envia_e_real_envia_uma_vez(conn, evo, monkeypatch):
    lead, c, r = rascunho_aprovado(conn)
    m = primeiro_contato.solicitar_envio(conn, r["id"], "user:rev", "revisor")
    assert m["status"] == "simulada" and m["modo"] == "simulacao" and evo.envios == []  # simulação: nada sai
    configurar(monkeypatch, real_mode=True)
    m = primeiro_contato.solicitar_envio(conn, r["id"], "user:rev", "revisor")
    assert m["status"] == "na_fila"
    drain()
    m = conn.execute("select * from wa_messages where id = %s", (m["id"],)).fetchone()
    assert m["status"] == "aceita" and m["wa_message_id"] == "BAE1" and len(evo.envios) == 1
    assert evo.envios[0] == {"path": "/message/sendText/inpi-agent", "number": c["valor_normalizado"][1:], "text": r["conteudo"]}
    assert conn.execute("select status from wa_rascunhos where id = %s", (r["id"],)).fetchone()["status"] == "enviado"
    with pytest.raises(Recusado):  # 8. duplicidade: o primeiro contato é único
        primeiro_contato.solicitar_envio(conn, r["id"], "user:rev", "revisor")
    novo = primeiro_contato.criar_rascunho(conn, lead["id"], c["id"], "user:op")
    with pytest.raises(Recusado, match="Já houve envio"):
        primeiro_contato.solicitar_envio(conn, aprovar(conn, novo)["id"], "user:rev", "revisor")
    assert len(evo.envios) == 1


# 9, 10, 11, 12, 13 -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("modo_envio", "status", "trecho"),
    [("conexao", "falhou", "não enviado: sem conexão"), ("401", "falhou", "recusou a chave"),
     ("sem_id", "reconciliar", "sem o id"), ("timeout", "reconciliar", "resultado desconhecido"),
     ("500", "reconciliar", "HTTP 500")],
)  # fmt: skip
def test_falhas_da_evolution_sem_reenvio_automatico(conn, evo, monkeypatch, modo_envio, status, trecho):
    _, _, r = rascunho_aprovado(conn)
    configurar(monkeypatch, real_mode=True)
    evo.envio = modo_envio
    m = primeiro_contato.solicitar_envio(conn, r["id"], "user:rev", "revisor")
    drain()
    m = conn.execute("select * from wa_messages where id = %s", (m["id"],)).fetchone()
    assert m["status"] == status and trecho in m["motivo"] and m["tentativas"] == 1
    assert sum(1 for x in evo.chamadas if "sendText" in x) <= 1  # uma única tentativa
    drain()  # nada é repetido sozinho
    assert sum(1 for x in evo.chamadas if "sendText" in x) <= 1
    if status == "reconciliar":  # uma pessoa confere no celular
        primeiro_contato.reconciliar(conn, m["id"], "nao_enviada", "user:rev")
        assert conn.execute("select status from wa_messages where id = %s", (m["id"],)).fetchone()["status"] == "falhou"


def test_sem_credenciais_e_erro_de_autenticacao(conn, evo, monkeypatch):
    _, _, r = rascunho_aprovado(conn)
    configurar(monkeypatch, real_mode=True, EVOLUTION_API_KEY="")  # 10. sem credenciais: nunca é "real"
    assert evolution.modo() == "simulacao" and evolution.verificar_conexao()["status"] == "nao_configurada"
    assert primeiro_contato.solicitar_envio(conn, r["id"], "user:rev", "revisor")["status"] == "simulada"
    configurar(monkeypatch, real_mode=True)
    evo.auth_estado = 401  # 11. chave recusada na verificação: bloqueia antes de qualquer envio
    with pytest.raises(Recusado, match="erro_autenticacao"):
        primeiro_contato.solicitar_envio(conn, r["id"], "user:rev", "revisor")
    assert evo.envios == []


# 14 ----------------------------------------------------------------------------------------------------------------
def test_concorrencia_entre_operadores(conn, evo, monkeypatch):
    lead, c = preparar(conn)
    r = primeiro_contato.criar_rascunho(conn, lead["id"], c["id"], "user:a")
    primeiro_contato.editar(conn, r["id"], "Versão do operador A. Responda SAIR para sair.", r["versao"], "user:a")
    with pytest.raises(Recusado, match="Outra pessoa alterou"):  # B editou a versão velha
        primeiro_contato.editar(conn, r["id"], "Versão do operador B", r["versao"], "user:b")
    with pytest.raises(Recusado, match="mudou"):  # aprovador viu a versão velha
        aprovar(conn, r)
    atual = conn.execute("select * from wa_rascunhos where id = %s", (r["id"],)).fetchone()
    aprovar(conn, atual)
    configurar(monkeypatch, real_mode=True)
    primeiro_contato.solicitar_envio(conn, r["id"], "user:a", "revisor")
    with pytest.raises(Recusado):  # segundo clique em "Enviar" antes do worker
        primeiro_contato.solicitar_envio(conn, r["id"], "user:b", "revisor")
    drain()
    assert len(evo.envios) == 1


# 15, 16, 17 ---------------------------------------------------------------------------------------------------------
def test_historico_isolamento_e_reinicio_do_worker(conn, evo, monkeypatch):
    lead, c, r = rascunho_aprovado(conn)
    configurar(monkeypatch, real_mode=True)
    evo.dono = "5548999990000@s.whatsapp.net"  # 16. conectado o número de OUTRO negócio: bloqueia
    with pytest.raises(Recusado, match="não é o número autorizado"):
        primeiro_contato.solicitar_envio(conn, r["id"], "user:rev", "revisor")
    evo.dono = "554931913301@s.whatsapp.net"
    m = primeiro_contato.solicitar_envio(conn, r["id"], "user:rev", "revisor")
    # 17. o worker caiu depois de "pegar" a mensagem: na volta, não envia de novo (fica para conferência)
    conn.execute("update wa_messages set status = 'reconciliar', motivo = 'envio em andamento' where id = %s", (m["id"],))
    drain()
    assert evo.envios == [] and conn.execute("select status from wa_messages where id = %s", (m["id"],)).fetchone()["status"] == "reconciliar"
    assert all("/inpi-agent" in x or x.endswith("fetchInstances") for x in evo.chamadas)  # só a instância do INPI Agent
    acoes = [a["acao"] for a in conn.execute("select acao from wa_auditoria where lead_id = %s order by id", (lead["id"],))]
    assert acoes[:3] == ["rascunho_gerado", "rascunho_aprovado", "envio_bloqueado"] and "envio_solicitado" in acoes  # 15
    assert conn.execute("select count(*) n from audit_log where tabela = 'wa_rascunhos'").fetchone()["n"] >= 2


# 18, 20 + isolamento do webhook -------------------------------------------------------------------------------------
def test_webhook_registra_sem_responder(conn, evo, monkeypatch):
    lead, c, r = rascunho_aprovado(conn)
    configurar(monkeypatch, real_mode=True)
    m = primeiro_contato.solicitar_envio(conn, r["id"], "user:rev", "revisor")
    drain()
    url = f"/webhooks/evolution/inpi-agent?token={TOKEN}"
    num = c["valor_normalizado"][1:]
    with TestClient(app) as cli:
        assert cli.post("/webhooks/evolution/inpi-agent?token=errado", json={}).status_code == 403
        assert cli.post(f"/webhooks/evolution/kisabor?token={TOKEN}", json={"event": "messages.upsert"}).status_code == 403
        assert cli.post(url, json={"event": "x", "instance": "kisabor"}).status_code == 403
        up = {"event": "messages.update", "instance": "inpi-agent", "data": {"keyId": "BAE1", "status": "DELIVERY_ACK", "fromMe": True}}
        assert cli.post(url, json=up).json()["aplicados"] == 1
        assert cli.post(url, json=up).json()["repetidos"] == 1  # deduplicação
        cli.post(url, json={"event": "MESSAGES_UPDATE", "instance": "inpi-agent", "data": {"keyId": "BAE1", "status": "READ"}})
        resp = {"event": "messages.upsert", "instance": "inpi-agent",
                "data": {"key": {"remoteJid": f"{num}@s.whatsapp.net", "fromMe": False, "id": "IN1"}, "message": {"conversation": "Tenho interesse"}}}
        assert cli.post(url, json=resp).json()["aplicados"] == 1
        outro = {"event": "messages.upsert", "instance": "inpi-agent",
                 "data": {"key": {"remoteJid": "5511988887777@s.whatsapp.net", "fromMe": False, "id": "IN2"}, "message": {"conversation": "oi"}}}
        assert cli.post(url, json=outro).json()["ignorados"] == 1  # conversa de outro número: nem é gravada
        cli.post(url, json={"event": "connection.update", "instance": "inpi-agent", "data": {"state": "close"}})
    msg = conn.execute("select * from wa_messages where id = %s", (m["id"],)).fetchone()
    assert msg["status"] == "lida" and msg["entregue_em"] and msg["lida_em"]
    ent = conn.execute("select * from wa_messages where direcao = 'entrada'").fetchall()
    assert len(ent) == 1 and ent[0]["corpo"] is None and ent[0]["numero"] == c["valor_normalizado"]  # texto não é guardado
    assert conn.execute("select pipeline_stage from leads where id = %s", (lead["id"],)).fetchone()["pipeline_stage"] == "resposta_recebida"
    assert conn.execute("select count(*) n from wa_webhook_events where wa_message_id = 'IN2'").fetchone()["n"] == 0
    assert conn.execute("select status_conexao from wa_contas where instancia = 'inpi-agent'").fetchone()["status_conexao"] == "desconectado"
    assert len(evo.envios) == 1  # 20. nenhuma resposta automática
    # pedido de saída pela resposta = opt-out imediato, ainda sem responder nada
    r2 = evolution_webhook.processar(conn, "messages.upsert", {"instance": "inpi-agent", "data": {
        "key": {"remoteJid": f"{num}@s.whatsapp.net", "fromMe": False, "id": "IN3"}, "message": {"conversation": "SAIR"}}})
    assert r2["optouts"] == 1 and len(evo.envios) == 1
    assert conn.execute("select count(*) n from suppression_list where origem = 'whatsapp:evolution'").fetchone()["n"] == 1


# 19 + um provedor por vez ------------------------------------------------------------------------------------------
def test_desativacao_emergencial_e_meta_desligada(conn, evo, monkeypatch):
    _, _, r = rascunho_aprovado(conn)
    configurar(monkeypatch, real_mode=True)
    m = primeiro_contato.solicitar_envio(conn, r["id"], "user:rev", "revisor")
    with TestClient(app) as cli:
        st = cli.get("/api/integracao-whatsapp").json()
        assert st["modo"] == "real" and "chave" not in json.dumps(st).lower().replace("chave da instância", "")
        assert "chave-da-instancia" not in json.dumps(st)  # credencial nunca vai para o navegador
        assert cli.post("/api/integracao-whatsapp/testar").json()["numero_confere"] is True
        assert cli.post("/api/integracao-whatsapp/desativar-envios").json()["cancelados"] == 1
        assert cli.post(f"/api/rascunhos/{r['id']}/enviar").status_code == 409
    drain()
    assert evo.envios == [] and conn.execute("select status from wa_messages where id = %s", (m["id"],)).fetchone()["status"] == "cancelada"
    # a Cloud API da Meta não envia nem processa webhook enquanto o provedor for a Evolution
    assert "Meta desativada" in wa_cloud.bloqueio(conn, {"numero": DEST, "contact_id": None})
    with TestClient(app) as cli:
        link = cli.post(f"/api/rascunhos/{r['id']}/abrir-whatsapp").json()
    assert link["url"].startswith("https://wa.me/") and "não registra envio" in link["aviso"]
    assert conn.execute("select count(*) n from wa_messages where status in ('aceita','enviada')").fetchone()["n"] == 0


def test_configuracao_insegura_impede_a_api_de_subir():
    from app.config import Settings
    from app.security import problemas_de_configuracao

    s = Settings(app_env="homologacao", auth_mode="dev", mensageria_provedor="evolution", evolution_send_enabled=True,
                 evolution_simulation=False, evolution_webhook_token="curto")  # fmt: skip
    p = " | ".join(problemas_de_configuracao(s))
    assert "exige login" in p and "EVOLUTION_NUMERO_AUTORIZADO" in p and "24 caracteres" in p
