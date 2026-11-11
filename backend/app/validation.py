"""Validação de contatos (Agente 05). Regra 4: encontrado ≠ verificado.

Níveis (contacts.verificacao):
  encontrado        apareceu numa fonte (página citada pela pesquisa ou cadastro da Receita)
  formato_ok        formato válido (e-mail sintático, telefone brasileiro válido, URL válida)
  dominio_ok        validado automaticamente: o valor foi reencontrado na página citada
                    e, no caso de e-mail, o domínio recebe e-mail (registro MX)
  verificado_humano confirmado por uma pessoa
  invalido          formato inválido, página não contém o valor, domínio sem MX...
"""

import hashlib
import re
from urllib.parse import urlparse

import httpx
import phonenumbers

from app import net_guard
from app.config import get_settings

http_transport: httpx.BaseTransport | None = None  # testes
_EMAIL = re.compile(r"^[a-z0-9._%+'-]+@[a-z0-9.-]+\.[a-z]{2,}$")


def mx_lookup(domain: str) -> bool | None:
    """True/False se o domínio tem MX; None se a consulta falhou. Substituível nos testes."""
    try:
        import dns.resolver

        return len(dns.resolver.resolve(domain, "MX", lifetime=8)) > 0
    except Exception as exc:  # noqa: BLE001
        name = type(exc).__name__
        return False if name in ("NXDOMAIN", "NoAnswer", "NoNameservers") else None


def normalize_contact(tipo: str, valor: str) -> str | None:
    v = (valor or "").strip()
    if not v:
        return None
    if tipo == "email":
        v = v.lower().removeprefix("mailto:")
        if not _EMAIL.match(v) or net_guard.dominio_reservado(v.split("@", 1)[1]):
            return None  # inclui domínios de exemplo (.invalid, .test, example.com...)
        return v
    if tipo in ("telefone", "whatsapp"):
        for tentativa in (v, com_nono_digito(v)):
            if not tentativa:
                continue
            try:
                n = phonenumbers.parse(tentativa, "BR")
            except phonenumbers.NumberParseException:
                continue
            if phonenumbers.is_valid_number(n):
                return phonenumbers.format_number(n, phonenumbers.PhoneNumberFormat.E164)
        return None
    if tipo in ("site", "instagram", "linkedin", "facebook", "tiktok", "youtube", "outro"):
        if tipo == "instagram" and v.startswith("@"):
            v = "https://www.instagram.com/" + v[1:]
        if not re.match(r"^https?://", v, re.I):
            v = "https://" + v
        u = urlparse(v)
        if not u.netloc or "." not in u.netloc:
            return None
        host = u.netloc.lower().removeprefix("www.")
        if net_guard.dominio_reservado(u.hostname):
            return None
        path = u.path.rstrip("/")
        return f"{host}{path}".lower() if tipo != "site" else host
    return v


def com_nono_digito(valor: str) -> str | None:
    """Celular no formato antigo (DDD + 8 dígitos começando em 6-9): acrescenta o 9 que a Anatel tornou obrigatório.

    A base da Receita guarda muitos celulares assim; sem isso eles seriam descartados como inválidos.
    """
    d = re.sub(r"\D", "", valor)
    if d.startswith("55") and len(d) == 12:
        d = d[2:]
    if len(d) == 10 and d[2] in "6789":
        return f"{d[:2]}9{d[2:]}"
    return None


def host_of(url_or_host: str | None) -> str | None:
    if not url_or_host:
        return None
    s = url_or_host if "://" in url_or_host else "https://" + url_or_host
    return urlparse(s).netloc.lower().removeprefix("www.") or None


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def value_in_text(tipo: str, normalizado: str, texto: str) -> bool:
    t = texto.lower()
    if tipo == "email":
        return normalizado in t
    if tipo in ("telefone", "whatsapp"):
        nacional = _digits(normalizado)[-8:]  # 8 últimos dígitos: tolera DDD/+55/formatação
        return nacional in _digits(texto)
    if tipo == "site":
        return normalizado in t.replace("www.", "")
    # redes sociais: o nome do perfil (último trecho da URL) precisa aparecer
    perfil = normalizado.rstrip("/").rsplit("/", 1)[-1]
    return bool(perfil) and perfil in t


def fetch_page(url: str) -> tuple[int, str, bytes]:
    s = get_settings()
    ua = {"User-Agent": s.rpi_user_agent}
    with httpx.Client(timeout=30, follow_redirects=False, transport=http_transport, headers=ua) as c:
        r = net_guard.get(c, url)  # proteção SSRF: IPs internos, redirecionamentos e domínios reservados
        return r.status_code, r.text if r.status_code < 400 else "", r.content


def check_contact(contact: dict, evidence: dict, site_host: str | None) -> tuple[str, dict]:
    """Calcula o novo nível de verificação. Não rebaixa decisões humanas."""
    if contact["verificacao"] in ("verificado_humano",):
        return contact["verificacao"], {}
    s = get_settings()
    tipo, norm = contact["tipo"], contact["valor_normalizado"]
    checagem: dict = {}
    if normalize_contact(tipo, contact["valor"]) is None:
        return "invalido", {"motivo": "formato inválido"}
    nivel = "formato_ok"

    na_pagina = None
    if contact["fonte_tipo"] == "web" and s.validar_buscar_pagina and evidence.get("url", "").startswith("http"):
        try:
            status, texto, raw = fetch_page(evidence["url"])
            checagem["pagina_http"] = status
            checagem["pagina_sha256"] = hashlib.sha256(raw).hexdigest()
            # site fora do ar (4xx/5xx) = não deu para conferir; só invalida se a página abriu e o valor sumiu
            na_pagina = value_in_text(tipo, norm, texto) if status < 400 else None
        except httpx.HTTPError as exc:
            checagem["pagina_erro"] = type(exc).__name__
        checagem["na_pagina"] = na_pagina
        if na_pagina is False:
            return "invalido", checagem | {"motivo": "valor não encontrado na página citada"}

    if tipo == "email":
        dominio = norm.split("@", 1)[1]
        mx = mx_lookup(dominio) if s.validar_dns_mx else None
        checagem["mx"] = mx
        if mx is False:
            return "invalido", checagem | {"motivo": "domínio do e-mail não recebe mensagens (sem MX)"}
        checagem["dominio_igual_site"] = bool(site_host and (dominio == site_host or dominio.endswith("." + site_host)))
        provedores = (
            "gmail.com",
            "hotmail.com",
            "outlook.com",
            "yahoo.com",
            "yahoo.com.br",
            "uol.com.br",
            "bol.com.br",
            "icloud.com",
            "live.com",
        )
        checagem["provedor_gratuito"] = dominio in provedores
        if mx and (na_pagina or checagem["dominio_igual_site"]):
            nivel = "dominio_ok"
    elif na_pagina:
        nivel = "dominio_ok"
    return nivel, checagem
