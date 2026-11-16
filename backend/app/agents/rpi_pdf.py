"""V2.9 · Leitura antecipada do PDF da RPI e conciliação PDF × XML.

    rpi.pdf           baixa o PDF do Volume I assim que aparece no índice (sem esperar o XML), lê o texto, guarda as
                      entradas de interesse comercial (com o trecho original e a página) e enfileira a qualificação
                      por estado: SC, depois RS, PR e os demais.
    rpi.pdf_importar  qualifica um lote de estado: grava processos, titulares, publicações e oportunidades pelo mesmo
                      importador do XML (origem 'pdf') e dispara a operação semanal, que monta os leads.

O XML continua sendo coletado e lido pelos agentes de sempre (rpi.collect / rpi.parse). Quando é lido, conciliar()
compara os dois e registra o que confere, o que só um deles trouxe e o que diverge. O XML oficial substitui o texto
das publicações vindas do PDF; o trecho original do PDF continua em rpi_pdf_registros. Nada é apagado.
"""

import os
import tempfile
import time
from datetime import UTC, datetime
from urllib.parse import urlparse

from psycopg.types.json import Jsonb

from app import comercial, reset, servicos
from app.config import get_settings
from app.jobs import queue
from app.jobs.registry import JobContext, PermanentError, RetryLater, handler
from app.rpi import http
from app.rpi.importer import import_processes
from app.rpi.normalize import normalize_name, parse_date_br
from app.rpi.pdf_parser import extrair_texto, ler_texto, para_processos
from app.rpi.service import store_original
from app.storage import get_storage

# Ordem de qualificação: SC primeiro, depois RS, PR e os demais (V2.6 · comercial.UF_PRIORIDADE)
LOTES = [("SC", 2), ("RS", 3), ("PR", 4), ("DEMAIS", 6)]
FONTES = ("pdf_i", "pdf_ii", "xml")


# ------------------------------------------------------------------ monitoramento por arquivo
def pdf_primeiro_ativo(conn) -> bool:
    r = conn.execute("select valor from app_config where chave = 'rpi_pdf_primeiro'").fetchone()
    return bool(r) and r["valor"].strip().lower() in ("true", "1", "sim")


def registrar_fontes(conn, edition_id: int, links: dict) -> list[str]:
    """Registra cada arquivo do índice na primeira vez em que aparece (o horário de detecção não muda depois)."""
    urls = {"xml": links.get("marcas_xml")}
    for url in links.get("marcas_pdfs") or []:
        nome = urlparse(url).path.rsplit("/", 1)[-1].upper()
        if nome.endswith("_I.PDF"):
            urls["pdf_i"] = url
        elif nome.endswith("_II.PDF"):
            urls["pdf_ii"] = url
    novas = []
    for fonte, url in urls.items():
        if not url:
            continue
        r = conn.execute(
            """insert into rpi_fontes (edition_id, fonte, url) values (%s, %s, %s)
               on conflict (edition_id, fonte) do update set url = excluded.url
                 where rpi_fontes.url is distinct from excluded.url
               returning (xmax = 0) as nova""",
            (edition_id, fonte, url),
        ).fetchone()
        if r and r["nova"]:
            novas.append(fonte)
    return novas


def atualizar_fonte(conn, edition_id: int, fonte: str, **campos) -> None:
    if not campos:
        return
    sets = ", ".join(f"{k} = %({k})s" for k in campos)
    valores = {k: Jsonb(v) if isinstance(v, dict) else v for k, v in campos.items()}
    conn.execute(
        f"update rpi_fontes set {sets}, atualizado_em = now() where edition_id = %(_ed)s and fonte = %(_f)s",
        valores | {"_ed": edition_id, "_f": fonte},
    )


def fonte(conn, edition_id: int, nome: str) -> dict | None:
    return conn.execute("select * from rpi_fontes where edition_id = %s and fonte = %s", (edition_id, nome)).fetchone()


def xml_ja_lido(conn, edition_id: int) -> bool:
    return bool(
        conn.execute(
            """select 1 from rpi_files f join rpi_editions e on e.id = f.edition_id
                where f.edition_id = %s and f.formato = 'zip' and e.status = 'parsed'
                  and exists (select 1 from publications p where p.edition_id = f.edition_id and p.fonte = 'xml')
                limit 1""",
            (edition_id,),
        ).fetchone()
        or conn.execute(
            "select 1 from rpi_fontes where edition_id = %s and fonte = 'xml' and status = 'processado'", (edition_id,)
        ).fetchone()
    )


def enfileirar_pdf(conn, ed: dict, parent_id: int | None = None) -> bool:
    """Enfileira a leitura do PDF do Volume I, se ligada, ainda não feita e o XML ainda não tiver sido lido."""
    if not pdf_primeiro_ativo(conn) or xml_ja_lido(conn, ed["id"]):
        return False
    f = fonte(conn, ed["id"], "pdf_i")
    if f is None or f["status"] in ("processado", "ignorado", "processando"):
        return False
    queue.enqueue(conn, "rpi.pdf", {"numero": ed["numero"]}, dedupe_key=f"rpi.pdf:{ed['numero']}", prioridade=3,
                  max_tentativas=8, parent_id=parent_id)  # fmt: skip
    return True


# ------------------------------------------------------------------ agentes
def _pdf_morto(conn, job: dict, erro: str) -> None:
    ed = conn.execute("select id from rpi_editions where numero = %s", (int(job["payload"]["numero"]),)).fetchone()
    if ed:
        reset.registrar_importacao(conn, int(job["payload"]["numero"]), ok=False, detalhe=f"PDF: {erro}")
        atualizar_fonte(conn, ed["id"], "pdf_i", status="erro", ultimo_erro=erro.splitlines()[0][:500], etapa=None,
                        uf_em_processamento=None)  # fmt: skip


def _lote(uf: str | None, pais: str | None) -> str:
    if pais == "BR" and uf in ("SC", "RS", "PR"):
        return uf
    return "DEMAIS"


@handler("rpi.pdf", on_dead=_pdf_morto)
def ler_pdf(conn, ctx: JobContext) -> dict:
    s = get_settings()
    if reset.importacao_bloqueada(conn):
        raise RetryLater("importações bloqueadas durante a limpeza dos dados", 120)
    numero = int(ctx.payload["numero"])
    if not comercial.dentro_do_corte(numero, s):
        return {"ignorado": f"RPI {numero} é anterior à edição mínima operacional ({comercial.edicao_minima(s)})"}
    ed = conn.execute("select * from rpi_editions where numero = %s", (numero,)).fetchone()
    if ed is None:
        raise PermanentError(f"Edição {numero} não registrada; rode rpi.discover")
    if xml_ja_lido(conn, ed["id"]):
        atualizar_fonte(conn, ed["id"], "pdf_i", status="ignorado", etapa="XML já lido: o PDF não é necessário")
        return {"ignorado": "o XML desta edição já foi lido"}
    f = fonte(conn, ed["id"], "pdf_i")
    if f is None or not f["url"]:
        raise PermanentError(f"Edição {numero} sem link do PDF do Volume I no índice")

    t0 = time.monotonic()
    atualizar_fonte(conn, ed["id"], "pdf_i", status="baixando", etapa="baixando o PDF", tentativas=f["tentativas"] + 1)
    with http.client() as c:
        r = c.get(f["url"], timeout=600)
        r.raise_for_status()  # 404 logo depois de aparecer no índice: nova tentativa com espera
        data = r.content
    if not data.startswith(b"%PDF"):
        raise RuntimeError(f"{f['url']} não retornou um PDF; nova tentativa mais tarde")
    arq = store_original(conn, get_storage(), ed, data, nome_arquivo=urlparse(f["url"]).path.rsplit("/", 1)[-1],
                         formato="pdf", source_url=f["url"], volume="I")  # fmt: skip
    t1 = time.monotonic()
    atualizar_fonte(conn, ed["id"], "pdf_i", status="processando", baixado_em=datetime.now(UTC), rpi_file_id=arq["id"],
                    tempo_download_s=round(t1 - t0, 1), processamento_inicio=datetime.now(UTC),
                    etapa="lendo o texto do PDF")  # fmt: skip

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(data)
    try:
        leitura = ler_texto(extrair_texto(tmp.name))
    finally:
        os.unlink(tmp.name)
    if leitura.edicao is not None and leitura.edicao != numero:
        raise PermanentError(f"O PDF baixado é da revista {leitura.edicao}, não da {numero}")
    if not leitura.entradas:
        raise PermanentError("Nenhuma entrada de processo encontrada no PDF (layout mudou?)")

    catalogo = conn.execute("select codigo, nome, categoria_comercial, ativo_para_leads from despacho_types").fetchall()
    codigo_por_nome, categoria = {}, {}
    for d in catalogo:
        codigo_por_nome.setdefault(d["nome"], d["codigo"])
        if d["ativo_para_leads"]:
            categoria[d["codigo"]] = d["categoria_comercial"]
    alvo = [e for e in leitura.entradas if categoria.get(codigo_por_nome.get(e.despacho_nome))]
    por_lote: dict[str, int] = {}
    for e in alvo:
        cod = codigo_por_nome[e.despacho_nome]
        tit = e.titulares
        br = next((t for t in tit if t.pais == "BR"), None)
        lote = _lote(br.uf if br else None, br.pais if br else (tit[0].pais if tit else None))
        por_lote[lote] = por_lote.get(lote, 0) + 1
        conn.execute(
            """insert into rpi_pdf_registros (edition_id, rpi_file_id, numero_processo, despacho_nome, despacho_codigo,
                                              categoria, titulares, uf, procurador, pagina, texto, campos, lote_uf)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               on conflict (edition_id, numero_processo, despacho_nome) do nothing""",
            (ed["id"], arq["id"], e.numero_processo, e.despacho_nome, cod, categoria[cod],
             Jsonb([{"nome": t.nome, "pais": t.pais, "uf": t.uf} for t in tit]), br.uf if br else None,
             e.procurador, e.pagina, e.texto, Jsonb(e.campos), lote),
        )  # fmt: skip

    if leitura.data and not ed["data_publicacao"]:
        conn.execute("update rpi_editions set data_publicacao = %s where id = %s", (parse_date_br(leitura.data), ed["id"]))
    atualizar_fonte(
        conn, ed["id"], "pdf_i", paginas=leitura.paginas, registros=len(leitura.entradas), registros_alvo=len(alvo),
        etapa="qualificando por estado (SC primeiro)",
        detalhes={"por_lote": por_lote, "nomes_de_despacho_desconhecidos": len({e.despacho_nome for e in leitura.entradas
                                                                             if e.despacho_nome not in codigo_por_nome})},
    )  # fmt: skip
    lotes = []
    for lote, prioridade in LOTES:
        if por_lote.get(lote):
            queue.enqueue(conn, "rpi.pdf_importar", {"numero": numero, "lote": lote},
                          dedupe_key=f"rpi.pdf_importar:{numero}:{lote}", prioridade=prioridade,
                          parent_id=ctx.job["id"])  # fmt: skip
            lotes.append(lote)
    if not lotes:
        _concluir_pdf(conn, ed["id"])
    return {"numero": numero, "paginas": leitura.paginas, "entradas": len(leitura.entradas), "alvo": len(alvo),
            "por_lote": por_lote, "segundos": round(time.monotonic() - t0, 1)}  # fmt: skip


def _concluir_pdf(conn, edition_id: int) -> None:
    f = fonte(conn, edition_id, "pdf_i")
    dur = None
    if f and f["processamento_inicio"]:
        dur = round((datetime.now(UTC) - f["processamento_inicio"]).total_seconds(), 1)
    atualizar_fonte(conn, edition_id, "pdf_i", status="processado", processado_em=datetime.now(UTC),
                    tempo_processamento_s=dur, etapa=None, uf_em_processamento=None)  # fmt: skip


@handler("rpi.pdf_importar", on_dead=_pdf_morto)
def importar_lote(conn, ctx: JobContext) -> dict:
    numero, lote = int(ctx.payload["numero"]), ctx.payload["lote"]
    ed = conn.execute("select * from rpi_editions where numero = %s for update", (numero,)).fetchone()
    if ed is None:
        raise PermanentError(f"Edição {numero} não registrada")
    if xml_ja_lido(conn, ed["id"]):
        _concluir_pdf(conn, ed["id"])
        return {"ignorado": "o XML desta edição já foi lido; ele é a fonte completa"}
    atualizar_fonte(conn, ed["id"], "pdf_i", uf_em_processamento=lote, etapa=f"qualificando {lote}")
    regs = conn.execute(
        "select * from rpi_pdf_registros where edition_id = %s and lote_uf = %s and importado_em is null order by id",
        (ed["id"], lote),
    ).fetchall()
    codigo_por_nome = {r["despacho_nome"]: r["despacho_codigo"] for r in regs}
    entradas = [e for r in regs for e in ler_texto(r["texto"]).entradas]
    procs = para_processos(entradas, codigo_por_nome)
    # dentro do lote: oposições antes de indeferimentos (prioridade comercial da V2.6)
    cat_por_codigo = {r["despacho_codigo"]: r["categoria"] for r in regs}
    procs.sort(key=lambda p: min(comercial.PRIORIDADE_CATEGORIA.get(cat_por_codigo.get(d.codigo), 9) for d in p.despachos))
    stats = import_processes(conn, ed["id"], numero, regs[0]["rpi_file_id"] if regs else None, procs, origem="pdf")
    conn.execute("update rpi_pdf_registros set importado_em = now() where id = any(%s)", ([r["id"] for r in regs],))

    numeros = [p.numero for p in procs]
    oportunidades = servicos.sincronizar(conn, numeros=numeros)
    analise = servicos.analisar(conn, numeros=numeros)
    if ed["status"] != "parsed":  # a edição já pode trabalhar com o que veio do PDF
        conn.execute(
            """update rpi_editions set status = 'parsed', processada_em = now(), coletada_em = coalesce(coletada_em, now()),
                      stats = %s where id = %s""",
            (Jsonb({"fonte": "pdf_i", "observacao": "leitura antecipada do PDF; o XML complementa quando sair"}), ed["id"]),
        )
    queue.enqueue(conn, "rpi.semana", {"numero": numero}, dedupe_key=f"rpi.semana:{numero}", prioridade=5,
                  parent_id=ctx.job["id"])  # fmt: skip
    pendentes = conn.execute(
        "select count(*) n from rpi_pdf_registros where edition_id = %s and importado_em is null", (ed["id"],)
    ).fetchone()["n"]
    if pendentes == 0:
        _concluir_pdf(conn, ed["id"])
    reset.registrar_importacao(conn, numero, ok=True)
    return {"numero": numero, "lote": lote, "registros": len(regs), "processos": len(procs),
            "elegiveis": stats.oportunidades_elegiveis, "descartadas": stats.oportunidades_descartadas,
            "oportunidades_servico": oportunidades, "analise": analise}  # fmt: skip


# ------------------------------------------------------------------ conciliação PDF × XML
def conciliar(conn, edition_id: int) -> dict | None:
    """Compara o que o PDF trouxe com o XML oficial da mesma edição. Idempotente."""
    regs = conn.execute(
        "select * from rpi_pdf_registros where edition_id = %s and despacho_codigo is not null", (edition_id,)
    ).fetchall()
    if not regs:
        return None
    pdf = {(r["numero_processo"], r["despacho_codigo"]): r for r in regs}
    xml = {
        (r["numero_processo"], r["despacho_codigo"]): r
        for r in conn.execute(
            """select p.numero_processo, p.despacho_codigo, p.procurador_na_publicacao
                 from publications p
                 join despacho_types d on d.codigo = p.despacho_codigo and d.ativo_para_leads
                where p.edition_id = %s and p.fonte = 'xml'""",
            (edition_id,),
        ).fetchall()
    }
    titulares = {}
    for r in conn.execute(
        """select ph.numero_processo, h.nome_normalizado, h.uf from process_holders ph join holders h on h.id = ph.holder_id
            where ph.numero_processo = any(%s)""",
        ([k[0] for k in pdf.keys() & xml.keys()],),
    ).fetchall():
        titulares.setdefault(r["numero_processo"], set()).add((r["nome_normalizado"], r["uf"] or None))

    cont = {"confere": 0, "so_pdf": 0, "so_xml": 0, "divergente": 0}
    for chave in pdf.keys() | xml.keys():
        numero, codigo = chave
        r, x = pdf.get(chave), xml.get(chave)
        dif: dict = {}
        if r and x:
            t_pdf = {(normalize_name(t["nome"]), t.get("uf") or None) for t in r["titulares"]}
            t_xml = titulares.get(numero, set())
            if t_pdf != t_xml:
                dif["titulares"] = {"pdf": sorted(map(list, t_pdf)), "xml": sorted(map(list, t_xml))}
            if bool(r["procurador"]) != bool(x["procurador_na_publicacao"]):
                dif["procurador"] = {"pdf": r["procurador"], "xml": x["procurador_na_publicacao"]}
            situacao = "divergente" if dif else "confere"
        else:
            situacao = "so_pdf" if r else "so_xml"
        cont[situacao] += 1
        novo = conn.execute(
            """insert into rpi_reconciliacao (edition_id, numero_processo, despacho_codigo, situacao, diferencas,
                                              pdf_registro_id)
               values (%s, %s, %s, %s, %s, %s)
               on conflict (edition_id, numero_processo, despacho_codigo) do update
                 set situacao = excluded.situacao, diferencas = excluded.diferencas, atualizado_em = now()
               returning (xmax = 0) as nova""",
            (edition_id, numero, codigo, situacao, Jsonb(dif), r["id"] if r else None),
        ).fetchone()
        if novo["nova"] and situacao in ("divergente", "so_pdf"):
            motivo = (
                f"RPI: o PDF e o XML divergem no processo {numero} ({codigo}): {', '.join(dif)}. Confira antes do contato."
                if situacao == "divergente"
                else f"RPI: o processo {numero} ({codigo}) foi lido no PDF mas não está no XML oficial. Confira."
            )
            conn.execute(
                "insert into review_tasks (entidade, entidade_id, motivo) values ('rpi_reconciliacao', %s, %s)",
                (f"{edition_id}:{numero}:{codigo}", motivo),
            )
    atualizar_fonte(conn, edition_id, "xml", detalhes={"conciliacao": cont})
    return cont
