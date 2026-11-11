"""Operações compartilhadas entre os agentes da RPI e a API (upload manual)."""

import io
import zipfile
from datetime import date

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.rpi.xml_parser import RpiFormatError, iter_rpi
from app.storage import Storage, sha256_of


def upsert_edition(
    conn: Connection, numero: int, data: date | None, *, fonte_url: str | None = None, links: dict | None = None
) -> dict:
    return conn.execute(
        """insert into rpi_editions (numero, data_publicacao, fonte_url, links)
           values (%s, %s, %s, %s)
           on conflict (numero) do update set
             data_publicacao = coalesce(excluded.data_publicacao, rpi_editions.data_publicacao),
             fonte_url = coalesce(excluded.fonte_url, rpi_editions.fonte_url),
             links = case when excluded.links = '{}'::jsonb then rpi_editions.links else excluded.links end
           returning *""",
        (numero, data, fonte_url, Jsonb(links or {})),
    ).fetchone()


def inspect_marcas_zip(data: bytes) -> tuple[str, int]:
    """Valida o zip de marcas e devolve (nome do XML interno, número da revista)."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise RpiFormatError("arquivo não é um zip válido") from exc
    if (bad := zf.testzip()) is not None:
        raise RpiFormatError(f"zip corrompido no membro {bad}")
    xmls = [n for n in zf.namelist() if n.lower().endswith(".xml")]
    if len(xmls) != 1:
        raise RpiFormatError(f"esperado 1 XML no zip, encontrados {len(xmls)}")
    with zf.open(xmls[0]) as fp:
        revista, _ = iter_rpi(fp)
    return xmls[0], revista.numero


def store_original(
    conn: Connection,
    storage: Storage,
    edition: dict,
    data: bytes,
    *,
    nome_arquivo: str,
    formato: str,
    source_url: str,
    volume: str | None = None,
) -> dict:
    """Guarda o arquivo original (imutável) e registra em rpi_files.

    O caminho inclui o início do hash: se o INPI republicar um arquivo
    corrigido com o mesmo nome, as duas versões ficam preservadas.
    """
    digest = sha256_of(data)
    existing = conn.execute("select * from rpi_files where sha256 = %s", (digest,)).fetchone()
    if existing:
        return existing
    path = f"rpi/{edition['numero']}/{digest[:12]}_{nome_arquivo}"
    content_type = {"zip": "application/zip", "pdf": "application/pdf"}.get(formato, "application/octet-stream")
    storage.put_immutable(path, data, content_type)
    return conn.execute(
        """insert into rpi_files (edition_id, secao, volume, formato, source_url, storage_path, sha256, bytes,
                                  nome_arquivo)
           values (%s, 'marcas', %s, %s, %s, %s, %s, %s, %s) returning *""",
        (edition["id"], volume, formato, source_url, path, digest, len(data), nome_arquivo),
    ).fetchone()


def latest_xml_file(conn: Connection, edition_id: int) -> dict | None:
    return conn.execute(
        "select * from rpi_files where edition_id = %s and formato = 'zip' order by id desc limit 1",
        (edition_id,),
    ).fetchone()
