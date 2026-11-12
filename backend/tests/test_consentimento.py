"""V2.0 Fase 8: regra de consentimento. Número público não é consentimento."""

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import consent, wa_cloud
from app.main import app
from tests.test_fases3a7 import drain, mundo  # noqa: F401
from tests.test_site_crawler import sites  # noqa: F401
from tests.test_whatsapp_api import ENV, NUM, Meta, assinar, configurar, criar, evento_msg, meta, msg, preparar  # noqa: F401

AUT = {
    "empresa_identificada": "Prestador Teste", "obtido_em": "2026-11-10T14:00:00Z", "metodo": "email",
    "fonte_evidencia": "e-mail de 10/11/2026, assunto 'Re: Publicação do INPI'", "texto_autorizacao": "Autorizo. Meu WhatsApp é (11) 98888-7777",
    "numero_fornecido": True,
}  # fmt: skip


def regras(c, contact_id):
    e = c.get(f"/api/contacts/{contact_id}/elegibilidade").json()
    return e["elegivel"], {r["regra"]: r["ok"] for r in e["regras"]}


def test_numero_publico_validado_nao_e_elegivel_sem_autorizacao(conn, sites, meta):  # noqa: F811
    lead, wa = preparar(conn)
    with TestClient(app) as c:
        ok, r = regras(c, wa["id"])
        assert not ok
        # validado pela empresa e lead aprovado, mas SEM autorização e sem o número ter sido fornecido
        assert r["contato_validado"] and r["lead_aprovado"] and r["sem_optout"]
        assert not r["autorizacao"] and not r["numero_fornecido"]

        # autorização registrada, mas o número não foi fornecido pelo destinatário: ainda não
        k = c.post(f"/api/contacts/{wa['id']}/consents", json=AUT | {"numero_fornecido": False}).json()
        ok, r = regras(c, wa["id"])
        assert not ok and r["autorizacao"] and not r["numero_fornecido"]
        assert c.post(f"/api/contacts/{wa['id']}/consents", json=AUT).status_code == 409  # não duplica ativa

        # revoga e registra a correta
        assert c.post(f"/api/consents/{k['id']}/revoke", json={"origem": "registro incorreto"}).status_code == 200
        k2 = c.post(f"/api/contacts/{wa['id']}/consents", json=AUT)
        assert k2.status_code == 201 and k2.json()["versao_aviso"] == consent.AVISO_VERSAO
        ok, r = regras(c, wa["id"])
        assert r["autorizacao"] and r["numero_fornecido"] and not r["template_aprovado"] and not ok  # falta só a Meta

        # lead deixa de estar aprovado -> deixa de ser elegível
        conn.execute("update leads set status = 'qualificado' where id = %s", (lead["id"],))
        assert not regras(c, wa["id"])[1]["lead_aprovado"]
    hist = conn.execute("select status from consents order by id").fetchall()
    assert [h["status"] for h in hist] == ["revogado", "ativo"]  # a prova da primeira continua guardada


def test_candidato_nunca_e_elegivel_mesmo_com_autorizacao(conn, sites, meta):  # noqa: F811
    lead, wa = preparar(conn)
    conn.execute("update contacts set verificacao = 'formato_ok' where id = %s", (wa["id"],))
    with TestClient(app) as c:
        c.post(f"/api/contacts/{wa['id']}/consents", json=AUT)
        ok, r = regras(c, wa["id"])
    assert not ok and not r["contato_validado"] and r["autorizacao"]


def test_validacoes_do_registro(conn, sites, meta):  # noqa: F811
    lead, wa = preparar(conn)
    with TestClient(app) as c:
        assert c.post(f"/api/contacts/{wa['id']}/consents", json=AUT | {"obtido_em": "2099-01-01T00:00:00Z"}).status_code == 422
        assert c.post(f"/api/contacts/{wa['id']}/consents", json=AUT | {"fonte_evidencia": ""}).status_code == 422
        assert c.post(f"/api/contacts/{wa['id']}/consents", json=AUT | {"metodo": "achei na internet"}).status_code == 422
        assert c.post("/api/contacts/999999/consents", json=AUT).status_code == 404
        # opt-out impede registrar autorização
        c.post("/api/optout", json={"tipo": "telefone", "valor": NUM})
        assert c.post(f"/api/contacts/{wa['id']}/consents", json=AUT).status_code == 409
    assert conn.execute("select count(*) n from consents").fetchone()["n"] == 0


def test_envio_real_so_com_todas_as_regras(conn, sites, meta, monkeypatch):  # noqa: F811
    lead, wa = preparar(conn)
    configurar(monkeypatch, WHATSAPP_NUMEROS_TESTE="")  # sem atalho de homologação
    m = criar(conn, lead, wa)
    drain()
    m1 = msg(conn, m["id"])
    assert m1["status"] == "bloqueada" and "Sem autorização" in m1["motivo"] and meta.envios == []

    # com a autorização comprovada, a mesma mensagem passa
    conn.execute(
        """insert into consents (contact_id, canal, finalidade, empresa_identificada, obtido_em, metodo, fonte_evidencia,
                                 texto_autorizacao, versao_aviso, numero_fornecido)
           values (%s, 'whatsapp', %s, 'Prestador', now(), 'email', 'e-mail x', 'Autorizo', %s, true)""",
        (wa["id"], consent.FINALIDADE_PADRAO, consent.AVISO_VERSAO),
    )
    conn.execute("update wa_messages set status = 'na_fila', motivo = null where id = %s", (m["id"],))
    from app import db
    from app.jobs import queue

    with db.transaction("t") as c:
        queue.enqueue(c, "whatsapp.send", {"message_id": m["id"]})
    drain()
    assert msg(conn, m["id"])["status"] == "aceita" and len(meta.envios) == 1


def test_em_producao_numero_de_teste_nao_fura_a_regra(conn, sites, meta, monkeypatch):  # noqa: F811
    lead, wa = preparar(conn)
    configurar(monkeypatch)  # NUM está em WHATSAPP_NUMEROS_TESTE
    m = criar(conn, lead, wa)
    monkeypatch.setenv("APP_ENV", "producao")
    from app.config import get_settings

    get_settings.cache_clear()
    drain()
    assert msg(conn, m["id"])["status"] == "bloqueada" and meta.envios == []


def test_revogar_cancela_o_que_estava_na_fila(conn, sites, meta, monkeypatch):  # noqa: F811
    lead, wa = preparar(conn)
    with TestClient(app) as c:
        k = c.post(f"/api/contacts/{wa['id']}/consents", json=AUT).json()
        configurar(monkeypatch, WHATSAPP_LIMITE_POR_DIA="0", AUTH_MODE="dev")
        m = criar(conn, lead, wa)
        assert msg(conn, m["id"])["status"] == "na_fila"
        assert c.post(f"/api/consents/{k['id']}/revoke", json={"origem": "pediu por telefone"}).status_code == 200
        assert c.post(f"/api/consents/{k['id']}/revoke", json={"origem": "de novo"}).status_code == 409
    m = msg(conn, m["id"])
    assert m["status"] == "cancelada" and "revogada" in m["motivo"]
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("delete from consents")


def test_pedido_de_autorizacao_por_email(conn, sites, meta):  # noqa: F811
    lead, wa = preparar(conn)
    email = conn.execute("select * from contacts where holder_id = %s and tipo = 'email' limit 1", (wa["holder_id"],)).fetchone()
    outro = conn.execute("select id from contacts where holder_id <> %s limit 1", (wa["holder_id"],)).fetchone()
    with TestClient(app) as c:
        corpo = {"via_contact_id": email["id"], "empresa_identificada": "Fulano, agente de propriedade industrial"}
        r = c.post(f"/api/contacts/{wa['id']}/consent-requests", json=corpo)
        assert r.status_code == 201
        p = r.json()
        assert p["para"] == email["valor_normalizado"] and p["mailto"].startswith(f"mailto:{email['valor_normalizado']}?subject=")
        assert "828886318" in p["texto"] and "Autorizo" in p["texto"] and "exclusão" in p["texto"]
        assert "dias" not in p["texto"] and "prazo" not in p["texto"].lower()  # sem prazos legais
        # nada foi enviado pelo sistema, e pedir de novo é recusado
        assert conn.execute("select count(*) n from wa_messages").fetchone()["n"] == 0
        assert c.post(f"/api/contacts/{wa['id']}/consent-requests", json=corpo).status_code == 409
        if outro:
            assert c.post(f"/api/contacts/{wa['id']}/consent-requests", json=corpo | {"via_contact_id": outro["id"]}).status_code == 409
        # a resposta positiva vira consentimento ligado ao pedido
        k = c.post(f"/api/contacts/{wa['id']}/consents", json=AUT | {"pedido_id": p["id"]}).json()
        lista = c.get(f"/api/contacts/{wa['id']}/consents").json()
        assert lista["pedidos"][0]["status"] == "autorizado" and lista["pedidos"][0]["consent_id"] == k["id"]
        # o pedido em si NÃO é autorização
    assert conn.execute("select count(*) n from consents").fetchone()["n"] == 1


def test_optout_pelo_whatsapp_revoga_e_tira_a_elegibilidade(conn, sites, meta, monkeypatch):  # noqa: F811
    lead, wa = preparar(conn)
    with TestClient(app) as c:
        c.post(f"/api/contacts/{wa['id']}/consents", json=AUT)
        configurar(monkeypatch, AUTH_MODE="dev")
        corpo, cab = assinar(evento_msg("wamid.sair", "PARAR"))
        assert c.post("/webhooks/whatsapp", content=corpo, headers=cab).json()["optouts"] == 1
        ok, r = regras(c, wa["id"])
    assert not ok and not r["sem_optout"] and not r["autorizacao"] and not r["contato_validado"]
    assert wa_cloud.eh_optout("PARAR")
