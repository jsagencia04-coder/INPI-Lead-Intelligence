"""WhatsApp: níveis de validação (validado pela empresa, confirmado por pessoa, candidato)."""

import io

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.agents.site_crawler import extract_contacts
from app.main import app
from app.whatsapp import evidencia_indica_whatsapp, is_br_mobile
from tests.test_fases3a7 import drain, enqueue, importar_rpi, mundo  # noqa: F401
from tests.test_site_crawler import sites  # noqa: F401


def test_regras_basicas():
    assert is_br_mobile("+5511988887777") and not is_br_mobile("+551133334444")
    assert evidencia_indica_whatsapp("link https://wa.me/5511988887777")
    assert evidencia_indica_whatsapp("Fale pelo WhatsApp: (11) 98888-7777")
    assert not evidencia_indica_whatsapp("Telefone: (11) 98888-7777")


def test_numero_no_texto_perto_de_whatsapp_vira_whatsapp():
    html = "<p>Atendimento WhatsApp: (11) 98888-7777</p><p>Fixo: (11) 3333-4444</p>"
    tipos = {(a["tipo"], a["normalizado"]) for a in extract_contacts("https://x.com.br/", html)}
    assert ("whatsapp", "+5511988887777") in tipos and ("telefone", "+551133334444") in tipos


def _pipeline():
    importar_rpi()
    for t in ("inpi.verify_pending", "cnpj.sync", "leads.build", "research.free_batch"):
        enqueue(t)
        drain()


def test_whatsapp_publicado_pela_empresa_fica_validado(conn, sites):  # noqa: F811
    _pipeline()
    lead = conn.execute("""select l.* from leads l join holders h on h.id = l.holder_id
                           where h.nome_original like 'INDÚSTRIA%%GAMA%%'""").fetchone()
    assert (lead["whatsapp"], lead["whatsapp_status"]) == ("+5511988887777", "validado")
    assert lead["score_detalhes"]["whatsapp"] == 25
    with TestClient(app) as c:
        lista = c.get("/api/leads", params={"whatsapp": "validado"}).json()
        assert [x["id"] for x in lista["items"]] == [lead["id"]]
        x = c.get("/api/leads-export", params={"formato": "xlsx", "whatsapp": "validado"})
        ws = load_workbook(io.BytesIO(x.content))["Leads"]
        cab = [h.value for h in ws[1]]
        linha = dict(zip(cab, [v.value for v in ws[2]], strict=False))
        assert linha["whatsapp"] == "+5511988887777" and linha["whatsapp_status"] == "validado"
        assert c.get("/api/office/state").json()["kpis"]["leads_whatsapp"] == 1
        assert c.get("/api/dashboard/summary").json()["leads_whatsapp_validado"] == 1


def test_celular_vira_candidato_e_so_pessoa_confirma(conn, mundo):  # noqa: F811
    importar_rpi()
    enqueue("inpi.verify_pending")
    drain()
    h = conn.execute("select id from holders where nome_original = 'CICRANA DE SOUZA EXEMPLO'").fetchone()["id"]
    ev = conn.execute(
        "insert into evidences (url, trecho, fonte_tipo) values ('https://exemplo.com.br/', "
        "'Telefone (61) 99999-8888', 'web') returning id"
    ).fetchone()["id"]
    conn.execute(
        "insert into contacts (holder_id, tipo, valor, valor_normalizado, evidence_id, fonte_tipo, verificacao)"
        " values (%s, 'telefone', '(61) 99999-8888', '+5561999998888', %s, 'web', 'formato_ok')",
        (h, ev),
    )
    enqueue("leads.build")
    drain()
    lead = conn.execute("select * from leads where holder_id = %s", (h,)).fetchone()
    assert lead["whatsapp_status"] == "candidato" and lead["score_detalhes"]["whatsapp"] == 8
    wa = conn.execute("select * from contacts where holder_id = %s and tipo = 'whatsapp'", (h,)).fetchone()
    assert wa["observacao"].startswith("Candidato")
    # validação automática não promove candidato (a fonte não diz que é WhatsApp)
    enqueue("lead.validate_contacts", {"holder_id": h})
    drain()
    assert conn.execute("select verificacao from contacts where id = %s", (wa["id"],)).fetchone()["verificacao"] != "dominio_ok"
    with TestClient(app) as c:
        c.post(f"/api/contacts/{wa['id']}/verify", json={"verificacao": "verificado_humano"})
    drain()
    assert (
        conn.execute("select whatsapp_status from leads where holder_id = %s", (h,)).fetchone()["whatsapp_status"] == "confirmado"
    )


# ------------------------------------------------------------------ correções da busca (diagnóstico com dados reais)
def test_celular_da_receita_no_formato_antigo_ganha_o_nono_digito():
    from app.validation import normalize_contact

    assert normalize_contact("telefone", "1187654321") == "+5511987654321"  # como a Receita guarda
    assert normalize_contact("telefone", "(21) 8765-4321") == "+5521987654321"
    assert normalize_contact("telefone", "1133334444") == "+551133334444"  # fixo continua fixo
    assert normalize_contact("telefone", "11987654321") == "+5511987654321"
    assert normalize_contact("telefone", "123") is None


def test_links_e_textos_de_whatsapp_reconhecidos():
    casos = {
        '<a href="https://wa.me/5511988887777?text=Oi">zap</a>': "+5511988887777",
        '<a href="https://wa.me/+5511988887777">zap</a>': "+5511988887777",
        '<a href="https://api.whatsapp.com/send/?phone=5511988887777&text=oi">zap</a>': "+5511988887777",
        '<a href="https://api.whatsapp.com/send?l=pt&amp;phone=%2B5511988887777">zap</a>': "+5511988887777",
        '<a href="whatsapp://send?phone=5511988887777">zap</a>': "+5511988887777",
        '<div data-link="https://web.whatsapp.com/send?phone=5511988887777"></div>': "+5511988887777",
        '<script>window.widget={"url":"https://wa.me/5511988887777"}</script>': "+5511988887777",
        "<p>WhatsApp 11 98888-7777</p>": "+5511988887777",
        "<p>Whats: +55 11 9 8888 7777</p>": "+5511988887777",
        '<a href="https://wa.me/11988887777">zap</a>': "+5511988887777",
    }
    for html, esperado in casos.items():
        achados = {(a["tipo"], a["normalizado"]) for a in extract_contacts("https://x.com.br/", html)}
        assert ("whatsapp", esperado) in achados, html
    # número solto sem a palavra WhatsApp continua sendo só telefone; CNPJ e datas não viram telefone
    achados = extract_contacts("https://x.com.br/", "<p>Ligue 11 98888-7777. CNPJ 11.111.111/0001-91, desde 10/11/2026</p>")
    assert [(a["tipo"], a["normalizado"]) for a in achados] == [("telefone", "+5511988887777")]


def test_recontatos_recupera_celulares_e_vira_candidato(conn, mundo):  # noqa: F811
    importar_rpi()
    for t in ("inpi.verify_pending", "cnpj.sync", "leads.build"):
        enqueue(t)
        drain()
    h = conn.execute("select id, cnpj from holders where cnpj is not null limit 1").fetchone()
    conn.execute("update cnpj_estabelecimentos set telefone2 = '1187654321' where cnpj = %s", (h["cnpj"],))
    antes = conn.execute("select count(*) n from contacts").fetchone()["n"]
    enqueue("cnpj.recontatos")
    drain()
    tel = conn.execute(
        "select * from contacts where holder_id = %s and valor_normalizado = '+5511987654321'", (h["id"],)
    ).fetchall()
    assert {c["tipo"] for c in tel} == {"telefone", "whatsapp"}  # telefone da Receita + WhatsApp CANDIDATO
    wa = next(c for c in tel if c["tipo"] == "whatsapp")
    assert wa["wa_nivel"] == "candidate" and wa["wa_comercial"] == "desconhecido"  # nunca validado sozinho
    lead = conn.execute("select whatsapp, whatsapp_status from leads where holder_id = %s", (h["id"],)).fetchone()
    assert lead["whatsapp_status"] in ("candidato", "validado")
    # rodar de novo não duplica
    enqueue("cnpj.recontatos")
    drain()
    assert conn.execute("select count(*) n from contacts").fetchone()["n"] == antes + 2
