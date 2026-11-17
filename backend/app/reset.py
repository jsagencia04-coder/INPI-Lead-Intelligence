"""V2.11 · Limpeza dos dados operacionais e espera pela próxima Revista do INPI.

    CONFIRM_RESET=RESET_INPI python -m app.reset --proxima "2026-11-17 00:00:01" --edicao-minima 2915
    python -m app.reset --simular        mostra o que seria apagado e o que fica, sem apagar nada

Sem CONFIRM_RESET=RESET_INPI a limpeza é recusada. Tudo numa transação: se qualquer etapa falhar, nada é apagado.
A rotina em si está no banco (reset_operational_data, migration 20261120000020).
"""

import argparse
import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Sao_Paulo")
CONFIRMACAO = "RESET_INPI"

# Tudo o que não é operacional fica. Um teste garante que toda tabela nova seja classificada aqui.
PRESERVADAS = {
    "app_users": "usuários e permissões",
    "app_config": "configurações do sistema (atualizadas com o novo status)",
    "schema_migrations": "estrutura do banco",
    "schedules": "agendamentos (só a referência ao último job é zerada)",
    "despacho_types": "catálogo de despachos do INPI",
    "pipeline_etapas": "etapas do pipeline",
    "uf_prioridade": "prioridade dos estados",
    "feriados": "calendário de prazos",
    "wa_modelos": "modelos de mensagem",
    "wa_modelos_historico": "histórico dos modelos",
    "wa_contas": "conta/integração do WhatsApp",
    "suppression_list": "descadastros (opt-out): quem pediu para sair continua bloqueado",
    "audit_log": "trilha de auditoria",
    "cnpj_empresas": "base pública da Receita (referência para achar CNPJ/endereço)",
    "cnpj_estabelecimentos": "base pública da Receita",
    "cnpj_municipios": "base pública da Receita",
    "system_resets": "registro das próprias limpezas",
    "system_health": "histórico de saúde do sistema (TI, 14 dias)",
    "_modelos_fabrica": "cópia de fábrica dos modelos (só existe no ambiente de testes)",
}


def tabelas_operacionais(conn) -> list[str]:
    return conn.execute("select reset_tabelas_operacionais() t").fetchone()["t"]


def classificar(conn) -> dict:
    todas = {r["relname"] for r in conn.execute(
        "select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace"
        " where n.nspname = 'public' and c.relkind = 'r'").fetchall()}  # fmt: skip
    ops = set(tabelas_operacionais(conn))
    return {
        "limpar": sorted(ops & todas),
        "preservar": sorted(set(PRESERVADAS) & todas),
        "sem_classificacao": sorted(todas - ops - set(PRESERVADAS)),
        "inexistentes": sorted(ops - todas),
    }


def simular(conn) -> dict:
    c = classificar(conn)
    c["linhas_a_remover"] = {t: conn.execute(f'select count(*) n from public."{t}"').fetchone()["n"] for t in c["limpar"]}
    c["linhas_preservadas"] = {t: conn.execute(f'select count(*) n from public."{t}"').fetchone()["n"] for t in c["preservar"]}
    return c


def reset_operational_data(conn, *, proxima: datetime, edicao_minima: int, ator: str, confirmacao: str | None = None) -> dict:
    """resetOperationalData(): exige CONFIRM_RESET=RESET_INPI (ou a confirmação explícita)."""
    confirmacao = confirmacao if confirmacao is not None else os.environ.get("CONFIRM_RESET")
    if confirmacao != CONFIRMACAO:
        raise PermissionError("Limpeza recusada: defina CONFIRM_RESET=RESET_INPI")
    c = classificar(conn)
    if c["sem_classificacao"] or c["inexistentes"]:
        raise RuntimeError(f"Tabelas sem classificação ou ausentes, nada foi apagado: {c}")
    if proxima.tzinfo is None:
        proxima = proxima.replace(tzinfo=FUSO)
    return conn.execute(
        "select reset_operational_data(%s, %s, %s, %s) r", (confirmacao, ator, proxima, edicao_minima)
    ).fetchone()["r"]


def importacao_bloqueada(conn) -> bool:
    r = conn.execute("select valor from app_config where chave = 'importacao_bloqueada'").fetchone()
    return bool(r) and r["valor"] == "true"


def status_sistema(conn) -> dict:
    chaves = ("system_status", "last_publication_id", "last_successful_import", "last_import_status",
              "next_scheduled_run", "timezone")  # fmt: skip
    cfg = {
        r["chave"]: r["valor"] for r in conn.execute("select chave, valor from app_config where chave = any(%s)", (list(chaves),))
    }
    return {k: (cfg.get(k) or None) for k in chaves}


def registrar_importacao(conn, numero: int, ok: bool, detalhe: str | None = None) -> None:
    """registerImportRun(): estado da última importação; em falha, alerta (sendFailureAlert)."""
    valores = {"last_import_status": "success" if ok else "failed"}
    if ok:
        valores |= {"system_status": "operational", "last_publication_id": str(numero),
                    "last_successful_import": datetime.now(FUSO).isoformat(timespec="seconds")}  # fmt: skip
    for k, v in valores.items():
        conn.execute(
            """insert into app_config (chave, valor) values (%s, %s)
               on conflict (chave) do update set valor = excluded.valor, atualizado_em = now()""",
            (k, v),
        )
    if not ok:
        conn.execute(
            "insert into agent_events (tipo, agente, referencia, descricao) values ('rpi.failed', 'sistema', %s, %s)",
            (f"rpi:{numero}", f"Falha na importação da RPI {numero}: {(detalhe or '')[:400]}"),
        )
        conn.execute(
            "insert into review_tasks (entidade, entidade_id, motivo) values ('rpi_importacao', %s, %s)",
            (str(numero), f"Falha na importação da RPI {numero}: {(detalhe or '')[:400]}"),
        )


def main() -> None:
    import psycopg
    from psycopg.rows import dict_row

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--simular", action="store_true")
    ap.add_argument("--proxima", default="2026-11-17 00:00:01", help="horário local de São Paulo")
    ap.add_argument("--edicao-minima", type=int, default=2915)
    a = ap.parse_args()
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
        if a.simular:
            print(json.dumps(simular(conn), ensure_ascii=False, indent=1, default=str))
            return
        proxima = datetime.fromisoformat(a.proxima).replace(tzinfo=FUSO)
        try:
            rel = reset_operational_data(conn, proxima=proxima, edicao_minima=a.edicao_minima, ator="cli:app.reset")
        except PermissionError as exc:
            sys.exit(str(exc))
        print(json.dumps(rel, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
