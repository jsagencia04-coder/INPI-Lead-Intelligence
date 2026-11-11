"""Proteção contra SSRF para todo acesso a endereços vindos de fora (sites de titulares, páginas citadas pela IA).

Regras:
  * só http/https, só portas 80 e 443, sem usuário/senha na URL;
  * o nome é resolvido e TODOS os IPs precisam ser públicos (nada de loopback, rede privada,
    link-local/metadados de nuvem, CGNAT, multicast ou reservado);
  * redirecionamentos são seguidos manualmente, no máximo 5, e cada salto passa pelas mesmas regras;
  * domínios reservados para exemplos (RFC 2606/6761) são recusados;
  * a resposta é limitada em tamanho.

Risco residual: DNS rebinding (o nome pode resolver para outro IP entre a checagem e a conexão).
"""

import ipaddress
import re
import socket
from urllib.parse import urljoin, urlparse

import httpx

MAX_REDIRECTS = 5
MAX_BYTES = 3_000_000
_RESERVADO = re.compile(
    r"(^|\.)(example\.(com|net|org)|exemplo\.com(\.br)?|localhost)$|\.(invalid|test|example|localhost|local|internal|lan)$"
)


class Bloqueado(httpx.HTTPError):
    """Endereço recusado pelas regras de segurança (herda de HTTPError: quem já trata erro de rede trata este)."""


def _resolver_padrao(host: str) -> list[str]:
    return list({info[4][0] for info in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)})


resolver = _resolver_padrao  # substituível nos testes


def dominio_reservado(host: str | None) -> bool:
    h = (host or "").lower().strip(".")
    if not h or "." not in h or h.replace(".", "").isdigit():
        return True  # vazio, nome de rede interna sem ponto (ex.: "db") ou IP escrito como número
    try:
        ipaddress.ip_address(h.strip("[]"))
        return True  # IP literal nunca é contato/site legítimo de empresa
    except ValueError:
        return bool(_RESERVADO.search(h))


def ip_publico(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if isinstance(a, ipaddress.IPv6Address) and a.ipv4_mapped:
        a = a.ipv4_mapped
    return a.is_global and not a.is_multicast


def checar_url(url: str) -> str:
    """Devolve a URL se for segura; senão levanta Bloqueado com o motivo."""
    u = urlparse(url)
    if u.scheme not in ("http", "https"):
        raise Bloqueado(f"esquema não permitido: {u.scheme or '(vazio)'}")
    if u.username or u.password:
        raise Bloqueado("URL com usuário/senha")
    host = (u.hostname or "").lower()
    try:
        porta = u.port
    except ValueError as exc:
        raise Bloqueado("porta inválida") from exc
    if porta not in (None, 80, 443):
        raise Bloqueado(f"porta não permitida: {porta}")
    if dominio_reservado(host):
        raise Bloqueado(f"domínio reservado ou IP literal: {host}")
    try:
        ips = resolver(host)
    except OSError as exc:
        raise Bloqueado(f"nome não resolve: {host}") from exc
    if not ips or not all(ip_publico(ip) for ip in ips):
        raise Bloqueado(f"{host} aponta para endereço interno ou reservado")
    return url


def get(client: httpx.Client, url: str, max_bytes: int = MAX_BYTES) -> httpx.Response:
    """GET seguro. O client precisa ter follow_redirects=False (conferido aqui)."""
    if client.follow_redirects:
        raise RuntimeError("net_guard.get exige client com follow_redirects=False")
    atual = url
    for _ in range(MAX_REDIRECTS + 1):
        checar_url(atual)
        with client.stream("GET", atual) as r:
            if r.is_redirect and r.headers.get("location"):
                atual = urljoin(atual, r.headers["location"])
                continue
            partes, total = [], 0
            for bloco in r.iter_bytes():
                total += len(bloco)
                if total > max_bytes:
                    raise Bloqueado("resposta grande demais")
                partes.append(bloco)
            return httpx.Response(r.status_code, headers=_sem_codificacao(r.headers), content=b"".join(partes), request=r.request)
    raise Bloqueado("redirecionamentos demais")


def _sem_codificacao(headers: httpx.Headers) -> dict[str, str]:
    # o corpo já foi descomprimido por iter_bytes(); remover os cabeçalhos evita descompressão dupla
    return {k: v for k, v in headers.items() if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")}
