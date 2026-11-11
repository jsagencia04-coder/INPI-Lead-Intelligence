"""Pesquisa gratuita: leitura dos sites oficiais com vínculo obrigatório."""

import httpx
import pytest

from app import validation
from app.agents import site_crawler
from app.agents.site_crawler import candidate_domains, extract_contacts, vinculo
from tests.test_fases3a7 import drain, enqueue, importar_rpi, mundo  # noqa: F401

SITES = {
    "https://gamaalimentos.com.br/": """<html><body><a href="/fale-conosco">Fale conosco</a>
        <a href="https://www.instagram.com/gamaalimentos/">Insta</a> <a href="https://www.instagram.com/p/xyz/">post</a>
        <a href="https://wa.me/11988887777">WhatsApp</a>
        <footer>Gama Alimentos - CNPJ 11.111.111/0001-91 - São Paulo/SP</footer>
        <img src="logo@2x.png"></body></html>""",
    "https://gamaalimentos.com.br/fale-conosco": """<html><body><h1>Contato</h1>
        <a href="mailto:vendas@gamaalimentos.com.br">vendas@gamaalimentos.com.br</a>
        <p>Telefone: (11) 3333-4444</p><a href="tel:+551133334444">ligar</a></body></html>""",
    "https://delta.com.br/": "<html><body>Delta Distribuidora de Combustíveis Ltda - contato@delta.com.br</body></html>",
    "https://belteta.com.br/": "<html><body>BELTRANO LIRA EXEMPLO - beltrano@belteta.com.br</body></html>",
}
ROBOTS = {"https://belteta.com.br/robots.txt": "User-agent: *\nDisallow: /"}


def handler(req: httpx.Request) -> httpx.Response:
    u = str(req.url)
    if u in ROBOTS:
        return httpx.Response(200, text=ROBOTS[u])
    if u.endswith("/robots.txt"):
        return httpx.Response(404)
    if u in SITES:
        return httpx.Response(200, text=SITES[u], headers={"content-type": "text/html; charset=utf-8"})
    if u.startswith("http://") or "gamaalimentos.com/" in u or ".com/" in u:
        raise httpx.ConnectError("sem DNS")
    return httpx.Response(404, headers={"content-type": "text/html"})


@pytest.fixture
def sites(monkeypatch, mundo):  # noqa: F811
    monkeypatch.setattr(site_crawler, "transport", httpx.MockTransport(handler))
    monkeypatch.setattr(validation, "http_transport", httpx.MockTransport(handler))
    monkeypatch.setattr(validation, "mx_lookup", lambda d: d in ("gama.com.br", "gmail.com", "gamaalimentos.com.br"))
    yield mundo


def test_extracao_de_contatos():
    achados = extract_contacts(
        "https://x.com.br/", SITES["https://gamaalimentos.com.br/"] + SITES["https://gamaalimentos.com.br/fale-conosco"]
    )
    tipos = {(a["tipo"], a["normalizado"]) for a in achados}
    assert ("email", "vendas@gamaalimentos.com.br") in tipos
    assert ("whatsapp", "+5511988887777") in tipos
    assert ("telefone", "+551133334444") in tipos
    assert ("instagram", "instagram.com/gamaalimentos") in tipos
    assert not any("logo@2x" in a["valor"] for a in achados)
    assert not any("/p/" in a["valor"] for a in achados)  # post não é perfil


def test_vinculo_e_dominios():
    h = {"nome_original": "INDÚSTRIA E COMÉRCIO DE ALIMENTOS GAMA LTDA -ME", "cnpj": "11111111000191"}
    assert vinculo("CNPJ 11.111.111/0001-91", h, None, [])[0] == "cnpj"
    assert vinculo("Gama Alimentos", h, "GAMA ALIMENTOS", [])[0] == "nome_fantasia"
    assert vinculo("Bem-vindo à Gama", h, None, ["GAMA"])[0] == "marca"
    assert vinculo("outra empresa", h, None, ["GAMA"])[0] is None
    contatos = [
        {"tipo": "email", "valor_normalizado": "contador@gmail.com", "verificacao": "formato_ok", "fonte_tipo": "receita"},
        {"tipo": "email", "valor_normalizado": "fiscal@gama.com.br", "verificacao": "formato_ok", "fonte_tipo": "receita"},
    ]
    doms = dict(candidate_domains(h, contatos, "GAMA ALIMENTOS", ["GA"]))
    assert doms["gama.com.br"] == "receita" and "gmail.com" not in doms
    assert doms["gamaalimentos.com.br"] == "provavel" and "ga.com.br" not in doms


def test_pesquisa_gratuita_ponta_a_ponta(conn, sites):
    importar_rpi()
    enqueue("inpi.verify_pending")
    drain()
    enqueue("cnpj.sync")
    drain()
    enqueue("leads.build")
    drain()
    enqueue("research.free_batch")
    drain()

    gama = conn.execute("select id from holders where nome_original like 'INDÚSTRIA%GAMA%'").fetchone()["id"]
    web = {
        (c["tipo"], c["valor_normalizado"]): c
        for c in conn.execute(
            "select c.*, e.url from contacts c join evidences e on e.id = c.evidence_id"
            " where c.holder_id = %s and c.fonte_tipo = 'web'",
            (gama,),
        )
    }
    assert ("email", "vendas@gamaalimentos.com.br") in web
    assert ("site", "gamaalimentos.com.br") in web
    assert web[("email", "vendas@gamaalimentos.com.br")]["url"] == "https://gamaalimentos.com.br/fale-conosco"
    assert float(web[("email", "vendas@gamaalimentos.com.br")]["confianca"]) == 0.85  # vínculo pelo CNPJ
    # validação automática reencontra o valor na página citada
    v = conn.execute(
        "select verificacao from contacts where holder_id = %s and valor_normalizado = %s", (gama, "vendas@gamaalimentos.com.br")
    ).fetchone()["verificacao"]
    assert v == "dominio_ok"  # reencontrado na página citada + domínio recebe e-mail

    # delta.com.br é de outra empresa (só o nome "Delta" coincide): nada é gravado
    delta = conn.execute("select id from holders where nome_original like 'COMERCIAL DELTA%'").fetchone()["id"]
    assert (
        conn.execute("select count(*) n from contacts where holder_id = %s and fonte_tipo = 'web'", (delta,)).fetchone()["n"] == 0
    )
    run = conn.execute("select erro from research_runs where holder_id = %s and agente = 'research.free'", (delta,)).fetchone()
    assert "delta.com.br" in run["erro"]

    # robots.txt proíbe: nada lido
    bel = conn.execute("select id from holders where nome_original = 'BELTRANO LIRA EXEMPLO'").fetchone()["id"]
    assert conn.execute("select count(*) n from contacts where holder_id = %s", (bel,)).fetchone()["n"] == 0

    # não repete na mesma janela
    enqueue("research.free_batch")
    drain()
    assert conn.execute("select count(*) n from jobs where tipo = 'research.free'").fetchone()["n"] == len(
        conn.execute("select distinct holder_id from research_runs where agente = 'research.free'").fetchall()
    )


def test_dominio_do_email_da_receita_liga_o_site_ao_titular(conn, sites, monkeypatch):
    """Site que não cita razão social nem CNPJ, mas é o domínio do e-mail cadastrado na Receita (e só desse titular)."""
    importar_rpi()
    for t in ("inpi.verify_pending", "leads.build"):
        enqueue(t)
        drain()
    paginas = {
        "https://lojaunica.com.br/": '<html><a href="https://wa.me/5531977776666">Fale no WhatsApp</a> Bem-vindo!</html>',
        "https://contabilidadeabc.com.br/": '<html><a href="https://wa.me/5531955554444">WhatsApp</a></html>',
        "https://compartilhado.com.br/": '<html><a href="https://wa.me/5531933332222">WhatsApp</a></html>',
    }

    def h(req: httpx.Request) -> httpx.Response:
        u = str(req.url)
        return (
            httpx.Response(200, text=paginas[u], headers={"content-type": "text/html"}) if u in paginas else httpx.Response(404)
        )

    monkeypatch.setattr(site_crawler, "transport", httpx.MockTransport(h))
    monkeypatch.setattr(validation, "http_transport", httpx.MockTransport(h))
    monkeypatch.setattr(validation, "mx_lookup", lambda d: True)
    hs = [r["id"] for r in conn.execute("select id from holders order by id limit 4").fetchall()]

    def email(hid, valor):
        ev = conn.execute("insert into evidences (url, fonte_tipo) values ('receita:cnpj', 'receita') returning id").fetchone()[
            "id"
        ]
        conn.execute(
            "insert into contacts (holder_id, tipo, valor, valor_normalizado, evidence_id, fonte_tipo) values (%s, 'email', %s, %s, %s, 'receita')",
            (hid, valor, valor, ev),
        )

    email(hs[0], "contato@lojaunica.com.br")  # domínio próprio e exclusivo
    email(hs[1], "fiscal@contabilidadeabc.com.br")  # contador
    email(hs[2], "a@compartilhado.com.br")  # mesmo domínio em dois titulares = terceiro
    email(hs[3], "b@compartilhado.com.br")
    for hid in hs:
        enqueue("research.free", {"holder_id": hid})
    drain()
    was = {
        r["holder_id"]: r
        for r in conn.execute("select * from contacts where tipo = 'whatsapp' and fonte_tipo = 'web'").fetchall()
    }
    assert set(was) == {hs[0]}  # só o site do próprio titular entrou
    assert was[hs[0]]["valor_normalizado"] == "+5531977776666" and "e-mail" in was[hs[0]]["observacao"].lower()
    assert was[hs[0]]["wa_nivel"] == "company_evidence"  # a empresa publica como WhatsApp, e o número foi reencontrado
    assert site_crawler.dominios_de_terceiros(conn, ["contabilidadeabc.com.br", "compartilhado.com.br", "lojaunica.com.br"]) == {
        "contabilidadeabc.com.br", "compartilhado.com.br"}  # fmt: skip


def test_lote_inclui_nao_confirmados_e_refaz_metodo_antigo(conn, mundo):  # noqa: F811
    importar_rpi()
    enqueue("leads.build")
    drain()
    total = conn.execute("select count(*) n from leads where status <> 'descartado' and mesclado_em is null").fetchone()["n"]
    um = conn.execute("select holder_id from leads limit 1").fetchone()["holder_id"]
    conn.execute(
        "insert into research_runs (holder_id, agente, modelo, status) values (%s, 'research.free', 'sem IA', 'succeeded')", (um,)
    )
    enqueue("research.free_batch")
    from app.worker import run_one

    run_one("w-test")
    n = conn.execute("select count(*) n from jobs where tipo = 'research.free'").fetchone()["n"]
    assert n == total and total > 1  # todos entram, inclusive o já pesquisado com o método antigo
