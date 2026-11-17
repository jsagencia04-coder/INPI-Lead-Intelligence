"""Consentimento e elegibilidade para envio (V2.0, Fase 8).

Encontrar um número público NÃO é consentimento. Só se envia WhatsApp quando TODAS as regras passam:
  1. contato validado (a empresa publica como WhatsApp, ou uma pessoa confirmou);
  2. o destinatário forneceu o número;
  3. há autorização comprovada e ativa para o canal WhatsApp;
  4. o contato não está na lista de supressão (opt-out);
  5. o template está aprovado pela Meta;
  6. o lead foi aprovado por uma pessoa (e, quando houver campanha, ela precisa estar autorizada).
"""

import hashlib

AVISO_VERSAO = "2026-11-v1"
FINALIDADE_PADRAO = "Contato comercial sobre o processo de marca no INPI"

PEDIDO_TEXTO = (
    "Olá. Sou {empresa}. Acompanho as publicações do INPI e vi uma publicação sobre o processo {processo}, "
    'da marca "{marca}", na Revista da Propriedade Industrial.\n\n'
    "Posso enviar informações sobre essa publicação pelo WhatsApp? Se sim, responda este e-mail com "
    '"Autorizo" e o número de WhatsApp que prefere.\n\n'
    "Se não tiver interesse, basta ignorar esta mensagem: não haverá novo contato. "
    "Seus dados foram obtidos em fontes públicas (INPI e Receita Federal) e você pode pedir a exclusão a qualquer momento."
)


def _hash(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()


def base_legal_primeiro_contato(conn) -> str:
    """V2.14: 'consentimento' (padrão) ou 'legitimo_interesse' (decisão do titular do sistema, em app_config)."""
    r = conn.execute("select valor from app_config where chave = 'primeiro_contato_base_legal'").fetchone()
    return r["valor"] if r and r["valor"] in ("consentimento", "legitimo_interesse") else "consentimento"


def elegibilidade(conn, contact_id: int, *, template: dict | None = None, primeiro_contato: bool = False) -> dict:
    """Confere cada regra para um contato. Devolve {elegivel, regras:[{regra, ok, detalhe}]}.

    primeiro_contato=True com base legal 'legitimo_interesse' (V2.14): a 1ª mensagem comercial não exige autorização
    prévia nem número fornecido pelo destinatário, desde que o WhatsApp tenha sido publicado pela própria empresa
    (ou confirmado por pessoa). Continuam valendo: opt-out, lead aprovado, uma única mensagem por contato (verificada
    no primeiro contato), limite diário e auditoria."""
    c = conn.execute(
        """select c.*, l.id as lead_id, l.status as lead_status
             from contacts c left join leads l on l.holder_id = c.holder_id and l.mesclado_em is null
            where c.id = %s""",
        (contact_id,),
    ).fetchone()
    if c is None:
        return {"elegivel": False, "regras": [{"regra": "contato", "ok": False, "detalhe": "Contato não encontrado"}]}
    k = conn.execute(
        "select * from consents where contact_id = %s and canal = 'whatsapp' and status = 'ativo' order by id desc limit 1",
        (contact_id,),
    ).fetchone()
    bloqueado = (
        conn.execute("select 1 from suppression_list where valor_hash = %s", (_hash(c["valor_normalizado"]),)).fetchone()
        is not None
    )
    validado = c["tipo"] == "whatsapp" and c["wa_nivel"] in ("company_evidence", "human_confirmed")
    legitimo = primeiro_contato and base_legal_primeiro_contato(conn) == "legitimo_interesse"
    regras = [
        {
            "regra": "contato_validado",
            "ok": validado,
            "detalhe": "WhatsApp publicado pela empresa ou confirmado por pessoa"
            if validado
            else "O WhatsApp ainda é só candidato/encontrado: confirme-o antes",
        },
        *(
            [
                {
                    "regra": "base_legal",
                    "ok": validado,
                    "detalhe": "Primeiro contato comercial (legítimo interesse): número publicado pela própria empresa"
                    if validado
                    else "Primeiro contato só para número publicado pela própria empresa ou confirmado por pessoa",
                }
            ]
            if legitimo
            else []
        ),
        *(
            []
            if legitimo
            else [
                {
                    "regra": "numero_fornecido",
                    "ok": bool(k and k["numero_fornecido"]),
                    "detalhe": "O destinatário forneceu o número"
                    if k and k["numero_fornecido"]
                    else "O número não foi fornecido pelo destinatário",
                },
                {
                    "regra": "autorizacao",
                    "ok": k is not None,
                    "detalhe": f"Autorização registrada em {k['obtido_em']:%d/%m/%Y} ({k['metodo']})"
                    if k
                    else "Sem autorização registrada",
                },
            ]
        ),
        {"regra": "sem_optout", "ok": not bloqueado, "detalhe": "Fora da lista de supressão" if not bloqueado else "Em opt-out"},
        {
            "regra": "lead_aprovado",
            "ok": c["lead_status"] in ("aprovado", "contatado", "convertido"),
            "detalhe": "Lead aprovado por uma pessoa"
            if c["lead_status"] in ("aprovado", "contatado", "convertido")
            else "O lead ainda não foi aprovado",
        },
    ]
    if template is not None:
        regras.append(
            {
                "regra": "template_aprovado",
                "ok": bool(template.get("ok")),
                "detalhe": "Template aprovado pela Meta" if template.get("ok") else f"Template: {template.get('motivo')}",
            }
        )
    return {"elegivel": all(r["ok"] for r in regras), "regras": regras, "contact_id": contact_id}
