"""V2.3: monitoramento semanal da RPI, oposições (A × B), localização, prioridade territorial (SC primeiro),
temperatura dos leads, mapa e Central RPI. Critérios de aceitação 1–14 cobertos aqui e nos testes anteriores."""

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app import semana
from app.agents.leads import temperatura
from app.jobs import queue
from app.jobs.scheduler import proxima_janela, proximo_disparo, tick
from app.main import app
from app.worker import run_one
from tests.rpi_helpers import make_zip, xml_text
from tests.test_fases3a7 import drain, enqueue, mundo  # noqa: F401

SP = ZoneInfo("America/Sao_Paulo")


def proc(numero, uf, despacho="IPAS423", nome=None, marca=None, protocolo="03/11/2026", pais="BR"):
    nome = nome or f"TITULAR {uf or 'SEM UF'} {numero} LTDA"
    uf_attr = f' uf="{uf}"' if uf else ""
    prot = (
        f'<protocolo numero="8502{numero[-6:]}" data="{protocolo}" codigoServico="332">'
        f'<requerente nome-razao-social="OPONENTE EXEMPLO S.A." pais="BR" uf="SP"/></protocolo>'
        if despacho == "IPAS423"
        else ""
    )
    nomes = {"IPAS423": "Notificação de oposição", "IPAS009": "Publicação de pedido de registro para oposição"}
    return f"""
  <processo numero="{numero}">
    <despachos><despacho codigo="{despacho}" nome="{nomes[despacho]}">{prot}</despacho></despachos>
    <titulares><titular nome-razao-social="{nome}" pais="{pais}"{uf_attr}/></titulares>
    <marca apresentacao="Nominativa" natureza="Produtos e/ou Serviço"><nome>{marca or "MARCA " + numero}</nome></marca>
  </processo>"""


EXTRA = "".join(
    [
        proc("950000001", "SC"),
        proc("950000002", "SC", nome="CAFE SERRANO LTDA", marca="SERRANO"),
        proc("950000003", "SC", despacho="IPAS009"),  # pedido publicado para oposição (categoria B)
        proc("950000004", "RS"),
        proc("950000005", "PR"),
        proc("950000006", "MG"),
        proc("950000007", None),  # sem UF declarada -> localização pendente
    ]
)


def importar(conn, numero=2915, drenar=True):
    with TestClient(app) as c:
        r = c.post("/api/rpi/upload", files={"file": (f"RM{numero}.zip", make_zip(xml_text(numero, EXTRA), f"RM{numero}.xml"),
                                                        "application/zip")})  # fmt: skip
        assert r.status_code == 201
    if drenar:
        drain(400)


def ate_operacao(conn):
    """Roda a fila só até a SILVANE distribuir o trabalho (para inspecionar a ordem das tarefas)."""
    for _ in range(50):
        if conn.execute("select 1 from jobs where tipo = 'rpi.semana' and status = 'succeeded'").fetchone():
            return
        run_one("w-test")
    raise AssertionError("rpi.semana não executou")


def holder(conn, numero):
    return conn.execute(
        "select h.* from holders h join process_holders ph on ph.holder_id = h.id where ph.numero_processo = %s", (numero,)
    ).fetchone()


# ------------------------------------------------------------------ 4/5. detecção automática e agenda da terça
def test_janela_da_terca_no_fuso_de_brasilia():
    s = {
        "intervalo_minutos": 10,
        "dias_semana": [2, 3],
        "hora_inicio": time(5, 0),
        "hora_fim": time(23, 59),
        "fuso": "America/Sao_Paulo",
    }
    seg = datetime(2026, 11, 16, 12, 0, tzinfo=SP)  # segunda
    ter_cedo = datetime(2026, 11, 17, 3, 0, tzinfo=SP)
    ter = datetime(2026, 11, 17, 10, 0, tzinfo=SP)
    ter_noite = datetime(2026, 11, 17, 23, 55, tzinfo=SP)
    qui = datetime(2026, 11, 19, 9, 0, tzinfo=SP)
    assert proxima_janela(s, seg) == datetime(2026, 11, 17, 5, 0, tzinfo=SP)
    assert proxima_janela(s, ter_cedo) == datetime(2026, 11, 17, 5, 0, tzinfo=SP)
    assert proxima_janela(s, ter) == ter  # dentro da janela: agora
    assert proximo_disparo(s, ter) == datetime(2026, 11, 17, 10, 10, tzinfo=SP)  # a cada 10 min
    assert proximo_disparo(s, ter_noite) == datetime(2026, 11, 18, 5, 0, tzinfo=SP)  # quarta cobre atraso/feriado
    assert proxima_janela(s, qui) == datetime(2026, 11, 24, 5, 0, tzinfo=SP)
    # funciona com horário em UTC (servidor) e devolve o mesmo instante
    assert proxima_janela(s, seg.astimezone(UTC)) == datetime(2026, 11, 17, 5, 0, tzinfo=SP)
    # sem janela: intervalo simples (agenda antiga continua igual)
    assert proximo_disparo({"intervalo_minutos": 180}, seg).hour == 15


def test_agendador_respeita_a_janela_sem_navegador(conn):
    hoje = datetime.now(SP).isoweekday()
    fora = [d for d in range(1, 8) if d != hoje][:2]
    conn.execute(
        """insert into schedules (nome, tipo, intervalo_minutos, dias_semana, hora_inicio, hora_fim, proximo_em)
           values ('rpi-terca-teste', 'rpi.discover', 10, %s, '00:00', '23:59', now() - interval '1 minute'),
                  ('rpi-hoje-teste', 'rpi.discover', 10, %s, '00:00', '23:59', now() - interval '1 minute')""",
        (fora, [hoje]),
    )
    from app import db

    with db.transaction("t") as c:
        criados = tick(c)
    assert len(criados) == 1  # só o agendamento cuja janela é hoje disparou
    s = {r["nome"]: r for r in conn.execute("select * from schedules where nome like '%%teste'")}
    assert s["rpi-terca-teste"]["ultimo_job_id"] is None and s["rpi-terca-teste"]["proximo_em"] > datetime.now(UTC)
    assert s["rpi-hoje-teste"]["ultimo_job_id"] == criados[0]


def test_nova_rpi_detectada_dispara_tudo_sozinha(conn, mundo, monkeypatch):  # noqa: F811
    """Fluxo real: o agendador chama rpi.discover; ninguém aperta botão. Termina com leads de SC priorizados."""
    from tests.rpi_helpers import FakeINPI

    f = FakeINPI()
    f.files["RM2914.zip"] = make_zip(xml_text(2914, EXTRA))
    f.install()
    try:
        enqueue("rpi.discover", {"desde": 2914})
        drain(400)
    finally:
        from app.rpi import http as rpi_http

        rpi_http.transport = None
    ed = conn.execute("select * from rpi_editions where numero = 2914").fetchone()
    assert ed["status"] == "parsed" and ed["detectada_em"] and ed["processada_em"]
    op = conn.execute("select * from rpi_operacoes where edition_id = %s", (ed["id"],)).fetchone()
    assert op and op["priorizada_em"] and op["detalhes"]["distribuicao"]["SC"]
    assert conn.execute("select count(*) n from jobs where tipo = 'rpi.semana' and status = 'succeeded'").fetchone()["n"] == 1


# ------------------------------------------------------------------ 7. oposição apresentada × publicada para oposição
def test_oposicao_apresentada_diferente_de_publicacao_para_oposicao(conn, mundo):  # noqa: F811
    importar(conn)
    a = conn.execute("select * from opportunities where numero_processo = '950000001'").fetchone()
    b = conn.execute("select * from opportunities where numero_processo = '950000003'").fetchone()
    assert (a["categoria"], b["categoria"]) == ("oposicao_apresentada", "oposicao")
    pub = conn.execute(
        "select publicacao_protocolo_data(protocolos) d, protocolos from publications where numero_processo = '950000001'"
    ).fetchone()
    assert pub["d"] == date(2026, 11, 3) and pub["protocolos"][0]["requerente"]["nome"] == "OPONENTE EXEMPLO S.A."
    la = conn.execute("select l.* from leads l where holder_id = %s", (holder(conn, "950000001")["id"],)).fetchone()
    assert la["categoria_principal"] == "oposicao_apresentada" and la["score_detalhes"]["categoria"] == 45
    with TestClient(app) as c:
        sc = c.get("/api/mapa/SC").json()["indicadores"]
    assert (sc["oposicoes_apresentadas"], sc["publicados_oposicao"]) == (2, 1)


# ------------------------------------------------------------------ 3. localização com origem e confiabilidade
def test_localizacao_confirmada_estimada_e_pendente(conn, mundo):  # noqa: F811
    importar(conn)
    for t in ("cnpj.sync",):
        enqueue(t)
        drain()
    gama = conn.execute("select * from holders where nome_original like 'INDÚSTRIA%%GAMA%%'").fetchone()
    assert (gama["geo_uf"], gama["geo_municipio"], gama["geo_fonte"], gama["geo_status"]) == (
        "SP",
        "Sao Paulo",
        "receita",
        "confirmada",
    )
    sc = holder(conn, "950000001")
    assert (sc["geo_uf"], sc["geo_fonte"], sc["geo_status"]) == ("SC", "rpi", "estimada")  # declarada na RPI
    sem = holder(conn, "950000007")
    assert (sem["geo_uf"], sem["geo_status"]) == (None, "pendente")  # nunca uma UF arbitrária
    with TestClient(app) as c:
        m = c.get("/api/mapa").json()
        assert m["processado"] and len(m["estados"]) == 27 and {e["uf"] for e in m["estados"]} >= {"SC", "DF", "RS", "AC"}
        assert m["pendente"]["leads"] == 1
        # uma pessoa confirma a UF; o cálculo automático não sobrescreve
        r = c.post(f"/api/holders/{sem['id']}/localizacao", json={"uf": "SC", "municipio": "Joinville"}).json()
        assert (r["geo_uf"], r["geo_fonte"], r["geo_status"]) == ("SC", "manual", "confirmada")
        drain()
        assert holder(conn, "950000007")["geo_fonte"] == "manual"
        assert c.post(f"/api/holders/{sem['id']}/localizacao", json={"uf": "XX"}).status_code == 422
        # limpar volta ao automático
        assert c.post(f"/api/holders/{sem['id']}/localizacao", json={}).json()["geo_status"] == "pendente"


def test_mapa_sem_rpi_processada_nao_mostra_zero(conn):
    with TestClient(app) as c:
        m = c.get("/api/mapa").json()
    assert m["processado"] is False and m["total"] == 0  # a tela mostra "sem dados", não "0 oportunidades"


# ------------------------------------------------------------------ 6. SC antes de RS, PR e demais
def test_santa_catarina_tem_prioridade_real_na_fila(conn, mundo):  # noqa: F811
    importar(conn, drenar=False)
    ate_operacao(conn)
    tarefas = conn.execute(
        """select j.tipo, j.prioridade, coalesce(h.geo_uf, 'PENDENTE') uf
             from jobs j
             left join process_holders ph on j.tipo = 'inpi.verify' and ph.numero_processo = j.payload->>'numero'
             left join holders h on h.id = coalesce(ph.holder_id, (j.payload->>'holder_id')::bigint)
            where j.status = 'queued' and j.tipo in ('inpi.verify', 'research.free')"""
    ).fetchall()
    pri = {}
    for t in tarefas:
        pri.setdefault(t["uf"], []).append(t["prioridade"])
    assert max(pri["SC"]) < min(pri["RS"]) and max(pri["RS"]) < min(pri["PR"]) and max(pri["PR"]) < min(pri["MG"])
    assert min(pri["PENDENTE"]) > max(v for k, vs in pri.items() if k != "PENDENTE" for v in vs)
    # a fila entrega SC primeiro, de fato
    from app import db

    with db.transaction("t") as c:
        primeiro = queue.claim(c, "w-ordem")
    alvo = primeiro["payload"].get("numero") or primeiro["payload"].get("holder_id")
    uf = conn.execute(
        "select h.geo_uf from holders h left join process_holders ph on ph.holder_id = h.id "
        "where ph.numero_processo = %s or h.id::text = %s limit 1",
        (str(alvo), str(alvo)),
    ).fetchone()["geo_uf"]
    assert uf == "SC"


def test_ordem_dos_demais_estados_e_configuravel_e_sc_fica_em_primeiro(conn):
    with TestClient(app) as c:
        atual = [u["uf"] for u in c.get("/api/uf-prioridade").json()]
        assert atual[:3] == ["SC", "RS", "PR"] and len(atual) == 27
        resto = [u for u in atual[3:] if u != "MG"]
        nova = ["MG", *resto]
        r = c.put("/api/uf-prioridade", json={"ufs": nova}).json()
        assert [u["uf"] for u in r][:4] == ["SC", "RS", "PR", "MG"]
        assert c.put("/api/uf-prioridade", json={"ufs": ["SC", *resto[:23]]}).status_code == 422  # SC não sai do 1º
    p = {r["uf"]: r["p"] for r in conn.execute("select uf, prioridade_fila_uf(uf) p from uf_prioridade")}
    assert p["SC"] < p["RS"] < p["PR"] < p["MG"] < p["SP"]


# ------------------------------------------------------------------ 8. reprocessar não duplica
def test_reprocessar_a_mesma_edicao_nao_duplica(conn, mundo):  # noqa: F811
    importar(conn)
    antes = {
        t: conn.execute(f"select count(*) n from {t}").fetchone()["n"]
        for t in ("leads", "publications", "opportunities", "holders")
    }
    with TestClient(app) as c:
        assert c.post("/api/rpi/editions/2915/parse").status_code == 202
        drain(400)
        assert c.post("/api/rpi-semana/2915/priorizar").status_code == 202
        drain(400)
    depois = {t: conn.execute(f"select count(*) n from {t}").fetchone()["n"] for t in antes}
    assert antes == depois
    dup = conn.execute(
        "select dedupe_key, count(*) n from jobs where status in ('queued','running') and dedupe_key is not null group by 1 having count(*) > 1"
    ).fetchall()
    assert dup == []
    assert conn.execute("select execucoes from rpi_operacoes").fetchone()["execucoes"] >= 1


# ------------------------------------------------------------------ temperatura, motivos e contatos não inventados
def test_temperatura_e_motivos():
    base = dict(categoria="oposicao_apresentada", dias_publicacao=2, contato_validado=True, contatos_total=2, whatsapp_status="validado",
                geo_status="estimada", cnpj_status="encontrado", abordado=False, procurador_confirmado=True, uf="SC")  # fmt: skip
    t, m = temperatura(**base)
    assert t == "quente" and any("oposição apresentada" in x for x in m) and any("SC" in x for x in m)
    assert temperatura(**base | {"contato_validado": False})[0] == "morno"  # oposição sozinha não valida o lead
    assert temperatura(**base | {"abordado": True})[0] == "morno"
    assert temperatura(**base | {"contatos_total": 0, "contato_validado": False})[0] == "em_pesquisa"
    assert temperatura(**base | {"geo_status": "pendente", "uf": None})[0] == "em_pesquisa"
    assert temperatura(**base | {"categoria": "oposicao", "dias_publicacao": 45})[0] == "morno"  # antiga demais


def test_lead_quente_de_sc_gera_marco_alerta_e_relatorio(conn, mundo):  # noqa: F811
    importar(conn)
    h = holder(conn, "950000002")
    ev = conn.execute(
        "insert into evidences (url, trecho, fonte_tipo) values ('https://cafeserrano.com.br/', 'WhatsApp (48) 99999-1111', 'web') returning id"
    ).fetchone()["id"]
    conn.execute(
        """insert into contacts (holder_id, tipo, valor, valor_normalizado, evidence_id, fonte_tipo, verificacao, confianca)
           values (%s, 'whatsapp', '(48) 99999-1111', '+5548999991111', %s, 'web', 'dominio_ok', 0.8)""",
        (h["id"], ev),
    )
    enqueue("leads.build")
    drain()
    lead = conn.execute("select * from leads where holder_id = %s", (h["id"],)).fetchone()
    # V2.4: sem conferir as petições no INPI ainda não é quente (pode já existir manifestação)
    assert lead["temperatura"] == "morno" and lead["classificacao_oposicao"] == "morno"
    assert any("petições ainda não conferidas" in m for m in lead["temperatura_motivos"])
    conn.execute(
        """insert into process_peticoes (protocolo, numero_processo, data, servico, descricao, cliente, fonte_url)
           values ('850200000002', '950000002', '2026-06-01', '389', 'Pedido de registro de marca', 'CAFE SERRANO LTDA', 'pepi')"""
    )
    enqueue("servicos.analisar")
    drain()
    lead = conn.execute("select * from leads where holder_id = %s", (h["id"],)).fetchone()
    assert lead["temperatura"] == "quente" and lead["score_detalhes"]["estado"] == 15
    assert "Contato comercial validado" in lead["temperatura_motivos"]
    # nenhum contato inventado: os demais titulares de SC seguem sem contato
    outro = holder(conn, "950000001")
    assert conn.execute("select count(*) n from contacts where holder_id = %s", (outro["id"],)).fetchone()["n"] == 0
    enqueue("rpi.semana_check")
    drain()
    op = conn.execute("select * from rpi_operacoes").fetchone()
    assert op["sc_primeiros_quentes_em"] is not None
    assert conn.execute("select count(*) n from agent_events where tipo = 'operacao.sc_pronto'").fetchone()["n"] == 1
    enqueue("rpi.semana_check")
    drain()
    assert (
        conn.execute("select count(*) n from agent_events where tipo = 'operacao.sc_pronto'").fetchone()["n"] == 1
    )  # avisa uma vez
    with TestClient(app) as c:
        alertas = {a["chave"]: a for a in c.get("/api/alerts").json()}
        assert alertas["sc_quentes"]["quantidade"] == 1 and alertas["sc_quentes"]["severidade"] == "oportunidade"
        rel = c.get("/api/rpi-semana/relatorio", params={"uf": "SC"}).json()
        assert (rel["oposicoes"], rel["publicados_oposicao"], rel["total_quentes"], rel["contatos_validados"]) == (2, 1, 1, 1)
        assert rel["leads_quentes"][0]["titular"] == "CAFE SERRANO LTDA" and rel["edicao"]["numero"] == 2915
        lst = c.get("/api/leads", params={"geo_uf": "SC", "temperatura": "quente"}).json()
        assert [x["titular"] for x in lst["items"]] == ["CAFE SERRANO LTDA"] and lst["items"][0]["geo_status"] == "estimada"
        x = c.get("/api/leads-export", params={"formato": "csv", "geo_uf": "SC"})
        txt = x.content.decode("utf-8-sig")
        assert "uf_localizacao" in txt and "Declarada na RPI" in txt and "CAFE SERRANO" in txt


def test_central_rpi_mostra_etapas_reais(conn, mundo):  # noqa: F811
    with TestClient(app) as c:
        assert c.get("/api/rpi-semana").json()["status"] is None  # sem edição: nada inventado
    importar(conn, drenar=False)
    ate_operacao(conn)
    with TestClient(app) as c:
        st = c.get("/api/rpi-semana").json()["status"]
    etapas = {e["chave"]: e["status"] for e in st["etapas"]}
    assert etapas["detectada"] == "concluida" and etapas["extraida"] == "concluida"
    assert etapas["SC"] in ("pendente", "em_execucao") and st["trabalhando_em"] == "SC"
    drain(400)
    with TestClient(app) as c:
        st = c.get("/api/rpi-semana").json()["status"]
        comp = c.get("/api/rpi-semana/comparativo", params={"uf": "SC"}).json()
    etapas = {e["chave"]: e["status"] for e in st["etapas"]}
    assert etapas["SC"] == "concluida" and etapas["RS"] == "concluida" and etapas["PR"] == "concluida"
    assert [u["uf"] for u in st["ufs"]][:3] == ["SC", "RS", "PR"]
    assert comp[0]["numero"] == 2915 and comp[0]["novos"] == comp[0]["leads"] == 3


def test_atraso_da_rpi_e_falha_geram_alerta(conn):
    conn.execute(
        "insert into rpi_editions (numero, data_publicacao, status, fonte_url) values (2914, '2026-11-10', 'parsed', 'x')"
    )
    qua = datetime(2026, 11, 18, 9, 0, tzinfo=SP)  # quarta da semana seguinte, sem a 2915
    terca_manha = datetime(2026, 11, 17, 10, 0, tzinfo=SP)
    a = semana.rpi_atrasada(conn, qua)
    assert a and a["terca"] == date(2026, 11, 17) and a["horas"] == 19.0
    assert semana.rpi_atrasada(conn, terca_manha) is None  # antes das 14h de terça não é atraso
    conn.execute(
        "insert into rpi_editions (numero, data_publicacao, status, fonte_url) values (2915, '2026-11-17', 'detected', 'x')"
    )
    assert semana.rpi_atrasada(conn, qua) is None
    # falha de coleta -> alerta crítico com caminho de recuperação
    conn.execute(
        "insert into jobs (tipo, status, finalizado_em, ultimo_erro) values ('rpi.collect', 'dead', now(), 'zip corrompido')"
    )
    with TestClient(app) as c:
        a = {x["chave"]: x for x in c.get("/api/alerts").json()}
    assert a["rpi_falha"]["severidade"] == "critico" and a["rpi_falha"]["href"] == "/rpi-semanal"


def test_arquivo_corrompido_nao_e_publicado(conn):
    with TestClient(app) as c:
        r = c.post("/api/rpi/upload", files={"file": ("RM2915.zip", b"PK\x03\x04 lixo", "application/zip")})
    assert r.status_code == 422
    assert conn.execute("select count(*) n from rpi_editions").fetchone()["n"] == 0


@pytest.mark.parametrize("papel", ["leitor"])
def test_leitor_nao_reordena_estados(papel):
    from app.security import pode

    assert not pode(papel, "PUT", "/api/uf-prioridade")
    assert pode("operador", "POST", "/api/rpi-semana/2915/priorizar")
    assert not pode("operador", "POST", "/api/holders/1/localizacao") and pode("revisor", "POST", "/api/holders/1/localizacao")
