"""Agente 04 (modo gratuito) — leitura dos sites oficiais, sem buscador pago e sem IA.

    research.free_batch  escolhe titulares ainda não visitados e enfileira research.free
    research.free        descobre o site do titular, confirma o vínculo e extrai os contatos publicados

De onde vem o site:
  1. domínio do e-mail cadastrado na Receita (exceto provedores gratuitos)
  2. sites já cadastrados no lead
  3. endereços prováveis a partir do nome fantasia e das marcas (ex.: marca.com.br)

Proteções (regras 3, 4 e 5):
  * Vínculo obrigatório: alguma página do domínio precisa citar o CNPJ, a razão social
    ou o nome fantasia do titular. Para domínios "adivinhados", citar só a marca não basta.
  * Cada contato guarda URL e trecho de origem e entra como 'encontrado'; o Agente 05 valida.
  * robots.txt respeitado, pausa entre requisições e no máximo 6 páginas por domínio.
"""

import contextlib
import json
import logging
import re
import time
import unicodedata
from html import unescape
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app import net_guard
from app.cnpj.receita import nome_chave
from app.config import get_settings
from app.jobs import queue
from app.jobs.registry import JobContext, handler
from app.rpi.normalize import normalize_name
from app.validation import normalize_contact
from app.whatsapp import MARCA_WHATS

log = logging.getLogger("agent.site")
transport: httpx.BaseTransport | None = None  # testes

PROVEDORES = {
    "ymail.com",
    "proton.me",
    "me.com",
    "email.com",
    "yahoo.com.ar",
    "r7.com",
    "oi.com.br",
    "gmail.com",
    "hotmail.com",
    "outlook.com",
    "yahoo.com",
    "yahoo.com.br",
    "uol.com.br",
    "bol.com.br",
    "icloud.com",
    "live.com",
    "terra.com.br",
    "ig.com.br",
    "globo.com",
    "msn.com",
    "hotmail.com.br",
    "outlook.com.br",
    "gmail.com.br",
    "protonmail.com",
    "zipmail.com.br",
}
LINK_CONTATO = re.compile(r"contato|contact|fale|atendimento|sobre|about|quem-somos|empresa", re.I)
EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
# com DDD entre parênteses (fixo ou celular) ou celular de 9 dígitos sem parênteses ("11 98888-7777", "+55 11 9 8888 7777")
FONE_TEXTO = re.compile(r"\(\s?\d{2}\s?\)\s?9?\s?\d{4}[-.\s]?\d{4}|(?<![\d/.-])(?:\+?55\s?)?\d{2}\s?9\s?\d{4}[-.\s]?\d{4}(?![\d/-])")
LIXO_EMAIL = re.compile(r"\.(png|jpe?g|gif|webp|svg)$|sentry|wixpress|example\.|exemplo\.|seudominio|@email\.com", re.I)
SOCIAL = {
    "instagram": re.compile(r"https?://(?:www\.)?instagram\.com/([A-Za-z0-9_.]+)/?", re.I),
    "facebook": re.compile(r"https?://(?:www\.|pt-br\.|m\.)?facebook\.com/([A-Za-z0-9_.-]+)/?", re.I),
    "linkedin": re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/company/([A-Za-z0-9_-]+)/?", re.I),
    "youtube": re.compile(r"https?://(?:www\.)?youtube\.com/(@[A-Za-z0-9_.-]+|c/[A-Za-z0-9_-]+|channel/[A-Za-z0-9_-]+)", re.I),
    "tiktok": re.compile(r"https?://(?:www\.)?tiktok\.com/(@[A-Za-z0-9_.]+)", re.I),
}
SOCIAL_IGNORAR = {
    "p",
    "reel",
    "reels",
    "explore",
    "sharer",
    "sharer.php",
    "share",
    "tr",
    "plugins",
    "dialog",
    "watch",
    "intent",
    "accounts",
    "home",
    "login",
}
# links de conversa: wa.me/NUM, api|web.whatsapp.com/send?phone=NUM (com ou sem barra, + ou %2B), whatsapp://send?phone=NUM
WHATSAPP = re.compile(
    r"(?:wa\.me/|(?:api|web)\.whatsapp\.com/send/?\?(?:[^\"'\s<>]*?&(?:amp;)?)?phone=|whatsapp://send/?\?phone=)(?:\+|%2B)?(\d{10,13})",
    re.I,
)
# domínios de terceiros que aparecem no e-mail cadastral (contador, assessoria): o site não é do titular
TERCEIRO = re.compile(r"contab|contador|assessor|consultor|advoc|advog|juridic|escritorio|despachante|registr|marcas?e?patentes", re.I)
METODO = "sem IA v2"  # muda quando a busca melhora: titulares pesquisados com método antigo são refeitos


def _slug(texto: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]", "", t)


def _texto(html: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()


def _trecho(texto: str, alvo: str, raio: int = 80) -> str:
    i = texto.lower().find(alvo.lower())
    if i < 0:
        return alvo
    return texto[max(0, i - raio) : i + len(alvo) + raio].strip()


def candidate_domains(holder: dict, contatos: list[dict], fantasia: str | None, marcas: list[str]) -> list[tuple[str, str]]:
    """Lista (domínio, origem). Origem 'receita'/'cadastrado' é forte; 'provavel' exige vínculo mais rígido."""
    out: dict[str, str] = {}
    for c in contatos:
        if c["tipo"] == "email" and c["verificacao"] != "invalido":
            dom = c["valor_normalizado"].split("@", 1)[1]
            if dom not in PROVEDORES:
                out.setdefault(dom, "receita" if c["fonte_tipo"] == "receita" else "cadastrado")
        if c["tipo"] == "site" and c["verificacao"] != "invalido":
            out.setdefault(c["valor_normalizado"].split("/", 1)[0], "cadastrado")
    for nome in [fantasia, *marcas]:
        s = _slug(nome or "")
        if 4 <= len(s) <= 30:
            for tld in ("com.br", "com"):
                out.setdefault(f"{s}.{tld}", "provavel")
    return list(out.items())[:8]


def vinculo(texto: str, holder: dict, fantasia: str | None, marcas: list[str]) -> tuple[str | None, float]:
    """Que dado do titular a página cita, e a confiança correspondente."""
    digitos = re.sub(r"\D", "", texto)
    cnpj = holder.get("cnpj")
    if cnpj and (cnpj in digitos or cnpj[:8] in re.sub(r"\D", "", " ".join(re.findall(r"\d[\d./-]{9,}\d", texto)))):
        return "cnpj", 0.85
    norm = normalize_name(texto)
    if (chave := nome_chave(holder["nome_original"])) and len(chave) >= 8 and chave in norm:
        return "razao_social", 0.7
    if fantasia and len(normalize_name(fantasia)) >= 5 and normalize_name(fantasia) in norm:
        return "nome_fantasia", 0.65
    for m in marcas:
        if m and len(normalize_name(m)) >= 4 and normalize_name(m) in norm:
            return "marca", 0.55
    return None, 0.0


def extract_contacts(url: str, html: str) -> list[dict]:
    texto = _texto(html)
    achados: list[dict] = []
    for href in re.findall(r"""href\s*=\s*["']([^"']+)["']""", html, re.I):
        href = unescape(href).strip()
        if href.lower().startswith("mailto:"):
            v = href[7:].split("?", 1)[0]
            achados.append({"tipo": "email", "valor": v, "trecho": _trecho(texto, v) if v in texto else f"link {href}"})
        elif href.lower().startswith("tel:"):
            v = href[4:]
            achados.append({"tipo": "telefone", "valor": v, "trecho": f"link {href}"})
        else:
            for tipo, rx in SOCIAL.items():
                if (m := rx.match(href)) and m.group(1).strip("/").lower() not in SOCIAL_IGNORAR:
                    achados.append({"tipo": tipo, "valor": m.group(0).rstrip("/"), "trecho": f"link {href}"})
    # links de WhatsApp em qualquer lugar do HTML (href, botões flutuantes, atributos data-*, scripts de widget)
    for m in WHATSAPP.finditer(unescape(html)):
        d = m.group(1)
        d = d if d.startswith("55") and len(d) >= 12 else "55" + d
        achados.append({"tipo": "whatsapp", "valor": "+" + d, "trecho": f"link {m.group(0)[:120]}"})
    for e in EMAIL.findall(texto):
        achados.append({"tipo": "email", "valor": e, "trecho": _trecho(texto, e)})
    fim_anterior = 0
    for m in FONE_TEXTO.finditer(texto):
        f = m.group(0)
        # o rótulo precisa estar logo antes deste número (e depois do número anterior)
        perto = texto[max(fim_anterior, m.start() - 40) : m.start()]
        fim_anterior = m.end()
        tipo = "whatsapp" if MARCA_WHATS.search(perto) else "telefone"
        achados.append({"tipo": tipo, "valor": f, "trecho": _trecho(texto, f)})

    vistos, out = set(), []
    for a in achados:
        if a["tipo"] == "email" and LIXO_EMAIL.search(a["valor"]):
            continue
        norm = normalize_contact(a["tipo"], a["valor"])
        if not norm or (a["tipo"], norm) in vistos:
            continue
        vistos.add((a["tipo"], norm))
        out.append(a | {"normalizado": norm, "url": url})
    return out


class Crawler:
    def __init__(self):
        s = get_settings()
        self.ua = s.rpi_user_agent
        self.pausa = s.site_intervalo_segundos
        self.http = httpx.Client(
            timeout=httpx.Timeout(15, connect=8),
            follow_redirects=False,  # redirecionamentos são seguidos e conferidos pelo net_guard
            transport=transport,
            headers={"User-Agent": self.ua, "Accept-Language": "pt-BR,pt;q=0.9"},
        )
        self._last = 0.0

    def close(self):
        self.http.close()

    def get(self, url: str) -> httpx.Response | None:
        wait = self.pausa - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        try:
            r = net_guard.get(self.http, url)
        except httpx.HTTPError:
            return None
        ctype = r.headers.get("content-type", "")
        if r.status_code >= 400 or ("html" not in ctype and ctype):
            return None
        return r

    def robots(self, base: str) -> RobotFileParser:
        rp = RobotFileParser()
        r = None
        with contextlib.suppress(httpx.HTTPError):
            r = net_guard.get(self.http, base + "/robots.txt")
        rp.parse(r.text.splitlines() if r is not None and r.status_code == 200 else [])
        return rp

    def site(self, dominio: str, max_paginas: int = 6) -> list[tuple[str, str]]:
        """Páginas (url, html) do domínio: início + páginas de contato/sobre."""
        home = self.get(f"https://{dominio}/") or self.get(f"http://{dominio}/")
        if home is None:
            return []
        final = urlparse(str(home.url))
        base = f"{final.scheme}://{final.netloc}"
        rp = self.robots(base)
        if not rp.can_fetch(self.ua, base + "/"):
            return []
        paginas = [(str(home.url), home.text)]
        links = []
        for href in re.findall(r"""href\s*=\s*["']([^"'#]+)["']""", home.text, re.I):
            u = urljoin(base + "/", unescape(href))
            if urlparse(u).netloc == final.netloc and LINK_CONTATO.search(urlparse(u).path) and u not in links:
                links.append(u)
        for extra in ("/contato", "/fale-conosco"):
            if base + extra not in links:
                links.append(base + extra)
        for u in links:
            if len(paginas) >= max_paginas:
                break
            if not rp.can_fetch(self.ua, u):
                continue
            r = self.get(u)
            if r is not None and str(r.url) not in [p[0] for p in paginas]:
                paginas.append((str(r.url), r.text))
        return paginas


def _motivo(prova: str) -> str:
    if prova == "dominio_do_email_na_receita":
        return "que é o domínio do e-mail cadastrado pela empresa na Receita"
    return f"que cita o {prova.replace('_', ' ')} do titular"


def dominios_de_terceiros(conn, dominios: list[str]) -> set[str]:
    """Domínios de e-mail que NÃO identificam o titular: de contador/assessoria ou usados por mais de um titular."""
    fora = {d for d in dominios if TERCEIRO.search(d)}
    for d in dominios:
        if d in fora:
            continue
        n = conn.execute(
            "select count(distinct holder_id) n from contacts where tipo = 'email' and split_part(valor_normalizado, '@', 2) = %s",
            (d,),
        ).fetchone()["n"]
        if n > 1:
            fora.add(d)
    return fora


def _contexto(conn, holder_id: int) -> tuple[dict, list[dict], str | None, list[str]]:
    h = conn.execute("select * from holders where id = %s", (holder_id,)).fetchone()
    contatos = conn.execute("select * from contacts where holder_id = %s", (holder_id,)).fetchall()
    fantasia = None
    if h["cnpj"]:
        e = conn.execute("select nome_fantasia from cnpj_estabelecimentos where cnpj = %s", (h["cnpj"],)).fetchone()
        fantasia = e["nome_fantasia"] if e else None
    marcas = [
        r["marca_nome"]
        for r in conn.execute(
            """select distinct p.marca_nome from processes p join process_holders ph on ph.numero_processo = p.numero_processo
            where ph.holder_id = %s and p.marca_nome is not null""",
            (holder_id,),
        )
    ]
    return h, contatos, fantasia, marcas


@handler("research.free")
def research_free(conn, ctx: JobContext) -> dict:
    hid = int(ctx.payload["holder_id"])
    h, contatos, fantasia, marcas = _contexto(conn, hid)
    run = conn.execute(
        "insert into research_runs (holder_id, agente, modelo, job_id) values (%s, 'research.free', %s, %s) returning id",
        (hid, METODO, ctx.job["id"]),
    ).fetchone()
    dominios = candidate_domains(h, contatos, fantasia, marcas)
    terceiros = dominios_de_terceiros(conn, [d for d, o in dominios if o == "receita"])
    crawler = Crawler()
    visitados, aceitos, sem_vinculo = [], 0, []
    try:
        for dominio, origem in dominios:
            paginas = crawler.site(dominio)
            if not paginas:
                continue
            visitados.append(dominio)
            prova, conf = None, 0.0
            for _, html in paginas:
                p, c = vinculo(_texto(html), h, fantasia, marcas)
                if c > conf:
                    prova, conf = p, c
            fraco = prova in (None, "marca") and origem == "provavel"
            if prova is None and origem == "receita" and dominio not in terceiros:
                # o domínio é o do e-mail que a própria empresa cadastrou na Receita, e só ela o usa:
                # a ligação com o titular vem do cadastro oficial, mesmo que a página não cite a razão social
                prova, conf = "dominio_do_email_na_receita", 0.6
            if prova is None or fraco:
                sem_vinculo.append(dominio)
                continue
            achados = {}
            for url, html in paginas:
                for a in extract_contacts(url, html):
                    achados.setdefault((a["tipo"], a["normalizado"]), a)
            site_url = paginas[0][0]
            achados.setdefault(
                ("site", dominio),
                {
                    "tipo": "site",
                    "valor": dominio,
                    "normalizado": dominio,
                    "url": site_url,
                    "trecho": f"Site {_motivo(prova)}",
                },
            )
            for a in achados.values():
                ev = conn.execute(
                    "insert into evidences (research_run_id, url, trecho, fonte_tipo) values (%s, %s, %s, 'web') returning id",
                    (run["id"], a["url"], a["trecho"][:1000]),
                ).fetchone()
                r = conn.execute(
                    """insert into contacts (holder_id, tipo, valor, valor_normalizado, evidence_id, fonte_tipo, confianca,
                                             observacao)
                       values (%s, %s, %s, %s, %s, 'web', %s, %s)
                       on conflict (holder_id, tipo, valor_normalizado) do nothing returning id""",
                    (
                        hid,
                        a["tipo"],
                        a["valor"],
                        a["normalizado"],
                        ev["id"],
                        conf,
                        f"Encontrado no site {dominio}, {_motivo(prova)}",
                    ),
                ).fetchone()
                aceitos += 1 if r else 0
    finally:
        crawler.close()

    conn.execute(
        """update research_runs set status = 'succeeded', finalizado_em = now(), consultas = %s::jsonb, erro = %s
            where id = %s""",
        (
            json.dumps([f"site:{d}" for d, _ in dominios]),
            json.dumps({"visitados": visitados, "sem_vinculo": sem_vinculo}, ensure_ascii=False),
            run["id"],
        ),
    )
    conn.execute("update leads set pesquisado_em = coalesce(pesquisado_em, now()) where holder_id = %s", (hid,))
    if aceitos:
        queue.enqueue(
            conn, "lead.validate_contacts", {"holder_id": hid}, dedupe_key=f"lead.validate_contacts:{hid}", prioridade=70
        )
    else:
        queue.enqueue(conn, "leads.build", {}, dedupe_key="leads.build", prioridade=80)
    return {
        "holder_id": hid,
        "dominios_testados": len(dominios),
        "sites_lidos": visitados,
        "sem_vinculo": sem_vinculo,
        "contatos_novos": aceitos,
    }


@handler("research.free_batch")
def research_free_batch(conn, ctx: JobContext) -> dict:
    s = get_settings()
    rows = conn.execute(
        """select l.holder_id from leads l
            where l.status not in ('descartado') and l.mesclado_em is null
              and not exists (select 1 from research_runs r where r.holder_id = l.holder_id and r.agente = 'research.free'
                                and r.modelo = %s and r.iniciado_em > now() - make_interval(days => %s))
              and not exists (select 1 from jobs j where j.tipo = 'research.free' and j.status in ('queued','running')
                                and (j.payload->>'holder_id')::bigint = l.holder_id)
            -- primeiro quem já tem a ausência de procurador confirmada no INPI; depois quem tem e-mail com
            -- domínio próprio na Receita (é onde a busca mais acha site e WhatsApp); depois prioridade e score
            order by l.procurador_confirmado desc,
                     exists (select 1 from contacts c where c.holder_id = l.holder_id and c.tipo = 'email'
                               and c.verificacao <> 'invalido'
                               and split_part(c.valor_normalizado, '@', 2) <> all(%s)) desc,
                     case l.prioridade when 'alta' then 1 when 'media' then 2 else 3 end, l.score desc nulls last
            limit %s""",
        (METODO, s.pesquisa_refazer_dias, sorted(PROVEDORES), s.site_lote_por_execucao),
    ).fetchall()
    for r in rows:
        queue.enqueue(
            conn, "research.free", {"holder_id": r["holder_id"]}, dedupe_key=f"research.free:{r['holder_id']}", prioridade=85
        )
    return {"enfileirados": len(rows)}
