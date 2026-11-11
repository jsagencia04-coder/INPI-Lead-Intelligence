from fastapi.testclient import TestClient

from app import db
from app.config import get_settings
from app.jobs import queue, scheduler
from app.jobs.registry import load_agents
from app.main import app
from app.storage import get_storage, sha256_of
from app.worker import run_one
from tests.rpi_helpers import FakeINPI, make_zip, xml_text

load_agents()


def drain(n=20):
    for _ in range(n):
        if not run_one("w-test"):
            return


def discover(payload=None):
    with db.transaction("test") as c:
        queue.enqueue(c, "rpi.discover", payload or {})
    drain()


def test_pipeline_completo_descobre_baixa_e_interpreta(conn):
    fake = FakeINPI().install()
    discover()

    ed = conn.execute("select * from rpi_editions").fetchall()
    assert [(e["numero"], e["status"]) for e in ed] == [(2914, "parsed")]  # banco vazio: só a mais recente
    assert str(ed[0]["data_publicacao"]) == "2026-11-10"
    assert not any("Marcas2914" in u for u in fake.calls)  # PDFs desligados por padrão

    s = ed[0]["stats"]
    assert s["processos_no_xml"] == 12
    assert s["processos_importados"] == 9  # escopo 'alvo'
    assert s["oportunidades_elegiveis"] == 6
    assert s["elegiveis_por_categoria"] == {
        "oposicao": 1,
        "extincao_prorrogacao": 1,
        "indeferimento": 2,
        "exigencia": 2,
    }
    assert s["motivos_descarte"] == {"possui procurador": 1, "Protocolo de Madri": 1, "titular estrangeiro": 1}
    assert s["titulares_unicos"] == 9
    assert s["despachos_novos"] == ["IPAS999"]

    # arquivo original preservado e íntegro
    f = conn.execute("select * from rpi_files").fetchone()
    assert f["nome_arquivo"] == "RM2914.zip" and f["source_url"].endswith("/txt/RM2914.zip")
    assert sha256_of(get_storage().get(f["storage_path"])) == f["sha256"] == sha256_of(fake.files["RM2914.zip"])

    # regras de procurador
    st = {
        r["numero_processo"]: r["procurador_status"]
        for r in conn.execute("select numero_processo, procurador_status from processes")
    }
    assert st["945410948"] == "com_procurador"
    assert st["942334000"] == "sem_na_rpi"  # procurador de petição de terceiro ignorado
    assert "939400901" not in st  # deferimento: fora do escopo

    # titular repetido vira um só
    assert conn.execute("select count(*) n from holders where nome_normalizado = 'FULANO DE TAL EXEMPLO'").fetchone()["n"] == 1
    assert conn.execute("select count(*) n from process_holders where numero_processo = '935837620'").fetchone()["n"] == 2

    # despacho desconhecido vira tarefa de revisão
    assert conn.execute("select revisar from despacho_types where codigo = 'IPAS999'").fetchone()["revisar"]
    assert conn.execute("select count(*) n from review_tasks where entidade_id = 'IPAS999'").fetchone()["n"] == 1

    # dashboard
    with TestClient(app) as c:
        d = c.get("/api/dashboard/summary").json()
        assert d["processos_importados"] == 9
        assert d["processos_sem_procurador"] == 6
        assert d["processos_descartados"] == 3
        lst = c.get("/api/processes", params={"oportunidade": "elegivel", "categoria": "indeferimento"}).json()
        assert {p["numero_processo"] for p in lst["items"]} == {"937208078", "942334000"}
        assert c.get("/api/processes", params={"q": "cicrana"}).json()["total"] == 1
        det = c.get("/api/processes/942334000").json()
        assert det["oportunidades"][0]["status"] == "elegivel"
        assert len(det["publicacoes"]) == 3


def test_reprocessar_e_idempotente(conn):
    FakeINPI().install()
    discover()

    def snap():
        return {
            t: conn.execute(f"select count(*) n from {t}").fetchone()["n"]
            for t in ("processes", "publications", "opportunities", "holders", "process_holders", "rpi_files")
        }

    antes = snap()
    with TestClient(app) as c:
        assert c.post("/api/rpi/editions/2914/parse").status_code == 202
    drain()
    assert snap() == antes
    stats = conn.execute("select stats from rpi_editions").fetchone()["stats"]
    assert stats["publicacoes_novas"] == 0


def test_procurador_em_edicao_posterior_descarta_oportunidade(conn):
    fake = FakeINPI().install()
    discover()
    # Na 2915 o processo 945424620 aparece com procurador.
    xml2915 = xml_text(2915).replace(
        "<nome>MARCA ALFA</nome>\n    </marca>",
        "<nome>MARCA ALFA</nome>\n    </marca>\n    <procurador>NOVO PROCURADOR</procurador>",
    )
    fake.files["RM2915.zip"] = make_zip(xml2915, "RM2915.xml")
    fake.index = fake.index.replace(
        '<tr class="warning"> <td>2914</td>',
        "<tr> <td>2915</td> <td> 2026-11-17 </td>"
        ' <td><a href="https://revistas.inpi.gov.br/txt/RM2915.zip">XML</a></td></tr>'
        '<tr class="warning"> <td>2914</td>',
    )
    discover()
    p = conn.execute("select * from processes where numero_processo = '945424620'").fetchone()
    assert (p["procurador_status"], p["procurador_nome"], p["procurador_fonte"]) == (
        "com_procurador",
        "NOVO PROCURADOR",
        "rpi:2915",
    )
    ops = conn.execute("""select e.numero, o.status, o.motivo_descarte from opportunities o
                          join rpi_editions e on e.id = o.edition_id
                          where numero_processo = '945424620' order by e.numero""").fetchall()
    assert [o["status"] for o in ops] == ["descartada", "descartada"]
    assert ops[0]["motivo_descarte"] == "procurador identificado na RPI 2915"

    # O caminho inverso não vale: ausência posterior não remove procurador conhecido.
    st = conn.execute("select procurador_status from processes where numero_processo = '945410948'").fetchone()
    assert st["procurador_status"] == "com_procurador"
    hist = conn.execute(
        "select count(*) n from audit_log where tabela = 'processes' and registro_id = '945424620' and acao = 'UPDATE'"
    ).fetchone()["n"]
    assert hist >= 1


def test_xml_indisponivel_faz_retry_e_depois_marca_erro(conn):
    fake = FakeINPI().install()
    fake.status["RM2914.zip"] = 404
    discover()
    job = conn.execute("select * from jobs where tipo = 'rpi.collect'").fetchone()
    assert job["status"] == "queued" and "404" in job["ultimo_erro"]
    assert conn.execute("select status from rpi_editions").fetchone()["status"] == "detected"
    conn.execute("update jobs set tentativas = max_tentativas - 1, run_after = now() where id = %s", (job["id"],))
    drain()
    ed = conn.execute("select status, observacoes from rpi_editions").fetchone()
    assert ed["status"] == "error" and "rpi.collect" in ed["observacoes"]
    # depois de corrigido, o botão "Coletar" refaz o caminho
    fake.status.clear()
    with TestClient(app) as c:
        assert c.post("/api/rpi/editions/2914/collect").status_code == 202
    drain()
    assert conn.execute("select status from rpi_editions").fetchone()["status"] == "parsed"


def test_xml_de_outra_edicao_e_rejeitado(conn):
    fake = FakeINPI().install()
    fake.files["RM2914.zip"] = make_zip(xml_text(2900))
    discover()
    assert conn.execute("select status from jobs where tipo = 'rpi.collect'").fetchone()["status"] == "dead"
    assert conn.execute("select status from rpi_editions").fetchone()["status"] == "error"


def test_descobrir_desde_e_nao_repetir(conn):
    fake = FakeINPI().install()
    discover({"desde": 2913})
    assert [r["numero"] for r in conn.execute("select numero from rpi_editions order by numero")] == [2913, 2914]
    n = len(fake.calls)
    discover()
    assert len(fake.calls) == n + 1  # só leu o índice
    assert conn.execute("select count(*) n from jobs where tipo = 'rpi.collect'").fetchone()["n"] == 2


def test_pdfs_opcionais(conn, monkeypatch):
    monkeypatch.setenv("RPI_DOWNLOAD_PDF", "true")
    get_settings.cache_clear()
    try:
        FakeINPI().install()
        discover()
        files = conn.execute("select formato, volume, nome_arquivo from rpi_files order by id").fetchall()
        assert [(f["formato"], f["volume"]) for f in files] == [("zip", None), ("pdf", "1"), ("pdf", "2")]
    finally:
        monkeypatch.delenv("RPI_DOWNLOAD_PDF")
        get_settings.cache_clear()


def test_escopo_todos(conn):
    FakeINPI().install()
    discover()
    with TestClient(app) as c:
        c.post("/api/rpi/editions/2914/parse", params={"scope": "todos"})
    drain()
    assert conn.execute("select count(*) n from processes").fetchone()["n"] == 12


def test_upload_manual(conn):
    with TestClient(app) as c:
        r = c.post("/api/rpi/upload", files={"file": ("RM2914.zip", make_zip(xml_text()), "application/zip")})
        assert r.status_code == 201 and r.json()["numero"] == 2914
        assert c.post("/api/rpi/upload", files={"file": ("x.zip", b"lixo", "application/zip")}).status_code == 422
        drain()
        eds = c.get("/api/rpi/editions").json()
        assert eds[0]["status"] == "parsed" and eds[0]["arquivos"][0]["source_url"] == "upload:dev@local"
        orig = c.get(f"/api/rpi/files/{eds[0]['arquivos'][0]['id']}")
        assert orig.status_code == 200 and orig.headers["x-content-sha256"] == eds[0]["arquivos"][0]["sha256"]


def test_classificar_despacho_resolve_revisao(conn):
    FakeINPI().install()
    discover()
    with TestClient(app) as c:
        r = c.patch("/api/rpi/despachos/IPAS999", json={"categoria_comercial": "exigencia", "ativo_para_leads": True})
        assert r.status_code == 200 and r.json()["confirmado_por"] == "user:dev@local" and not r.json()["revisar"]
        assert conn.execute("select status from review_tasks where entidade_id='IPAS999'").fetchone()["status"] == "resolvida"
        # reprocessar passa a considerar o despacho reclassificado
        c.post("/api/rpi/editions/2914/parse")
        drain()
        assert c.get("/api/processes/946000001").status_code == 200
        lista = c.get("/api/rpi/despachos").json()
        assert lista[0]["ativo_para_leads"] is True


def test_agendador_dispara_uma_vez(conn):
    conn.execute("update schedules set proximo_em = now() - interval '1 minute'")
    with db.transaction("test") as c:
        assert len(scheduler.tick(c)) == 1
    with db.transaction("test") as c:
        assert scheduler.tick(c) == []
    assert conn.execute("select tipo from jobs").fetchone()["tipo"] == "rpi.discover"
