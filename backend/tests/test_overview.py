"""UX V2.2: painel executivo, alertas e desempenho dos agentes (somente leitura)."""

from fastapi.testclient import TestClient

from app.main import app
from tests.test_fases3a7 import drain, enqueue, mundo  # noqa: F401
from tests.test_site_crawler import sites  # noqa: F401
from tests.test_whatsapp import _pipeline


def test_painel_com_banco_vazio(conn):
    with TestClient(app) as c:
        o = c.get("/api/dashboard/overview").json()
    assert o["kpis"]["leads"] == 0 and o["kpis"]["taxa_conversao"] is None
    assert len(o["series"]) == 14 and all(s["leads"] == 0 for s in o["series"])
    assert o["pipeline"] == [] and o["agentes"] == {}
    assert o["pendencias"] == []
    conn.execute(
        "insert into schedules (nome, tipo, intervalo_minutos, ativo, proximo_em) values ('cnpj-receita', 'cnpj.sync', 10080, false, now())"
    )
    with TestClient(app) as c:
        assert [p["chave"] for p in c.get("/api/alerts").json()] == ["receita"]  # Receita desligada vira aviso


def test_painel_reflete_os_dados(conn, sites):  # noqa: F811
    _pipeline()
    antes = conn.execute("select count(*) n, max(updated_at) u from leads").fetchone()
    with TestClient(app) as c:
        o = c.get("/api/dashboard/overview", params={"dias": 7}).json()
        alertas = c.get("/api/alerts").json()
        st = c.get("/api/office/stats").json()
    k = o["kpis"]
    assert k["leads"] == conn.execute("select count(*) n from leads where status <> 'descartado'").fetchone()["n"] > 0
    assert k["whatsapp_validado"] == 1 and k["autorizacoes"] == 0
    assert len(o["series"]) == 7 and o["series"][-1]["leads"] == k["leads"] and o["series"][-1]["tarefas_ok"] > 0
    assert sum(p["n"] for p in o["pipeline"]) == conn.execute("select count(*) n from leads").fetchone()["n"]
    assert {w["chave"] for w in o["whatsapp_niveis"]} >= {"company_evidence"}
    assert o["edicoes"][0]["numero"] == 2914
    ag = o["agentes"]["research.free"]
    assert ag["execucoes"] >= 1 and ag["taxa_sucesso"] == 100.0 and st["tipos"]["research.free"]["execucoes"] == ag["execucoes"]
    # pendências: ordenadas por gravidade e só com quantidade > 0
    sev = [p["severidade"] for p in alertas]
    ordem = {"critico": 0, "aviso": 1, "oportunidade": 2, "info": 3}
    assert sev == sorted(sev, key=lambda s: ordem[s]) and all(p["quantidade"] > 0 for p in alertas)
    assert alertas == o["pendencias"]
    # somente leitura: nada mudou
    depois = conn.execute("select count(*) n, max(updated_at) u from leads").fetchone()
    assert antes == depois


def test_pendencias_de_falha_e_worker(conn):
    conn.execute("insert into jobs (tipo, status, finalizado_em, ultimo_erro) values ('rpi.discover', 'dead', now(), 'x')")
    conn.execute("update schedules set proximo_em = now() - interval '1 hour', ativo = true where nome = 'rpi-descoberta'")
    with TestClient(app) as c:
        a = c.get("/api/alerts").json()
    assert [x["chave"] for x in a[:2]] == ["worker", "falhas"] and a[0]["severidade"] == "critico"
    assert a[1]["href"] == "/jobs?status=dead"
