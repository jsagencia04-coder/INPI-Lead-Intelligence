"""V2.0 Fase 6: pipeline comercial de 17 etapas e jornada do lead."""

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.test_consentimento import AUT
from tests.test_fases3a7 import drain, enqueue, importar_rpi, mundo  # noqa: F401
from tests.test_site_crawler import sites  # noqa: F401
from tests.test_whatsapp import _pipeline
from tests.test_whatsapp_api import NUM, assinar, configurar, criar, evento_msg, evento_status, meta  # noqa: F401


def etapa(conn, lead_id):
    return conn.execute("select pipeline_stage from leads where id = %s", (lead_id,)).fetchone()["pipeline_stage"]


def jornada(conn, lead_id):
    return [r["para"] for r in conn.execute("select para from lead_stage_history where lead_id = %s order by id", (lead_id,))]


def test_jornada_completa_pelos_fatos(conn, sites, meta, monkeypatch):  # noqa: F811
    importar_rpi()
    enqueue("leads.build")
    drain()
    gama = conn.execute("""select l.id, l.holder_id from leads l join holders h on h.id = l.holder_id
                           where h.nome_original like 'INDÚSTRIA%%GAMA%%'""").fetchone()
    lid = gama["id"]
    assert etapa(conn, lid) == "lead_novo"

    for t in ("inpi.verify_pending", "cnpj.sync", "leads.build"):
        enqueue(t)
        drain()
    assert etapa(conn, lid) == "contato_identificado"  # telefone/e-mail da Receita: identificado, não validado

    enqueue("research.free_batch")
    drain()
    assert etapa(conn, lid) == "contato_validado"  # WhatsApp publicado pela empresa

    wa = conn.execute("select * from contacts where holder_id = %s and wa_nivel = 'company_evidence'", (gama["holder_id"],)).fetchone()
    with TestClient(app) as c:
        c.patch(f"/api/leads/{lid}", json={"status": "aprovado"})
        assert etapa(conn, lid) == "aguardando_autorizacao"  # número público não é consentimento
        c.post(f"/api/contacts/{wa['id']}/consents", json=AUT)
        assert etapa(conn, lid) == "elegivel_primeiro_contato"

        configurar(monkeypatch, AUTH_MODE="dev", WHATSAPP_LIMITE_POR_DIA="0")
        lead = conn.execute("select * from leads where id = %s", (lid,)).fetchone()
        m = criar(conn, lead, wa)
        assert etapa(conn, lid) == "mensagem_programada"

        # a Meta aceita, entrega e o titular responde (status só pelo webhook)
        conn.execute("update wa_messages set status = 'aceita', aceita_em = now(), wa_message_id = 'wamid.p1' where id = %s", (m["id"],))
        assert etapa(conn, lid) == "mensagem_enviada"
        corpo, cab = assinar(evento_status("wamid.p1", "delivered"))
        c.post("/webhooks/whatsapp", content=corpo, headers=cab)
        assert etapa(conn, lid) == "mensagem_entregue"
        corpo, cab = assinar(evento_msg("wamid.r1", "Tenho interesse, pode me ligar?"))
        c.post("/webhooks/whatsapp", content=corpo, headers=cab)
        assert etapa(conn, lid) == "resposta_recebida"

        # daqui em diante é decisão de uma pessoa
        assert c.post(f"/api/leads/{lid}/pipeline", json={"etapa": "interessado", "motivo": "pediu ligação"}).status_code == 200
        assert c.post(f"/api/leads/{lid}/pipeline", json={"etapa": "proposta_enviada", "motivo": "proposta 12/11"}).status_code == 200
        # um fato novo (outra resposta) não desfaz a decisão manual
        corpo, cab = assinar(evento_msg("wamid.r2", "Recebi a proposta"))
        c.post("/webhooks/whatsapp", content=corpo, headers=cab)
        assert etapa(conn, lid) == "proposta_enviada"

        j = c.get(f"/api/leads/{lid}/jornada").json()
        assert j["pipeline_manual"] is True and j["etapa_pelos_fatos"] == "resposta_recebida"
        manuais = [h for h in j["historico"] if h["origem"] == "manual"]
        assert [h["para"] for h in manuais] == ["interessado", "proposta_enviada"] and manuais[0]["motivo"] == "pediu ligação"
        assert all(h["ator"].startswith("user:") for h in manuais)

        # opt-out prevalece sobre qualquer etapa, inclusive manual, e não tem volta
        corpo, cab = assinar(evento_msg("wamid.r3", "SAIR"))
        c.post("/webhooks/whatsapp", content=corpo, headers=cab)
        assert etapa(conn, lid) == "opt_out"
        assert c.post(f"/api/leads/{lid}/pipeline", json={"etapa": "negociacao", "motivo": "tentar de novo"}).status_code == 409

    assert jornada(conn, lid) == [
        "lead_novo", "contato_identificado", "contato_validado", "aguardando_autorizacao", "elegivel_primeiro_contato",
        "mensagem_programada", "mensagem_enviada", "mensagem_entregue", "resposta_recebida", "interessado",
        "proposta_enviada", "opt_out",
    ]  # fmt: skip
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("delete from lead_stage_history")  # a jornada não se apaga


def test_contato_manual_registrado_conta_como_mensagem_enviada(conn, sites):  # noqa: F811
    _pipeline()
    lead = conn.execute("select * from leads where whatsapp_status = 'validado'").fetchone()
    with TestClient(app) as c:
        c.patch(f"/api/leads/{lead['id']}", json={"status": "aprovado"})
        c.post(f"/api/leads/{lead['id']}/outreach", json={"canal": "whatsapp", "resultado": "enviada"})
    assert etapa(conn, lead["id"]) == "mensagem_enviada"


def test_funil_listagem_e_volta_ao_automatico(conn, sites):  # noqa: F811
    _pipeline()
    with TestClient(app) as c:
        f = c.get("/api/pipeline").json()
        assert len(f["etapas"]) == 17 and [e["ordem"] for e in f["etapas"]] == list(range(1, 18))
        assert f["total"] == sum(e["leads"] for e in f["etapas"]) == conn.execute(
            "select count(*) n from leads where mesclado_em is null").fetchone()["n"]
        por = {e["id"]: e["leads"] for e in f["etapas"]}
        assert por["contato_validado"] == 1 and por["elegivel_primeiro_contato"] == 0 and por["mensagem_enviada"] == 0
        lst = c.get("/api/pipeline/leads", params={"etapa": "contato_validado"}).json()
        assert lst["total"] == 1 and "GAMA" in lst["items"][0]["titular"] and lst["items"][0]["marcas"]
        assert c.get("/api/pipeline/leads", params={"etapa": "inexistente"}).status_code == 422
        lid = lst["items"][0]["id"]
        assert c.post(f"/api/leads/{lid}/pipeline", json={"etapa": "mensagem_entregue", "motivo": "forçar"}).status_code == 422
        assert c.post(f"/api/leads/{lid}/pipeline", json={"etapa": "perdido", "motivo": ""}).status_code == 422  # exige motivo
        c.post(f"/api/leads/{lid}/pipeline", json={"etapa": "perdido", "motivo": "sem orçamento"})
        assert etapa(conn, lid) == "perdido"
        r = c.post(f"/api/leads/{lid}/pipeline", json={"etapa": "automatico", "motivo": "voltou a responder"}).json()
        assert r["pipeline_stage"] == "contato_validado" and r["pipeline_manual"] is False
    # o status original do lead não foi tocado pelo pipeline
    assert conn.execute("select status from leads where id = %s", (lid,)).fetchone()["status"] == "qualificado"


def test_status_existente_e_preservado_e_mapeado(conn, mundo):  # noqa: F811
    importar_rpi()
    enqueue("leads.build")
    drain()
    ids = [r["id"] for r in conn.execute("select id from leads order by id limit 2").fetchall()]
    conn.execute("update leads set status = 'convertido' where id = %s", (ids[0],))
    conn.execute("update leads set status = 'descartado', motivo_descarte = 'sem interesse' where id = %s", (ids[1],))
    assert etapa(conn, ids[0]) == "fechado" and etapa(conn, ids[1]) == "perdido"
