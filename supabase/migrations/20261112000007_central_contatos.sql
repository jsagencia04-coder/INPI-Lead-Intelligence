-- V2.0 · Fases 1 e 2 — Central de contatos e níveis de WhatsApp em campos independentes.
-- Migration incremental: só acrescenta colunas, uma função, um gatilho e uma view. Nada é apagado.
--
-- Quatro informações que NÃO se confundem (cada uma no seu campo):
--   eh_celular     o número tem formato de celular brasileiro (fato de formato, nada mais)
--   wa_conta       existe conta de WhatsApp nesse número? Só uma pessoa confirma
--                  (não há consulta oficial e gratuita; automações não oficiais violam os termos do WhatsApp)
--   wa_comercial   é o WhatsApp comercial da empresa? (a própria empresa publica, ou uma pessoa confirma)
--   autorização    fica na tabela consents (migration 0008). Número público NÃO é consentimento.

alter table contacts
  add column eh_celular   boolean,
  add column wa_nivel     text check (wa_nivel in ('found','candidate','company_evidence','human_confirmed','invalid')),
  add column wa_conta     text not null default 'desconhecido'
                          check (wa_conta in ('desconhecido','confirmada','inexistente')),
  add column wa_comercial text not null default 'desconhecido'
                          check (wa_comercial in ('desconhecido','publicado_pela_empresa','confirmado','nao'));

comment on column contacts.wa_nivel is
  'found=número encontrado; candidate=celular válido sem prova de WhatsApp; company_evidence=a empresa publica como '
  'WhatsApp; human_confirmed=pessoa confirmou conta e vínculo; invalid=inválido/incorreto. Só para tipo=whatsapp.';

-- O nível é derivado do que o pipeline existente já grava (verificacao), para que nenhum agente precise mudar.
create or replace function contacts_wa_derive() returns trigger language plpgsql as $$
begin
  new.eh_celular := case when new.tipo in ('telefone','whatsapp')
                         then new.valor_normalizado ~ '^\+55[0-9]{2}9[0-9]{8}$' end;
  if new.tipo = 'whatsapp' then
    new.wa_nivel := case new.verificacao
      when 'invalido'          then 'invalid'
      when 'verificado_humano' then 'human_confirmed'
      when 'dominio_ok'        then 'company_evidence'
      when 'formato_ok'        then case when new.eh_celular then 'candidate' else 'found' end
      else 'found' end;
    if new.verificacao = 'verificado_humano' then
      new.wa_conta := 'confirmada';
      if new.wa_comercial = 'desconhecido' then new.wa_comercial := 'confirmado'; end if;
    elsif new.verificacao = 'dominio_ok' and new.wa_comercial = 'desconhecido' then
      new.wa_comercial := 'publicado_pela_empresa';
    end if;
  else
    new.wa_nivel := null;
  end if;
  return new;
end $$;

create trigger contacts_wa_derive before insert or update on contacts
  for each row execute function contacts_wa_derive();

-- Preenche os contatos existentes (passa pelo gatilho acima; a alteração fica na auditoria).
update contacts set eh_celular = null where tipo in ('telefone','whatsapp');

create index contacts_wa_nivel_idx on contacts (wa_nivel) where wa_nivel is not null;
