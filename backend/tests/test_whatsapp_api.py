"""V2.0 Fase 7: WhatsApp Cloud API oficial. A Meta é simulada; nenhum envio real acontece nos testes."""

import hashlib
import hmac
import json

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from app import wa_cloud
from app.config import get_settings
from app.main import app
from tests.test_fases3a7 import drain, importar_rpi, mundo  # noqa: F401
from tests.test_site_crawler import sites  # noqa: F401
from tests.test_whatsapp import _pipeline

NUM = "+5511988887777"
SEGREDO = "segredo-de-teste"
ENV = {
    "WHATSAPP_PHONE_NUMBER_ID": "111", "WHATSAPP_BUSINESS_ACCOUNT_ID": "222", "WHATSAPP_ACCESS_TOKEN": "token-de-teste",
    "WHATSAPP_VERIFY_TOKEN": "verifica-123", "WHATSAPP_APP_SECRET": SEGREDO, "WHATSAPP_TEMPLATE_NAME": "primeiro_contato",
    "WHATSAPP_ENVIO_ATIVO": "true", "WHATSAPP_NUMEROS_TESTE": NUM, "AUTH_MODE": "supabase",
    "MENSAGERIA_PROVEDOR": "meta",  # estes testes cobrem o provedor Meta (desligado por padrão desde a V2.5)
}  # fmt: skip


class Meta:
    """Simula a Graph API: registra o que recebeu e responde conforme o roteiro."""

    def __init__(self):
        self.envios: list[dict] = []
        self.template = "APPROVED"
        self.resposta: httpx.Response | Exception | None = None

    def __call__(self, req: httpx.Request) -> httpx.Response:
        assert req.headers["Authorization"] == "Bearer token-de-teste"
        if req.method == "GET":
            return httpx.Response(
                200, json={"data": [{"name": "primeiro_contato", "language": "pt_BR", "status": self.template}]}
            )
        if isinstance(self.resposta, Exception):
            raise self.resposta
        self.envios.append(json.loads(req.content))
        return self.resposta or httpx.Response(200, json={"messages": [{"id": f"wamid.{len(self.envios)}"}]})


@pytest.fixture
def meta(monkeypatch):
    m = Meta()
    monkeypatch.setattr(wa_cloud, "transport", httpx.MockTransport(m))
    wa_cloud._template_cache.clear()
    yield m
    get_settings.cache_clear()


def configurar(monkeypatch, **extra):
    for k, v in (ENV | extra).items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()


def preparar(conn):
    """Pipeline até ter um lead aprovado com WhatsApp publicado pela empresa."""
    _pipeline()
    wa = conn.execute("select * from contacts where wa_nivel = 'company_evidence'").fetchone()
    lead = conn.execute("update leads set status = 'aprovado' where holder_id = %s returning *", (wa["holder_id"],)).fetchone()
    return lead, wa


def criar(conn, lead, wa):
    """Cria a mensagem pela regra de negócio (a rota HTTP exige login quando AUTH_MODE=supabase)."""
    from app import db

    with db.transaction("user:teste") as c:
        return wa_cloud.criar_saida(c, lead_id=lead["id"], contact_id=wa["id"], numero_processo=None, params=None)


def msg(conn, mid):
    return conn.execute("select * from wa_messages where id = %s", (mid,)).fetchone()


def assinar(payload: dict) -> tuple[bytes, dict]:
    corpo = json.dumps(payload).encode()
    return corpo, {"X-Hub-Signature-256": "sha256=" + hmac.new(SEGREDO.encode(), corpo, hashlib.sha256).hexdigest()}


def evento_status(wa_id, status, ts=1_800_000_000, **extra):
    return {"entry": [{"changes": [{"value": {"statuses": [{"id": wa_id, "status": status, "timestamp": str(ts)} | extra]}}]}]}


def evento_msg(wa_id, texto, de=NUM.lstrip("+")):
    m = {"id": wa_id, "from": de, "timestamp": "1800000100", "type": "text", "text": {"body": texto}}
    return {"entry": [{"changes": [{"value": {"messages": [m]}}]}]}


def test_sem_configuracao_fica_em_simulacao_e_nao_chama_a_meta(conn, sites, meta):  # noqa: F811
    lead, wa = preparar(conn)
    with TestClient(app) as c:
        st = c.get("/api/whatsapp/status").json()
        assert st["modo"] == "simulacao" and not st["configurado"] and "WHATSAPP_ACCESS_TOKEN" in st["pendencias_para_envio_real"]
        r = c.post("/api/whatsapp/messages", json={"lead_id": lead["id"], "contact_id": wa["id"]})
        assert r.status_code == 201 and r.json()["status"] == "simulada" and r.json()["modo"] == "simulacao"
        assert r.json()["template_params"][1] == r.json()["numero_processo"]  # variáveis = fatos do processo
        # pedir de novo não duplica
        r2 = c.post("/api/whatsapp/messages", json={"lead_id": lead["id"], "contact_id": wa["id"]})
        assert r2.json()["id"] == r.json()["id"] and r2.json()["duplicada"] is True
    drain()
    assert meta.envios == [] and conn.execute("select count(*) n from jobs where tipo = 'whatsapp.send'").fetchone()["n"] == 0


def test_lead_nao_aprovado_ou_contato_errado_e_recusado(conn, sites, meta):  # noqa: F811
    lead, wa = preparar(conn)
    conn.execute("update leads set status = 'qualificado' where id = %s", (lead["id"],))
    email = conn.execute("select id from contacts where holder_id = %s and tipo = 'email' limit 1", (wa["holder_id"],)).fetchone()
    with TestClient(app) as c:
        assert c.post("/api/whatsapp/messages", json={"lead_id": lead["id"], "contact_id": wa["id"]}).status_code == 409
        conn.execute("update leads set status = 'aprovado' where id = %s", (lead["id"],))
        assert c.post("/api/whatsapp/messages", json={"lead_id": lead["id"], "contact_id": email["id"]}).status_code == 409
        r = c.post("/api/whatsapp/messages", json={"lead_id": lead["id"], "contact_id": wa["id"], "numero_processo": "900000001"})
        assert r.status_code == 409


def test_envio_real_e_status_apenas_pelo_webhook(conn, sites, meta, monkeypatch):  # noqa: F811
    lead, wa = preparar(conn)
    configurar(monkeypatch)
    m = criar(conn, lead, wa)
    assert m["status"] == "na_fila" and m["modo"] == "real"
    drain()
    m = msg(conn, m["id"])
    assert m["status"] == "aceita" and m["wa_message_id"] == "wamid.1" and m["aceita_em"]
    assert m["enviada_em"] is None and m["entregue_em"] is None and m["lida_em"] is None  # nada inventado
    env = meta.envios[0]
    assert env["to"] == NUM.lstrip("+") and env["template"]["name"] == "primeiro_contato"
    assert len(env["template"]["components"][0]["parameters"]) == 5
    # mesma mensagem não é criada nem enviada de novo
    assert criar(conn, lead, wa)["duplicada"] is True
    drain()
    assert len(meta.envios) == 1

    with TestClient(app) as c:
        # fora de ordem: 'lida' chega antes de 'entregue'; o status não regride
        for st in ("sent", "read", "delivered"):
            corpo, cab = assinar(evento_status("wamid.1", st))
            assert c.post("/webhooks/whatsapp", content=corpo, headers=cab).status_code == 200
        m = msg(conn, m["id"])
        assert m["status"] == "lida" and m["enviada_em"] and m["entregue_em"] and m["lida_em"]
        # evento repetido pela Meta é ignorado
        corpo, cab = assinar(evento_status("wamid.1", "read"))
        assert c.post("/webhooks/whatsapp", content=corpo, headers=cab).json()["repetidos"] == 1
        # falha tardia não derruba uma mensagem já entregue
        corpo, cab = assinar(evento_status("wamid.1", "failed", ts=1_800_000_500, errors=[{"code": 131026, "title": "x"}]))
        c.post("/webhooks/whatsapp", content=corpo, headers=cab)
        assert msg(conn, m["id"])["status"] == "lida"
    # eventos guardados como chegaram e imutáveis
    assert conn.execute("select count(*) n from wa_webhook_events").fetchone()["n"] == 4
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("delete from wa_webhook_events")


@pytest.mark.parametrize(
    ("env", "motivo"),
    [
        ({"AUTH_MODE": "dev"}, "login obrigatório"),
        ({"WHATSAPP_NUMEROS_TESTE": "+5511900000000"}, "Sem autorização registrada"),
        ({"WHATSAPP_NUMEROS_TESTE": ""}, "Sem autorização registrada"),
    ],
)
def test_bloqueios_impedem_o_envio(conn, sites, meta, monkeypatch, env, motivo):  # noqa: F811
    lead, wa = preparar(conn)
    configurar(monkeypatch, **env)
    m = criar(conn, lead, wa)
    drain()
    m = msg(conn, m["id"])
    assert m["status"] == "bloqueada" and motivo in m["motivo"] and meta.envios == []


def test_template_nao_aprovado_e_optout_bloqueiam(conn, sites, meta, monkeypatch):  # noqa: F811
    lead, wa = preparar(conn)
    configurar(monkeypatch)
    meta.template = "PENDING"
    m = criar(conn, lead, wa)
    drain()
    assert "template não aprovado" in msg(conn, m["id"])["motivo"] and meta.envios == []
    # opt-out registrado depois de a mensagem entrar na fila
    conn.execute("update wa_messages set status = 'na_fila', idempotency_key = 'x' where id = %s", (m["id"],))
    conn.execute("insert into suppression_list (tipo, valor_hash) values ('telefone', %s)", (wa_cloud.hash_numero(NUM),))
    meta.template = "APPROVED"
    wa_cloud._template_cache.clear()
    from app import db
    from app.jobs import queue

    with db.transaction("t") as c:
        queue.enqueue(c, "whatsapp.send", {"message_id": m["id"]})
    drain()
    assert "opt-out" in msg(conn, m["id"])["motivo"] and meta.envios == []


def test_falhas_retry_seguro_e_limites(conn, sites, meta, monkeypatch):  # noqa: F811
    lead, wa = preparar(conn)
    configurar(monkeypatch)
    # 1) timeout de leitura = resultado incerto: NÃO reenvia
    meta.resposta = httpx.ReadTimeout("lento")
    m = criar(conn, lead, wa)
    drain()
    m1 = msg(conn, m["id"])
    assert m1["status"] == "falhou" and "incerto" in m1["motivo"]
    assert conn.execute("select count(*) n from jobs where tipo = 'whatsapp.send' and status = 'queued'").fetchone()["n"] == 0

    def refila(resposta):
        meta.resposta = resposta
        conn.execute("update wa_messages set status = 'na_fila', motivo = null where id = %s", (m["id"],))
        conn.execute("delete from jobs where tipo = 'whatsapp.send'")
        from app import db
        from app.jobs import queue

        with db.transaction("t") as c:
            queue.enqueue(c, "whatsapp.send", {"message_id": m["id"]})
        drain(3)
        return msg(conn, m["id"]), conn.execute("select status from jobs where tipo = 'whatsapp.send'").fetchone()["status"]

    # 2) recusa definitiva da Meta: falhou, com código, sem repetir
    m2, job = refila(httpx.Response(400, json={"error": {"code": 131026, "message": "Message undeliverable"}}))
    assert m2["status"] == "falhou" and m2["erro_codigo"] == "131026" and job == "succeeded"
    assert "token-de-teste" not in (m2["motivo"] or "")
    # 3) sem conexão: o pedido nem saiu; a mensagem continua na fila e o job tenta depois
    m3, job = refila(httpx.ConnectError("sem rede"))
    assert m3["status"] == "na_fila" and job == "queued"
    # 4) limite de taxa da Meta: idem
    m4, job = refila(httpx.Response(429, json={"error": {"code": 130429, "message": "Rate limit hit"}}))
    assert m4["status"] == "na_fila" and job == "queued"
    # 5) limite diário próprio: não chama a Meta
    configurar(monkeypatch, WHATSAPP_LIMITE_POR_DIA="0")
    antes = len(meta.envios)
    m5, job = refila(None)
    assert m5["status"] == "na_fila" and job == "queued" and len(meta.envios) == antes


def test_webhook_verificacao_e_assinatura(conn, meta, monkeypatch):
    with TestClient(app) as c:
        # sem segredo configurado, nada é aceito
        assert c.post("/webhooks/whatsapp", json={}).status_code == 503
        configurar(monkeypatch)
        ok = c.get(
            "/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "verifica-123", "hub.challenge": "42"}
        )
        assert ok.status_code == 200 and ok.text == "42"
        assert c.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "errado"}).status_code == 403
        corpo, cab = assinar(evento_msg("wamid.in1", "oi"))
        assert c.post("/webhooks/whatsapp", content=corpo).status_code == 401
        assert c.post("/webhooks/whatsapp", content=corpo, headers={"X-Hub-Signature-256": "sha256=00"}).status_code == 401
        assert c.post("/webhooks/whatsapp", content=corpo + b" ", headers=cab).status_code == 401  # corpo adulterado
        assert conn.execute("select count(*) n from wa_messages").fetchone()["n"] == 0
        # status de mensagem desconhecida não cria nem altera nada
        corpo, cab = assinar(evento_status("wamid.nao-existe", "delivered"))
        assert c.post("/webhooks/whatsapp", content=corpo, headers=cab).json()["desconhecidos"] == 1


def test_resposta_recebida_e_optout_imediato(conn, sites, meta, monkeypatch):  # noqa: F811
    lead, wa = preparar(conn)
    conn.execute(
        """insert into consents (contact_id, canal, finalidade, empresa_identificada, obtido_em, metodo, fonte_evidencia,
                                 texto_autorizacao, versao_aviso)
           values (%s, 'whatsapp', 'f', 'e', now(), 'email', 'x', 't', 'v1')""",
        (wa["id"],),
    )
    configurar(monkeypatch, WHATSAPP_LIMITE_POR_DIA="0")  # mantém a mensagem na fila
    pendente = criar(conn, lead, wa)
    with TestClient(app) as c:
        corpo, cab = assinar(evento_msg("wamid.in1", "Olá, tenho interesse"))
        assert c.post("/webhooks/whatsapp", content=corpo, headers=cab).json() == {
            "status": 0, "mensagens": 1, "optouts": 0, "repetidos": 0, "desconhecidos": 0}  # fmt: skip
        entrada = conn.execute("select * from wa_messages where direcao = 'entrada'").fetchone()
        assert entrada["lead_id"] == lead["id"] and entrada["corpo"] == "Olá, tenho interesse" and entrada["status"] == "recebida"
        assert c.post("/webhooks/whatsapp", content=corpo, headers=cab).json()["repetidos"] == 1  # reentrega não duplica

        corpo, cab = assinar(evento_msg("wamid.in2", "  Sair. "))
        assert c.post("/webhooks/whatsapp", content=corpo, headers=cab).json()["optouts"] == 1
    sup = conn.execute("select * from suppression_list").fetchone()
    assert sup["valor_hash"] == wa_cloud.hash_numero(NUM) and sup["origem"] == "whatsapp:resposta" and sup["criado_em"]
    assert msg(conn, pendente["id"])["status"] == "cancelada"
    k = conn.execute("select * from consents").fetchone()
    assert k["status"] == "revogado" and k["revogado_em"] and k["revogacao_origem"] == "whatsapp:resposta"
    assert conn.execute("select verificacao from contacts where id = %s", (wa["id"],)).fetchone()["verificacao"] == "invalido"
    from app import db

    with pytest.raises(wa_cloud.ErroDeRegra), db.transaction("t") as c2:
        wa_cloud.criar_saida(c2, lead_id=lead["id"], contact_id=wa["id"], numero_processo=None, params=None)


def test_palavras_de_optout():
    for t in ("SAIR", "sair", "Parar!", "pare", "STOP", "não quero receber mensagens", "Por favor me remova da lista"):
        assert wa_cloud.eh_optout(t), t
    for t in ("Quero saber mais", "Não entendi", "Pode parar por aqui amanhã?", "", None):
        assert not wa_cloud.eh_optout(t), t


def test_status_nao_expoe_credenciais(conn, meta, monkeypatch):
    configurar(monkeypatch, AUTH_MODE="dev")
    with TestClient(app) as c:
        texto = c.get("/api/whatsapp/status").text
    assert "token-de-teste" not in texto and SEGREDO not in texto and "verifica-123" not in texto
