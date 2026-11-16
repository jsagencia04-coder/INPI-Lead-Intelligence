"""Envio da origem para o destino (roda na ORIGEM, dentro do container da api, que tem psycopg e httpx).

    python enviar.py medir                 só mede (nada sai)
    python enviar.py banco                 snapshot consistente do PostgreSQL (COPY binário por tabela) + manifesto
    python enviar.py arquivos              volume de dados (/srv/backend/data) em tar.gz
    python enviar.py env                   variáveis listadas em CHAVES (separadas por vírgula) → origem.env
                                           (os valores vão direto ao destino; nada é impresso)

Variáveis: DATABASE_URL (já existe no container), DESTINO (https://<host>/_migracao), MIGRACAO_TOKEN.
Opcionais: SCHEMA (padrão public) e PREFIXO (padrão db) para copiar outro banco, ex.: o da Evolution
(SCHEMA=evolution_api PREFIXO=evo DATABASE_URL=<banco da evolution>), gerando evo__<tabela>.bin e evo_manifesto.json.
Tudo em um único snapshot REPEATABLE READ somente leitura: a origem não é alterada.
Saída sem segredos: só nomes, contagens, tamanhos e sha256.
"""

import hashlib
import json
import os
import sys
import tarfile
import threading

import httpx
import psycopg

DB = os.environ["DATABASE_URL"]
DADOS = os.environ.get("DADOS_DIR", "/srv/backend/data")
SCHEMA = os.environ.get("SCHEMA", "public")
PREFIXO = os.environ.get("PREFIXO", "db")
MANIFESTO = "manifesto.json" if PREFIXO == "db" else f"{PREFIXO}_manifesto.json"


def _put(nome: str, gen) -> dict:
    h = hashlib.sha256()

    def conta():
        for b in gen:
            h.update(b)
            yield b

    r = httpx.put(f"{os.environ['DESTINO']}/arquivo/{nome}", content=conta(), timeout=None,
                  headers={"X-Token": os.environ["MIGRACAO_TOKEN"]})  # fmt: skip
    r.raise_for_status()
    d = r.json()
    if d["sha256"] != h.hexdigest():
        raise RuntimeError(f"{nome}: sha256 diferente no destino")
    return d


def _tabelas(conn):
    return [r[0] for r in conn.execute("select tablename from pg_tables where schemaname = %s order by 1", (SCHEMA,))]


def _colunas(conn, t):
    return [r[0] for r in conn.execute(
        """select column_name from information_schema.columns where table_schema = %s and table_name = %s
              and is_generated = 'NEVER' order by ordinal_position""", (SCHEMA, t))]  # fmt: skip


def medir():
    with psycopg.connect(DB) as conn:
        tam = conn.execute("select pg_size_pretty(pg_database_size(current_database()))").fetchone()[0]
        linhas = {t: conn.execute(f'select count(*) from "{SCHEMA}"."{t}"').fetchone()[0] for t in _tabelas(conn)}
        jobs = dict(conn.execute("select status, count(*) from jobs group by 1").fetchall())
        mig = conn.execute("select max(versao) from schema_migrations").fetchone()[0] if "schema_migrations" in linhas else None
    total, arqs = 0, 0
    for raiz, _, fs in os.walk(DADOS):
        for f in fs:
            total += os.path.getsize(os.path.join(raiz, f))
            arqs += 1
    print(json.dumps({"banco": tam, "tabelas": len(linhas), "linhas": sum(linhas.values()), "por_tabela": linhas,
                      "jobs": jobs, "ultima_migration": mig, "dados_bytes": total, "dados_arquivos": arqs}, default=str))  # fmt: skip


def banco():
    conn = psycopg.connect(DB)
    conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
    conn.read_only = True
    man = {"schema": SCHEMA, "tabelas": [], "sequencias": []}
    with conn.transaction():
        for t in _tabelas(conn):
            cols = _colunas(conn, t)
            linhas = conn.execute(f'select count(*) from "{SCHEMA}"."{t}"').fetchone()[0]
            lista = ", ".join(f'"{c}"' for c in cols)

            def gen(t=t, lista=lista):
                with conn.cursor().copy(f'copy (select {lista} from "{SCHEMA}"."{t}") to stdout (format binary)') as cp:
                    yield from cp

            r = _put(f"{PREFIXO}__{t}.bin", gen())
            man["tabelas"].append({"tabela": t, "colunas": cols, "linhas": linhas, "arquivo": f"{PREFIXO}__{t}.bin",
                                   "bytes": r["bytes"], "sha256": r["sha256"]})  # fmt: skip
        for (nome,) in conn.execute("select quote_ident(schemaname) || '.' || quote_ident(sequencename) from pg_sequences where schemaname = %s",
                                 (SCHEMA,)).fetchall():
            v, chamada = conn.execute(f"select last_value, is_called from {nome}").fetchone()
            man["sequencias"].append({"nome": nome, "valor": v, "chamada": chamada})
    conn.close()
    _put(MANIFESTO, iter([json.dumps(man, default=str).encode()]))
    print(json.dumps({"tabelas": len(man["tabelas"]), "linhas": sum(t["linhas"] for t in man["tabelas"]),
                      "bytes": sum(t["bytes"] for t in man["tabelas"]), "sequencias": len(man["sequencias"])}))  # fmt: skip


def arquivos():
    r_fd, w_fd = os.pipe()

    erro = []

    def escrever():
        try:
            with os.fdopen(w_fd, "wb") as w, tarfile.open(fileobj=w, mode="w|gz") as tar:
                tar.add(DADOS, arcname=".")
        except Exception as exc:  # noqa: BLE001
            erro.append(exc)

    th = threading.Thread(target=escrever, daemon=True)
    th.start()

    def gen():
        with os.fdopen(r_fd, "rb") as r:
            while b := r.read(1 << 20):
                yield b

    r = _put("dados.tar.gz", gen())
    th.join()
    if erro:
        raise RuntimeError(f"falha ao empacotar os arquivos: {erro[0]}")
    print(json.dumps(r))


def env():
    chaves = [c.strip() for c in os.environ["CHAVES"].split(",") if c.strip()]
    linhas = [f"{c}={os.environ[c]}" for c in chaves if os.environ.get(c)]
    r = _put("origem.env", iter([("\n".join(linhas) + "\n").encode()]))
    print(json.dumps({"variaveis": [ln.split("=", 1)[0] for ln in linhas], "bytes": r["bytes"]}))


if __name__ == "__main__":
    {"medir": medir, "banco": banco, "arquivos": arquivos, "env": env}[sys.argv[1]]()
