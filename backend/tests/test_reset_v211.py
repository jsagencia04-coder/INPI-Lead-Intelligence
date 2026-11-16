"""V2.11 · limpeza dos dados operacionais e espera pela próxima Revista (17/11/2026 00:00:01, America/Sao_Paulo)."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app import db, reset
from app.agents import rpi as rpi_agent
from app.jobs import queue, scheduler
from app.jobs.registry import load_agents
from app.main import app
from app.worker import run_one
from tests.rpi_helpers import FakeINPI

load_agents()
SP = ZoneInfo("America/Sao_Paulo")
PROXIMA = datetime(2026, 11, 17, 0, 0, 1, tzinfo=SP)


def drain(n=40):
    for _ in range(n):
        if not run_one("w-test"):
            return


def discover():
    with db.transaction("test") as c:
        queue.enqueue(c, "rpi.discover", {})
    drain()


def popular(conn):
    FakeINPI().install()
    discover()
    conn.execute(
        """insert into schedules (nome, tipo, intervalo_minutos, dias_semana, hora_inicio, hora_fim, proximo_em)
           values ('rpi-terca', 'rpi.discover', 10, '{2,3}', '05:00', '23:59', now()) on conflict (nome) do nothing"""
    )
    conn.execute("insert into app_users (email, papel) values ('dono@exemplo.com', 'admin')")
    conn.execute("insert into suppression_list (tipo, valor_hash, motivo) values ('telefone', repeat('a', 64), 'SAIR')")
    conn.execute("update wa_modelos set texto = texto || ' (editado)' where codigo = 'MODELO_01'")


def test_toda_tabela_esta_classificada(conn):
    c = reset.classificar(conn)
    assert c["sem_classificacao"] == [] and c["inexistentes"] == []
    assert not set(c["limpar"]) & set(c["preservar"])


def test_recusa_sem_confirmacao(conn, monkeypatch):
    popular(conn)
    monkeypatch.delenv("CONFIRM_RESET", raising=False)
    with pytest.raises(PermissionError):
        reset.reset_operational_data(conn, proxima=PROXIMA, edicao_minima=2915, ator="teste")
    with pytest.raises(Exception, match="confirmação"):
        conn.execute("select reset_operational_data('reset', 'x', now(), 2915)")
    assert conn.execute("select count(*) n from processes").fetchone()["n"] > 0  # nada foi apagado


def test_limpeza_completa_preserva_configuracao_e_agenda_a_proxima_revista(conn, monkeypatch):
    popular(conn)
    sim = reset.simular(conn)
    assert sim["linhas_a_remover"]["processes"] > 0 and sim["linhas_a_remover"]["rpi_editions"] == 1
    modelos = conn.execute("select codigo, texto, versao from wa_modelos order by codigo").fetchall()
    usuarios = conn.execute("select email from app_users").fetchall()

    monkeypatch.setenv("CONFIRM_RESET", "RESET_INPI")
    rel = reset.reset_operational_data(conn, proxima=PROXIMA, edicao_minima=2915, ator="teste")
    assert rel["linhas_removidas"]["processes"] > 0

    # operacionais vazias, sequências reiniciadas
    for t in reset.tabelas_operacionais(conn):
        assert conn.execute(f'select count(*) n from public."{t}"').fetchone()["n"] == 0, t
    novo = conn.execute("insert into rpi_editions (numero) values (2915) returning id").fetchone()
    assert novo["id"] == 1
    conn.execute("delete from rpi_editions")

    # preservado
    assert conn.execute("select codigo, texto, versao from wa_modelos order by codigo").fetchall() == modelos
    assert conn.execute("select email from app_users").fetchall() == usuarios
    assert conn.execute("select count(*) n from suppression_list").fetchone()["n"] == 1
    assert conn.execute("select count(*) n from despacho_types").fetchone()["n"] > 0
    assert {r["nome"] for r in conn.execute("select nome from schedules")} >= {"rpi-terca", "rpi-descoberta"}
    assert conn.execute("select count(*) n from system_resets").fetchone()["n"] == 1

    # status de espera e primeira execução às 00:00:01 de São Paulo (03:00:01 UTC)
    st = reset.status_sistema(conn)
    assert st == {
        "system_status": "waiting_for_next_issue",
        "last_publication_id": None,
        "last_successful_import": None,
        "last_import_status": None,
        "next_scheduled_run": "2026-11-17T00:00:01-03:00",
        "timezone": "America/Sao_Paulo",
    }
    terca = conn.execute("select * from schedules where nome = 'rpi-terca'").fetchone()
    assert terca["proximo_em"] == datetime(2026, 11, 17, 3, 0, 1, tzinfo=UTC)
    assert terca["fuso"] == "America/Sao_Paulo" and str(terca["hora_inicio"]) == "00:00:01"
    # o agendador dispara na janela de terça às 00:00:01 e não antes
    assert scheduler.proxima_janela(dict(terca), datetime(2026, 11, 16, 23, 0, tzinfo=SP)) == PROXIMA
    assert conn.execute("select valor from app_config where chave = 'rpi_edicao_minima'").fetchone()["valor"] == "2915"

    # painel zerado
    with TestClient(app) as c:
        d = c.get("/api/dashboard/summary").json()
        assert d["processos_importados"] == 0 and d["processos_sem_procurador"] == 0
        assert c.get("/api/sistema/status").json()["system_status"] == "waiting_for_next_issue"

    # reimportar depois da limpeza funciona, sem duplicidade, e grava a última importação
    conn.execute("update app_config set valor = '1' where chave = 'rpi_edicao_minima'")
    discover()
    discover()
    assert conn.execute("select count(*) n from rpi_editions").fetchone()["n"] == 1
    assert conn.execute("select count(*) n from rpi_files").fetchone()["n"] == 1  # mesmo hash: um arquivo só
    dup = conn.execute(
        "select count(*) n from (select 1 from publications group by numero_processo, edition_id, despacho_codigo having count(*) > 1) x"
    ).fetchone()["n"]
    assert dup == 0
    st = reset.status_sistema(conn)
    assert st["system_status"] == "operational" and st["last_import_status"] == "success"
    assert st["last_publication_id"] == "2914" and st["last_successful_import"]


def test_bloqueio_e_alerta_de_falha(conn):
    FakeINPI().install()
    conn.execute("update app_config set valor = 'true' where chave = 'importacao_bloqueada'")
    discover()
    j = conn.execute("select status, ultimo_erro from jobs where tipo = 'rpi.discover'").fetchone()
    assert j["status"] == "queued" and "bloqueadas" in j["ultimo_erro"]
    assert conn.execute("select count(*) n from rpi_editions").fetchone()["n"] == 0

    conn.execute("update app_config set valor = 'false' where chave = 'importacao_bloqueada'")
    conn.execute("insert into rpi_editions (numero) values (2915)")
    with db.transaction("test") as c:
        rpi_agent._mark_error(c, {"tipo": "rpi.collect", "id": 1, "payload": {"numero": 2915}}, "HTTP 500 no INPI")
    assert reset.status_sistema(conn)["last_import_status"] == "failed"
    assert conn.execute("select count(*) n from agent_events where tipo = 'rpi.failed'").fetchone()["n"] == 1
    assert conn.execute("select count(*) n from review_tasks where entidade = 'rpi_importacao'").fetchone()["n"] == 1
