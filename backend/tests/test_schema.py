import psycopg
import pytest

from app import db


def test_migrations_idempotentes(database):
    from app.migrate import migrate

    assert migrate(database) == []


def test_auditoria_registra_ator_e_mudancas(conn):
    with db.transaction("user:ana@exemplo.com") as c:
        c.execute("insert into processes (numero_processo, marca_nome) values ('912345678', 'ACME')")
    with db.transaction("agent:inpi.verify#1") as c:
        c.execute("update processes set procurador_status = 'sem_confirmado' where numero_processo = '912345678'")
        c.execute("update processes set procurador_status = 'sem_confirmado' where numero_processo = '912345678'")
    rows = conn.execute(
        "select acao, ator, depois->>'procurador_status' as ps from audit_log "
        "where tabela = 'processes' and registro_id = '912345678' order by id"
    ).fetchall()
    # o 2º update não mudou nada e não deve gerar registro
    assert [(r["acao"], r["ator"], r["ps"]) for r in rows] == [
        ("INSERT", "user:ana@exemplo.com", "desconhecido"),
        ("UPDATE", "agent:inpi.verify#1", "sem_confirmado"),
    ]


def test_numero_processo_invalido_rejeitado(conn):
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("insert into processes (numero_processo) values ('ABC-1')")


def test_arquivo_rpi_e_imutavel(conn):
    conn.execute("insert into rpi_editions (numero) values (2900)")
    conn.execute(
        """insert into rpi_files (edition_id, formato, source_url, storage_path, sha256, bytes)
           values (1, 'xml', 'https://exemplo/RM2900.zip', 'rpi/2900/RM2900.zip', repeat('a', 64), 10)"""
    )
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("update rpi_files set bytes = 11")
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("delete from rpi_files")


def test_contato_exige_evidencia(conn):
    conn.execute("insert into holders (nome_original, nome_normalizado) values ('Ana', 'ANA')")
    with pytest.raises(psycopg.errors.NotNullViolation):
        conn.execute("insert into contacts (holder_id, tipo, valor, valor_normalizado) values (1,'email','a@b.com','a@b.com')")


def test_titular_deduplicado_por_nome_uf_pais(conn):
    conn.execute("insert into holders (nome_original, nome_normalizado, uf, pais) values ('Ana', 'ANA', 'SP', 'BR')")
    conn.execute("insert into holders (nome_original, nome_normalizado, uf, pais) values ('Ana', 'ANA', 'RJ', 'BR')")
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute("insert into holders (nome_original, nome_normalizado, uf, pais) values ('ANA', 'ANA', 'SP', 'BR')")


def test_rls_habilitado_em_todas_as_tabelas(conn):
    sem_rls = conn.execute(
        "select relname from pg_class c join pg_namespace n on n.oid = c.relnamespace "
        "where n.nspname = 'public' and c.relkind = 'r' and not c.relrowsecurity"
    ).fetchall()
    assert sem_rls == []
