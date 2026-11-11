"""Central de contatos (V2.0, Fase 1): todos os contatos encontrados, uma linha por titular.

Somente leitura. A origem de cada contato (URL da evidência, trecho e data) acompanha o dado.
Contatos não se duplicam: a tabela contacts tem unicidade por (titular, tipo, valor normalizado).
"""

import csv
import io
import re
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from psycopg.types.json import Jsonb

from app import db
from app.auth import User, current_user

router = APIRouter(prefix="/api/contact-central", dependencies=[Depends(current_user)])

Filtro = Literal[
    "todos", "whatsapp", "wa_candidato", "wa_empresa", "wa_humano", "telefones", "emails", "sem_contatos",
    "pendentes", "invalidos", "leads_aprovados", "com_permissao", "bloqueados",
]  # fmt: skip

FILTROS: dict[str, str] = {
    "todos": "true",
    "whatsapp": "n_whatsapp > 0",
    "wa_candidato": "tem_wa_candidato",
    "wa_empresa": "tem_wa_empresa",
    "wa_humano": "tem_wa_humano",
    "telefones": "n_telefone > 0",
    "emails": "n_email > 0",
    "sem_contatos": "n_contatos = 0",
    "pendentes": "n_pendentes > 0",
    "invalidos": "n_invalidos > 0",
    "leads_aprovados": "lead_status in ('aprovado','contatado','convertido')",
    "com_permissao": "n_com_permissao > 0",
    "bloqueados": "(n_bloqueados > 0 or titular_bloqueado)",
}

ORDENS: dict[str, str] = {
    "titular": "titular",
    "pesquisa": "pesquisado_em",
    "confianca": "confianca_max",
    "score": "score",
    "contatos": "n_contatos",
}

BUSCA = """
  (%(q)s::text is null
   or titular ilike '%%' || %(q)s || '%%' or razao_social ilike '%%' || %(q)s || '%%'
   or nome_fantasia ilike '%%' || %(q)s || '%%' or marcas ilike '%%' || %(q)s || '%%'
   or (%(dig)s::text is not null and (cnpj like %(dig)s || '%%' or processos like '%%' || %(dig)s || '%%')))
"""


def _busca(q: str | None) -> dict:
    q = (q or "").strip() or None
    dig = re.sub(r"\D", "", q) if q else ""
    # só trata como CNPJ/processo quando a busca é essencialmente numérica
    return {"q": q, "dig": dig if dig and len(dig) >= 6 and len(dig) >= len(q or "") - 5 else None}


def _order(ordenar: str, direcao: str) -> str:
    col = ORDENS.get(ordenar, "titular")
    return f"{col} {'desc' if direcao == 'desc' else 'asc'} nulls last, holder_id"


@router.get("")
def list_contacts(
    filtro: Filtro = "todos",
    q: str | None = None,
    ordenar: Literal["titular", "pesquisa", "confianca", "score", "contatos"] = "titular",
    direcao: Literal["asc", "desc"] = "asc",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    p = _busca(q) | {"l": limit, "o": offset}
    where = f"where {FILTROS[filtro]} and {BUSCA}"
    with db.get_pool().connection() as conn:
        total = conn.execute(f"select count(*) n from v_contact_central {where}", p).fetchone()["n"]
        rows = conn.execute(
            f"select * from v_contact_central {where} order by {_order(ordenar, direcao)} limit %(l)s offset %(o)s", p
        ).fetchall()
    return {"total": total, "items": rows}


@router.get("/counts")
def counts() -> dict:
    """Quantos titulares há em cada filtro (para os rótulos da tela)."""
    cols = ", ".join(f"count(*) filter (where {cond}) as {nome}" for nome, cond in FILTROS.items())
    with db.get_pool().connection() as conn:
        return conn.execute(f"select {cols} from v_contact_central").fetchone()


TIPOS_EXPORT = ["whatsapp", "telefone", "email", "site", "instagram", "linkedin"]
WA_NIVEL_PT = {
    "found": "encontrado",
    "candidate": "candidato (celular, sem prova de WhatsApp)",
    "company_evidence": "evidência empresarial",
    "human_confirmed": "confirmado por pessoa",
    "invalid": "inválido",
}
EXPORT_COLS = (
    ["titular", "razao_social", "nome_fantasia", "cnpj", "uf", "marcas", "processos", "lead_status"]
    + [f"{t}{s}" for t in TIPOS_EXPORT for s in ("", "_status", "_confianca", "_origem")]
    + ["whatsapp_nivel", "whatsapp_autorizado", "bloqueado", "outros_contatos", "data_pesquisa"]
)


def _fonte(c: dict) -> str:
    url = c.get("fonte_url") or ""
    return (
        url
        if url.startswith("http")
        else {"receita": "Receita Federal (CNPJ)", "manual": "Cadastro manual"}.get(c.get("fonte_tipo") or "", url)
    )


def export_row(r: dict) -> dict:
    """Uma linha por titular: o melhor contato de cada tipo, com status, confiança e origem."""
    out = {k: r.get(k) for k in ("titular", "razao_social", "nome_fantasia", "cnpj", "uf", "marcas", "processos", "lead_status")}
    validos = [c for c in r["contatos"] if c["verificacao"] != "invalido"]
    usados = set()
    for t in TIPOS_EXPORT:
        c = next((c for c in validos if c["tipo"] == t), None)  # já vêm ordenados do melhor para o pior
        if c:
            usados.add(c["id"])
        out[t] = c["valor"] if c else None
        out[f"{t}_status"] = c["verificacao"] if c else None
        out[f"{t}_confianca"] = c["confianca"] if c else None
        out[f"{t}_origem"] = _fonte(c) if c else None
    wa = next((c for c in validos if c["tipo"] == "whatsapp"), None)
    out["whatsapp_nivel"] = WA_NIVEL_PT.get(wa["wa_nivel"]) if wa else None
    out["whatsapp_autorizado"] = ("sim" if wa["com_permissao"] else "não") if wa else None
    out["bloqueado"] = "sim" if r["titular_bloqueado"] or r["n_bloqueados"] else "não"
    out["outros_contatos"] = " | ".join(f"{c['tipo']}: {c['valor']}" for c in validos if c["id"] not in usados) or None
    out["data_pesquisa"] = r["pesquisado_em"].strftime("%d/%m/%Y") if r.get("pesquisado_em") else None
    return out


@router.get("/export")
def export_contacts(
    formato: Literal["csv", "xlsx"] = "xlsx",
    filtro: Filtro = "todos",
    q: str | None = None,
    user: User = Depends(current_user),
) -> Response:
    p = _busca(q)
    with db.transaction(user.actor) as conn:
        rows = conn.execute(
            f"select * from v_contact_central where {FILTROS[filtro]} and {BUSCA} order by titular, holder_id", p
        ).fetchall()
        conn.execute(
            "insert into exports_log (formato, filtros, linhas, criado_por) values (%s, %s, %s, %s)",
            (formato, Jsonb({"origem": "central_contatos", "filtro": filtro, "q": p["q"]}), len(rows), user.actor),
        )
    linhas = [export_row(r) for r in rows]
    nome = f"contatos_{datetime.now(UTC):%Y%m%d_%H%M}"
    if formato == "csv":
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=EXPORT_COLS, delimiter=";")
        w.writeheader()
        w.writerows(linhas)
        return Response(
            ("﻿" + buf.getvalue()).encode("utf-8"),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{nome}.csv"'},
        )
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Contatos"
    ws.append(EXPORT_COLS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for linha in linhas:
        ws.append([linha[k] for k in EXPORT_COLS])
    ws.freeze_panes = "B2"
    ws.column_dimensions["A"].width = 40
    aviso = wb.create_sheet("Leia-me")
    for texto in [
        "Central de contatos do INPI Lead Intelligence.",
        "Cada contato traz o status de validação e a origem (URL da página ou Receita Federal).",
        "WhatsApp 'candidato' é um celular sem prova de que tem WhatsApp. Telefone da Receita não é WhatsApp validado.",
        "'whatsapp_autorizado' só é 'sim' quando há consentimento registrado. Número público não é consentimento.",
        "Contatos em opt-out aparecem como bloqueados. Não use esta planilha para envio em massa.",
        f"Gerado em {datetime.now(UTC):%d/%m/%Y %H:%M} UTC por {user.actor}. Filtro: {filtro}.",
    ]:
        aviso.append([texto])
    out = io.BytesIO()
    wb.save(out)
    return Response(
        out.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nome}.xlsx"'},
    )
