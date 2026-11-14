"""V2.7 · Três modelos de mensagem no banco e envio direto pelo backend (Evolution simulada; nada sai do sistema)."""

import pytest
from fastapi.testclient import TestClient

from app import evolution_webhook, modelos, primeiro_contato
from app.main import app
from app.primeiro_contato import Recusado
from tests.test_primeiro_contato import aprovar, configurar, evo, preparar  # noqa: F401
from tests.test_servicos_reais import real  # noqa: F401

CHAVE = "clique-0001-abcd"


def api(method, url, **kw):
    with TestClient(app) as c:
        return c.request(method, url, **kw)


# 1, 2 · edição dos três modelos, salvos no PostgreSQL (sem publicar versão)
def test_tres_modelos_editaveis_no_banco(conn):
    d = api("GET", "/api/wa-modelos").json()
    assert [m["codigo"] for m in d["modelos"]] == ["MODELO_01", "MODELO_02", "MODELO_03"]
    assert [m["tipo_oportunidade"] for m in d["modelos"]] == ["oposicao", "indeferimento", "institucional"]
    assert set(d["variaveis"]) == {"nome_titular", "marca", "numero_processo", "tipo_despacho", "edicao_rpi", "estado", "empresa", "nome_atendente"}
    m1 = d["modelos"][0]
    novo = m1["texto"].replace("Podemos conversar?", "Posso te ligar?")
    r = api("PUT", "/api/wa-modelos/MODELO_01", json={"nome": "Oposição (revisado)", "descricao": m1["descricao"], "texto": novo,
                                                       "ativo": True, "versao": m1["versao"]})  # fmt: skip
    assert r.status_code == 200 and r.json()["versao"] == 2 and r.json()["atualizado_por"]
    row = conn.execute("select texto, nome from wa_modelos where codigo = 'MODELO_01'").fetchone()
    assert "Posso te ligar?" in row["texto"] and row["nome"] == "Oposição (revisado)"
    hist = api("GET", "/api/wa-modelos/MODELO_01/historico").json()
    assert [h["versao"] for h in hist] == [2, 1] and "Podemos conversar?" in hist[1]["texto"]  # versão anterior preservada
    # versão velha, variável inventada ou sem descadastro: recusado
    assert api("PUT", "/api/wa-modelos/MODELO_01", json={**{k: m1[k] for k in ("nome", "descricao", "texto", "ativo")}, "versao": 1}).status_code == 409
    ruim = {"nome": "x" * 5, "descricao": "abc", "ativo": True, "versao": 2}
    assert "{{cpf}}" in api("PUT", "/api/wa-modelos/MODELO_01", json=ruim | {"texto": "Olá {{cpf}}, responda SAIR para sair."}).json()["detail"]
    assert "SAIR" in api("PUT", "/api/wa-modelos/MODELO_01", json=ruim | {"texto": "Olá {{nome_titular}}, tudo bem com você?"}).json()["detail"]
    # remetente editável na tela
    assert api("PUT", "/api/wa-modelos-remetente", json={"nome_atendente": "Julio", "empresa": "Marcas Sul"}).json() == {
        "nome_atendente": "Julio", "empresa": "Marcas Sul"}  # fmt: skip


# 3 · substituição segura das variáveis
def test_substituicao_segura():
    texto, alertas, usadas = modelos.renderizar("Olá {{nome_titular}}, marca {{marca}}, RPI {{edicao_rpi}} {{x}}",
                                                {"nome_titular": "ACME LTDA", "marca": None, "edicao_rpi": "2914"})  # fmt: skip
    assert texto == "Olá ACME LTDA, marca [marca], RPI 2914 [x]"
    assert "None" not in texto and any("marca" in a for a in alertas) and any("desconhecida" in a for a in alertas)
    assert usadas == {"nome_titular": "ACME LTDA", "marca": None, "edicao_rpi": "2914"}


def test_previa_sem_gravar(conn):
    p = api("POST", "/api/wa-modelos/MODELO_02/previa", json={}).json()
    assert p["exemplo"] and "MARCA EXEMPLO" in p["texto"] and "indeferimento" in p["texto"]
    assert any("atendente" in a for a in p["alertas"])  # remetente não configurado → alerta, sem inventar nome
    assert conn.execute("select count(*) n from wa_rascunhos").fetchone()["n"] == 0


# 4, 5 · seleção automática pela oportunidade e escolha manual compatível
def test_selecao_de_modelo(conn, evo):
    lead, c = preparar(conn)  # lead real com oposição (944040470)
    d = api("GET", f"/api/primeiro-contato/{lead['id']}").json()
    assert d["modelo_sugerido"] == "MODELO_01"
    assert {m["codigo"]: m["compativel"] for m in d["modelos"]} == {"MODELO_01": True, "MODELO_02": False, "MODELO_03": True}
    r = primeiro_contato.criar_rascunho(conn, lead["id"], c["id"], "user:op")
    assert r["gerado_por"].startswith("modelo:MODELO_01") and r["finalidade"] == "Manifestação à oposição"
    r3 = primeiro_contato.criar_rascunho(conn, lead["id"], c["id"], "user:op", "MODELO_03")
    assert r3["gerado_por"].startswith("modelo:MODELO_03") and r3["versao"] == r["versao"] + 1
    with pytest.raises(Recusado, match="não combina"):
        primeiro_contato.criar_rascunho(conn, lead["id"], c["id"], "user:op", "MODELO_02")
    conn.execute("update wa_modelos set ativo = false where codigo = 'MODELO_01'")
    with pytest.raises(Recusado, match="inativo"):
        primeiro_contato.criar_rascunho(conn, lead["id"], c["id"], "user:op", "MODELO_01")
    assert modelos.sugerido(None) == "MODELO_03" and modelos.sugerido({"servico": "recurso_indeferimento"}) == "MODELO_02"
    # o texto do modelo não muda com a personalização
    assert "{{nome_titular}}" in conn.execute("select texto from wa_modelos where codigo = 'MODELO_03'").fetchone()["texto"]
    assert "{{" not in r3["conteudo"] and r3["modelo_texto"].startswith("Olá, {{nome_titular}}")


# 6, 9 · aprovação presa ao modelo e à finalidade
def test_aprovacao_presa_ao_modelo(conn, evo):
    lead, c = preparar(conn)
    a = aprovar(conn, primeiro_contato.criar_rascunho(conn, lead["id"], c["id"], "user:op"))
    assert a["aprovacao_hash"] == primeiro_contato.hash_aprovacao(a)
    trocado = dict(a) | {"modelo_id": a["modelo_id"] + 1}
    assert primeiro_contato.hash_aprovacao(trocado) != a["aprovacao_hash"]
    conn.execute("update wa_modelos set ativo = false where id = %s", (a["modelo_id"],))
    with pytest.raises(Recusado, match="desativado"):
        primeiro_contato.solicitar_envio(conn, a["id"], "user:rev", "revisor")


# 7, 8, 9, 10, 11, 17 · envio direto pelo backend, na mesma requisição, sem abrir nada
def test_envio_direto_idempotente(conn, evo, monkeypatch):
    lead, c = preparar(conn)
    a = aprovar(conn, primeiro_contato.criar_rascunho(conn, lead["id"], c["id"], "user:op"))
    s = api("POST", f"/api/rascunhos/{a['id']}/enviar", json={"chave": CHAVE}).json()  # 7. simulado
    assert s["status"] == "simulada" and evo.envios == []
    configurar(monkeypatch, real_mode=True, EVOLUTION_NUMEROS_TESTE=a["numero"])  # 8. só o número de teste autorizado
    a2 = aprovar(conn, primeiro_contato.criar_rascunho(conn, lead["id"], c["id"], "user:op"))
    r = api("POST", f"/api/rascunhos/{a2['id']}/enviar", json={"chave": "clique-real-0001"})
    m = r.json()
    assert r.status_code == 200 and m["status"] == "aceita" and m["wa_message_id"] == "BAE1"  # 11. aceito pelo provedor, já na resposta
    assert len(evo.envios) == 1 and evo.envios[0]["path"] == "/message/sendText/inpi-agent" and "wa.me" not in str(m)
    # 17. clique repetido (mesma chave): devolve o mesmo envio, sem nova chamada
    assert api("POST", f"/api/rascunhos/{a2['id']}/enviar", json={"chave": "clique-real-0001"}).json()["id"] == m["id"]
    assert len(evo.envios) == 1
    # 12. outro clique (outra chave) para o mesmo contato: bloqueado (primeiro contato é único)
    assert api("POST", f"/api/rascunhos/{a2['id']}/enviar", json={"chave": "clique-real-0002"}).status_code == 409
    # 10. a tela acompanha pelo status; "entregue" só com o evento do WhatsApp
    assert api("GET", f"/api/wa-mensagens/{m['id']}").json()["entregue_em"] is None
    evolution_webhook.processar(conn, "messages.update", {"instance": "inpi-agent", "data": {"keyId": "BAE1", "status": "DELIVERY_ACK"}})
    assert api("GET", f"/api/wa-mensagens/{m['id']}").json()["status"] == "entregue"
    # 18. histórico com modelo, texto, aprovador e id do provedor
    env = api("GET", f"/api/primeiro-contato/{lead['id']}").json()["envios"]
    real_ = next(e for e in env if e["id"] == m["id"])
    assert real_["modelo_codigo"] == "MODELO_01" and real_["aprovado_por"] == "user:revisor" and real_["wa_message_id"] == "BAE1"
    assert "TELEVAULT" in real_["corpo"]


# 13, 14 · sem consentimento e após opt-out
def test_bloqueios_de_consentimento(conn, evo, monkeypatch):
    lead, c = preparar(conn, consentimento=False)
    a = aprovar(conn, primeiro_contato.criar_rascunho(conn, lead["id"], c["id"], "user:op"))
    configurar(monkeypatch, real_mode=True)
    assert api("POST", f"/api/rascunhos/{a['id']}/enviar", json={"chave": CHAVE}).status_code == 409
    assert evo.envios == []


# 15, 16 · falha de conexão e tempo esgotado: nada é repetido sozinho
@pytest.mark.parametrize(("modo", "status"), [("conexao", "falhou"), ("timeout", "reconciliar")])
def test_falha_e_timeout(conn, evo, monkeypatch, modo, status):
    lead, c = preparar(conn)
    a = aprovar(conn, primeiro_contato.criar_rascunho(conn, lead["id"], c["id"], "user:op"))
    configurar(monkeypatch, real_mode=True)
    evo.envio = modo
    m = api("POST", f"/api/rascunhos/{a['id']}/enviar", json={"chave": CHAVE}).json()
    assert m["status"] == status
    tentativas = len(evo.envios)
    assert api("POST", f"/api/rascunhos/{a['id']}/enviar", json={"chave": CHAVE}).json()["id"] == m["id"]  # mesmo clique
    assert len(evo.envios) == tentativas


def test_limite_diario(conn, evo, monkeypatch):
    lead, c = preparar(conn)
    a = aprovar(conn, primeiro_contato.criar_rascunho(conn, lead["id"], c["id"], "user:op"))
    configurar(monkeypatch, real_mode=True)
    conn.execute("update app_config set valor = '0' where chave = 'whatsapp_limite_diario'")
    r = api("POST", f"/api/rascunhos/{a['id']}/enviar", json={"chave": CHAVE})
    assert r.status_code == 409 and "Limite diário" in r.json()["detail"] and evo.envios == []


# 19, 20 · resposta: avisa na tela, não responde nada, a conversa segue no celular
def test_resposta_gera_aviso_sem_responder(conn, evo, monkeypatch):
    lead, c = preparar(conn)
    a = aprovar(conn, primeiro_contato.criar_rascunho(conn, lead["id"], c["id"], "user:op"))
    configurar(monkeypatch, real_mode=True)
    api("POST", f"/api/rascunhos/{a['id']}/enviar", json={"chave": CHAVE})
    num = c["valor_normalizado"].lstrip("+")
    evolution_webhook.processar(conn, "messages.upsert", {"instance": "inpi-agent", "data": {
        "key": {"remoteJid": f"{num}@s.whatsapp.net", "fromMe": False, "id": "IN9"}, "message": {"conversation": "Oi, quero saber mais"}}})
    novas = api("GET", "/api/primeiro-contato-respostas").json()
    assert novas["novas"] == 1 and novas["itens"][0]["lead_id"] == lead["id"]
    assert api("POST", "/api/primeiro-contato-respostas/vistas").json()["marcadas"] == 1
    assert api("GET", "/api/primeiro-contato-respostas").json()["novas"] == 0
    assert len(evo.envios) == 1  # nenhuma resposta automática nem novo contato
    assert conn.execute("select pipeline_stage from leads where id = %s", (lead["id"],)).fetchone()["pipeline_stage"] == "resposta_recebida"


# V2.8 · botão único "Enviar" no card do lead: o clique aprova o texto mostrado e envia na hora
def test_enviar_em_um_clique(conn, evo, monkeypatch):
    lead, c = preparar(conn)
    configurar(monkeypatch, real_mode=True)
    texto = api("POST", "/api/wa-modelos/MODELO_01/previa", json={"lead_id": lead["id"]}).json()["texto"]
    r = api("POST", f"/api/primeiro-contato/{lead['id']}/enviar", json={"contact_id": c["id"], "texto": texto + " [completar]", "chave": "um-clique-0001"})
    assert r.status_code == 409 and "lacunas" in r.text and evo.envios == []  # texto com lacuna não sai
    assert api("GET", f"/api/primeiro-contato/{lead['id']}").json()["rascunho"] is None  # recusa desfaz tudo: nada fica aprovado
    m = api("POST", f"/api/primeiro-contato/{lead['id']}/enviar", json={"contact_id": c["id"], "texto": texto, "chave": "um-clique-0002"}).json()
    assert m["status"] == "aceita" and len(evo.envios) == 1 and evo.envios[0]["text"] == texto
    assert api("POST", f"/api/primeiro-contato/{lead['id']}/enviar", json={"contact_id": c["id"], "texto": texto, "chave": "um-clique-0002"}).json()["id"] == m["id"]
    assert len(evo.envios) == 1
    r = conn.execute("select status, aprovado_por from wa_rascunhos where lead_id = %s", (lead["id"],)).fetchone()
    assert r["status"] == "enviado" and r["aprovado_por"]
    assert conn.execute("select count(*) n from wa_auditoria where acao = 'envio_um_clique_recusado'").fetchone()["n"] == 1


def test_um_clique_sem_autorizacao_bloqueia(conn, evo, monkeypatch):
    lead, c = preparar(conn, consentimento=False)
    configurar(monkeypatch, real_mode=True)
    texto = api("POST", "/api/wa-modelos/MODELO_01/previa", json={"lead_id": lead["id"]}).json()["texto"].replace("[marca]", "X")
    r = api("POST", f"/api/primeiro-contato/{lead['id']}/enviar", json={"contact_id": c["id"], "texto": texto, "chave": "um-clique-0003"})
    assert r.status_code == 409 and "autoriza" in r.text.lower() and evo.envios == []
