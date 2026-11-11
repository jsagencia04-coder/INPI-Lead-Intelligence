"""Cliente mínimo da Claude API (Messages), com controle de custo.

Usa httpx diretamente (sem SDK) para manter o controle de timeout, de testes e
da contabilidade de gasto. Cada chamada é registrada em llm_calls.
"""

from dataclasses import dataclass, field

import httpx

from app.config import get_settings

transport: httpx.BaseTransport | None = None  # testes


class BudgetExceeded(Exception):
    pass


class LLMNotConfigured(Exception):
    pass


@dataclass
class LLMResult:
    content: list[dict]
    stop_reason: str
    tokens_in: int = 0
    tokens_out: int = 0
    buscas: int = 0
    custo_usd: float = 0.0
    consultas: list[str] = field(default_factory=list)


def week_spend(conn) -> float:
    r = conn.execute(
        "select coalesce(sum(custo_usd), 0) as s from llm_calls where criado_em >= date_trunc('week', now())"
    ).fetchone()
    return float(r["s"])


def ensure_budget(conn, estimativa: float = 0.0):
    s = get_settings()
    gasto = week_spend(conn)
    if gasto + estimativa > s.ia_orcamento_semanal_usd:
        raise BudgetExceeded(f"Orçamento semanal de IA atingido (US$ {gasto:.2f} de {s.ia_orcamento_semanal_usd:.2f})")


def _price(modelo: str) -> tuple[float, float]:
    s = get_settings()
    if modelo == s.modelo_resumo:
        return s.preco_resumo_in, s.preco_resumo_out
    return s.preco_pesquisa_in, s.preco_pesquisa_out


def call(
    *,
    model: str,
    system: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    max_tokens: int = 2048,
    tool_choice: dict | None = None,
    max_continuations: int = 4,
) -> LLMResult:
    """Chama a API e segue `pause_turn` (busca web longa) até o fim do turno."""
    s = get_settings()
    if not s.anthropic_api_key:
        raise LLMNotConfigured("ANTHROPIC_API_KEY não configurada")
    msgs = list(messages)
    total = LLMResult(content=[], stop_reason="")
    with httpx.Client(timeout=httpx.Timeout(300, connect=30), transport=transport) as c:
        for _ in range(max_continuations + 1):
            body: dict = {"model": model, "max_tokens": max_tokens, "system": system, "messages": msgs}
            if tools:
                body["tools"] = tools
            if tool_choice:
                body["tool_choice"] = tool_choice
            r = c.post(
                s.anthropic_api_url,
                json=body,
                headers={
                    "x-api-key": s.anthropic_api_key,
                    "anthropic-version": s.anthropic_version,
                    "content-type": "application/json",
                },
            )
            if r.status_code >= 400:
                raise RuntimeError(f"Claude API {r.status_code}: {r.text[:500]}")
            data = r.json()
            u = data.get("usage", {})
            total.tokens_in += (
                u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
            )
            total.tokens_out += u.get("output_tokens", 0)
            total.buscas += (u.get("server_tool_use") or {}).get("web_search_requests", 0)
            total.content.extend(data.get("content", []))
            total.consultas += [
                b["input"].get("query", "")
                for b in data.get("content", [])
                if b.get("type") == "server_tool_use" and b.get("name") == "web_search"
            ]
            total.stop_reason = data.get("stop_reason", "")
            if total.stop_reason != "pause_turn":
                break
            msgs = msgs + [{"role": "assistant", "content": data["content"]}]
    pin, pout = _price(model)
    total.custo_usd = total.tokens_in / 1e6 * pin + total.tokens_out / 1e6 * pout + total.buscas * s.preco_busca_web
    return total


def record(conn, res: LLMResult, *, proposito: str, modelo: str, job_id: int | None, holder_id: int | None):
    conn.execute(
        """insert into llm_calls (proposito, modelo, job_id, holder_id, tokens_in, tokens_out, buscas_web, custo_usd)
           values (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (proposito, modelo, job_id, holder_id, res.tokens_in, res.tokens_out, res.buscas, res.custo_usd),
    )
