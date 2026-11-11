"""WhatsApp comercial: níveis de validação, candidatos e mensagem.

Não existe forma oficial e gratuita de perguntar ao WhatsApp se um número tem conta;
serviços que fazem isso violam os termos do WhatsApp. Por isso a validação é por
evidência e por confirmação humana:

  confirmado  uma pessoa abriu a conversa e confirmou (contacts.verificacao = verificado_humano)
  validado    a própria empresa publica o número como WhatsApp (link wa.me ou "WhatsApp" junto
              do número) numa página com vínculo comprovado, e o número foi reencontrado lá (dominio_ok)
  candidato   celular encontrado sem indicação de WhatsApp: precisa de confirmação
"""

import re

MARCA_WHATS = re.compile(r"wa\.me|whats\s?app|api\.whatsapp|\bwhats\b|\bzap\b|\bwpp\b", re.I)
_CELULAR_BR = re.compile(r"^\+55\d{2}9\d{8}$")
CANDIDATO_OBS = "Candidato: celular sem indicação de WhatsApp. Confirme abrindo a conversa."


def is_br_mobile(e164: str) -> bool:
    return bool(_CELULAR_BR.match(e164 or ""))


def evidencia_indica_whatsapp(trecho: str | None, url: str | None = None) -> bool:
    return bool(MARCA_WHATS.search(f"{trecho or ''} {url or ''}"))


def derive_candidates(conn, holder_id: int) -> int:
    """Celulares (de qualquer fonte) viram candidatos a WhatsApp, com a mesma evidência."""
    rows = conn.execute(
        """insert into contacts (holder_id, tipo, valor, valor_normalizado, evidence_id, fonte_tipo, verificacao,
                                 confianca, observacao)
           select c.holder_id, 'whatsapp', c.valor, c.valor_normalizado, c.evidence_id, c.fonte_tipo, 'formato_ok',
                  0.35, %s
             from contacts c
            where c.holder_id = %s and c.tipo = 'telefone' and c.verificacao <> 'invalido'
              and c.valor_normalizado ~ '^\\+55[0-9]{2}9[0-9]{8}$'
           on conflict (holder_id, tipo, valor_normalizado) do nothing
           returning id""",
        (CANDIDATO_OBS, holder_id),
    ).fetchall()
    return len(rows)


def best_whatsapp(conn, holder_id: int) -> tuple[str | None, str | None]:
    r = conn.execute(
        """select valor_normalizado,
                  case verificacao when 'verificado_humano' then 'confirmado' when 'dominio_ok' then 'validado'
                       else 'candidato' end as status
             from contacts
            where holder_id = %s and tipo = 'whatsapp' and verificacao <> 'invalido'
            order by case verificacao when 'verificado_humano' then 1 when 'dominio_ok' then 2 else 3 end,
                     confianca desc nulls last, id
            limit 1""",
        (holder_id,),
    ).fetchone()
    return (r["valor_normalizado"], r["status"]) if r else (None, None)
