"""INPI AI Office: eventos reais (triggers), estado derivado da fila e WebSocket."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import db
from app.config import get_settings
from app.jobs import queue
from app.jobs.registry import load_agents
from app.main import app
from app.worker import run_one
from tests.rpi_helpers import make_zip, xml_text

load_agents()


def tipos_eventos(conn, agente=None):
    q = "select tipo from agent_events" + (" where agente = %s" if agente else "") + " order by id"
    return [r["tipo"] for r in conn.execute(q, (agente,) if agente else ())]


def state(c):
    return c.get("/api/office/state").json()


def test_ciclo_de_vida_do_job_vira_eventos(conn):
    with db.transaction("t") as c:
        queue.enqueue(c, "system.ping")
    run_one("w")
    assert tipos_eventos(conn) == ["task.created", "task.started", "agent.started", "task.completed", "agent.completed"]
    ev = conn.execute("select * from agent_events where tipo = 'task.completed'").fetchone()
    assert ev["agente"] == "system.ping" and ev["referencia"].startswith("job:") and ev["resultado"]["pong"] is True


def test_falha_temporaria_e_definitiva(conn):
    with db.transaction("t") as c:
        queue.enqueue(c, "system.ping", {"fail": "transient"}, max_tentativas=2)
    run_one("w")
    assert tipos_eventos(conn)[-2:] == ["task.failed", "agent.waiting"]
    conn.execute("update jobs set run_after = now()")
    run_one("w")
    assert tipos_eventos(conn)[-2:] == ["task.failed", "agent.error"]
    erro = conn.execute("select resultado from agent_events where tipo = 'task.failed' order by id desc").fetchone()
    assert "transitória" in erro["resultado"]["erro"]


def test_estado_derivado_da_fila(conn):
    with TestClient(app) as c:
        with db.transaction("t") as tx:
            queue.enqueue(tx, "system.ping")
        assert state(c)["tipos"]["system.ping"]["state"] == "waiting"
        with db.transaction("t") as tx:
            queue.claim(tx, "w")
        s = state(c)["tipos"]["system.ping"]
        assert s["state"] == "working" and s["executando"] == 1
        conn.execute("update jobs set status = 'queued', locked_by = null")
        run_one("w")
        s = state(c)["tipos"]["system.ping"]
        assert s["state"] == "completed" and s["concluidos_hoje"] == 1 and s["ultimo"]["status"] == "succeeded"
        conn.execute("update jobs set finalizado_em = now() - interval '10 minutes'")
        assert state(c)["tipos"]["system.ping"]["state"] == "idle"

        # agente de IA em execução aparece como "pensando"
        with db.transaction("t") as tx:
            queue.enqueue(tx, "research.holder", {"holder_id": 1})
            queue.claim(tx, "w", ["research.holder"])
        s = state(c)["tipos"]["research.holder"]
        assert s["state"] == "thinking" and s["tarefa"] == "Pesquisando contatos do titular #1 com IA"
        assert "agent.thinking" in tipos_eventos(conn, "research.holder")

        # falha definitiva recente -> error
        with db.transaction("t") as tx:
            queue.enqueue(tx, "system.ping", {"fail": "permanent"})
        run_one("w")
        assert state(c)["tipos"]["system.ping"]["state"] == "error"


def test_agendador_parado_aparece_como_erro(conn):
    with TestClient(app) as c:
        assert state(c)["sistema"]["worker_ok"] is True
        conn.execute("update schedules set proximo_em = now() - interval '1 hour'")
        s = state(c)
        assert s["sistema"]["worker_ok"] is False and s["tipos"]["scheduler"]["state"] == "error"
        assert "rpi-descoberta" in s["tipos"]["scheduler"]["tarefa"]


def test_eventos_de_negocio_rpi_e_leads(conn):
    with TestClient(app) as c:
        c.post("/api/rpi/upload", files={"file": ("RM2914.zip", make_zip(xml_text()), "application/zip")})
        for _ in range(10):
            run_one("w")
        with db.transaction("t") as tx:
            queue.enqueue(tx, "leads.build")
        run_one("w")
        ev = c.get("/api/office/events").json()
        tipos = [e["tipo"] for e in ev]
        assert "rpi.imported" in tipos and "rpi.processed" in tipos and "lead.discovered" in tipos
        proc = next(e for e in ev if e["tipo"] == "rpi.processed")
        assert proc["descricao"] == "Revista 2914: 12 processos, 6 elegíveis"
        assert c.get("/api/office/events", params={"after": ev[-1]["id"]}).json() == []
        k = state(c)["kpis"]
        assert k["leads"] > 0 and k["ultimo_evento_id"] == ev[-1]["id"]
        h = c.get("/api/office/history", params={"tipos": "rpi.parse"}).json()
        assert h[0]["status"] == "succeeded" and h[0]["tarefa"] == "Interpretando a RPI 2914"


def test_websocket_envia_snapshot_e_novos_eventos(conn):
    with TestClient(app) as c, c.websocket_connect("/ws/office") as ws:
        primeiro = ws.receive_json()
        assert primeiro["tipo"] == "snapshot" and "tipos" in primeiro["estado"]
        with db.transaction("t") as tx:
            queue.enqueue(tx, "system.ping")
        msg = ws.receive_json()
        while msg["tipo"] != "update":
            msg = ws.receive_json()
        assert [e["tipo"] for e in msg["eventos"]] == ["task.created"]
        assert msg["estado"]["tipos"]["system.ping"]["state"] == "waiting"


def test_websocket_exige_login_em_producao(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "supabase")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "x" * 40)
    get_settings.cache_clear()
    try:
        with TestClient(app) as c, pytest.raises(WebSocketDisconnect), c.websocket_connect("/ws/office") as ws:
            ws.receive_json()
        assert c.get("/api/office/state").status_code == 401
    finally:
        monkeypatch.delenv("AUTH_MODE")
        get_settings.cache_clear()
