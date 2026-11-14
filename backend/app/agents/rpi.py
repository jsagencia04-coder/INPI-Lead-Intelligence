"""Agentes 01 (RPI Collector) e 02 (RPI Parser).

    rpi.discover  lê o índice da RPI e enfileira as edições novas
    rpi.collect   baixa o XML de marcas (e os PDFs, se configurado) e guarda os originais
    rpi.parse     interpreta o XML e grava processos, titulares, despachos e oportunidades

Todos são determinísticos (sem IA) e idempotentes: rodar de novo não duplica nada.
"""

import io
import time
import zipfile
from datetime import UTC, datetime
from urllib.parse import urlparse

from psycopg.types.json import Jsonb

from app import comercial, servicos
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
    minimo = comercial.edicao_minima(s)
    start = max(start, minimo)  # V2.6: nada anterior à edição mínima entra na coleta

    # Novas a partir de `start`, mais as já detectadas que ainda não foram baixadas.
    # Edições em 'error' só voltam por ação humana (botão Reprocessar).
    novas = [
        e
        for e in editions
        if e.marcas_xml
        and e.numero >= minimo
        and ((e.numero >= start and e.numero not in known) or known.get(e.numero) == "detected")
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
        "edicao_minima": minimo,
        "enfileiradas": enfileiradas,
        "releituras": releituras_pendentes(conn),
    }


def releituras_pendentes(conn) -> list[int]:
    """Edições lidas com um catálogo de despachos diferente do atual (ex.: um código passou a gerar oportunidade
    depois da leitura) são relidas com prioridade. É o que evita a falha silenciosa da RPI 2914 (V2.6)."""
    pend = [
        r["numero"]
        for r in conn.execute(
            """select numero from rpi_editions
                where status = 'parsed' and numero >= rpi_edicao_minima()
                  and catalogo_versao is distinct from catalogo_versao() order by numero"""
        ).fetchall()
    ]
    for n in pend:
        queue.enqueue(conn, "rpi.parse", {"numero": n}, dedupe_key=f"rpi.parse:{n}", prioridade=5)
    return pend


def _mark_error(conn, job: dict, erro: str) -> None:
    conn.execute(
        "update rpi_editions set status = 'error', observacoes = %s where numero = %s",
        (f"{job['tipo']} #{job['id']}: {erro.splitlines()[0][:500]}", int(job["payload"]["numero"])),
    )


@handler("rpi.collect", on_dead=_mark_error)
def collect(conn, ctx: JobContext) -> dict:
    s = get_settings()
    numero = int(ctx.payload["numero"])
    if not comercial.dentro_do_corte(numero, s):
        return {"ignorado": f"RPI {numero} é anterior à edição mínima operacional ({comercial.edicao_minima(s)})"}
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
    if not comercial.dentro_do_corte(numero, s):
        return {"ignorado": f"RPI {numero} é anterior à edição mínima operacional ({comercial.edicao_minima(s)})"}
    inicio = time.monotonic()
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
    # V2.4: oportunidades de serviço (oposição sofrida → manifestação; indeferimento → recurso), cruzadas com o
    # histórico: processos desta edição que já eram acompanhados também são reanalisados (recurso, decisão...).
    numeros = [
        r["numero_processo"] for r in conn.execute("select numero_processo from publications where edition_id = %s", (ed["id"],))
    ]
    resumo["oportunidades_servico"] = servicos.sincronizar(conn, numeros=numeros)
    resumo["analise_processual"] = servicos.analisar(conn, numeros=numeros)
    auditoria = auditoria_da_edicao(conn, ed, f, stats, revista, round(time.monotonic() - inicio, 1))
    conn.execute(
        "update rpi_editions set stats = %s, auditoria = %s, catalogo_versao = catalogo_versao() where id = %s",
        (Jsonb(resumo), Jsonb(auditoria), ed["id"]),
    )
    # Operação semanal: monta os leads e começa por Santa Catarina, sem esperar a agenda de hora em hora.
    # Só para a edição mais recente (edições antigas, importadas para o histórico, não disparam a operação da semana).
    mais_recente = conn.execute("select max(numero) m from rpi_editions where status = 'parsed'").fetchone()["m"] == numero
    if s.rpi_operacao_semanal_auto and mais_recente:
        queue.enqueue(
            conn, "rpi.semana", {"numero": numero}, dedupe_key=f"rpi.semana:{numero}", prioridade=5, parent_id=ctx.job["id"]
        )
    elif not mais_recente:
        # Edição antiga importada depois da mais recente: os processos dela agora são acompanhados, então a edição
        # mais recente é relida (idempotente) para capturar o que veio depois (recurso, decisão, arquivamento).
        ult = conn.execute("select max(numero) m from rpi_editions where status = 'parsed'").fetchone()["m"]
        queue.enqueue(conn, "rpi.parse", {"numero": ult}, dedupe_key=f"rpi.parse:{ult}:releitura", prioridade=90)
        queue.enqueue(conn, "leads.build", {}, dedupe_key="leads.build", prioridade=80)
    return resumo


@handler("rpi.historico")
def historico(conn, ctx: JobContext) -> dict:
    """Busca as edições anteriores à mais recente (padrão: 9 semanas ≈ 60 dias), para cruzar oposições e
    indeferimentos cujo prazo ainda pode estar aberto. Idempotente: edições já importadas são ignoradas."""
    n = int(ctx.payload.get("edicoes", 9))
    ult = conn.execute("select max(numero) m from rpi_editions where status = 'parsed'").fetchone()["m"]
    if ult is None:
        return {"ignorado": "nenhuma edição processada"}
    desde = max(ult - n, comercial.edicao_minima())  # V2.6: o histórico também respeita a edição mínima
    if desde >= ult:
        return {"ignorado": f"nenhuma edição entre a mínima ({comercial.edicao_minima()}) e a {ult}"}
    queue.enqueue(conn, "rpi.discover", {"desde": desde}, dedupe_key=f"rpi.discover:historico:{desde}", prioridade=40,
                  parent_id=ctx.job["id"])  # fmt: skip
    return {"desde": desde, "ate": ult - 1}


def auditoria_da_edicao(conn, ed: dict, arquivo: dict, stats, revista, segundos: float) -> dict:
    """Relatório de execução da edição (V2.6). 'completa' só quando o XML foi lido até o fim e tudo foi gravado.
    O XML de marcas é um documento único (sem páginas): a completude é a leitura integral do arquivo, com contagem de
    processos lidos e conferência das oposições e indeferimentos gravados contra os encontrados no arquivo."""
    gravadas = conn.execute(
        """select count(*) filter (where categoria = 'oposicao_apresentada') as oposicoes,
                  count(*) filter (where categoria = 'indeferimento') as indeferimentos
             from opportunities where edition_id = %s""",
        (ed["id"],),
    ).fetchone()
    divergencias = []
    if gravadas["oposicoes"] != stats.oposicoes:
        divergencias.append(f"oposições: {stats.oposicoes} no XML, {gravadas['oposicoes']} gravadas")
    if gravadas["indeferimentos"] != stats.indeferimentos:
        divergencias.append(f"indeferimentos: {stats.indeferimentos} no XML, {gravadas['indeferimentos']} gravados")
    rep = stats.representacao
    return {
        "edicao": revista.numero,
        "data_publicacao": revista.data.isoformat() if revista.data else None,
        "arquivo": arquivo["nome_arquivo"],
        "sha256": arquivo["sha256"],
        "formato": "XML oficial de marcas (documento único, sem paginação)",
        "leitura_integral": True,
        "processos_lidos": stats.processos_no_xml,
        "processos_gravados": stats.processos_importados,
        "oposicoes_encontradas": stats.oposicoes,
        "indeferimentos_encontrados": stats.indeferimentos,
        "oposicoes_gravadas": gravadas["oposicoes"],
        "indeferimentos_gravados": gravadas["indeferimentos"],
        "com_procurador": rep.get("COM_PROCURADOR", 0),
        "sem_procurador_confirmado": rep.get("SEM_PROCURADOR_CONFIRMADO", 0),
        "representacao_desconhecida": rep.get("PROCURADOR_DESCONHECIDO", 0),
        "erros_identificacao_procurador": rep.get("ERRO_NA_IDENTIFICACAO", 0),
        "representacao_por_tipo": stats.as_json()["representacao_por_tipo"],
        "duplicidades_no_xml": stats.duplicados,
        "oportunidades_descartadas": dict(stats.motivos_descarte),
        "despachos_novos": stats.despachos_novos,
        "erros_de_extracao": divergencias,
        "tempo_segundos": segundos,
        "completa": not divergencias,
        "processado_em": datetime.now(UTC).isoformat(),
    }
