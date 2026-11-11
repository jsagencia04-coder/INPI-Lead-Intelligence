"""Normalização de nomes de titulares e datas da RPI."""

import re
import unicodedata
from datetime import date, datetime

_PUNCT = re.compile(r"[^\w&]+", re.UNICODE)
_SPACES = re.compile(r"\s+")

# Marcadores que indicam pessoa jurídica (comparados sobre o nome normalizado).
_PJ_MARKERS = re.compile(
    r"\b(LTDA|LIMITADA|S ?A|EIRELI|ME|EPP|MEI|CIA|COMPANHIA|INDUSTRIA|INDUSTRIAS|COMERCIO|COMERCIAL|"
    r"ASSOCIACAO|INSTITUTO|FUNDACAO|COOPERATIVA|SOCIEDADE|CONDOMINIO|IGREJA|SINDICATO|FEDERACAO|"
    r"CONFEDERACAO|CLUBE|GRUPO|HOLDING|PARTICIPACOES|SERVICOS|EMPREENDIMENTOS|CONSULTORIA|TECNOLOGIA|"
    r"UNIVERSIDADE|FACULDADE|ESCOLA|COLEGIO|PREFEITURA|MUNICIPIO|SECRETARIA|GOVERNO|ESTADO|"
    r"LIMITED|LTD|INC|LLC|GMBH|CORP|CORPORATION|CO|AG|SAS|SRL|SPA|BV|NV|PLC|KG)\b"
)
# "A. B. AIRES DE OLIVEIRA": formato típico de firma de empresário individual (tem CNPJ).
_FIRMA_INDIVIDUAL = re.compile(r"^([A-Z]\. ?){1,3}[A-Z]")


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def normalize_name(name: str) -> str:
    """Maiúsculas, sem acentos e pontuação, espaços colapsados. Usado na chave do titular."""
    n = strip_accents(name).upper()
    n = _PUNCT.sub(" ", n)
    return _SPACES.sub(" ", n).strip()


def guess_tipo(nome_original: str) -> str:
    """'PJ' quando há marcador claro; caso contrário 'indefinido'.

    Não classificamos como PF só pela ausência de marcadores: isso será
    resolvido com a base de CNPJ (Fase 4).
    """
    if _PJ_MARKERS.search(normalize_name(nome_original)):
        return "PJ"
    if _FIRMA_INDIVIDUAL.match(strip_accents(nome_original).upper().strip()):
        return "PJ"
    return "indefinido"


def parse_date_br(value: str | None) -> date | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None
