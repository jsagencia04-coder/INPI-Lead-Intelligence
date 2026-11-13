from fastapi.testclient import TestClient

from app.main import app
from app.worker import run_one


def client():
    return TestClient(app)


def test_health():
    with client() as c:
        r = c.get("/health")
    assert r.status_code == 200 and r.json()["schema"].endswith("_primeiro_contato_evolution.sql")


def test_fluxo_api_fila_worker_dashboard():
    with client() as c:
        assert c.get("/api/dashboard/summary").json()["processos_importados"] == 0
        r = c.post("/api/jobs", json={"tipo": "system.ping"})
        assert r.status_code == 201 and r.json()["criado_por"] == "user:dev@local"
        assert c.get("/api/dashboard/history").json()["jobs"][0]["status"] == "queued"
        run_one("w-api")
        assert c.get("/api/jobs", params={"status": "succeeded"}).json()[0]["tipo"] == "system.ping"


def test_tipo_de_job_desconhecido_rejeitado():
    with client() as c:
        assert c.post("/api/jobs", json={"tipo": "nao.existe"}).status_code == 422


def test_retry_manual_de_job_dead(conn):
    with client() as c:
        job = c.post("/api/jobs", json={"tipo": "system.ping", "payload": {"fail": "permanent"}}).json()
        run_one("w")
        assert c.post(f"/api/jobs/{job['id']}/retry").json()["status"] == "queued"
        assert c.post(f"/api/jobs/{job['id']}/retry").status_code == 409


def test_processo_e_lead_detalhe(conn):
    conn.execute("insert into rpi_editions (numero) values (2900)")
    conn.execute("insert into processes (numero_processo, marca_nome) values ('912345678','ACME')")
    conn.execute("insert into holders (nome_original, nome_normalizado, uf) values ('Ana Silva','ANA SILVA','SP')")
    conn.execute("insert into process_holders values ('912345678', 1, 1)")
    conn.execute("insert into publications (numero_processo, edition_id, despacho_codigo) values ('912345678',1,'X')")
    conn.execute("insert into leads (holder_id) values (1)")
    conn.execute("insert into lead_processes values (1, '912345678')")
    with client() as c:
        p = c.get("/api/processes/912345678").json()
        assert p["titulares"][0]["nome_original"] == "Ana Silva" and p["publicacoes"][0]["rpi_numero"] == 2900
        assert c.get("/api/processes", params={"q": "acm"}).json()["total"] == 1
        lead = c.get("/api/leads/1").json()
        assert lead["processos"][0]["ultimo_despacho"]["rpi"] == 2900
        assert lead["precisa_revisao"] is True
        assert c.get("/api/leads").json()["items"][0]["n_processos"] == 1
        assert c.get("/api/leads/999").status_code == 404
