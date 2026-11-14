"""V2.6 · RPI mínima 2914, oposições, procurador, prioridade comercial e geográfica, mapa → pipeline.

Os XML são montados no formato real da RPI (mesmos elementos e atributos do XML oficial da 2914).
"""

import os

import pytest
from fastapi.testclient import TestClient

from app import comercial, db
from app.config import get_settings
from app.jobs import queue
from app.main import app
from tests.rpi_helpers import FakeINPI, make_zip
from tests.test_fases3a7 import drain, enqueue

OPOSICAO = ("IPAS423", "Notificação de oposição")
INDEFERIMENTO = ("IPAS024", "Indeferimento do pedido")
PUBLICADO = ("IPAS009", "Publicação de pedido de registro para oposição (exame formal concluído)")


def proc(num, desp=OPOSICAO, uf="SC", procurador=None, vazio=False, pais="BR", titular=None, texto="850260447873 de 31/08/2026"):
    p = "<procurador></procurador>" if vazio else (f"<procurador>{procurador}</procurador>" if procurador else "")
    return f"""<processo numero="{num}">
    <despachos><despacho codigo="{desp[0]}" nome="{desp[1]}"><texto-complementar>{texto}</texto-complementar></despacho></despachos>
    <titulares><titular nome-razao-social="{titular or f"EMPRESA {num} LTDA"}" pais="{pais}" uf="{uf}"/></titulares>
    <marca apresentacao="Nominativa" natureza="De Produto"><nome>MARCA {num}</nome></marca>
    {p}
  </processo>"""


def revista(numero, procs, data="10/11/2026"):
    return (
        f'<?xml version="1.0" encoding="UTF-8" ?>\n<revista numero="{numero}" data="{data}">\n'
        + "\n".join(procs)
        + "\n</revista>"
    )


def upload(numero, procs, data="10/11/2026", status=201):
    with TestClient(app) as c:
        r = c.post(
            "/api/rpi/upload",
            files={"file": (f"RM{numero}.zip", make_zip(revista(numero, procs, data), f"RM{numero}.xml"), "application/zip")},
        )
    assert r.status_code == status, r.text
    drain()
    return r


@pytest.fixture
def corte(conn):
    os.environ["RPI_EDICAO_MINIMA"] = "2914"
    os.environ["RPI_OPERACAO_SEMANAL_AUTO"] = "false"
    get_settings.cache_clear()
    conn.execute("update app_config set valor = '2914' where chave = 'rpi_edicao_minima'")
    conn.execute("update despacho_types set ativo_para_leads = false where codigo = 'IPAS009'")  # como em produção (V2.4)
    yield
    os.environ["RPI_EDICAO_MINIMA"] = "1"
    os.environ.pop("RPI_OPERACAO_SEMANAL_AUTO", None)
    get_settings.cache_clear()


def api(method, url, **kw):
    with TestClient(app) as c:
        return c.request(method, url, **kw)


# ------------------------------------------------------------------ 1. edição mínima
def test_config_centralizada(conn, corte):
    assert comercial.edicao_minima() == 2914
    assert conn.execute("select rpi_edicao_minima() m").fetchone()["m"] == 2914
    assert [comercial.dentro_do_corte(n) for n in (2913, 2914, 2915, 2916)] == [False, True, True, True]


def test_rpi_2913_descartada_e_2914_2915_2916_aceitas(conn, corte):
    upload(2913, [proc("900000001")], status=422)
    for n in (2914, 2915, 2916):
        upload(n, [proc(f"9000{n}1")])
    eds = {r["numero"]: r["status"] for r in conn.execute("select numero, status from rpi_editions")}
    assert eds == {2914: "parsed", 2915: "parsed", 2916: "parsed"}
    # o worker também recusa (coleta e leitura), sem marcar erro
    enqueue("rpi.parse", {"numero": 2913})
    enqueue("rpi.collect", {"numero": 2913})
    drain()
    jobs = conn.execute("select tipo, status, resultado from jobs where payload->>'numero' = '2913'").fetchall()
    assert jobs and all(j["status"] == "succeeded" and "anterior à edição mínima" in j["resultado"]["ignorado"] for j in jobs)
    assert api("POST", "/api/rpi/editions/2913/parse").status_code == 422


def test_descoberta_respeita_minimo(conn, corte):
    fake = FakeINPI().install()
    enqueue("rpi.discover", {"desde": 2900})
    drain()
    assert {r["numero"] for r in conn.execute("select numero from rpi_editions")} == {2914}
    assert not any("RM2913" in u for u in fake.calls)


def test_historico_anterior_fora_da_operacao_e_reversivel(conn, corte):
    # registros antigos (importados antes da V2.6) não aparecem no mapa nem nos indicadores, mas não são apagados
    conn.execute("update app_config set valor = '1' where chave = 'rpi_edicao_minima'")
    os.environ["RPI_EDICAO_MINIMA"] = "1"
    get_settings.cache_clear()
    upload(2913, [proc("911111111", uf="RS")], data="03/11/2026")
    upload(2914, [proc("922222222", uf="SC")])
    os.environ["RPI_EDICAO_MINIMA"] = "2914"
    get_settings.cache_clear()
    with db.transaction("t") as c:
        r = comercial.sincronizar_config(c)
    assert r["oportunidades_retiradas"] == 1 and r["servicos_retirados"] == 1
    lista = api("GET", "/api/servicos").json()
    assert [i["numero_processo"] for i in lista["items"]] == ["922222222"]
    conn.execute("update holders set geo_uf = nullif(uf, ''), geo_status = 'estimada'")
    mapa = {e["uf"]: e for e in api("GET", "/api/mapa").json()["estados"]}
    assert mapa["RS"].get("oposicoes_sofridas", 0) == 0 and mapa["SC"]["oposicoes_sofridas"] == 1
    assert all(e["numero"] >= 2914 for e in api("GET", "/api/rpi-semana").json()["edicoes"])
    ind = api("GET", "/api/comercial/indicadores").json()
    assert ind["oportunidades"]["oposicoes"] == 1 and ind["rpis_processadas"] == 1
    # nada foi apagado e o corte é reversível
    assert conn.execute("select count(*) n from opportunities where numero_processo = '911111111'").fetchone()["n"] == 1
    os.environ["RPI_EDICAO_MINIMA"] = "2913"
    get_settings.cache_clear()
    with db.transaction("t") as c:
        r = comercial.sincronizar_config(c)
    assert r["oportunidades_devolvidas"] == 1 and r["servicos_devolvidos"] == 1
    assert len(api("GET", "/api/servicos").json()["items"]) == 2


# ------------------------------------------------------------------ 2. oposição
def test_catalogo_oficial_de_oposicao(conn, corte):
    r = conn.execute("select * from despacho_types where codigo = 'IPAS423'").fetchone()
    assert (r["nome"], r["categoria_comercial"], r["prioridade_comercial"]) == (
        "Notificação de oposição",
        "oposicao_apresentada",
        1,
    )
    assert "RPI 2914" in r["fonte_validacao"]
    assert (
        conn.execute("select prioridade_comercial from despacho_types where codigo = 'IPAS024'").fetchone()[
            "prioridade_comercial"
        ]
        == 2
    )
    # "publicado para oposição" tem a palavra oposição mas NÃO é oposição apresentada
    assert (
        conn.execute("select prioridade_comercial from despacho_types where codigo = 'IPAS009'").fetchone()[
            "prioridade_comercial"
        ]
        is None
    )


def test_oposicoes_da_ultima_rpi_capturadas_sem_perda(conn, corte):
    procs = [proc(f"94400{i:04d}") for i in range(30)]  # 30 oposições sem procurador
    procs += [proc(f"94500{i:04d}", procurador="ESCRITÓRIO X") for i in range(10)]  # 10 com procurador
    procs += [proc(f"94600{i:04d}", desp=INDEFERIMENTO) for i in range(5)]
    procs += [proc(f"94700{i:04d}", desp=PUBLICADO) for i in range(7)]  # não é oposição
    upload(2914, procs)
    a = conn.execute("select auditoria from rpi_editions where numero = 2914").fetchone()["auditoria"]
    assert (a["oposicoes_encontradas"], a["oposicoes_gravadas"]) == (40, 40)
    assert (a["indeferimentos_encontrados"], a["indeferimentos_gravados"]) == (5, 5)
    assert a["completa"] and a["erros_de_extracao"] == [] and a["processos_lidos"] == 52
    assert (a["com_procurador"], a["sem_procurador_confirmado"]) == (10, 35)
    n = conn.execute(
        "select count(*) n from oportunidades_servico where servico = 'manifestacao_oposicao' and elegivel"
    ).fetchone()["n"]
    assert n == 30
    assert (
        conn.execute(
            "select count(*) n from opportunities o where o.numero_processo like '947%' and o.categoria like 'oposicao%'"
        ).fetchone()["n"]
        == 0
    )


def test_catalogo_alterado_depois_da_leitura_gera_releitura(conn, corte):
    """A falha real da RPI 2914: o código de oposição foi ativado depois da leitura e a releitura ficou parada."""
    conn.execute("update despacho_types set ativo_para_leads = false where codigo = 'IPAS423'")
    upload(2914, [proc("944040470")])
    assert conn.execute("select count(*) n from opportunities").fetchone()["n"] == 0
    conn.execute("update despacho_types set ativo_para_leads = true where codigo = 'IPAS423'")
    alerta = api("GET", "/api/comercial/indicadores").json()["edicoes"][0]["alerta"]
    assert "Releitura pendente" in alerta
    # a releitura entra na frente de milhares de pesquisas e verificações já enfileiradas
    with db.transaction("t") as c:
        for i in range(50):
            queue.enqueue(c, "research.free", {"i": i}, prioridade=60)
    FakeINPI().install()
    enqueue("rpi.discover")
    from app.worker import run_one

    for _ in range(4):
        run_one("w-test")
    assert conn.execute("select count(*) n from opportunities where categoria = 'oposicao_apresentada'").fetchone()["n"] == 1
    assert api("GET", "/api/comercial/indicadores").json()["edicoes"][0]["alerta"] is None


# ------------------------------------------------------------------ 3. procurador
def test_estados_de_representacao(conn, corte):
    upload(
        2914,
        [
            proc("950000001"),  # campo ausente → sem procurador confirmado (XML lido por inteiro)
            proc("950000002", procurador="ADVOGADO FULANO"),  # com procurador → excluído
            proc("950000003", vazio=True),  # elemento vazio → erro na identificação (não vira "sem")
        ],
    )
    st = {
        r["numero_processo"]: r
        for r in conn.execute(
            "select numero_processo, procurador_status, procurador_situacao(procurador_status) s from processes"
        )
    }
    assert st["950000001"]["s"] == "SEM_PROCURADOR_CONFIRMADO"
    assert st["950000002"]["s"] == "COM_PROCURADOR"
    assert st["950000003"]["s"] == "ERRO_NA_IDENTIFICACAO"
    assert [i["numero_processo"] for i in api("GET", "/api/servicos").json()["items"]] == ["950000001"]
    motivos = {
        r["numero_processo"]: r["motivo_descarte"]
        for r in conn.execute("select numero_processo, motivo_descarte from opportunities")
    }
    assert motivos == {"950000001": None, "950000002": "possui procurador", "950000003": "erro na identificação do procurador"}


def test_procurador_desconhecido_nao_entra(conn, corte):
    assert comercial.motivo_procurador("desconhecido") == "representação desconhecida"
    assert comercial.motivo_procurador(None) == "representação desconhecida"
    assert comercial.motivo_procurador("sem_confirmado") is None and comercial.motivo_procurador("sem_na_rpi") is None
    upload(2914, [proc("951000001")])
    conn.execute("update processes set procurador_status = 'desconhecido' where numero_processo = '951000001'")
    assert api("GET", "/api/servicos").json()["total"] == 0


# ------------------------------------------------------------------ 4. ordenação comercial e geográfica
def test_ordem_oposicao_antes_de_indeferimento_e_sc_rs_pr(conn, corte):
    upload(
        2914,
        [
            proc("960000001", desp=INDEFERIMENTO, uf="SC"),
            proc("960000002", uf="PR"),
            proc("960000003", uf="SP"),
            proc("960000004", uf="RS"),
            proc("960000005", desp=INDEFERIMENTO, uf="RS"),
            proc("960000006", uf="SC"),
            proc("960000007", desp=INDEFERIMENTO, uf="PR"),
            proc("960000008", uf="", pais="BR"),  # sem UF: separado, por último no grupo
        ],
    )
    conn.execute("select atualizar_localizacao()") if conn.execute("select to_regproc('atualizar_localizacao') r").fetchone()[
        "r"
    ] else None
    conn.execute("update holders set geo_uf = nullif(uf, ''), geo_status = 'estimada' where geo_uf is null")
    itens = api("GET", "/api/servicos").json()["items"]
    assert [(i["prioridade"], i["geo_uf"]) for i in itens] == [
        (1, "SC"),
        (1, "RS"),
        (1, "PR"),
        (1, "SP"),
        (1, None),
        (2, "SC"),
        (2, "RS"),
        (2, "PR"),
    ]
    sc = api("GET", "/api/servicos", params={"uf": "SC", "servico": "manifestacao_oposicao"}).json()["items"]
    assert [i["numero_processo"] for i in sc] == ["960000006"]
    sul = api("GET", "/api/comercial/indicadores").json()["sul"]
    assert [(s["uf"], s["oposicoes"], s["indeferimentos"]) for s in sul] == [("SC", 1, 1), ("RS", 1, 1), ("PR", 1, 1)]
    assert comercial.UF_PRIORIDADE == {"SC": 1, "RS": 2, "PR": 3}
    assert [r["uf"] for r in conn.execute("select uf from uf_prioridade order by ordem limit 3")] == ["SC", "RS", "PR"]


# ------------------------------------------------------------------ 5. mapa → pipeline
@pytest.fixture
def com_leads(conn, corte):
    upload(2914, [proc("970000001", uf="SC", titular="ALFA LTDA"), proc("970000002", desp=INDEFERIMENTO, uf="SC", titular="ALFA LTDA"),
                  proc("970000003", uf="RS", titular="BETA LTDA")])  # fmt: skip
    enqueue("leads.build")
    drain()
    return {r["numero_processo"]: r["lead_id"] for r in conn.execute("select numero_processo, lead_id from lead_processes")}


def test_adicionar_ao_pipeline_sem_duplicar(conn, com_leads):
    lead = com_leads["970000001"]
    conn.execute("insert into lead_notes (lead_id, texto) values (%s, 'nota antiga')", (lead,))
    hist_antes = conn.execute("select count(*) n from lead_stage_history where lead_id = %s", (lead,)).fetchone()["n"]
    f = api("GET", "/api/pipeline/processo/970000001").json()
    assert f["processo"]["titular"] == "ALFA LTDA" and f["processo"]["prioridade"] == 1 and not f["ja_no_pipeline"]
    assert f["processo"]["procurador_situacao"] == "SEM_PROCURADOR_CONFIRMADO" and f["processo"]["rpi_numero"] == 2914
    r = api("POST", "/api/pipeline/processo/970000001", json={}).json()
    assert r == {
        "ja_existia": False,
        "lead_id": lead,
        "etapa": r["etapa"],
        "mensagem": "Lead adicionado ao Pipeline com sucesso.",
    }
    # de novo: não cria outro registro
    r2 = api("POST", "/api/pipeline/processo/970000001", json={}).json()
    assert r2["ja_existia"] and r2["mensagem"] == "Este processo já está cadastrado no Pipeline." and r2["lead_id"] == lead
    assert api("GET", "/api/pipeline/processo/970000001").json()["ja_no_pipeline"]
    # outro processo do mesmo titular: mesma pessoa, oportunidade própria; o lead não é duplicado
    api("POST", "/api/pipeline/processo/970000002", json={})
    assert conn.execute("select count(*) n from pipeline_processos where lead_id = %s", (lead,)).fetchone()["n"] == 2
    assert (
        conn.execute(
            "select count(*) n from leads where holder_id = (select holder_id from leads where id = %s)", (lead,)
        ).fetchone()["n"]
        == 1
    )
    # notas e histórico preservados
    assert conn.execute("select texto from lead_notes where lead_id = %s", (lead,)).fetchone()["texto"] == "nota antiga"
    assert conn.execute("select count(*) n from lead_stage_history where lead_id = %s", (lead,)).fetchone()["n"] >= hist_antes
    # o pipeline abre direto no lead certo
    etapa = conn.execute("select pipeline_stage from leads where id = %s", (lead,)).fetchone()["pipeline_stage"]
    itens = api("GET", "/api/pipeline/leads", params={"etapa": etapa, "lead_id": lead}).json()["items"]
    assert [i["id"] for i in itens] == [lead] and "970000001" in itens[0]["processos_no_pipeline"]
    assert api("GET", "/api/pipeline", params={"adicionados": True}).json()["adicionados"] == 1


def test_etapa_inicial_e_movimentacoes_indevidas(conn, com_leads):
    lead = com_leads["970000003"]
    # sem evidência de conversa não dá para começar como "interessado"
    r = api("POST", "/api/pipeline/processo/970000003", json={"etapa": "interessado"})
    assert r.status_code == 409
    assert api("POST", f"/api/leads/{lead}/pipeline", json={"etapa": "negociacao", "motivo": "teste"}).status_code == 409
    assert conn.execute("select count(*) n from pipeline_processos").fetchone()["n"] == 0
    # com contato registrado por uma pessoa, a escolha manual vale e fica no histórico
    conn.execute("insert into outreach_log (lead_id, canal, aprovado_por) values (%s, 'telefone', 'user:t')", (lead,))
    r = api("POST", "/api/pipeline/processo/970000003", json={"etapa": "interessado"}).json()
    assert r["etapa"] == "interessado"
    h = conn.execute(
        "select para, origem from lead_stage_history where lead_id = %s order by id desc limit 1", (lead,)
    ).fetchone()
    assert (h["para"], h["origem"]) == ("interessado", "manual")


def test_etapa_existente_preservada_e_opt_out(conn, com_leads):
    lead = com_leads["970000001"]
    conn.execute("insert into outreach_log (lead_id, canal, aprovado_por) values (%s, 'telefone', 'user:t')", (lead,))
    api("POST", f"/api/leads/{lead}/pipeline", json={"etapa": "proposta_enviada", "motivo": "proposta por e-mail"})
    r = api("POST", "/api/pipeline/processo/970000001", json={}).json()
    assert r["etapa"] == "proposta_enviada"  # incluir não mexe na etapa atual
    lead2 = com_leads["970000003"]
    conn.execute("update leads set pipeline_stage = 'opt_out' where id = %s", (lead2,))
    assert api("POST", "/api/pipeline/processo/970000003", json={}).status_code == 409


def test_etapas_do_funil(conn):
    e = api("GET", "/api/pipeline").json()["etapas"]
    assert [x["ordem"] for x in e] == list(range(1, 18))
    assert [x["fase"] for x in e][::4] == ["Identificação", "Elegibilidade", "Primeiro contato", "Negociação", "Resultado"][:5]
    assert all(x["cor"] and x["descricao"] and x["regra"] for x in e)


# ------------------------------------------------------------------ 6. fila
def test_tarefas_da_rpi_nao_ficam_atras_da_fila(conn):
    with db.transaction("t") as c:
        j = queue.enqueue(c, "rpi.parse", {"numero": 1}, dedupe_key="rpi.parse:1", prioridade=90)
        assert j["prioridade"] == 10
        b = queue.enqueue(c, "leads.build", {}, dedupe_key="leads.build", prioridade=80)
        assert b["prioridade"] == 20
        assert queue.enqueue(c, "leads.build", {}, dedupe_key="leads.build", prioridade=6)["prioridade"] == 6
        assert queue.enqueue(c, "research.free", {}, prioridade=65)["prioridade"] == 65


def test_lista_de_leads_do_mapa_em_ordem_comercial(conn, com_leads):
    conn.execute("update holders set geo_uf = nullif(uf, ''), geo_status = 'estimada'")
    itens = api("GET", "/api/leads", params={"operacional": True, "ordem": "comercial"}).json()["items"]
    assert [i["geo_uf"] for i in itens] == ["SC", "RS"]  # os dois têm oposição; SC antes de RS
