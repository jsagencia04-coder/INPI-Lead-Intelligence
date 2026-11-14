import os
import tempfile

import psycopg
import pytest

ADMIN_URL = os.environ.get("TEST_ADMIN_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
TEST_DB = "inpi_test"
TEST_URL = ADMIN_URL.rsplit("/", 1)[0] + f"/{TEST_DB}"

os.environ["DATABASE_URL"] = TEST_URL
os.environ["AUTH_MODE"] = "dev"
os.environ["APP_ENV"] = "demo"
# V2.6: os testes antigos usam edições reais anteriores à 2914 (fixtures 2904, 2905, 2909); a regra da edição mínima
# tem testes próprios (test_operacao_v26.py), que ligam o corte explicitamente.
os.environ["RPI_EDICAO_MINIMA"] = "1"
os.environ["PEPI_INTERVALO_SEGUNDOS"] = "0"
os.environ["SITE_INTERVALO_SEGUNDOS"] = "0"
os.environ["CNPJ_CACHE_DIR"] = tempfile.mkdtemp(prefix="inpi-cnpj-")
os.environ["STORAGE_LOCAL_DIR"] = tempfile.mkdtemp(prefix="inpi-storage-")


@pytest.fixture(autouse=True)
def _dns_de_teste(monkeypatch):
    """Os sites dos testes não existem: todo nome resolve para um IP público fictício (sem rede)."""
    from app import net_guard

    monkeypatch.setattr(net_guard, "resolver", lambda host: ["93.184.216.34"])


@pytest.fixture(scope="session", autouse=True)
def database():
    with psycopg.connect(ADMIN_URL, autocommit=True) as c:
        c.execute(f"drop database if exists {TEST_DB} with (force)")
        c.execute(f"create database {TEST_DB}")
    from app.config import get_settings
    from app.migrate import migrate

    get_settings.cache_clear()
    migrate(TEST_URL)
    with psycopg.connect(TEST_URL, autocommit=True) as c:  # V2.7: cópia dos 3 modelos de fábrica, restaurada a cada teste
        c.execute("create table _modelos_fabrica as select * from wa_modelos")
        c.execute("alter table _modelos_fabrica enable row level security")
    yield TEST_URL
    from app import db

    db.close_pool()


@pytest.fixture(autouse=True)
def clean(database):
    with psycopg.connect(database, autocommit=True) as c:
        c.execute(
            """truncate pipeline_processos, corte_rpi_backup, wa_auditoria, wa_rascunhos, wa_contas, oportunidades_servico, process_peticoes, rpi_operacoes, cnpj_municipios, lead_stage_history, consent_requests, app_users, wa_webhook_events, wa_messages, consents, jobs,
                audit_log, review_tasks, outreach_log, lead_processes, leads,
               contacts, evidences, research_runs, inpi_verifications, process_holders, opportunities,
               holders, publications, processes, rpi_files, rpi_editions, llm_calls, lead_notes, reports,
               exports_log, suppression_list, cnpj_estabelecimentos, cnpj_empresas, agent_events restart identity cascade"""
        )
        c.execute("update app_config set valor = 'demo' where chave = 'ambiente'")
        c.execute("update app_config set valor = 'false' where chave = 'whatsapp_envio_bloqueado'")
        c.execute("update app_config set valor = '1' where chave = 'rpi_edicao_minima'")
        c.execute("update app_config set valor = '' where chave in ('primeiro_contato_atendente','primeiro_contato_empresa')")
        c.execute("update app_config set valor = '20' where chave = 'whatsapp_limite_diario'")
        c.execute("truncate wa_modelos_historico, wa_modelos restart identity cascade")
        c.execute("insert into wa_modelos select * from _modelos_fabrica")
        c.execute(
            "insert into wa_modelos_historico (modelo_id, versao, nome, texto, ativo, alterado_por)"
            " select id, versao, nome, texto, ativo, atualizado_por from wa_modelos"
        )
        c.execute("delete from despacho_types where fonte like 'detectado%'")
        c.execute(
            "update despacho_types set ativo_para_leads = categoria_comercial not in ('outro','arquivamento'),"
            " revisar = false, confirmado_por = null"
        )
        # truncate jobs ... cascade também esvazia schedules (FK ultimo_job_id); recria o seed
        c.execute(
            "insert into schedules (nome, tipo, intervalo_minutos, proximo_em)"
            " values ('rpi-descoberta', 'rpi.discover', 180, now() + interval '1 day')"
        )
    yield


@pytest.fixture
def conn(database):
    from psycopg.rows import dict_row

    with psycopg.connect(database, row_factory=dict_row, autocommit=True) as c:
        yield c
