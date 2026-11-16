"""V2.9 · extração paralela PDF + XML da RPI: o PDF do Volume I gera os primeiros leads (SC primeiro) sem esperar o
XML; o XML, quando sai, complementa e é conciliado com o PDF, sem apagar nada e registrando a origem."""

from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.agents import rpi_pdf
from app.jobs import queue
from app.jobs.registry import load_agents
from app.main import app
from app.rpi.pdf_parser import ler_texto, para_processos
from app.worker import run_one
from tests.rpi_helpers import FakeINPI

load_agents()
TRECHO = (Path(__file__).parent / "fixtures" / "marcas_2914_I_trecho.txt").read_text(encoding="utf-8")


def drain(n=60):
    for _ in range(n):
        if not run_one("w-test"):
            return


def discover():
    with db.transaction("test") as c:
        queue.enqueue(c, "rpi.discover", {})
    drain()


def ligar_pdf(conn, monkeypatch, texto=TRECHO):
    conn.execute("update app_config set valor = 'true' where chave = 'rpi_pdf_primeiro'")
    monkeypatch.setattr(rpi_pdf, "extrair_texto", lambda caminho: texto)


def test_leitura_do_texto_do_pdf():
    lei = ler_texto(TRECHO)
    assert lei.edicao == 2914 and lei.data == "10/11/2026" and lei.paginas == 4
    nums = [e.numero_processo for e in lei.entradas]
    assert nums == ["950000001", "950000002", "950000003", "950000004", "950000005", "937208078", "942334000",
                    "950000006", "950000007"]  # fmt: skip
    e = {x.numero_processo: x for x in lei.entradas}
    t = e["950000001"].titulares[0]
    assert (t.nome, t.pais, t.uf) == ("LOJA EXEMPLO CATARINENSE LTDA", "BR", "SC")
    assert e["950000003"].titulares[0].pais == "US" and e["950000003"].titulares[0].uf is None
    assert e["950000002"].procurador == "ESCRITORIO FICTICIO DE MARCAS" and e["950000001"].procurador is None
    # campo que continua na página seguinte, depois do cabeçalho e do número da página
    assert "MEGA MOTOS" in e["942334000"].campo("Detalhes do despacho")
    assert "824590570 (CAÇA-PALAVRA GRILO)" in e["942334000"].campo("Detalhes do despacho")  # citação, não entrada
    assert e["942334000"].pagina == 3 and e["950000004"].pagina == 2
    # nome de despacho desconhecido não vira processo
    procs = para_processos(lei.entradas, {"Notificação de oposição": "IPAS423", "Indeferimento do pedido": "IPAS024"})
    assert "950000007" not in {p.numero for p in procs} and len(procs) == 8


def test_pdf_antes_do_xml_gera_leads_de_sc_primeiro(conn, monkeypatch):
    fake = FakeINPI()
    fake.status["RM2914.zip"] = 404  # o XML ainda não saiu
    fake.install()
    ligar_pdf(conn, monkeypatch)
    discover()

    fontes = {r["fonte"]: r for r in conn.execute("select * from rpi_fontes").fetchall()}
    assert set(fontes) == {"pdf_i", "pdf_ii", "xml"}
    assert all(f["detectado_em"] for f in fontes.values())
    pdf = fontes["pdf_i"]
    assert pdf["status"] == "processado" and pdf["registros"] == 9 and pdf["registros_alvo"] == 8
    assert pdf["tempo_download_s"] is not None and pdf["tempo_processamento_s"] is not None
    assert pdf["detalhes"]["por_lote"] == {"SC": 2, "RS": 1, "PR": 1, "DEMAIS": 4}
    assert fontes["xml"]["status"] == "detectado"  # 404: nova tentativa mais tarde, sem travar o PDF
    assert "404" in conn.execute("select ultimo_erro from jobs where tipo = 'rpi.collect'").fetchone()["ultimo_erro"]

    ed = conn.execute("select * from rpi_editions").fetchone()
    assert ed["status"] == "parsed" and ed["stats"]["fonte"] == "pdf_i"
    assert str(ed["data_publicacao"]) == "2026-11-10"

    # os lotes foram qualificados nesta ordem: SC, RS, PR, demais
    lotes = [
        r["payload"]["lote"]
        for r in conn.execute(
            "select payload from jobs where tipo = 'rpi.pdf_importar' and status = 'succeeded' order by finalizado_em, id"
        ).fetchall()
    ]
    assert lotes == ["SC", "RS", "PR", "DEMAIS"]

    # publicações com a origem registrada e o texto original preservado
    assert {r["fonte"] for r in conn.execute("select fonte from publications").fetchall()} == {"pdf"}
    reg = conn.execute("select * from rpi_pdf_registros where numero_processo = '950000001'").fetchone()
    assert reg["despacho_codigo"] == "IPAS423" and reg["categoria"] == "oposicao_apresentada" and reg["pagina"] == 1
    assert "LOJA EXEMPLO CATARINENSE" in reg["texto"] and reg["importado_em"] is not None
    assert (
        conn.execute("select procurador_fonte from processes where numero_processo = '950000002'").fetchone()["procurador_fonte"]
        == "rpi:2914:pdf"
    )

    opp = {
        r["numero_processo"]: (r["status"], r["motivo_descarte"])
        for r in conn.execute("select numero_processo, status, motivo_descarte from opportunities").fetchall()
    }
    assert opp["950000001"] == ("elegivel", None) and opp["950000006"] == ("elegivel", None)
    assert opp["950000002"][0] == "descartada"  # com procurador
    assert opp["950000003"] == ("descartada", "titular estrangeiro")

    # primeiros leads de SC já existem, antes do XML
    leads_sc = conn.execute(
        """select h.nome_original from leads l join holders h on h.id = l.holder_id
            where h.uf = 'SC' and l.status <> 'descartado' order by 1"""
    ).fetchall()
    assert [r["nome_original"] for r in leads_sc] == ["LOJA EXEMPLO CATARINENSE LTDA", "OFICINA FLORIANOPOLIS EXEMPLO LTDA"]

    # indicadores
    with TestClient(app) as c:
        d = c.get("/api/rpi-fontes").json()
    assert d["edicao"]["numero"] == 2914
    assert [f["fonte"] for f in d["fontes"]] == ["pdf_i", "xml", "pdf_ii"]
    assert d["publicacoes_por_fonte"] == {"pdf": 8}
    assert d["leads_qualificados"][0]["uf"] == "SC" and d["leads_qualificados"][0]["pelo_pdf"] == 2

    # ---- o XML sai: complementa, substitui o texto das publicações e é conciliado com o PDF
    fake.status.pop("RM2914.zip")
    conn.execute("update jobs set run_after = now() where status = 'queued'")
    drain()
    ed = conn.execute("select * from rpi_editions").fetchone()
    assert ed["status"] == "parsed" and ed["stats"]["processos_no_xml"] == 12
    x = conn.execute("select * from rpi_fontes where fonte = 'xml'").fetchone()
    assert x["status"] == "processado" and x["registros"] == 12 and x["processado_em"] is not None

    fontes_pub = {
        r["numero_processo"]: r["fonte"]
        for r in conn.execute("select numero_processo, fonte from publications where despacho_codigo in ('IPAS024','IPAS423')")
    }
    assert fontes_pub["937208078"] == "xml" and fontes_pub["942334000"] == "xml"  # o XML oficial substitui
    assert fontes_pub["950000001"] == "pdf"  # só o PDF trouxe: continua, marcado como PDF
    assert conn.execute("select count(*) n from rpi_pdf_registros").fetchone()["n"] == 8  # originais preservados

    conc = {
        r["numero_processo"]: (r["situacao"], r["diferencas"])
        for r in conn.execute("select * from rpi_reconciliacao where despacho_codigo in ('IPAS024','IPAS423')")
    }
    assert conc["937208078"] == ("confere", {})
    assert conc["942334000"][0] == "divergente" and "procurador" in conc["942334000"][1]
    assert conc["950000001"][0] == "so_pdf"
    tarefas = [r["motivo"] for r in conn.execute("select motivo from review_tasks where entidade = 'rpi_reconciliacao'")]
    assert any("942334000" in t and "divergem" in t for t in tarefas)
    assert any("950000001" in t and "não está no XML" in t for t in tarefas)

    # sem duplicidade: rodar o XML de novo não cria nada repetido
    antes = conn.execute("select count(*) n from rpi_reconciliacao").fetchone()["n"]
    with db.transaction("test") as c:
        queue.enqueue(c, "rpi.parse", {"numero": 2914}, dedupe_key="rpi.parse:2914:de-novo")
    drain()
    assert conn.execute("select count(*) n from rpi_reconciliacao").fetchone()["n"] == antes
    assert conn.execute("select count(*) n from review_tasks where entidade = 'rpi_reconciliacao'").fetchone()["n"] == len(
        tarefas
    )


def test_xml_primeiro_dispensa_o_pdf(conn, monkeypatch):
    FakeINPI().install()
    discover()  # leitura antecipada desligada: o fluxo de sempre, só XML
    assert not conn.execute("select 1 from jobs where tipo = 'rpi.pdf'").fetchone()
    ligar_pdf(conn, monkeypatch)
    ed = conn.execute("select * from rpi_editions").fetchone()
    assert rpi_pdf.enfileirar_pdf(conn, ed) is False  # o XML já foi lido: o PDF não é necessário
    with db.transaction("test") as c:
        queue.enqueue(c, "rpi.pdf", {"numero": 2914})
    drain()
    assert conn.execute("select status from rpi_fontes where fonte = 'pdf_i'").fetchone()["status"] == "ignorado"
    assert conn.execute("select count(*) n from rpi_pdf_registros").fetchone()["n"] == 0


def test_pdf_indisponivel_continua_monitorando(conn, monkeypatch):
    fake = FakeINPI()
    fake.status["Marcas2914_I.pdf"] = 404
    fake.install()
    ligar_pdf(conn, monkeypatch)
    discover()
    # o XML segue normalmente; o PDF fica para nova tentativa, sem confundir com a validação do XML
    ed = conn.execute("select * from rpi_editions").fetchone()
    assert ed["status"] == "parsed" and ed["stats"]["processos_no_xml"] == 12
    assert conn.execute("select status from rpi_fontes where fonte = 'xml'").fetchone()["status"] == "processado"
    assert conn.execute("select count(*) n from publications where fonte = 'pdf'").fetchone()["n"] == 0
