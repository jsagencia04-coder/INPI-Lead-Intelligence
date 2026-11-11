"""V2.0 Fase 1/2: Central de contatos e níveis de WhatsApp em campos independentes."""

import csv
import io

import psycopg
import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.main import app
from tests.test_fases3a7 import drain, enqueue, importar_rpi, mundo  # noqa: F401
from tests.test_site_crawler import sites  # noqa: F401
from tests.test_whatsapp import _pipeline


def _contato(conn, holder, tipo, valor, norm, verificacao="formato_ok", fonte="web", url="https://empresa-real.com.br/contato"):
    ev = conn.execute(
        "insert into evidences (url, trecho, fonte_tipo) values (%s, %s, %s) returning id", (url, f"trecho {valor}", fonte)
    ).fetchone()["id"]
    return conn.execute(
        "insert into contacts (holder_id, tipo, valor, valor_normalizado, evidence_id, fonte_tipo, verificacao, confianca)"
        " values (%s, %s, %s, %s, %s, %s, %s, 0.5) returning *",
        (holder, tipo, valor, norm, ev, fonte, verificacao),
    ).fetchone()


def _holder(conn, nome="CICRANA DE SOUZA EXEMPLO"):
    return conn.execute("select id from holders where nome_original = %s", (nome,)).fetchone()["id"]


def test_niveis_de_whatsapp_sao_campos_independentes(conn, mundo):  # noqa: F811
    importar_rpi()
    h = _holder(conn)
    tel = _contato(conn, h, "telefone", "(61) 99999-8888", "+5561999998888")
    fixo = _contato(conn, h, "telefone", "(61) 3333-4444", "+556133334444")
    assert tel["eh_celular"] is True and fixo["eh_celular"] is False
    assert tel["wa_nivel"] is None  # telefone celular não é WhatsApp

    wa = _contato(conn, h, "whatsapp", "(61) 99999-8888", "+5561999998888", "encontrado")
    assert (wa["wa_nivel"], wa["wa_conta"], wa["wa_comercial"]) == ("found", "desconhecido", "desconhecido")

    def nivel(verificacao):
        return conn.execute(
            "update contacts set verificacao = %s where id = %s returning wa_nivel, wa_conta, wa_comercial",
            (verificacao, wa["id"]),
        ).fetchone()

    assert nivel("formato_ok") == {"wa_nivel": "candidate", "wa_conta": "desconhecido", "wa_comercial": "desconhecido"}
    # a empresa publica como WhatsApp: é o canal comercial, mas a existência da conta segue não confirmada
    assert nivel("dominio_ok") == {
        "wa_nivel": "company_evidence",
        "wa_conta": "desconhecido",
        "wa_comercial": "publicado_pela_empresa",
    }
    assert nivel("verificado_humano")["wa_nivel"] == "human_confirmed"
    assert conn.execute("select wa_conta from contacts where id = %s", (wa["id"],)).fetchone()["wa_conta"] == "confirmada"
    assert nivel("invalido")["wa_nivel"] == "invalid"
    # nenhum desses níveis cria autorização
    assert conn.execute("select count(*) n from consents").fetchone()["n"] == 0


def test_telefone_da_receita_nunca_vira_whatsapp_validado(conn, mundo):  # noqa: F811
    importar_rpi()
    for t in ("inpi.verify_pending", "cnpj.sync", "leads.build"):
        enqueue(t)
        drain()
    niveis = {
        r["wa_nivel"]
        for r in conn.execute("select wa_nivel from contacts where tipo = 'whatsapp' and fonte_tipo = 'receita'").fetchall()
    }
    assert niveis <= {"found", "candidate"}


def test_central_lista_filtra_busca_ordena_e_pagina(conn, sites):  # noqa: F811
    _pipeline()
    with TestClient(app) as c:
        todos = c.get("/api/contact-central").json()
        assert todos["total"] >= 2 and len({x["holder_id"] for x in todos["items"]}) == len(todos["items"])
        gama = c.get("/api/contact-central", params={"filtro": "wa_empresa"}).json()["items"]
        assert len(gama) == 1 and "GAMA" in gama[0]["titular"]
        g = gama[0]
        wa = next(x for x in g["contatos"] if x["tipo"] == "whatsapp")
        assert wa["wa_nivel"] == "company_evidence" and wa["fonte_url"].startswith("http") and wa["com_permissao"] is False
        assert g["marcas"] and g["processos"] and g["lead_id"] and g["pesquisado_em"]

        # busca por nome, marca, processo e CNPJ levam ao mesmo titular
        proc = g["processos"].split(", ")[0]
        marca = g["marcas"].split(", ")[0]
        for termo in ("gama", marca, proc, g["cnpj"]):
            if termo:
                achados = c.get("/api/contact-central", params={"q": termo}).json()["items"]
                assert g["holder_id"] in [x["holder_id"] for x in achados], termo
        assert c.get("/api/contact-central", params={"q": "zzz-nao-existe"}).json()["total"] == 0

        # contadores batem com as listas
        cont = c.get("/api/contact-central/counts").json()
        for f in ("todos", "whatsapp", "wa_empresa", "sem_contatos", "com_permissao", "bloqueados", "leads_aprovados"):
            assert cont[f] == c.get("/api/contact-central", params={"filtro": f}).json()["total"], f
        assert cont["com_permissao"] == 0  # número público não é consentimento

        # ordenação e paginação
        asc = [x["titular"] for x in c.get("/api/contact-central", params={"ordenar": "titular"}).json()["items"]]
        desc = [
            x["titular"] for x in c.get("/api/contact-central", params={"ordenar": "titular", "direcao": "desc"}).json()["items"]
        ]
        assert asc == sorted(asc) and desc == asc[::-1]
        p1 = c.get("/api/contact-central", params={"limit": 1}).json()
        p2 = c.get("/api/contact-central", params={"limit": 1, "offset": 1}).json()
        assert p1["total"] == todos["total"] and p1["items"][0]["holder_id"] != p2["items"][0]["holder_id"]
        assert c.get("/api/contact-central", params={"ordenar": "titular; drop table x"}).status_code == 422


def test_filtros_de_permissao_bloqueio_e_invalidos(conn, sites):  # noqa: F811
    _pipeline()
    wa = conn.execute("select * from contacts where wa_nivel = 'company_evidence'").fetchone()
    conn.execute(
        """insert into consents (contact_id, canal, finalidade, empresa_identificada, obtido_em, metodo,
                                 fonte_evidencia, texto_autorizacao, versao_aviso)
           values (%s, 'whatsapp', 'contato comercial sobre registro de marca', 'Prestador teste', now(), 'email',
                   'mensagem-teste-1', 'Pode me chamar no WhatsApp', 'v1')""",
        (wa["id"],),
    )
    with TestClient(app) as c:
        perm = c.get("/api/contact-central", params={"filtro": "com_permissao"}).json()
        assert [x["holder_id"] for x in perm["items"]] == [wa["holder_id"]]
        c.post("/api/optout", json={"tipo": "telefone", "valor": wa["valor_normalizado"], "motivo": "pediu para sair"})
        # o opt-out prevalece sobre o consentimento
        assert c.get("/api/contact-central", params={"filtro": "com_permissao"}).json()["total"] == 0
        bloq = c.get("/api/contact-central", params={"filtro": "bloqueados"}).json()
        assert wa["holder_id"] in [x["holder_id"] for x in bloq["items"]]
        inval = c.get("/api/contact-central", params={"filtro": "invalidos"}).json()
        assert wa["holder_id"] in [x["holder_id"] for x in inval["items"]]
    # consentimento não se apaga: revoga-se
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("delete from consents")
    conn.execute("update consents set status = 'revogado', revogado_em = now(), revogacao_origem = 'teste'")
    assert (
        conn.execute("select n_com_permissao from v_contact_central where holder_id = %s", (wa["holder_id"],)).fetchone()[
            "n_com_permissao"
        ]
        == 0
    )


def test_contatos_nao_duplicam(conn, mundo):  # noqa: F811
    importar_rpi()
    h = _holder(conn)
    _contato(conn, h, "email", "contato@empresa-real.com.br", "contato@empresa-real.com.br")
    with pytest.raises(psycopg.errors.UniqueViolation):
        _contato(conn, h, "email", "Contato@Empresa-Real.com.br", "contato@empresa-real.com.br")


def test_exportacao_csv_e_excel(conn, sites):  # noqa: F811
    _pipeline()
    with TestClient(app) as c:
        x = c.get("/api/contact-central/export", params={"formato": "xlsx", "filtro": "wa_empresa"})
        assert x.status_code == 200
        ws = load_workbook(io.BytesIO(x.content))["Contatos"]
        linha = dict(zip([h.value for h in ws[1]], [v.value for v in ws[2]], strict=False))
        assert linha["whatsapp"] and linha["whatsapp_nivel"] == "evidência empresarial"
        assert linha["whatsapp_autorizado"] == "não" and linha["whatsapp_origem"].startswith("http")
        assert ws.max_row == 2
        y = c.get("/api/contact-central/export", params={"formato": "csv"})
        linhas = list(csv.DictReader(io.StringIO(y.content.decode("utf-8-sig")), delimiter=";"))
        assert len(linhas) == c.get("/api/contact-central").json()["total"]
    log = conn.execute("select * from exports_log order by id desc limit 1").fetchone()
    assert log["filtros"]["origem"] == "central_contatos"
