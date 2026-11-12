"""Consulta ao pePI (https://busca.inpi.gov.br/pePI), base de marcas do INPI.

Fluxo observado em 10/11/2026 (consulta anônima, sem login):
  1. GET  /servlet/LoginController?action=login         -> abre sessão anônima (cookie)
  2. POST /servlet/MarcasServletController              -> Action=searchMarca, tipoPesquisa=BY_NUM_PROC,
                                                           NumPedido=<processo>; devolve link com CodPedido
  3. GET  /servlet/MarcasServletController?Action=detail&CodPedido=<cod>

A página de detalhe tem seções "accordion" (titulares, representantes, datas,
petições, publicações). "Representante Legal" vazio = sem procurador na base do
INPI, o que é a confirmação exigida pela regra do projeto.

Captcha: o sistema NUNCA tenta resolver. Se a resposta vier sem os marcadores
esperados (bloqueio, captcha, manutenção), a verificação fica 'indisponivel' e o
lote para, para tentar mais tarde.
"""

import re
import time
from dataclasses import dataclass, field
from datetime import date
from html import unescape
from html.parser import HTMLParser

import httpx

from app.config import get_settings
from app.rpi.normalize import parse_date_br

transport: httpx.BaseTransport | None = None  # sobrescrito nos testes


class PepiBlocked(Exception):
    """Resposta inesperada (captcha, bloqueio, manutenção). Parar e tentar depois."""


@dataclass
class PepiResult:
    numero: str
    resultado: str  # ok | nao_encontrado
    fonte_url: str
    cod_pedido: str | None = None
    marca: str | None = None
    situacao: str | None = None
    apresentacao: str | None = None
    natureza: str | None = None
    titulares: list[str] = field(default_factory=list)
    procuradores: list[str] = field(default_factory=list)
    representantes_presente: bool = False
    data_deposito: date | None = None
    data_concessao: date | None = None
    data_vigencia: date | None = None
    publicacoes: list[dict] = field(default_factory=list)
    peticoes: list[dict] = field(default_factory=list)  # protocolo, data, servico, descricao, cliente
    html: bytes = b""

    @property
    def procurador_status(self) -> str:
        if self.procuradores:
            return "com_procurador"
        return "sem_confirmado" if self.representantes_presente else "desconhecido"


def _clean(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(text).replace("\xa0", " ")).strip()


class _Rows(HTMLParser):
    """Coleta linhas (<tr>) com o texto de cada célula (<td>), só do primeiro nível."""

    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._td_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "tr" and self._td_depth == 0:
            self._row = []
        elif tag == "td":
            self._td_depth += 1
            if self._td_depth == 1 and self._row is not None:
                self._cell = []

    def handle_endtag(self, tag):
        if tag == "td" and self._td_depth:
            if self._td_depth == 1 and self._row is not None and self._cell is not None:
                self._row.append(re.sub(r"\s+", " ", "".join(self._cell).replace("\xa0", " ")).strip())
                self._cell = None
            self._td_depth -= 1
        elif tag == "tr" and self._td_depth == 0 and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _section_rows(html: str, section_id: str) -> list[list[str]] | None:
    i = html.find(f'id="accordion-{section_id}"')
    if i < 0:
        return None
    j = html.find("<tbody>", i)
    k = html.find("</tbody>", j)
    if j < 0 or k < 0:
        return []
    p = _Rows()
    p.feed(html[j : k + 8])
    return p.rows


def _label(html: str, label: str) -> str | None:
    m = re.search(rf"<font class=normal>\s*{re.escape(label)}\s*</font>\s*</td>\s*<td[^>]*>(.*?)</td>", html, re.S | re.I)
    if not m:
        return None
    return _clean(m.group(1)) or None


def _secao_por_titulo(html: str, titulo: str) -> str | None:
    """Trecho HTML de uma seção "accordion" pelo título (o id numérico muda de processo para processo)."""
    m = re.search(rf'id="accordion-([\w-]+)"\s*/>\s*<label[^>]*>\s*<font class="titulo">\s*{re.escape(titulo)}', html, re.I)
    if not m:
        return None
    ini = m.end()
    fim = html.find('id="accordion-', ini)
    return html[ini : fim if fim > 0 else len(html)]


def parse_peticoes(html: str) -> list[dict]:
    """Seção "Petições": protocolo, data, código e descrição do serviço e cliente (quem peticionou).

    Na página real a linha tem tabelas aninhadas (dados do pagamento e descrição do serviço); a tabela não fecha
    o <tbody>. Por isso a leitura é por linha de primeiro nível, limitada à própria seção.
    """
    sec = _secao_por_titulo(html, "Petições")
    if sec is None:
        return []
    p = _Rows()
    p.feed(sec)
    out = []
    for row in p.rows:
        i = next((k for k, c in enumerate(row) if re.fullmatch(r"\d{12}", c)), None)
        if i is None or i + 1 >= len(row):
            continue
        data = parse_date_br(row[i + 1])
        serv_idx = next((k for k in range(i + 2, len(row)) if re.match(r"^\d{3,5}\b", row[k])), None)
        servico = descricao = cliente = None
        if serv_idx is not None:
            cel = row[serv_idx]
            servico = re.match(r"^(\d{3,5})", cel)[1]
            descricao = re.sub(rf"^{servico}\s*(Descrição do Serviço)?\s*{servico}?\s*", "", cel).strip() or None
            cliente = next((c for c in row[serv_idx + 1 :] if c and c not in ("-",)), None)
        out.append({"protocolo": row[i], "data": data, "servico": servico, "descricao": descricao, "cliente": cliente})
    return out


def parse_detail(html: str, numero: str, fonte_url: str) -> PepiResult:
    m = re.search(r'id="numeroProcesso"[^>]*value\s*=\s*"(\d+)"', html)
    if not m:
        raise PepiBlocked("página de detalhe sem o número do processo (captcha, bloqueio ou layout novo)")
    if m.group(1) != numero:
        raise PepiBlocked(f"detalhe devolveu o processo {m.group(1)}, esperado {numero}")

    r = PepiResult(numero=numero, resultado="ok", fonte_url=fonte_url)
    r.marca = _label(html, "Marca:")
    r.situacao = _label(html, "Situação:")
    r.apresentacao = _label(html, "Apresentação:")
    r.natureza = _label(html, "Natureza:")
    r.titulares = [row[1] for row in (_section_rows(html, "titulares") or []) if len(row) > 1 and row[1]]

    reps = _section_rows(html, "representantes")
    r.representantes_presente = reps is not None
    r.procuradores = [row[-1] for row in (reps or []) if row and row[-1] and row[-1] != row[0]]

    datas = _section_rows(html, "datas") or []
    if datas:
        cells = (datas[0] + ["", "", ""])[:3]
        r.data_deposito, r.data_concessao, r.data_vigencia = (parse_date_br(c) for c in cells)

    r.peticoes = parse_peticoes(html)
    for sec in re.findall(r'id="accordion-([\w-]+)"', html):
        for row in _section_rows(html, sec) or []:
            if len(row) >= 3 and re.fullmatch(r"\d{4}", row[0]) and parse_date_br(row[1]):
                r.publicacoes.append(
                    {
                        "rpi": int(row[0]),
                        "data": row[1],
                        "despacho": row[2],
                        "complemento": row[5] if len(row) > 5 and row[5] != "-" else None,
                    }
                )
    return r


class PepiClient:
    def __init__(self):
        s = get_settings()
        self.base = s.pepi_base_url.rstrip("/")
        self.intervalo = s.pepi_intervalo_segundos
        self.http = httpx.Client(headers={"User-Agent": s.rpi_user_agent}, timeout=60, follow_redirects=True, transport=transport)
        self._logged = False
        self._last = 0.0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.http.close()

    def _pause(self):
        wait = self.intervalo - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    @staticmethod
    def _text(resp: httpx.Response) -> str:
        return resp.content.decode(resp.encoding or "iso-8859-1", errors="replace")

    def login(self):
        self._pause()
        self.http.get(f"{self.base}/servlet/LoginController", params={"action": "login"}).raise_for_status()
        self._logged = True

    def consultar(self, numero: str) -> PepiResult:
        if not self._logged:
            self.login()
        self._pause()
        url = f"{self.base}/servlet/MarcasServletController"
        resp = self.http.post(
            url,
            data={
                "NumPedido": numero,
                "NumGRU": "",
                "NumProtocolo": "",
                "NumInscricaoInternacional": "",
                "botao": " pesquisar » ",
                "Action": "searchMarca",
                "tipoPesquisa": "BY_NUM_PROC",
            },
        )
        resp.raise_for_status()
        html = self._text(resp)
        m = re.search(r"Action=detail&(?:amp;)?CodPedido=(\d+)", html)
        if not m:
            if "AVISO" in html and numero in html:
                return PepiResult(numero=numero, resultado="nao_encontrado", fonte_url=url, html=resp.content)
            if "LoginController" in html and "Continuar" in html and not getattr(self, "_relogin", False):
                self._relogin = True  # sessão expirou: uma nova tentativa
                self._logged = False
                return self.consultar(numero)
            raise PepiBlocked("resultado da pesquisa sem link de detalhe (captcha, bloqueio ou layout novo)")
        self._relogin = False
        self._pause()
        detail_url = f"{url}?Action=detail&CodPedido={m.group(1)}"
        d = self.http.get(detail_url)
        d.raise_for_status()
        result = parse_detail(self._text(d), numero, detail_url)
        result.cod_pedido = m.group(1)
        result.html = d.content
        return result
