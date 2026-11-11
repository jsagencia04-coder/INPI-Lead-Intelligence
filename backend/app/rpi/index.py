"""Leitura da página de índice da RPI (https://revistas.inpi.gov.br/rpi/).

Cada linha da tabela é uma edição: número, data e os links por seção. Para
marcas, a página traz o XML (txt/RM<N>.zip) e o PDF em volumes
(pdf/Marcas<N>_I.pdf, _II.pdf...).
"""

import re
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser

from app.rpi.normalize import parse_date_br

_XML_RE = re.compile(r"/RM(\d+)\.zip$", re.I)
_PDF_RE = re.compile(r"/Marcas(\d+)(?:_([IVX]+))?\.pdf$", re.I)


@dataclass
class EditionLinks:
    numero: int
    data: date | None
    marcas_xml: str | None = None
    marcas_pdfs: list[str] = field(default_factory=list)

    def as_json(self) -> dict:
        return {"marcas_xml": self.marcas_xml, "marcas_pdfs": self.marcas_pdfs}


class _RowParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: list[dict] = []
        self._row: dict | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = {"cells": [], "links": []}
        elif tag == "td" and self._row is not None:
            self._cell = []
        elif tag == "a" and self._row is not None:
            href = dict(attrs).get("href")
            if href:
                self._row["links"].append(href.strip())

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self._row is not None and self._cell is not None:
            self._row["cells"].append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None


def parse_index(html: str) -> list[EditionLinks]:
    p = _RowParser()
    p.feed(html)
    editions: dict[int, EditionLinks] = {}
    for row in p.rows:
        cells = row["cells"]
        if len(cells) < 2 or not cells[0].isdigit():
            continue
        numero = int(cells[0])
        ed = editions.setdefault(numero, EditionLinks(numero=numero, data=parse_date_br(cells[1])))
        for href in row["links"]:
            if (m := _XML_RE.search(href)) and int(m.group(1)) == numero:
                ed.marcas_xml = href
            elif (m := _PDF_RE.search(href)) and int(m.group(1)) == numero and href not in ed.marcas_pdfs:
                ed.marcas_pdfs.append(href)
    return sorted(editions.values(), key=lambda e: e.numero, reverse=True)
