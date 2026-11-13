"""Provedor Evolution API (V2.5) — instância exclusiva do INPI Agent.

Contrato usado (Evolution API v2.3.7, conferido na instalação e na documentação oficial):
  GET  /instance/connectionState/{instancia}      header apikey  -> {"instance": {"instanceName", "state"}}
  GET  /instance/fetchInstances?instanceName=...  header apikey  -> [{"name", "ownerJid", "connectionStatus", ...}]
  POST /message/sendText/{instancia}              header apikey  body {"number", "text"} -> {"key": {"id", ...}, "status"}

Regras:
  * Só o backend conhece a chave (token da instância). Nunca vai para o navegador nem para log.
  * Nunca chama a Evolution em testes de descoberta: a única chamada que envia é `enviar_texto`, usada só pelo worker
    depois de todas as verificações.
  * Nenhuma repetição automática: falha de conexão = não enviado (pessoa decide); tempo esgotado ou resposta
    inválida = "reconciliar" (pode ter saído; uma pessoa confere no celular).
"""

import re
from datetime import UTC, datetime

import httpx
from psycopg.types.json import Jsonb

from app.config import Settings, get_settings

transport: httpx.BaseTransport | None = None  # testes

ESTADO = {"open": "conectado", "connecting": "conectando", "close": "desconectado", "closed": "desconectado"}


class ResultadoEnvio:
    def __init__(self, status: str, motivo: str | None = None, message_id: str | None = None, codigo: str | None = None):
        self.status, self.motivo, self.message_id, self.codigo = status, motivo, message_id, codigo


def configurada(s: Settings | None = None) -> bool:
    s = s or get_settings()
    return bool(s.evolution_base_url and s.evolution_api_key and s.evolution_instance_name)


def modo(s: Settings | None = None) -> str:
    """'real' só com provedor evolution, credenciais, envio habilitado E simulação desligada."""
    s = s or get_settings()
    if s.mensageria_provedor == "evolution" and configurada(s) and s.evolution_send_enabled and not s.evolution_simulation:
        return "real"
    return "simulacao"


def numeros_teste(s: Settings | None = None) -> set[str]:
    s = s or get_settings()
    return {n.strip() for n in s.evolution_numeros_teste.split(",") if n.strip()}


def digitos(e164: str) -> str:
    return re.sub(r"\D", "", e164 or "")


def jid_para_e164(jid: str | None) -> str | None:
    if not jid:
        return None
    d = digitos(jid.split("@", 1)[0].split(":", 1)[0])
    return f"+{d}" if d else None


def _client(s: Settings) -> httpx.Client:
    return httpx.Client(
        base_url=s.evolution_base_url.rstrip("/"),
        headers={"apikey": s.evolution_api_key or "", "Content-Type": "application/json"},
        timeout=s.evolution_timeout_segundos,
        transport=transport,
    )


def verificar_conexao(conn=None) -> dict:
    """Só leitura: estado da instância e número conectado. Não envia nada."""
    s = get_settings()
    agora = datetime.now(UTC)
    if not configurada(s):
        r = {"status": "nao_configurada", "detalhe": "Falta EVOLUTION_BASE_URL e/ou EVOLUTION_API_KEY no servidor"}
    else:
        inst = s.evolution_instance_name
        try:
            with _client(s) as c:
                resp = c.get(f"/instance/connectionState/{inst}")
                if resp.status_code in (401, 403):
                    r = {"status": "erro_autenticacao", "detalhe": f"A Evolution recusou a chave (HTTP {resp.status_code})"}
                elif resp.status_code == 404:
                    r = {"status": "instancia_inexistente", "detalhe": f"Instância '{inst}' não encontrada"}
                elif resp.status_code >= 400:
                    r = {"status": "erro", "detalhe": f"HTTP {resp.status_code}"}
                else:
                    try:
                        estado = (resp.json().get("instance") or {}).get("state")
                    except (ValueError, AttributeError):
                        estado = None
                    if estado is None:
                        r = {"status": "resposta_invalida", "detalhe": "A Evolution respondeu sem o estado da instância"}
                    else:
                        r = {"status": ESTADO.get(estado, estado), "estado_evolution": estado}
                        numero = None
                        try:
                            f = c.get("/instance/fetchInstances", params={"instanceName": inst})
                            if f.status_code == 200:
                                lst = f.json()
                                item = (lst[0] if isinstance(lst, list) and lst else lst) or {}
                                item = item.get("instance", item) if isinstance(item, dict) else {}
                                numero = jid_para_e164(item.get("ownerJid") or item.get("owner"))
                        except (httpx.HTTPError, ValueError, AttributeError):
                            pass
                        r["numero"] = numero
        except httpx.TimeoutException:
            r = {"status": "timeout", "detalhe": "A Evolution não respondeu a tempo"}
        except httpx.HTTPError as exc:
            r = {"status": "sem_conexao", "detalhe": f"Sem conexão com a Evolution ({type(exc).__name__})"}
    autorizado = s.evolution_numero_autorizado
    r["numero_autorizado"] = autorizado
    r["numero_confere"] = bool(r.get("numero") and autorizado and digitos(r["numero"]) == digitos(autorizado))
    r["verificado_em"] = agora
    if conn is not None:
        conn.execute(
            """insert into wa_contas (provedor, instancia, numero, status_conexao, verificado_em, detalhes)
               values ('evolution', %s, %s, %s, %s, %s)
               on conflict (provedor, instancia) do update set numero = coalesce(excluded.numero, wa_contas.numero),
                 status_conexao = excluded.status_conexao, verificado_em = excluded.verificado_em, detalhes = excluded.detalhes""",
            (s.evolution_instance_name, r.get("numero"), r["status"], agora,
             Jsonb({k: v for k, v in r.items() if k in ("detalhe", "estado_evolution", "numero_confere")})),
        )  # fmt: skip
    return r


def enviar_texto(numero_e164: str, texto: str) -> ResultadoEnvio:
    """Uma única tentativa. Chamado SOMENTE pelo worker, depois de todas as verificações."""
    s = get_settings()
    try:
        with _client(s) as c:
            resp = c.post(f"/message/sendText/{s.evolution_instance_name}", json={"number": digitos(numero_e164), "text": texto})
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        # o pedido não chegou à Evolution: não saiu. Nada é repetido sozinho.
        return ResultadoEnvio("falhou", f"não enviado: sem conexão com a Evolution ({type(exc).__name__})", codigo="conexao")
    except httpx.HTTPError as exc:
        return ResultadoEnvio("reconciliar", f"resultado desconhecido ({type(exc).__name__}): confira no WhatsApp antes de qualquer ação")
    if resp.status_code in (401, 403):
        return ResultadoEnvio("falhou", "não enviado: a Evolution recusou a chave", codigo=f"http_{resp.status_code}")
    if resp.status_code in (400, 404, 422):
        return ResultadoEnvio("falhou", f"não enviado: pedido recusado pela Evolution (HTTP {resp.status_code})", codigo=f"http_{resp.status_code}")
    if resp.status_code >= 500:
        return ResultadoEnvio("reconciliar", f"resultado desconhecido (HTTP {resp.status_code}): confira no WhatsApp", codigo=f"http_{resp.status_code}")
    try:
        mid = resp.json()["key"]["id"]
    except (ValueError, KeyError, TypeError):
        mid = None
    if not mid:
        return ResultadoEnvio("reconciliar", "a Evolution respondeu sem o id da mensagem: confira no WhatsApp")
    return ResultadoEnvio("aceita", None, message_id=str(mid))
