"""Parser do XML de marcas da RPI (arquivo RM<N>.xml dentro de RM<N>.zip).

Leitura em streaming (iterparse): o XML de uma edição tem ~50 MB e ~38 mil
processos, e a memória fica constante.

Estrutura observada na RPI 2914 (10/11/2026):

    revista[numero, data]
      processo[numero, data-deposito?, data-concessao?, data-vigencia?]
        despachos/despacho[codigo, nome]
            texto-complementar?
            protocolo[numero, data, codigoServico]?   (petições)
                requerente[nome-razao-social, pais, uf?] / procurador / cedentes / cessionarios
        titulares/titular[nome-razao-social, pais, uf?]
        marca[apresentacao, natureza]/nome?
        classes-vienna/classe-vienna[codigo, edicao]
        lista-classe-nice/classe-nice[codigo]/(especificacao, status)
        classe-nacional[codigo]/especificacao, sub-classes-nacional
        dados-de-madri[numero-inscricao-internacional, data-recebimento-inpi]
        apostila, procurador, sobrestadores, prioridade-unionista

Importante: o <procurador> filho direto de <processo> é o procurador do
processo. O <procurador> dentro de <protocolo> é de quem peticionou (pode ser
um terceiro, por exemplo um oponente) e NÃO conta como procurador do titular.
"""

import hashlib
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from typing import IO

from app.rpi.normalize import parse_date_br


class RpiFormatError(Exception):
    pass


@dataclass
class Titular:
    nome: str
    pais: str | None
    uf: str | None


@dataclass
class Despacho:
    codigo: str
    nome: str | None
    texto_complementar: str | None
    protocolos: list[dict] = field(default_factory=list)


@dataclass
class ProcessoRPI:
    numero: str
    data_deposito: date | None
    data_concessao: date | None
    data_vigencia: date | None
    despachos: list[Despacho]
    titulares: list[Titular]
    marca_nome: str | None
    apresentacao: str | None
    natureza: str | None
    classes_nice: list[str]
    nice_detalhes: list[dict]
    classes_vienna: list[str]
    procurador: str | None
    procurador_vazio: bool  # <procurador> presente mas sem nome: não dá para afirmar nada (erro de identificação)
    apostila: str | None
    madri: bool
    numero_inscricao_internacional: str | None
    raw_hash: str


@dataclass
class Revista:
    numero: int
    data: date | None


def _text(el: ET.Element | None) -> str | None:
    if el is None or el.text is None:
        return None
    t = el.text.strip()
    return t or None


def _pessoa(el: ET.Element) -> dict:
    return {
        k: v
        for k, v in {
            "nome": el.get("nome-razao-social"),
            "pais": el.get("pais"),
            "uf": el.get("uf"),
        }.items()
        if v
    }


def _protocolo(el: ET.Element) -> dict:
    p: dict = {"numero": el.get("numero"), "data": el.get("data"), "servico": el.get("codigoServico")}
    if (req := el.find("requerente")) is not None:
        p["requerente"] = _pessoa(req)
    if proc := _text(el.find("procurador")):
        p["procurador"] = proc
    cedentes = [_pessoa(c) for c in el.iterfind("cedentes/cedente")]
    if cedentes:
        p["cedentes"] = cedentes
    cess = [_pessoa(c) for c in el.iterfind("cessionarios/cessionario")]
    if cess:
        p["cessionarios"] = cess
    return p


def _build(el: ET.Element) -> ProcessoRPI:
    numero = (el.get("numero") or "").strip()
    if not numero.isdigit():
        raise RpiFormatError(f"processo com número inválido: {numero!r}")

    despachos = [
        Despacho(
            codigo=(d.get("codigo") or "").strip(),
            nome=(d.get("nome") or "").strip() or None,
            texto_complementar=_text(d.find("texto-complementar")),
            protocolos=[_protocolo(p) for p in d.iterfind("protocolo")],
        )
        for d in el.iterfind("despachos/despacho")
    ]
    # O mesmo código pode aparecer duas vezes no processo (ex.: duas petições
    # deferidas). Juntamos numa entrada só, preservando todos os protocolos.
    merged: dict[str, Despacho] = {}
    for d in despachos:
        if d.codigo in merged:
            m = merged[d.codigo]
            m.protocolos.extend(d.protocolos)
            if d.texto_complementar:
                m.texto_complementar = "\n\n".join(filter(None, [m.texto_complementar, d.texto_complementar]))
        else:
            merged[d.codigo] = d
    despachos = list(merged.values())

    titulares = [
        Titular(nome=t.get("nome-razao-social", "").strip(), pais=t.get("pais"), uf=t.get("uf"))
        for t in el.iterfind("titulares/titular")
        if t.get("nome-razao-social", "").strip()
    ]
    marca = el.find("marca")
    nice_detalhes, classes_nice = [], []
    for c in el.iterfind("lista-classe-nice/classe-nice"):
        cod = (c.get("codigo") or "").strip()
        classes_nice.append(cod)
        nice_detalhes.append({"codigo": cod, "especificacao": _text(c.find("especificacao")), "status": _text(c.find("status"))})
    for c in el.iterfind("classe-nacional"):
        nice_detalhes.append({"codigo": c.get("codigo"), "tipo": "nacional", "especificacao": _text(c.find("especificacao"))})
    madri = el.find("dados-de-madri")
    el_proc = el.find("procurador")

    return ProcessoRPI(
        numero=numero,
        data_deposito=parse_date_br(el.get("data-deposito")),
        data_concessao=parse_date_br(el.get("data-concessao")),
        data_vigencia=parse_date_br(el.get("data-vigencia")),
        despachos=despachos,
        titulares=titulares,
        marca_nome=_text(marca.find("nome")) if marca is not None else None,
        apresentacao=marca.get("apresentacao") if marca is not None else None,
        natureza=marca.get("natureza") if marca is not None else None,
        classes_nice=classes_nice,
        nice_detalhes=nice_detalhes,
        classes_vienna=[v.get("codigo") for v in el.iterfind("classes-vienna/classe-vienna") if v.get("codigo")],
        procurador=_text(el_proc),  # filho direto: procurador do processo
        procurador_vazio=el_proc is not None and _text(el_proc) is None,
        apostila=_text(el.find("apostila")),
        madri=madri is not None,
        numero_inscricao_internacional=madri.get("numero-inscricao-internacional") if madri is not None else None,
        raw_hash=hashlib.sha256(ET.tostring(el, encoding="utf-8")).hexdigest(),
    )


def iter_rpi(fp: IO[bytes]) -> tuple[Revista, Iterator[ProcessoRPI]]:
    """Retorna o cabeçalho da revista e um iterador de processos."""
    events = ET.iterparse(fp, events=("start", "end"))
    try:
        _, root = next(events)
    except (ET.ParseError, StopIteration) as exc:
        raise RpiFormatError(f"XML ilegível: {exc}") from exc
    if root.tag != "revista" or not (root.get("numero") or "").isdigit():
        raise RpiFormatError(f"raiz inesperada: <{root.tag} numero={root.get('numero')!r}>")
    revista = Revista(numero=int(root.get("numero")), data=parse_date_br(root.get("data")))

    def gen() -> Iterator[ProcessoRPI]:
        depth = 0
        try:
            for ev, el in events:
                if ev == "start":
                    depth += 1
                    continue
                depth -= 1
                if el.tag == "processo" and depth == 0:
                    yield _build(el)
                    root.clear()  # libera memória dos processos já lidos
        except ET.ParseError as exc:
            raise RpiFormatError(f"XML corrompido: {exc}") from exc

    return revista, gen()
