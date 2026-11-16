"""Leitura do PDF da RPI de marcas (Marcas<N>_I.pdf), para começar a qualificar antes de o XML sair (V2.9).

O texto vem do `pdftotext -raw` (poppler). Observado na RPI 2914 (Volume I, 8.067 páginas):

    MARCAS - RPI 2914 de 10/11/2026 4725      ← cabeçalho e número da página (descartados)
    943365465 Notificação de oposição         ← número do processo (9 dígitos) + nome do despacho, igual ao do XML
    Titular: TUBARAO PRODUTOS ... LTDA [BR/PR]
    Procurador: Thais Colus Gineti
    Petições: 850260531834 de 12/10/2026
    NCL(11): 30 / Especificação: ... / Detalhes do despacho: ...   (linhas seguintes continuam o campo anterior)

O PDF não traz o código do despacho (IPAS...): o código vem do catálogo oficial pelo nome. Um nome desconhecido
fica registrado (texto original preservado), mas não vira oportunidade. Funções puras: sem banco e sem rede.
"""

import hashlib
import re
import subprocess
from dataclasses import dataclass, field

from app.rpi.xml_parser import Despacho, ProcessoRPI, Titular

_INICIO = re.compile(r"^(\d{9})(?:\s+(.+))?$")  # número do processo, com ou sem o nome do despacho na mesma linha
_PAGINA = re.compile(r"^\d{1,5}$")
_CABECALHO = re.compile(r"^MARCAS - RPI (\d+) de (\d{2}/\d{2}/\d{4})")
_ROTULO = re.compile(
    r"^(Titular|Titulares|Procurador|Petições|Petição|NCL\(\d+\)|Especificação|Detalhes do despacho|Apresentação|"
    r"Natureza|Elemento nominativo|Marca|CFE\(\d+\)|Prioridade unionista|Data de depósito|Data de concessão|"
    r"Classe nacional|Apostila|Sobrestadores|Cedente|Cessionário|Requerente)\s*:\s*(.*)$"
)
_TITULAR = re.compile(r"^(?P<nome>.+?)\s*\[(?P<pais>[A-Z]{2})(?:/(?P<uf>[A-Z]{2}))?\]\s*$")
# Um nome de despacho: linha curta, sem rótulo, logo depois do número do processo
_MAX_NOME_DESPACHO = 160


@dataclass
class EntradaPDF:
    numero_processo: str
    despacho_nome: str
    pagina: int | None
    linhas: list[str] = field(default_factory=list)
    campos: dict[str, list[str]] = field(default_factory=dict)

    @property
    def texto(self) -> str:
        return "\n".join([self.numero_processo, self.despacho_nome, *self.linhas])

    def campo(self, nome: str) -> str | None:
        v = self.campos.get(nome)
        return " ".join(v).strip() if v else None

    @property
    def titulares(self) -> list[Titular]:
        out = []
        for bruto in self.campos.get("Titular", []) + self.campos.get("Titulares", []):
            for parte in re.split(r";\s*(?=[^;]+\[[A-Z]{2}(?:/[A-Z]{2})?\])", bruto):
                m = _TITULAR.match(parte.strip())
                if m:
                    out.append(Titular(nome=m["nome"].strip(), pais=m["pais"], uf=m["uf"]))
                elif parte.strip():
                    out.append(Titular(nome=parte.strip(), pais=None, uf=None))
        return out

    @property
    def procurador(self) -> str | None:
        return self.campo("Procurador")


@dataclass
class LeituraPDF:
    edicao: int | None
    data: str | None
    paginas: int
    entradas: list[EntradaPDF]


def extrair_texto(caminho_pdf: str, timeout: int = 900) -> str:
    """Texto do PDF inteiro, em ordem de leitura (as quebras de página viram \\f)."""
    r = subprocess.run(
        ["pdftotext", "-raw", "-enc", "UTF-8", caminho_pdf, "-"],
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if r.returncode != 0:
        raise RuntimeError(f"pdftotext falhou ({r.returncode}): {r.stderr.decode(errors='replace')[:300]}")
    return r.stdout.decode("utf-8", errors="replace")


def ler_texto(texto: str) -> LeituraPDF:
    """Aceita os dois formatos do pdftotext: número e despacho na mesma linha (-raw, o usado em produção) ou em
    linhas separadas. Um número de 9 dígitos só abre uma entrada se a linha seguinte for um rótulo (Titular:,
    Procurador:...): números de processo citados no meio de um texto ("824590570 (MARCA X).") não viram entrada."""
    edicao, data = None, None
    entradas: list[EntradaPDF] = []
    atual: EntradaPDF | None = None
    cand: dict | None = None  # possível início de entrada, aguardando a confirmação pela linha seguinte
    ultimo_campo: str | None = None
    paginas = texto.count("\f") + 1

    def continuar(linha: str) -> None:
        nonlocal ultimo_campo
        if atual is None:
            return
        atual.linhas.append(linha)
        if m := _ROTULO.match(linha):
            ultimo_campo = m.group(1)
            atual.campos.setdefault(ultimo_campo, []).append(m.group(2).strip())
        elif ultimo_campo:
            atual.campos[ultimo_campo][-1] = (atual.campos[ultimo_campo][-1] + " " + linha).strip()

    def descartar_cand() -> None:
        nonlocal cand
        if cand is not None:
            for ln in cand["linhas"]:
                continuar(ln)
        cand = None

    for pagina, bloco in enumerate(texto.split("\f"), start=1):
        for bruta in bloco.split("\n"):
            linha = bruta.strip()
            if not linha:
                continue
            if m := _CABECALHO.match(linha):
                edicao = edicao or int(m.group(1))
                data = data or m.group(2)
                continue
            if _PAGINA.match(linha):
                continue
            if m := _INICIO.match(linha):
                descartar_cand()
                nome = (m.group(2) or "").strip() or None
                if nome and (_ROTULO.match(nome) or len(nome) > _MAX_NOME_DESPACHO):
                    continuar(linha)
                    continue
                cand = {"numero": m.group(1), "nome": nome, "pagina": pagina, "linhas": [linha]}
                continue
            if cand is not None:
                if cand["nome"] is None:
                    if not _ROTULO.match(linha) and len(linha) <= _MAX_NOME_DESPACHO:
                        cand["nome"] = linha
                        cand["linhas"].append(linha)
                        continue
                    descartar_cand()
                elif _ROTULO.match(linha):
                    atual = EntradaPDF(numero_processo=cand["numero"], despacho_nome=cand["nome"], pagina=cand["pagina"])
                    entradas.append(atual)
                    cand, ultimo_campo = None, None
                else:
                    descartar_cand()
            continuar(linha)
    return LeituraPDF(edicao=edicao, data=data, paginas=paginas, entradas=entradas)


def para_processos(entradas: list[EntradaPDF], codigo_por_nome: dict[str, str]) -> list[ProcessoRPI]:
    """Agrupa as entradas por processo no mesmo formato do XML, para o importador comum.
    Só entram despachos cujo nome existe no catálogo oficial."""
    por_numero: dict[str, ProcessoRPI] = {}
    for e in entradas:
        codigo = codigo_por_nome.get(e.despacho_nome)
        if not codigo:
            continue
        d = Despacho(codigo=codigo, nome=e.despacho_nome, texto_complementar=e.campo("Detalhes do despacho"))
        p = por_numero.get(e.numero_processo)
        if p is None:
            p = por_numero[e.numero_processo] = ProcessoRPI(
                numero=e.numero_processo,
                data_deposito=None,
                data_concessao=None,
                data_vigencia=None,
                despachos=[],
                titulares=e.titulares,
                marca_nome=e.campo("Elemento nominativo") or e.campo("Marca"),
                apresentacao=e.campo("Apresentação"),
                natureza=e.campo("Natureza"),
                classes_nice=re.findall(r"\b\d{1,2}\b", e.campo("NCL(11)") or "")[:1],
                nice_detalhes=[],
                classes_vienna=[],
                procurador=e.procurador,
                procurador_vazio=False,
                apostila=None,
                madri="designação" in e.despacho_nome,  # despachos de designação = Protocolo de Madri
                numero_inscricao_internacional=None,
                raw_hash=hashlib.sha256(e.texto.encode()).hexdigest(),
            )
        elif not p.procurador and e.procurador:
            p.procurador = e.procurador
        if all(x.codigo != codigo for x in p.despachos):
            p.despachos.append(d)
    return list(por_numero.values())
