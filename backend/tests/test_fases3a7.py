"""Fases 3 a 7: teste ponta a ponta com INPI, Receita, Claude e sites simulados."""

import io
import json
import zipfile
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app import db, llm, validation
from app.agents import inpi as inpi_agent
from app.cnpj import receita
from app.config import get_settings
from app.inpi import pepi
from app.inpi.pepi import parse_detail
from app.jobs import queue
from app.jobs.registry import load_agents
from app.main import app
from app.worker import run_one
from tests import pepi_fixtures as F
from tests.rpi_helpers import make_zip, xml_text

load_agents()


def drain(n=200):
    for _ in range(n):
        if not run_one("w-test"):
            return


def enqueue(tipo, payload=None):
    with db.transaction("test") as c:
        queue.enqueue(c, tipo, payload or {})


# ------------------------------------------------------------------ simuladores
class FakePepi:
    def __init__(self):
        # processo -> (marca, titular, procurador)
        self.base = {
            "945424620": ("MARCA ALFA", "FULANO DE TAL EXEMPLO", None),
            "937208078": ("MARCA HIGIENE", "FULANO DE TAL EXEMPLO", "ESCRITÓRIO FICTÍCIO DE MARCAS"),
            "828886318": ("GAMA", "INDÚSTRIA E COMÉRCIO DE ALIMENTOS GAMA LTDA -ME", None),
            "939557835": ("DELTA", "COMERCIAL DELTA E FILHOS", None),
            "942334000": ("RESTAURADAS", "CICRANA DE SOUZA EXEMPLO", None),
            "935837620": ("BELTETA", "BELTRANO LIRA EXEMPLO", None),
        }
        self.bloqueados: set[str] = set()
        self.calls = 0

    def handler(self, req: httpx.Request) -> httpx.Response:
        self.calls += 1
        u = str(req.url)
        if "LoginController" in u:
            return httpx.Response(200, content=F.LOGIN.encode("latin-1"))
        if req.method == "POST":
            num = parse_qs(req.content.decode())["NumPedido"][0]
            if num in self.bloqueados:
                return httpx.Response(200, content=F.BLOQUEIO.encode())
            if num not in self.base:
                return httpx.Response(200, content=F.nao_encontrado(num).encode("latin-1"))
            return httpx.Response(200, content=F.resultado(num, num, self.base[num][0]).encode("latin-1"))
        num = u.rsplit("CodPedido=", 1)[1]
        marca, tit, proc = self.base[num]
        return httpx.Response(
            200,
            headers={"content-type": "text/html;charset=ISO-8859-1"},
            content=F.detalhe(num, marca, tit, proc).encode("latin-1"),
        )


def _csv(rows):
    return "\n".join(";".join(f'"{c}"' for c in r) for r in rows).encode("latin-1")


def _zip(name, data):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr(name, data)
    return b.getvalue()


def _estab(basico, uf, fantasia, tel, email, situacao="02"):
    r = [
        basico,
        "0001",
        "91",
        "1",
        fantasia,
        situacao,
        "20200101",
        "00",
        "",
        "",
        "20100101",
        "1091101",
        "",
        "RUA",
        "DAS FLORES",
        "10",
        "",
        "CENTRO",
        "01001000",
        uf,
        "7107",
        tel[:2],
        tel[2:],
        "",
        "",
        "",
        "",
        email,
        "",
        "",
    ]
    return r


class FakeReceita:
    def __init__(self):
        empresas = _csv(
            [
                ["11111111", "INDUSTRIA E COMERCIO DE ALIMENTOS GAMA LTDA - ME", "2062", "49", "10000,00", "01", ""],
                ["22222222", "COMERCIAL DELTA E FILHOS", "2135", "50", "0,00", "01", ""],
                ["33333333", "COMERCIAL DELTA E FILHOS", "2135", "50", "0,00", "01", ""],
                ["44444444", "OUTRA EMPRESA QUALQUER LTDA", "2062", "49", "1,00", "05", ""],
            ]
        )
        estab = _csv(
            [
                _estab("11111111", "SP", "GAMA ALIMENTOS", "1133334444", "contador@gmail.com"),
                _estab("22222222", "MG", "DELTA 1", "3132221111", ""),
                _estab("33333333", "MG", "DELTA 2", "3132222222", ""),
                _estab("44444444", "RJ", "OUTRA", "2122223333", ""),
            ]
        )
        self.files = {
            "Empresas0.zip": _zip("K3241.EMPRECSV", empresas),
            "Estabelecimentos0.zip": _zip("K3241.ESTABELE", estab),
            "Municipios.zip": _zip("F.K03200$Z.D41011.MUNICCSV", _csv([["7107", "SAO PAULO"], ["8105", "FLORIANOPOLIS"]])),
        }
        self.gets = 0

    def _ms(self, base, items):
        resp = "".join(
            f"<d:response><d:href>{base}{n}</d:href><d:propstat><d:prop>"
            f"<d:getcontentlength>{sz}</d:getcontentlength></d:prop></d:propstat></d:response>"
            for n, sz in items
        )
        return f'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">{resp}</d:multistatus>'

    def handler(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if req.method == "PROPFIND":
            if path.rstrip("/").endswith("webdav"):
                return httpx.Response(207, text=self._ms("/public.php/webdav/", [("", 0), ("2026-09/", 0), ("2026-10/", 0)]))
            return httpx.Response(207, text=self._ms(path, [(n, len(b)) for n, b in self.files.items()]))
        self.gets += 1
        return httpx.Response(200, content=self.files[path.rsplit("/", 1)[1]])


class FakeClaude:
    def __init__(self):
        self.calls = []

    def handler(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        self.calls.append(body)
        s = get_settings()
        if body["model"] == s.modelo_resumo:
            return httpx.Response(
                200,
                json={
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "t1",
                            "name": "registrar_texto",
                            "input": {"resumo": "Resumo gerado.", "abordagem": "Abordagem gerada (prazo estimado)."},
                        }
                    ],
                    "stop_reason": "tool_use",
                    "usage": {"input_tokens": 400, "output_tokens": 120},
                },
            )
        prompt = body["messages"][0]["content"]
        contatos = []
        if "GAMA" in prompt:
            contatos = [
                {
                    "tipo": "site",
                    "valor": "gama.com.br",
                    "url_fonte": "https://gama.com.br/",
                    "trecho": "Gama Alimentos - gama.com.br",
                    "vinculo": "nome e CNPJ no rodapé",
                    "confianca": 0.9,
                },
                {
                    "tipo": "email",
                    "valor": "contato@gama.com.br",
                    "url_fonte": "https://gama.com.br/contato",
                    "trecho": "Fale conosco: contato@gama.com.br",
                    "vinculo": "site oficial",
                    "confianca": 0.9,
                },
                {
                    "tipo": "telefone",
                    "valor": "(11) 99999-1234",
                    "url_fonte": "https://gama.com.br/contato",
                    "trecho": "WhatsApp (11) 99999-0000",
                    "vinculo": "site oficial",
                    "confianca": 0.8,
                },  # não confere
                {
                    "tipo": "instagram",
                    "valor": "@gamaalimentos",
                    "url_fonte": "https://www.instagram.com/gamaalimentos",
                    "trecho": "gamaalimentos • Gama Alimentos",
                    "vinculo": "bio cita a marca",
                    "confianca": 0.7,
                },
            ]
        content = [
            {"type": "server_tool_use", "id": "s1", "name": "web_search", "input": {"query": "titular contato"}},
            {"type": "web_search_tool_result", "tool_use_id": "s1", "content": []},
            {
                "type": "tool_use",
                "id": "t2",
                "name": "registrar_resultado",
                "input": {
                    "titular_identificado": bool(contatos),
                    "contatos": contatos,
                    "homonimos_encontrados": "DELTA" in prompt,
                    "observacoes": "teste",
                },
            },
        ]
        return httpx.Response(
            200,
            json={
                "content": content,
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 6000, "output_tokens": 900, "server_tool_use": {"web_search_requests": 2}},
            },
        )


PAGES = {
    "https://gama.com.br/": "Gama Alimentos gama.com.br CNPJ 11.111.111/0001-91",
    "https://gama.com.br/contato": "Fale conosco: contato@gama.com.br tel (11) 3333-4444",
    "https://www.instagram.com/gamaalimentos": "gamaalimentos Gama Alimentos",
}


@pytest.fixture
def mundo(monkeypatch):
    fp, fr, fc = FakePepi(), FakeReceita(), FakeClaude()
    monkeypatch.setattr(pepi, "transport", httpx.MockTransport(fp.handler))
    monkeypatch.setattr(receita, "transport", httpx.MockTransport(fr.handler))
    monkeypatch.setattr(llm, "transport", httpx.MockTransport(fc.handler))
    monkeypatch.setattr(
        validation,
        "http_transport",
        httpx.MockTransport(
            lambda r: httpx.Response(200, text=PAGES[str(r.url)]) if str(r.url) in PAGES else httpx.Response(404)
        ),
    )
    monkeypatch.setattr(validation, "mx_lookup", lambda d: d in ("gama.com.br", "gmail.com"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-teste")
    get_settings.cache_clear()
    inpi_agent.reset_client()
    yield fp, fr, fc
    inpi_agent.reset_client()
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    get_settings.cache_clear()


def importar_rpi(semana: bool = False):
    """Importa a RPI de teste. Por padrão sem a operação semanal automática, para testar cada agente isolado;
    os testes da V2.3 usam semana=True (fluxo real de terça-feira)."""
    import os

    from app.config import get_settings

    os.environ["RPI_OPERACAO_SEMANAL_AUTO"] = "true" if semana else "false"
    get_settings.cache_clear()
    try:
        with TestClient(app) as c:
            r = c.post("/api/rpi/upload", files={"file": ("RM2914.zip", make_zip(xml_text()), "application/zip")})
            assert r.status_code == 201
        drain()
    finally:
        os.environ.pop("RPI_OPERACAO_SEMANAL_AUTO", None)
        get_settings.cache_clear()


def lead_de(conn, nome_like):
    return conn.execute(
        "select l.* from leads l join holders h on h.id = l.holder_id where h.nome_original ilike %s",
        (f"%{nome_like}%",),
    ).fetchone()


# ------------------------------------------------------------------ Fase 3
def test_parser_do_detalhe_pepi():
    r = parse_detail(F.detalhe("945410948", "Beta", "COMÉRCIO BETA LTDA", "PROCURADORA UM"), "945410948", "u")
    assert (r.marca, r.titulares, r.procuradores, r.procurador_status) == (
        "Beta",
        ["COMÉRCIO BETA LTDA"],
        ["PROCURADORA UM"],
        "com_procurador",
    )
    assert str(r.data_deposito) == "2026-10-02" and r.data_concessao is None
    assert r.publicacoes[0]["rpi"] == 2914
    sem = parse_detail(F.detalhe("1", "X", "Y"), "1", "u")
    assert sem.procurador_status == "sem_confirmado"
    incompleto = parse_detail(F.detalhe("1", "X", "Y", com_secao_rep=False), "1", "u")
    assert incompleto.procurador_status == "desconhecido"  # sem a seção não há confirmação
    with pytest.raises(pepi.PepiBlocked):
        parse_detail(F.BLOQUEIO, "1", "u")


def test_fase3_verificacao_inpi(conn, mundo):
    fp, _, _ = mundo
    importar_rpi()
    enqueue("inpi.verify_pending")
    drain()
    st = {r["numero_processo"]: r for r in conn.execute("select * from processes")}
    assert st["945424620"]["procurador_status"] == "sem_confirmado"
    assert st["945424620"]["procurador_fonte"].startswith("inpi:")
    assert st["828886318"]["marca_nome"] == "GAMA"  # marca que faltava na RPI veio do INPI
    assert st["937208078"]["procurador_status"] == "com_procurador"
    assert st["937208078"]["procurador_nome"] == "ESCRITÓRIO FICTÍCIO DE MARCAS"
    op = conn.execute("select status, motivo_descarte from opportunities where numero_processo = '937208078'").fetchone()
    assert (op["status"], op["motivo_descarte"]) == ("descartada", "procurador identificado no INPI")
    v = conn.execute("select * from inpi_verifications where numero_processo = '945424620'").fetchone()
    assert v["resultado"] == "ok" and v["snapshot_sha256"] and v["fonte_url"].endswith("CodPedido=945424620")
    # titular do 935837620 no INPI é só um dos dois da RPI -> revisão humana
    assert (
        conn.execute("select count(*) n from review_tasks where entidade = 'process' and entidade_id = '935837620'").fetchone()[
            "n"
        ]
        == 1
    )
    # rodar de novo não reconsulta (janela de reverificação)
    calls = fp.calls
    enqueue("inpi.verify_pending")
    drain()
    assert fp.calls == calls


def test_fase3_bloqueio_pausa_a_fila(conn, mundo):
    fp, _, _ = mundo
    importar_rpi()
    fp.bloqueados = set(fp.base)
    enqueue("inpi.verify_pending")
    drain()
    jobs = conn.execute(
        "select status, run_after > now() + interval '1 hour' as pausado from jobs where tipo = 'inpi.verify'"
    ).fetchall()
    assert jobs and all(j["status"] == "queued" and j["pausado"] for j in jobs)
    assert conn.execute("select count(*) n from review_tasks where entidade = 'sistema'").fetchone()["n"] == 1
    assert conn.execute("select count(*) n from processes where procurador_status = 'sem_confirmado'").fetchone()["n"] == 0


# ------------------------------------------------------------------ Fases 4, 5 e 6
def test_pipeline_completo(conn, mundo):
    fp, fr, fc = mundo
    importar_rpi()
    enqueue("inpi.verify_pending")
    drain()

    # Fase 4a: CNPJ da Receita
    enqueue("cnpj.sync")
    drain()
    gama = conn.execute("select * from holders where nome_original like 'INDÚSTRIA%GAMA%'").fetchone()
    assert (gama["cnpj"], gama["cnpj_status"]) == ("11111111000191", "encontrado")
    delta = conn.execute("select * from holders where nome_original like 'COMERCIAL DELTA%'").fetchone()
    assert delta["cnpj_status"] == "ambiguo" and delta["cnpj"] is None and len(delta["cnpj_candidatos"]) == 2
    assert conn.execute("select count(*) n from cnpj_empresas").fetchone()["n"] == 3  # 'OUTRA' não é guardada
    rec = conn.execute(
        "select * from contacts where holder_id = %s and fonte_tipo = 'receita' order by tipo", (gama["id"],)
    ).fetchall()
    assert [c["tipo"] for c in rec] == ["email", "telefone"]
    assert rec[1]["valor_normalizado"] == "+551133334444"

    # Fase 5a: leads (antes da pesquisa)
    enqueue("leads.build")
    drain()
    lg = lead_de(conn, "%GAMA%")
    assert lg["procurador_confirmado"] and lg["categoria_principal"] == "extincao_prorrogacao"
    assert lead_de(conn, "FULANO")["categoria_principal"] == "oposicao"  # o indeferimento tinha procurador

    # Fase 4b: pesquisa web (só alta/média com procurador confirmado)
    conn.execute("update leads set prioridade = 'alta' where id = %s", (lg["id"],))
    enqueue("research.batch")
    drain()
    web = {
        c["tipo"]: c for c in conn.execute("select * from contacts where holder_id = %s and fonte_tipo = 'web'", (gama["id"],))
    }
    assert set(web) == {"site", "email", "instagram"}  # telefone fora do trecho foi rejeitado
    run = conn.execute("select * from research_runs where holder_id = %s", (gama["id"],)).fetchone()
    assert run["status"] == "succeeded" and run["buscas_web"] == 2
    assert json.loads(run["erro"])["rejeitados"][0]["motivo"] == "valor não aparece no trecho citado"
    custo = conn.execute(
        "select sum(custo_usd) s from llm_calls where proposito = 'research' and holder_id = %s", (gama["id"],)
    ).fetchone()["s"]
    assert float(custo) == pytest.approx(6000 / 1e6 * 3 + 900 / 1e6 * 15 + 2 * 0.01)

    # Fase 5b: validação (Agente 05)
    niveis = {
        c["tipo"] + "/" + c["fonte_tipo"]: c["verificacao"]
        for c in conn.execute("select * from contacts where holder_id = %s", (gama["id"],))
    }
    assert niveis == {
        "email/web": "dominio_ok",
        "site/web": "dominio_ok",
        "instagram/web": "dominio_ok",
        "email/receita": "formato_ok",  # e-mail cadastral de provedor gratuito não sobe sozinho
        "telefone/receita": "formato_ok",
    }
    lg = lead_de(conn, "%GAMA%")
    assert lg["status"] == "qualificado" and lg["score_detalhes"]["contatos"] == 20

    # Fase 6: resumo (Agente 06), relatório e exportação
    # um lead de prioridade baixa recebe o texto padrão (sem gastar IA)
    conn.execute("update leads set prioridade = 'baixa' where id = (select min(id) from leads where id <> %s)", (lg["id"],))
    enqueue("sales.summarize_batch")
    enqueue("reports.weekly")
    drain()
    lg = lead_de(conn, "%GAMA%")
    assert lg["resumo"] == "Resumo gerado." and lg["resumo_gerado_por"] == get_settings().modelo_resumo
    baixa = conn.execute("select * from leads where prioridade = 'baixa' and resumo is not null limit 1").fetchone()
    assert baixa["resumo_gerado_por"] == "modelo-padrao" and "Confirme os prazos" in baixa["sugestao_abordagem"]

    with TestClient(app) as c:
        rep = c.get("/api/reports").json()
        assert rep[0]["referencia"] == "RPI 2914"
        dados = c.get(f"/api/reports/{rep[0]['id']}").json()["dados"]
        assert dados["top_leads"] and dados["custo_ia_semana_usd"] > 0

        x = c.get("/api/leads-export", params={"formato": "xlsx"})
        ws = load_workbook(io.BytesIO(x.content))["Leads"]
        linhas = [dict(zip([h.value for h in ws[1]], [v.value for v in r], strict=False)) for r in ws.iter_rows(min_row=2)]
        g = next(r for r in linhas if "GAMA" in r["titular"])
        assert "contato@gama.com.br" in g["contatos_validados"] and "https://gama.com.br/contato" in g["fontes"]
        assert "contador@gmail.com" not in g["contatos_validados"]
        csv_txt = c.get("/api/leads-export", params={"formato": "csv"}).content.decode("utf-8-sig")
        assert csv_txt.splitlines()[0].startswith("lead_id;prioridade")
        assert conn.execute("select count(*) n from exports_log").fetchone()["n"] == 2

        # Ações humanas: aprovar, registrar prospecção (sem envio), opt-out
        assert c.post(f"/api/leads/{lg['id']}/outreach", json={"canal": "email"}).status_code == 409
        c.patch(f"/api/leads/{lg['id']}", json={"status": "aprovado", "revisado": True})
        email = next(ct for ct in c.get(f"/api/leads/{lg['id']}").json()["contatos"] if ct["valor"] == "contato@gama.com.br")
        r = c.post(
            f"/api/leads/{lg['id']}/outreach",
            json={"canal": "email", "contact_id": email["id"], "resultado": "enviado manualmente"},
        )
        assert r.status_code == 201 and r.json()["aprovado_por"] == "user:dev@local"
        assert c.get(f"/api/leads/{lg['id']}").json()["status"] == "contatado"

        assert c.post("/api/optout", json={"tipo": "email", "valor": "contato@gama.com.br"}).status_code == 201
        assert c.post(f"/api/leads/{lg['id']}/outreach", json={"canal": "email", "contact_id": email["id"]}).status_code == 409
        fulano = lead_de(conn, "FULANO")
        c.post("/api/optout", json={"tipo": "titular", "lead_id": fulano["id"]})
        drain()
        enqueue("leads.build")
        drain()
        assert lead_de(conn, "FULANO")["status"] == "descartado"
        assert lead_de(conn, "FULANO")["motivo_descarte"] == "opt-out (LGPD)"

        # Homônimos: pessoa escolhe o CNPJ
        r = c.post(f"/api/holders/{delta['id']}/cnpj", json={"cnpj": "22222222000191"})
        assert r.json()["cnpj_status"] == "manual"

        m = c.get("/api/metrics").json()
        assert m["ia_configurada"] is True
        assert any(x["proposito"] == "research" for x in m["custo_ia"])
        assert c.get("/api/dashboard/summary").json()["procurador_ausente_confirmado"] >= 4


def test_orcamento_de_ia_bloqueia_pesquisa(conn, mundo, monkeypatch):
    _, _, fc = mundo
    monkeypatch.setenv("IA_ORCAMENTO_SEMANAL_USD", "0")
    get_settings.cache_clear()
    importar_rpi()
    enqueue("inpi.verify_pending")
    drain()
    h = conn.execute("select id from holders limit 1").fetchone()
    enqueue("research.holder", {"holder_id": h["id"]})
    drain()
    assert fc.calls == []
    assert (
        "orçamento"
        in conn.execute("select lower(resultado->>'ignorado') i from jobs where tipo = 'research.holder'").fetchone()["i"]
    )


def test_sem_chave_de_api_nada_e_gasto(conn, mundo, monkeypatch):
    _, _, fc = mundo
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    get_settings.cache_clear()
    importar_rpi()
    enqueue("research.batch")
    enqueue("sales.summarize_batch")
    drain()
    assert fc.calls == []
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")  # para o teardown


def test_deduplicacao_por_cnpj(conn, mundo):
    importar_rpi()
    enqueue("inpi.verify_pending")
    drain()
    # dois titulares diferentes com o mesmo CNPJ (ex.: nome escrito de duas formas)
    ids = [
        r["id"]
        for r in conn.execute(
            "select id from holders where nome_original in ('BELTRANO LIRA EXEMPLO', 'CICRANA DE SOUZA EXEMPLO') order by id"
        )
    ]
    conn.execute("update holders set cnpj = '99999999000199', cnpj_status = 'manual' where id = any(%s)", (ids,))
    enqueue("leads.build")
    drain()
    leads = conn.execute("select * from leads where holder_id = any(%s) order by holder_id", (ids,)).fetchall()
    assert leads[0]["mesclado_em"] is None and leads[1]["mesclado_em"] == leads[0]["id"]
    assert leads[1]["status"] == "descartado"
    n = conn.execute("select count(*) n from lead_processes where lead_id = %s", (leads[0]["id"],)).fetchone()["n"]
    assert n == 2
