"""Aplica as migrations SQL de supabase/migrations em ordem.

Funciona tanto no Postgres local quanto no Supabase (use a connection string
do projeto). Alternativa equivalente no Supabase: `supabase db push`.

    python -m app.migrate
"""

import hashlib
import sys
from pathlib import Path

import psycopg

from app.config import get_settings

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "supabase" / "migrations"


def migrate(database_url: str, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    applied: list[str] = []
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute(
            """create table if not exists schema_migrations (
                 versao text primary key, sha256 char(64) not null,
                 aplicada_em timestamptz not null default now())"""
        )
        conn.execute("alter table schema_migrations enable row level security")
        done = {r[0]: r[1] for r in conn.execute("select versao, sha256 from schema_migrations")}
        for f in sorted(migrations_dir.glob("*.sql")):
            sql = f.read_text(encoding="utf-8")
            digest = hashlib.sha256(sql.encode()).hexdigest()
            if f.name in done:
                if done[f.name] != digest:
                    raise RuntimeError(f"Migration já aplicada foi alterada: {f.name}")
                continue
            with conn.transaction():
                conn.execute(sql)
                conn.execute(
                    "insert into schema_migrations (versao, sha256) values (%s, %s)",
                    (f.name, digest),
                )
            applied.append(f.name)
    return applied


if __name__ == "__main__":
    novas = migrate(get_settings().database_url)
    print("Aplicadas:", ", ".join(novas) if novas else "nenhuma (banco atualizado)")
    sys.exit(0)
