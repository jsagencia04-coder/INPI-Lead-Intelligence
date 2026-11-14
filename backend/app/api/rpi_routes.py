"""Endpoints da RPI: edições, arquivos originais, catálogo de despachos e upload manual."""

from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app import comercial, db
from app.auth import User, current_user
from app.jobs import queue
from app.rpi.service import inspect_marcas_zip, latest_xml_file, store_original, upsert_edition
from app.rpi.xml_parser import RpiFormatError
from app.storage import get_storage

router = APIRouter(prefix="/api/rpi", dependencies=[Depends(current_user)])

MAX_UPLOAD = 200 * 1024 * 1024


@router.get("/editions")
def list_editions(limit: int = Query(30, le=200)) -> list[dict]:
    with db.get_pool().connection() as conn:
        return conn.execute(
            """select e.*,
                      (select coalesce(json_agg(json_build_object(
                          'id', f.id, 'formato', f.formato, 'nome_arquivo', f.nome_arquivo, 'bytes', f.bytes,
                          'sha256', f.sha256, 'source_url', f.source_url, 'baixado_em', f.baixado_em)
                          order by f.id), '[]') from rpi_files f where f.edition_id = e.id) as arquivos
                 from rpi_editions e order by e.numero desc limit %s""",
            (limit,),
        ).fetchall()


@router.post("/discover", status_code=202)
def discover(desde: int | None = None, user: User = Depends(current_user)) -> dict:
    with db.transaction(user.actor) as conn:
        return queue.enqueue(conn, "rpi.discover", {"desde": desde} if desde else {}, dedupe_key="rpi.discover:manual")


@router.post("/editions/{numero}/collect", status_code=202)
def collect(numero: int, user: User = Depends(current_user)) -> dict:
    if not comercial.dentro_do_corte(numero):
        raise HTTPException(422, f"A RPI {numero} é anterior à edição mínima operacional ({comercial.edicao_minima()})")
    with db.transaction(user.actor) as conn:
        ed = conn.execute("select * from rpi_editions where numero = %s", (numero,)).fetchone()
        if ed is None:
            raise HTTPException(404, "Edição não registrada. Use 'Verificar novas edições' primeiro.")
        conn.execute("update rpi_editions set status = 'detected', observacoes = null where id = %s", (ed["id"],))
        return queue.enqueue(conn, "rpi.collect", {"numero": numero}, dedupe_key=f"rpi.collect:{numero}")


@router.post("/editions/{numero}/parse", status_code=202)
def reparse(numero: int, scope: Literal["alvo", "todos"] | None = None, user: User = Depends(current_user)) -> dict:
    """Reprocessa a edição a partir do arquivo original já armazenado (idempotente)."""
    if not comercial.dentro_do_corte(numero):
        raise HTTPException(422, f"A RPI {numero} é anterior à edição mínima operacional ({comercial.edicao_minima()})")
    with db.transaction(user.actor) as conn:
        ed = conn.execute("select * from rpi_editions where numero = %s", (numero,)).fetchone()
        f = latest_xml_file(conn, ed["id"]) if ed else None
        if f is None:
            raise HTTPException(409, "Edição sem arquivo XML armazenado")
        payload = {"numero": numero, "rpi_file_id": f["id"]} | ({"scope": scope} if scope else {})
        return queue.enqueue(conn, "rpi.parse", payload, dedupe_key=f"rpi.parse:{numero}")


@router.post("/upload", status_code=201)
async def upload(file: UploadFile = File(...), user: User = Depends(current_user)) -> dict:
    """Plano B: envio manual do RM<N>.zip baixado do site do INPI."""
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Arquivo maior que 200 MB")
    try:
        _, numero = inspect_marcas_zip(data)
    except RpiFormatError as exc:
        raise HTTPException(422, f"Arquivo inválido: {exc}") from exc
    if not comercial.dentro_do_corte(numero):
        raise HTTPException(422, f"A RPI {numero} é anterior à edição mínima operacional ({comercial.edicao_minima()})")
    with db.transaction(user.actor) as conn:
        ed = upsert_edition(conn, numero, None)
        f = store_original(
            conn,
            get_storage(),
            ed,
            data,
            nome_arquivo=file.filename or f"RM{numero}.zip",
            formato="zip",
            source_url=f"upload:{user.email or user.id}",
        )
        conn.execute(
            "update rpi_editions set status = 'downloaded', coletada_em = coalesce(coletada_em, now())"
            " where id = %s and status in ('detected','error')",
            (ed["id"],),
        )
        job = queue.enqueue(conn, "rpi.parse", {"numero": numero, "rpi_file_id": f["id"]}, dedupe_key=f"rpi.parse:{numero}")
    return {"numero": numero, "arquivo": f, "job": job}


@router.get("/files/{file_id}")
def download_original(file_id: int) -> Response:
    with db.get_pool().connection() as conn:
        f = conn.execute("select * from rpi_files where id = %s", (file_id,)).fetchone()
    if f is None:
        raise HTTPException(404, "Arquivo não encontrado")
    data = get_storage().get(f["storage_path"])
    media = "application/pdf" if f["formato"] == "pdf" else "application/zip"
    return Response(
        data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{f["nome_arquivo"]}"', "X-Content-SHA256": f["sha256"]},
    )


# ------------------------------------------------------------------ despachos
@router.get("/despachos")
def list_despachos() -> list[dict]:
    with db.get_pool().connection() as conn:
        return conn.execute(
            """select d.*, (select count(*) from publications p where p.despacho_codigo = d.codigo) as publicacoes
                 from despacho_types d
                order by d.ativo_para_leads desc, d.revisar desc, d.categoria_comercial, d.codigo"""
        ).fetchall()


class DespachoPatch(BaseModel):
    categoria_comercial: (
        Literal["oposicao", "exigencia", "indeferimento", "extincao_prorrogacao", "arquivamento", "outro"] | None
    ) = None
    ativo_para_leads: bool | None = None


@router.patch("/despachos/{codigo}")
def update_despacho(codigo: str, body: DespachoPatch, user: User = Depends(current_user)) -> dict:
    """Classificação humana. Vale para as próximas importações (e para reprocessamentos)."""
    with db.transaction(user.actor) as conn:
        row = conn.execute(
            """update despacho_types set
                 categoria_comercial = coalesce(%s, categoria_comercial),
                 ativo_para_leads = coalesce(%s, ativo_para_leads),
                 revisar = false, confirmado_por = %s, confirmado_em = now()
               where codigo = %s returning *""",
            (body.categoria_comercial, body.ativo_para_leads, user.actor, codigo),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Despacho não encontrado")
        conn.execute(
            """update review_tasks set status = 'resolvida', resolvido_em = now(), resolucao = %s
                where entidade = 'despacho_type' and entidade_id = %s and status = 'aberta'""",
            (f"classificado por {user.actor}", codigo),
        )
    return row
