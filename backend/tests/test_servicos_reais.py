"""V2.4 · Testes com PROCESSOS REAIS do INPI (RPI 2904, 2905, 2909 e 2914; petições consultadas no pePI em 12/11/2026).

Casos exigidos no escopo (seção 11) e o processo real usado em cada um:
  1  Marca que sofreu oposição ............................ 944040470 (TELEVAULT · CEI Controles, SC · RPI 2914)
  2  Marca que apresentou oposição contra outra ........... ASSA ABLOY / EPIROC (opositores) e 945199783 (IPAS009)
  3  Marca que já recebeu manifestação .................... 943447259 (HEALTH ESSENCE · PF, SC · RPI 2904)
  4  Oposição com prazo encerrado ......................... 942100506 (Instituto Ela por Elas, DF · RPI 2904)
  5  Indeferida sem recurso ............................... 938028383 (ESCOLA DAS CIDADES · TDBUSINESS, SC · RPI 2914)
  6  Indeferida com recurso protocolado ................... 930932480 (EKOA LIFE SCIENCES · IMP Bioinsumos, DF · RPI 2904 → 2914)
  7  Parcialmente deferida/indeferida ..................... 939053594 (XUCRO CORAÇÃO, SC · IPAS029 com itens excluídos) e 501881667 (IPAS781)
  8  Processo com dados incompletos ....................... 944032028 (IPAS423 sem marca/classe na RPI; sem contato)
  9  Titular pessoa física ................................ 943447259, 930647033
  10 Titular pessoa jurídica .............................. 944040470, 938028383
  11 Lead duplicado em edições diferentes ................. NANOVETORES (938471708 na RPI 2905 e 943766842 na RPI 2909)
"""

import os
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from app import servicos
from app.agents import inpi as inpi_agent
from app.config import get_settings
from app.inpi import pepi
from app.main import app
from tests import pepi_fixtures as F
from tests.pepi_real import PEPI, detalhe_real
from tests.rpi_helpers import make_zip
from tests.test_fases3a7 import drain, enqueue

REAL = Path(__file__).parent / "fixtures" / "rpi_real"
HOJE = date(2026, 11, 12)


class FakePepiReal:
    def __init__(self):
        self.consultados: list[str] = []

    def handler(self, req: httpx.Request) -> httpx.Response:
        u = str(req.url)
        if "LoginController" in u:
            return httpx.Response(200, content=F.LOGIN.encode("latin-1"))
        if req.method == "POST":
            num = parse_qs(req.content.decode())["NumPedido"][0]
            if num not in PEPI:
                return httpx.Response(200, content=F.nao_encontrado(num).encode("latin-1"))
            return httpx.Response(200, content=F.resultado(num, num, PEPI[num][0]).encode("latin-1"))
        num = u.rsplit("CodPedido=", 1)[1]
        self.consultados.append(num)
        return httpx.Response(
            200, headers={"content-type": "text/html;charset=ISO-8859-1"}, content=detalhe_real(num).encode("latin-1")
        )


def upload(numero: int):
    xml = (REAL / f"RM{numero}.xml").read_text(encoding="utf-8")
    with TestClient(app) as c:
        r = c.post("/api/rpi/upload", files={"file": (f"RM{numero}.zip", make_zip(xml, f"RM{numero}.xml"), "application/zip")})
        assert r.status_code == 201, r.text


@pytest.fixture
def real(monkeypatch, conn):
    fp = FakePepiReal()
    monkeypatch.setattr(pepi, "transport", httpx.MockTransport(fp.handler))
    monkeypatch.setattr(servicos, "hoje", lambda: HOJE)
    os.environ["RPI_OPERACAO_SEMANAL_AUTO"] = "false"
    get_settings.cache_clear()
    inpi_agent.reset_client()
    # como em produção após a migration 0015: "publicado para oposição" não gera lead novo
    conn.execute("update despacho_types set ativo_para_leads = false where codigo = 'IPAS009'")
    yield fp
    inpi_agent.reset_client()
    os.environ.pop("RPI_OPERACAO_SEMANAL_AUTO", None)
    get_settings.cache_clear()


def importar_tudo(conn, ordem=(2914, 2904, 2905, 2909)):
    """A mais recente primeiro e as antigas depois, como acontece na busca do histórico em produção."""
    for n in ordem:
        upload(n)
        drain(400)
    enqueue("inpi.verify_pending")
    drain(400)


def op(conn, numero, servico=None):
    return conn.execute(
        "select * from oportunidades_servico where numero_processo = %s and (%s::text is null or servico = %s) order by rpi_numero desc",
        (numero, servico, servico),
    ).fetchone()


def lead_do(conn, numero):
    return conn.execute(
        """select l.*, h.nome_original, h.tipo_provavel from leads l join holders h on h.id = l.holder_id
            join process_holders ph on ph.holder_id = h.id where ph.numero_processo = %s""",
        (numero,),
    ).fetchone()


def validar_contato(conn, numero, fone):
    h = conn.execute("select holder_id from process_holders where numero_processo = %s", (numero,)).fetchone()["holder_id"]
    ev = conn.execute(
        "insert into evidences (url, trecho, fonte_tipo) values ('https://exemplo-oficial.com.br/contato', %s, 'web') returning id",
        (f"WhatsApp {fone}",),
    ).fetchone()["id"]
    conn.execute(
        """insert into contacts (holder_id, tipo, valor, valor_normalizado, evidence_id, fonte_tipo, verificacao, confianca)
           values (%s, 'whatsapp', %s, %s, %s, 'web', 'dominio_ok', 0.8)""",
        (h, fone, "+55" + "".join(ch for ch in fone if ch.isdigit()), ev),
    )


# ------------------------------------------------------------------ prazos (regra do INPI + calendário)
def test_prazo_60_dias_com_dias_uteis_e_feriados(conn):
    fer = servicos.feriados(conn)
    # RPI 2914 (ter 10/11/2026): início qua 11/11; 60º dia = sáb 09/01/2027 → seg 11/01/2027
    p = servicos.calcular_prazo(date(2026, 11, 10), fer, HOJE)
    assert (p["inicio"], p["fim"], p["status"]) == (date(2026, 11, 11), date(2027, 1, 11), "em_andamento")
    # RPI 2904 (ter 01/09/2026): 60º dia = sáb 31/10 → dom 01/11 → seg 02/11 (Finados) → ter 03/11/2026
    p = servicos.calcular_prazo(date(2026, 9, 1), fer, HOJE)
    assert (p["fim"], p["status"]) == (date(2026, 11, 3), "encerrado")
    # RPI 2909 (ter 06/10/2026): 60º dia = sáb 05/12 → seg 07/12/2026; faltam 25 dias
    p = servicos.calcular_prazo(date(2026, 10, 6), fer, HOJE)
    assert (p["fim"], p["status"], p["restantes"]) == (date(2026, 12, 7), "em_andamento", 25)
    assert servicos.calcular_prazo(date(2026, 10, 6), fer, date(2026, 11, 25))["status"] == "proximo_fim"
    assert servicos.calcular_prazo(None, fer, HOJE)["status"] == "validar"  # sem data: não presume prazo aberto
    assert servicos.oposicao_do_texto("850260447873 de 31/08/2026") == ("850260447873", date(2026, 8, 31))


def test_peticoes_do_pepi_com_a_marcacao_real():
    r = pepi.parse_detail(detalhe_real("943447259"), "943447259", "https://busca.inpi.gov.br/x")
    assert [(p["servico"], p["descricao"], p["cliente"]) for p in r.peticoes][:2] == [
        ("339", "Manifestação", "JOAO TESTE PEREIRA"),
        ("332", "Oposição - valor por classe", "INP INDUSTRIA DE ALIMENTOS LTDA"),
    ]
    assert r.peticoes[0]["protocolo"] == "850260494593" and r.peticoes[0]["data"] == date(2026, 9, 23)


# ------------------------------------------------------------------ casos 1 a 11 com os processos reais
def test_processos_reais_classificados_corretamente(conn, real):
    importar_tudo(conn)
    # contatos comerciais verificáveis (caso real: o sistema não inventa; aqui simulamos a validação humana)
    validar_contato(conn, "944040470", "(47) 99999-0001")
    validar_contato(conn, "938028383", "(48) 99999-0002")
    validar_contato(conn, "939053594", "(49) 99999-0003")
    enqueue("leads.build")
    drain()

    # 1. Sofreu oposição: o lead é o TITULAR (CEI), não quem se opôs (ASSA ABLOY)
    o = op(conn, "944040470")
    assert (o["servico"], o["tipo_decisao"], o["rpi_numero"], o["data_publicacao"]) == (
        "manifestacao_oposicao", "oposicao", 2914, date(2026, 11, 10))  # fmt: skip
    assert (o["oposicao_protocolo"], o["oposicao_data"]) == ("850260447873", date(2026, 8, 31))
    assert o["opositor_nome"] == "ASSA ABLOY BRASIL INDÚSTRIA E COMÉRCIO LTDA" and "pePI" in o["opositor_fonte"]
    assert (o["prazo_fim"], o["prazo_status"], o["medida_status"]) == (date(2027, 1, 11), "em_andamento", "nao_identificada")
    assert "LPI art. 158" in o["prazo_fonte"] and o["classificacao"] == "quente"
    lead = lead_do(conn, "944040470")
    assert lead["nome_original"] == "CEI - CONTROLES ELETRÔNICOS INTELIGENTES LTDA" and lead["tipo_provavel"] == "PJ"  # caso 10
    assert (lead["classificacao_oposicao"], lead["servico_principal"], lead["temperatura"]) == (
        "quente", "manifestacao_oposicao", "quente")  # fmt: skip
    assert lead["prazo_ate"] == date(2027, 1, 11) and lead["categoria_principal"] == "oposicao_apresentada"
    assert conn.execute("select marca_nome from processes where numero_processo = '944040470'").fetchone()["marca_nome"] == "TELEVAULT"

    # 2. Quem APRESENTOU a oposição nunca vira titular nem lead; "publicado para oposição" não é oposição
    for opositor in ("ASSA ABLOY%", "EPIROC%", "INP INDUSTRIA%", "GLOBO COMUNICA%"):
        assert conn.execute("select count(*) n from holders where nome_original ilike %s", (opositor,)).fetchone()["n"] == 0
    assert op(conn, "945199783") is None
    assert conn.execute("select count(*) n from opportunities where numero_processo = '945199783'").fetchone()["n"] == 0

    # 3. Já recebeu manifestação (pePI 339 em 23/09/2026) → histórico, nunca quente; titular PF (caso 9)
    o = op(conn, "943447259")
    assert (o["medida_status"], o["medida_protocolo"], o["medida_data"]) == ("protocolada", "850260494593", date(2026, 9, 23))
    assert (o["situacao_processual"], o["classificacao"]) == ("historico", "historico")
    assert o["opositor_nome"] == "INP INDUSTRIA DE ALIMENTOS LTDA"
    # pessoa física: o sistema não presume PF pela ausência de "LTDA" (regra existente); fica "indefinido" até o CNPJ
    assert lead_do(conn, "943447259")["tipo_provavel"] == "indefinido"

    # 4. Oposição com prazo encerrado em 03/11/2026, sem manifestação → histórico
    o = op(conn, "942100506")
    assert (o["prazo_fim"], o["prazo_status"], o["medida_status"], o["classificacao"]) == (
        date(2026, 11, 3), "encerrado", "nao_identificada", "historico")  # fmt: skip
    assert o["opositor_nome"] == "GLOBO COMUNICAÇÃO E PARTICIPAÇÕES S.A."  # protocolo 850260077262 do IPAS423

    # 5. Indeferida sem recurso, prazo aberto, contato validado → quente (pipeline 2)
    o = op(conn, "938028383")
    assert (o["servico"], o["prazo_fim"], o["medida_status"], o["classificacao"]) == (
        "recurso_indeferimento", date(2027, 1, 11), "nao_identificada", "quente")  # fmt: skip
    assert "inciso VI do Art 124" in o["fundamentacao"] and "LPI art. 212" in o["prazo_fonte"]
    assert lead_do(conn, "938028383")["classificacao_recurso"] == "quente"

    # 6. Indeferida (RPI 2904) com recurso protocolado (IPAS360 na RPI 2914, protocolo 850260549596) → não é oportunidade nova
    o = op(conn, "930932480")
    assert o["rpi_numero"] == 2904 and o["medida_status"] == "protocolada" and o["medida_protocolo"] == "850260549596"
    assert "RPI 2914" in o["medida_fonte"] and o["classificacao"] == "historico"
    assert lead_do(conn, "930932480")["classificacao_recurso"] == "historico"

    # 7. Deferimento parcial (itens excluídos) → pipeline 2 separado, exige validação jurídica, nunca quente
    o = op(conn, "939053594")
    assert (o["servico"], o["tipo_decisao"], o["validacao_juridica"], o["classificacao"]) == (
        "recurso_indeferimento", "deferimento_parcial", True, "morno")  # fmt: skip
    m = op(conn, "501881667")  # IPAS781 (Madri): registrado, mas titular estrangeiro com procurador → não elegível
    assert m["tipo_decisao"] == "deferimento_parcial" and not m["elegivel"]

    # 8. Dados incompletos: a RPI não traz marca nem classe no IPAS423 e não há contato → PENDENTE (sem inventar)
    o = op(conn, "944032028")
    assert o["classificacao"] == "pendente" and any("Nenhum contato" in x for x in o["classificacao_motivos"])
    assert conn.execute("select count(*) n from contacts c join process_holders ph on ph.holder_id = c.holder_id "
                        "where ph.numero_processo = '944032028'").fetchone()["n"] == 0  # fmt: skip

    # 9. PF indeferida (Maria Teste) sem contato → pendente; nada é inventado
    assert lead_do(conn, "930647033")["tipo_provavel"] == "indefinido" and op(conn, "930647033")["classificacao"] == "pendente"

    # 11. Mesmo titular em edições diferentes (NANOVETORES, 2905 e 2909) → 1 lead, 2 oportunidades em pipelines separados
    a, b = lead_do(conn, "938471708"), lead_do(conn, "943766842")
    assert a["id"] == b["id"]
    assert conn.execute("select count(*) n from leads l join holders h on h.id = l.holder_id "
                        "where h.nome_original = 'NANOVETORES TECNOLOGIA S.A.'").fetchone()["n"] == 1  # fmt: skip
    assert (op(conn, "938471708")["prazo_fim"], op(conn, "938471708")["classificacao"]) == (date(2026, 11, 9), "historico")
    assert (op(conn, "943766842")["prazo_fim"], op(conn, "943766842")["situacao_processual"]) == (date(2026, 12, 7), "aberta")
    assert (a["classificacao_recurso"], a["classificacao_oposicao"]) == ("historico", "pendente")
    # Tprojetto: 2 processos com oposição na mesma RPI → 1 lead só
    assert lead_do(conn, "944032028")["id"] == lead_do(conn, "944032087")["id"]


def test_reimportar_nao_duplica_e_preserva_historico(conn, real):
    importar_tudo(conn)
    antes = conn.execute("select count(*) n, count(distinct (numero_processo, servico)) d from oportunidades_servico").fetchone()
    leads = conn.execute("select count(*) n from leads").fetchone()["n"]
    pets = conn.execute("select count(*) n from process_peticoes").fetchone()["n"]
    importar_tudo(conn, ordem=(2914, 2904))
    depois = conn.execute("select count(*) n, count(distinct (numero_processo, servico)) d from oportunidades_servico").fetchone()
    assert (depois["n"], depois["d"]) == (antes["n"], antes["d"])
    assert conn.execute("select count(*) n from leads").fetchone()["n"] == leads
    assert conn.execute("select count(*) n from process_peticoes").fetchone()["n"] == pets
    # edição antiga importada depois não troca o titular atual
    assert lead_do(conn, "930932480")["nome_original"] == "IMP BIOINSUMOS LTDA."


def test_paineis_separados_por_servico(conn, real):
    importar_tudo(conn)
    validar_contato(conn, "944040470", "(47) 99999-0001")
    validar_contato(conn, "938028383", "(48) 99999-0002")
    enqueue("leads.build")
    drain()
    with TestClient(app) as c:
        p = c.get("/api/servicos/painel").json()
        mo, rec = p["manifestacao_oposicao"], p["recurso_indeferimento"]
        # oposições sofridas por titulares brasileiros sem procurador: CEI, Tprojetto x2, NANOVETORES, João (PF), Instituto
        assert mo["identificadas"] == 6 and mo["titulares"] == 5 and mo["abertas"] == 4 and mo["protocoladas"] == 1
        assert mo["quentes"] == 1 and mo["contatos_encontrados"] == 1
        # indeferimentos: TDBUSINESS, Maria (PF), NANOVETORES (encerrado), IMP (recurso) + parcial MV EVENTOS
        assert rec["identificadas"] == 5 and rec["protocoladas"] == 1 and rec["quentes"] == 1 and rec["parciais"] == 1
        assert p["consolidado"]["quentes"] == 2
        assert [x["numero_processo"] for x in p["melhores"]][:2] == ["944040470", "938028383"]  # SC primeiro, quentes
        sc = c.get("/api/mapa/SC").json()["servicos"]
        assert (sc["oposicoes_sofridas"], sc["manifestacoes_cabiveis"], sc["manifestacoes_protocoladas"]) == (5, 4, 1)
        assert (sc["indeferimentos"], sc["recursos_cabiveis"], sc["recursos_protocolados"]) == (4, 3, 0)
        lst = c.get("/api/servicos", params={"servico": "recurso_indeferimento", "uf": "SC"}).json()
        assert {x["numero_processo"] for x in lst["items"]} == {"938028383", "930647033", "939053594", "938471708"}
        quentes = c.get("/api/servicos", params={"classificacao": "quente"}).json()["items"]
        assert {x["numero_processo"] for x in quentes} == {"944040470", "938028383"}
        csv = c.get("/api/servicos/export", params={"formato": "csv", "servico": "manifestacao_oposicao"}).content.decode("utf-8-sig")
        assert "ASSA ABLOY" in csv and "Manifestação à oposição" in csv and "11/01/2027" in csv
        rel = c.get("/api/servicos/resumo-executivo").json()
        assert rel["destaques"][0]["uf"] == "SC" and "manifestação" in rel["texto"].lower()
