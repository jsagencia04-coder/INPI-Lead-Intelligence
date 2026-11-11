"""Base CNPJ da Receita Federal (dados abertos), lida de forma econômica.

Origem: WebDAV público da Receita (Nextcloud), pastas mensais AAAA-MM com
Empresas0..9.zip e Estabelecimentos0..9.zip (CSV sem cabeçalho, ';', latin-1).
Layout (dicionário de dados oficial da Receita):

  Empresas:          0 cnpj_basico; 1 razão social; 2 natureza jurídica; 3 qualificação do
                     responsável; 4 capital social; 5 porte; 6 ente federativo
  Estabelecimentos:  0 cnpj_basico; 1 ordem; 2 dv; 3 matriz(1)/filial(2); 4 nome fantasia;
                     5 situação; 6 data situação; 7 motivo; 8 cidade exterior; 9 país;
                     10 início atividade; 11 CNAE principal; 12 CNAEs secundários;
                     13 tipo logradouro; 14 logradouro; 15 número; 16 complemento; 17 bairro;
                     18 CEP; 19 UF; 20 município; 21 DDD1; 22 telefone1; 23 DDD2; 24 telefone2;
                     25 DDD fax; 26 fax; 27 e-mail; 28 situação especial; 29 data situação especial

Em vez de importar ~60 milhões de linhas, a varredura guarda só as empresas
cujo nome normalizado coincide com algum titular pendente.
"""

import csv
import io
import re
import zipfile
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import httpx

from app.config import get_settings
from app.rpi.normalize import normalize_name, strip_accents

transport: httpx.BaseTransport | None = None  # testes

_MEI_PREFIX = re.compile(r"^\d{2}\.?\d{3}\.?\d{3}\s+")
_CPF_SUFFIX = re.compile(r"\s+\d{11}$")
csv.field_size_limit(10_000_000)


def nome_chave(nome: str) -> str:
    """Normaliza nomes de titulares e razões sociais para comparação.

    Remove o prefixo de CNPJ que a Receita coloca na razão social de MEIs
    ("12.345.678 FULANO DE TAL") e o CPF no final, quando houver.
    """
    n = _MEI_PREFIX.sub("", nome.strip())
    n = _CPF_SUFFIX.sub("", n)
    return normalize_name(n)


def _date(v: str) -> date | None:
    v = (v or "").strip()
    if len(v) == 8 and v.isdigit() and v != "00000000":
        try:
            return datetime.strptime(v, "%Y%m%d").date()
        except ValueError:
            return None
    return None


def _money(v: str):
    try:
        return float((v or "0").replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _rows(zip_path: Path) -> Iterator[list[str]]:
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            with zf.open(member) as raw:
                yield from csv.reader(io.TextIOWrapper(raw, encoding="latin-1", newline=""), delimiter=";")


def scan_empresas(files: list[Path], chaves: set[str]) -> list[dict]:
    """Empresas cujo nome normalizado está em `chaves`."""
    primeiros = {c.split(" ", 1)[0] for c in chaves if c}
    cache: dict[str, str] = {}
    out = []
    for f in files:
        for row in _rows(f):
            if len(row) < 6:
                continue
            raw = row[1].strip()
            tok = _MEI_PREFIX.sub("", raw).split(" ", 1)[0]
            t = cache.get(tok)
            if t is None:
                t = strip_accents(tok).upper().strip(".,-/")
                if len(cache) < 500_000:
                    cache[tok] = t
            if t not in primeiros:
                continue
            chave = nome_chave(raw)
            if chave in chaves:
                out.append(
                    {
                        "cnpj_basico": row[0].strip().zfill(8),
                        "razao_social": raw,
                        "nome_normalizado": chave,
                        "natureza_juridica": row[2].strip() or None,
                        "capital_social": _money(row[4]),
                        "porte": row[5].strip() or None,
                    }
                )
    return out


def scan_estabelecimentos(files: list[Path], basicos: set[str]) -> list[dict]:
    out = []
    for f in files:
        for row in _rows(f):
            if len(row) < 28 or row[0].strip().zfill(8) not in basicos:
                continue
            tel = lambda d, n: (re.sub(r"\D", "", d) + re.sub(r"\D", "", n)) or None  # noqa: E731
            out.append(
                {
                    "cnpj": row[0].strip().zfill(8) + row[1].strip().zfill(4) + row[2].strip().zfill(2),
                    "cnpj_basico": row[0].strip().zfill(8),
                    "matriz": row[3].strip() == "1",
                    "nome_fantasia": row[4].strip() or None,
                    "situacao_cadastral": row[5].strip() or None,
                    "data_situacao": _date(row[6]),
                    "data_inicio": _date(row[10]),
                    "cnae_principal": row[11].strip() or None,
                    "logradouro": " ".join(x for x in (row[13].strip(), row[14].strip()) if x) or None,
                    "numero": row[15].strip() or None,
                    "bairro": row[17].strip() or None,
                    "cep": row[18].strip() or None,
                    "uf": row[19].strip() or None,
                    "municipio_codigo": row[20].strip() or None,
                    "telefone1": tel(row[21], row[22]),
                    "telefone2": tel(row[23], row[24]),
                    "email": row[27].strip().lower() or None,
                }
            )
    return out


# ------------------------------------------------------------------ download (WebDAV)
def _client() -> httpx.Client:
    s = get_settings()
    return httpx.Client(
        auth=(s.cnpj_webdav_token, ""),
        timeout=httpx.Timeout(600, connect=60),
        follow_redirects=True,
        transport=transport,
        headers={"User-Agent": s.rpi_user_agent},
    )


def _propfind(c: httpx.Client, url: str) -> list[tuple[str, int]]:
    r = c.request("PROPFIND", url, headers={"Depth": "1"})
    r.raise_for_status()
    ns = {"d": "DAV:"}
    out = []
    for resp in ET.fromstring(r.content).findall("d:response", ns):
        href = resp.findtext("d:href", default="", namespaces=ns)
        size = resp.findtext(".//d:getcontentlength", default="0", namespaces=ns)
        out.append((href.rstrip("/").rsplit("/", 1)[-1], int(size or 0)))
    return out


def latest_month(c: httpx.Client) -> str:
    s = get_settings()
    meses = sorted(n for n, _ in _propfind(c, s.cnpj_webdav_url.rstrip("/") + "/") if re.fullmatch(r"\d{4}-\d{2}", n))
    if not meses:
        raise RuntimeError("Nenhuma pasta mensal encontrada no WebDAV da Receita")
    return meses[-1]


def ensure_files(mes: str | None = None) -> tuple[str, list[Path], list[Path]]:
    """Garante os zips do mês no cache local. Devolve (mês, empresas, estabelecimentos)."""
    s = get_settings()
    cache = Path(s.cnpj_cache_dir)
    with _client() as c:
        mes = mes or s.cnpj_mes or latest_month(c)
        pasta = cache / mes
        pasta.mkdir(parents=True, exist_ok=True)
        base = f"{s.cnpj_webdav_url.rstrip('/')}/{mes}/"
        remotos = {n: sz for n, sz in _propfind(c, base) if re.fullmatch(r"(Empresas|Estabelecimentos)\d\.zip", n)}
        if not remotos:
            raise RuntimeError(f"Mês {mes} sem arquivos Empresas/Estabelecimentos")
        for nome, tamanho in sorted(remotos.items()):
            destino = pasta / nome
            if destino.exists() and (not tamanho or destino.stat().st_size == tamanho):
                continue
            parte = destino.with_suffix(".part")
            with c.stream("GET", base + nome) as r, open(parte, "wb") as fp:
                r.raise_for_status()
                for chunk in r.iter_bytes(1 << 20):
                    fp.write(chunk)
            if tamanho and parte.stat().st_size != tamanho:
                raise RuntimeError(f"{nome}: tamanho {parte.stat().st_size} difere do esperado {tamanho}")
            parte.rename(destino)
    files = sorted(pasta.glob("*.zip"))
    return (
        mes,
        [f for f in files if f.name.startswith("Empresas")],
        [f for f in files if f.name.startswith("Estabelecimentos")],
    )
