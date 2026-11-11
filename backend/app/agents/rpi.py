"""Agentes 01 (RPI Collector) e 02 (RPI Parser).

    rpi.discover  lê o índice da RPI e enfileira as edições novas
    rpi.collect   baixa o XML de marcas (e os PDFs, se configurado) e guarda os originais
    rpi.parse     interpreta o XML e grava processos, titulares, despachos e oportunidades

Todos são determinísticos (sem IA) e idempotentes: rodar de novo não duplica nada.
"""

import io
import zipfile
from datetime import UTC, datetime
from urllib.parse import urlparse

from psycopg.types.json import Jsonb

from app.config import get_settings
from app.jobs import queue
from app.jobs.registry import JobContext, PermanentError, handler
from app.rpi import http
from app.rpi.importer import import_processes
from app.rpi.index import parse_index
from app.rpi.service import inspect_marcas_zip, latest_xml_file, store_original, upsert_edition
from app.rpi.xml_parser import RpiFormatError, iter_rpi
from app.storage import get_storage, sha256_of


def _filename(url: str) -> str:
    return urlparse(url).path.rsplit("/", 1)[-1]


@handler("rpi.discover")
def discover(conn, ctx: JobContext) -> dict:
    s = get_settings()
    with http.client() as c:
        r = c.get(s.rpi_index_url)
        r.raise_for_status()
    editions = parse_index(r.text)
    if not editions:
        raise RuntimeError("Nenhuma edição encontrada no índice da RPI (layout mudou?)")

    known = {row["numero"]: row["status"] for row in conn.execute("select numero, status from rpi_editions").fetchall()}
    start = ctx.payload.get("desde") or s.rpi_start_edition
    if start is None:
        start = max(known) + 1 if known else editions[0].numero  # banco vazio: só a mais recente

    # Novas a partir de `start`, mais as já detectadas que ainda não foram baixadas.
    # Edições em 'error' só voltam por ação humana (botão Reprocessar).
    novas = [
        e
        for e in editions
        if e.marcas_xml and ((e.numero >= start and e.numero not in known) or known.get(e.numero) == "detected")
    ]
    novas = sorted(novas, key=lambda e: e.numero)[: s.rpi_max_editions_per_run]
    enfileiradas = []
    for e in novas:
        upsert_edition(conn, e.numero, e.data, fonte_url=s.rpi_index_url, links=e.as_json())
        queue.enqueue(
            conn,
            "rpi.collect",
            {"numero": e.numero},
            dedupe_key=f"rpi.collect:{e.numero}",
            prioridade=50,
            parent_id=ctx.job["id"],
        )
        enfileiradas.append(e.numero)
    return {
        "ultima_no_indice": editions[0].numero,
        "edicoes_no_indice": len(editions),
        "enfileiradas": enfileiradas,
    }


def _mark_error(conn, job: dict, erro: str) -> None:
    conn.execute(
        "update rpi_editions set status = 'error', observacoes = %s where numero = %s",
        (f"{job['tipo']} #{job['id']}: {erro.splitlines()[0][:500]}", int(job["payload"]["numero"])),
    )


@handler("rpi.collect", on_dead=_mark_error)
def collect(conn, ctx: JobContext) -> dict:
    s = get_settings()
    numero = int(ctx.payload["numero"])
    ed = conn.execute("select * from rpi_editions where numero = %s for update", (numero,)).fetchone()
    if ed is None:
        raise PermanentError(f"Edição {numero} não registrada; rode rpi.discover")
    xml_url = (ed["links"] or {}).get("marcas_xml")
    if not xml_url:
        raise PermanentError(f"Edição {numero} sem link do XML de marcas no índice")

    storage = get_storage()
    conn.execute("update rpi_editions set status = 'downloading' where id = %s", (ed["id"],))
    with http.client() as c:
        r = c.get(xml_url)
        r.raise_for_status()  # 404 logo após a publicação = retry com backoff
        data = r.content
        try:
            _, numero_xml = inspect_marcas_zip(data)
        except RpiFormatError as exc:
            raise RuntimeError(f"Download inválido ({exc}); nova tentativa mais tarde") from exc
        if numero_xml != numero:
            raise PermanentError(f"O XML baixado é da revista {numero_xml}, não da {numero}")
        xml_file = store_original(conn, storage, ed, data, nome_arquivo=_filename(xml_url), formato="zip", source_url=xml_url)

        pdfs = []
        if s.rpi_download_pdf:
            for i, url in enumerate((ed["links"] or {}).get("marcas_pdfs", []), start=1):
                pr = c.get(url)
                pr.raise_for_status()
                if not pr.content.startswith(b"%PDF"):
                    raise RuntimeError(f"{url} não retornou um PDF")
                f = store_original(
                    conn,
                    storage,
                    ed,
                    pr.content,
                    nome_arquivo=_filename(url),
                    formato="pdf",
                    source_url=url,
                    volume=str(i),
                )
                pdfs.append(f["id"])

    conn.execute("update rpi_editions set status = 'downloaded', coletada_em = now() where id = %s", (ed["id"],))
    queue.enqueue(
        conn,
        "rpi.parse",
        {"numero": numero, "rpi_file_id": xml_file["id"]},
        dedupe_key=f"rpi.parse:{numero}",
        prioridade=50,
        parent_id=ctx.job["id"],
    )
    return {
        "numero": numero,
        "xml_file_id": xml_file["id"],
        "sha256": xml_file["sha256"],
        "bytes": xml_file["bytes"],
        "pdf_file_ids": pdfs,
    }


@handler("rpi.parse", on_dead=_mark_error)
def parse(conn, ctx: JobContext) -> dict:
    s = get_settings()
    numero = int(ctx.payload["numero"])
    ed = conn.execute("select * from rpi_editions where numero = %s for update", (numero,)).fetchone()
    if ed is None:
        raise PermanentError(f"Edição {numero} não registrada")
    f = (
        conn.execute("select * from rpi_files where id = %s", (ctx.payload["rpi_file_id"],)).fetchone()
        if ctx.payload.get("rpi_file_id")
        else latest_xml_file(conn, ed["id"])
    )
    if f is None or f["edition_id"] != ed["id"]:
        raise PermanentError(f"Arquivo XML da edição {numero} não encontrado")

    data = get_storage().get(f["storage_path"])
    if sha256_of(data) != f["sha256"]:
        raise PermanentError("Integridade violada: o hash do arquivo armazenado não confere")

    conn.execute("update rpi_editions set status = 'parsing' where id = %s", (ed["id"],))
    zf = zipfile.ZipFile(io.BytesIO(data))
    xml_name = next(n for n in zf.namelist() if n.lower().endswith(".xml"))
    scope = ctx.payload.get("scope") or s.rpi_import_scope
    try:
        with zf.open(xml_name) as fp:
            revista, processos = iter_rpi(fp)
            if revista.numero != numero:
                raise PermanentError(f"XML é da revista {revista.numero}, esperado {numero}")
            stats = import_processes(conn, ed["id"], numero, f["id"], processos, scope=scope)
    except RpiFormatError as exc:
        raise PermanentError(str(exc)) from exc

    resumo = stats.as_json() | {
        "escopo": scope,
        "arquivo": f["nome_arquivo"],
        "sha256": f["sha256"],
        "processado_em": datetime.now(UTC).isoformat(),
    }
    if stats.processos_no_xml == 0:
        raise PermanentError("XML sem processos")
    conn.execute(
        """update rpi_editions set status = 'parsed', processada_em = now(), stats = %s,
                  data_publicacao = coalesce(data_publicacao, %s)
            where id = %s""",
        (Jsonb(resumo), revista.data, ed["id"]),
    )
    return resumo
