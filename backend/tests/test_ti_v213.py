"""V2.13 · TI (Julio): monitoramento do sistema e correções automáticas seguras."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app import db
from app.agents import ti
from app.jobs import queue
from app.jobs.registry import load_agents
from app.main import app
from app.worker import run_one

load_agents()


@pytest.fixture(autouse=True)
def _disco_folgado(monkeypatch):
    """O disco da máquina de testes não é o do servidor: simula 60% livre."""
    from collections import namedtuple

    U = namedtuple("U", "total used free")
    monkeypatch.setattr(ti.shutil, "disk_usage", lambda p: U(100 * 2**30, 40 * 2**30, 60 * 2**30))


def rodar():
    with db.transaction("test") as c:
        queue.enqueue(c, "sistema.saude", {})
    run_one("w-test")


def test_tudo_ok_e_registro(conn):
    rodar()
    h = conn.execute("select * from system_health").fetchone()
    assert h["status"] == "ok", h["checks"]
    nomes = {c["nome"] for c in h["checks"]}
    assert {"banco", "agendador", "tarefas_travadas", "falhas_24h", "fila", "importacao", "rpi_semana", "disco"} <= nomes
    ev = conn.execute("select tipo from agent_events where agente = 'sistema.saude' and tipo like 'ti.%'").fetchall()
    assert [e["tipo"] for e in ev] == ["ti.ok"]
    with TestClient(app) as c:
        d = c.get("/api/sistema/saude").json()
        assert d["ultima"]["status"] == "ok" and d["ultimas_24h"] == {"ok": 1}
        assert c.get("/api/office/state").json()["saude"]["status"] == "ok"


def test_falha_gera_alerta_e_tarefa_travada_volta_para_fila(conn):
    rodar()
    conn.execute("update app_config set valor = 'failed' where chave = 'last_import_status'")
    j = conn.execute(
        "insert into jobs (tipo, status, locked_by, locked_at) values ('leads.build', 'running', 'w-morto', now() - interval '2 hours') returning id"
    ).fetchone()
    rodar()
    h = conn.execute("select * from system_health order by id desc limit 1").fetchone()
    assert h["status"] == "falha"
    assert h["acoes"] == [{"acao": "tarefas_travadas_devolvidas", "quantidade": 1}]
    assert conn.execute("select status from jobs where id = %s", (j["id"],)).fetchone()["status"] == "queued"
    assert [
        e["tipo"]
        for e in conn.execute("select tipo from agent_events where agente = 'sistema.saude' and tipo like 'ti.%' order by id")
    ] == [
        "ti.ok",
        "ti.falha",
    ]
    assert conn.execute("select count(*) n from review_tasks where entidade = 'sistema'").fetchone()["n"] == 1
    # mesma falha de novo: não repete o alerta
    rodar()
    assert conn.execute("select count(*) n from review_tasks where entidade = 'sistema'").fetchone()["n"] == 1


def test_rpi_da_semana_atrasada(conn):
    terca_tarde = datetime(2026, 11, 17, 18, 0, tzinfo=UTC)  # 15 h em São Paulo
    checks, _ = ti.verificar(conn, agora=terca_tarde, whatsapp=False)
    rpi = next(c for c in checks if c["nome"] == "rpi_semana")
    assert rpi["status"] == "atencao"
    conn.execute("insert into rpi_editions (numero, detectada_em) values (2915, '2026-11-17 09:00-03')")
    checks, _ = ti.verificar(conn, agora=terca_tarde, whatsapp=False)
    assert next(c for c in checks if c["nome"] == "rpi_semana")["status"] == "ok"
