-- V2.0 · Fase 6 — Pipeline comercial de 17 etapas, com histórico completo da jornada.
-- Incremental: acrescenta colunas, uma tabela, funções e gatilhos. O campo leads.status existente NÃO é alterado.
--
-- Etapas 1 a 10 e a 17 são AUTOMÁTICAS: derivadas de fatos gravados (contatos, autorizações, mensagens, opt-out).
-- Etapas 11 a 16 (interessado, reunião, proposta, negociação, fechado, perdido) são decisões de uma pessoa.
-- Uma etapa manual nunca é desfeita pelo sistema, exceto por opt-out, que sempre prevalece.

alter table leads
  add column pipeline_stage text not null default 'lead_novo' check (pipeline_stage in (
    'lead_novo','investigando','contato_identificado','contato_validado','aguardando_autorizacao',
    'elegivel_primeiro_contato','mensagem_programada','mensagem_enviada','mensagem_entregue','resposta_recebida',
    'interessado','reuniao','proposta_enviada','negociacao','fechado','perdido','opt_out')),
  add column pipeline_manual boolean not null default false,
  add column pipeline_desde timestamptz not null default now();
create index leads_pipeline_idx on leads (pipeline_stage) where mesclado_em is null;

create table lead_stage_history (
  id        bigserial primary key,
  lead_id   bigint not null references leads(id),
  de        text,
  para      text not null,
  origem    text not null check (origem in ('sistema','manual')),
  motivo    text,
  ator      text not null default app_actor(),
  criado_em timestamptz not null default now()
);
create index lead_stage_history_lead_idx on lead_stage_history (lead_id, id);
create trigger lead_stage_history_immutable before update or delete on lead_stage_history
  for each row execute function forbid_mutation();
alter table lead_stage_history enable row level security;

-- Etapa automática de um lead, calculada só com fatos.
create or replace function pipeline_auto(p_lead bigint) returns text language plpgsql stable as $$
declare
  l leads%rowtype;
  hk text;
begin
  select * into l from leads where id = p_lead;
  if not found then return null; end if;
  select holder_key into hk from holders where id = l.holder_id;

  if l.motivo_descarte ilike 'opt-out%'
     or exists (select 1 from suppression_list s where s.tipo = 'titular'
                 and s.valor_hash = encode(sha256(convert_to(hk, 'UTF8')), 'hex'))
     or exists (select 1 from contacts c join suppression_list s
                  on s.valor_hash = encode(sha256(convert_to(c.valor_normalizado, 'UTF8')), 'hex')
                 where c.holder_id = l.holder_id) then
    return 'opt_out';
  end if;
  if l.status = 'convertido' then return 'fechado'; end if;
  if l.status = 'descartado' then return 'perdido'; end if;

  if exists (select 1 from wa_messages m where m.lead_id = p_lead and m.direcao = 'entrada') then
    return 'resposta_recebida';
  end if;
  if exists (select 1 from wa_messages m where m.lead_id = p_lead and m.direcao = 'saida' and m.modo = 'real'
               and (m.entregue_em is not null or m.lida_em is not null)) then
    return 'mensagem_entregue';
  end if;
  if exists (select 1 from wa_messages m where m.lead_id = p_lead and m.direcao = 'saida' and m.modo = 'real'
               and m.aceita_em is not null and m.status <> 'falhou')
     or exists (select 1 from outreach_log o where o.lead_id = p_lead) then
    return 'mensagem_enviada';   -- pela API oficial (aceita pela Meta) ou contato manual registrado por uma pessoa
  end if;
  if exists (select 1 from wa_messages m where m.lead_id = p_lead and m.direcao = 'saida' and m.modo = 'real'
               and m.status = 'na_fila') then
    return 'mensagem_programada';
  end if;

  if l.status in ('aprovado','contatado') and exists (
       select 1 from contacts c where c.holder_id = l.holder_id and c.tipo = 'whatsapp'
          and c.wa_nivel in ('company_evidence','human_confirmed')) then
    if exists (select 1 from contacts c join consents k on k.contact_id = c.id
                where c.holder_id = l.holder_id and c.tipo = 'whatsapp'
                  and c.wa_nivel in ('company_evidence','human_confirmed')
                  and k.canal = 'whatsapp' and k.status = 'ativo' and k.numero_fornecido) then
      return 'elegivel_primeiro_contato';
    end if;
    return 'aguardando_autorizacao';
  end if;

  if exists (select 1 from contacts c where c.holder_id = l.holder_id
               and c.verificacao in ('dominio_ok','verificado_humano')) then
    return 'contato_validado';
  end if;
  if exists (select 1 from contacts c where c.holder_id = l.holder_id and c.verificacao <> 'invalido') then
    return 'contato_identificado';
  end if;
  if l.pesquisado_em is not null or l.status = 'pesquisando'
     or exists (select 1 from research_runs r where r.holder_id = l.holder_id) then
    return 'investigando';
  end if;
  return 'lead_novo';
end $$;

-- Aplica a etapa automática, respeitando decisões manuais (só o opt-out as sobrepõe) e gravando a jornada.
create or replace function pipeline_sync(p_lead bigint, p_motivo text default null) returns void language plpgsql as $$
declare
  atual text; manual boolean; nova text;
begin
  select pipeline_stage, pipeline_manual into atual, manual from leads where id = p_lead and mesclado_em is null;
  if not found then return; end if;
  nova := pipeline_auto(p_lead);
  if nova is null or nova = atual then return; end if;
  if manual and nova <> 'opt_out' then return; end if;
  update leads set pipeline_stage = nova, pipeline_desde = now(),
                   pipeline_manual = case when nova = 'opt_out' then false else pipeline_manual end
   where id = p_lead;
  insert into lead_stage_history (lead_id, de, para, origem, motivo) values (p_lead, atual, nova, 'sistema', p_motivo);
end $$;

-- Gatilhos: qualquer fato novo reavalia a etapa do lead correspondente.
create or replace function pipeline_trg() returns trigger language plpgsql as $$
declare
  r record; hid bigint; lid bigint; v_hash text;
begin
  r := case when tg_op = 'DELETE' then old else new end;
  if tg_table_name = 'leads' then
    if tg_op = 'INSERT' then
      insert into lead_stage_history (lead_id, de, para, origem, motivo) values (new.id, null, new.pipeline_stage, 'sistema', 'lead criado');
    end if;
    perform pipeline_sync(new.id, 'situação do lead');
  elsif tg_table_name = 'contacts' then
    for lid in select id from leads where holder_id = r.holder_id loop
      perform pipeline_sync(lid, 'contato ' || r.tipo);
    end loop;
  elsif tg_table_name in ('consents','consent_requests') then
    select holder_id into hid from contacts where id = r.contact_id;
    for lid in select id from leads where holder_id = hid loop
      perform pipeline_sync(lid, 'autorização');
    end loop;
  elsif tg_table_name in ('wa_messages','outreach_log') then
    if r.lead_id is not null then
      perform pipeline_sync(r.lead_id, case when tg_table_name = 'outreach_log' then 'contato manual registrado' else 'mensagem de WhatsApp' end);
    end if;
  elsif tg_table_name = 'research_runs' then
    for lid in select id from leads where holder_id = r.holder_id loop
      perform pipeline_sync(lid, 'pesquisa');
    end loop;
  elsif tg_table_name = 'suppression_list' then
    v_hash := new.valor_hash;
    for lid in
      select l.id from leads l join holders h on h.id = l.holder_id
       where encode(sha256(convert_to(h.holder_key, 'UTF8')), 'hex') = v_hash
      union
      select l.id from leads l join contacts c on c.holder_id = l.holder_id
       where encode(sha256(convert_to(c.valor_normalizado, 'UTF8')), 'hex') = v_hash
    loop
      perform pipeline_sync(lid, 'opt-out');
    end loop;
  end if;
  return null;
end $$;

create trigger leads_pipeline after insert or update of status, pesquisado_em, motivo_descarte, mesclado_em on leads
  for each row execute function pipeline_trg();
create trigger contacts_pipeline after insert or update of verificacao or delete on contacts
  for each row execute function pipeline_trg();
create trigger consents_pipeline after insert or update on consents
  for each row execute function pipeline_trg();
create trigger wa_messages_pipeline after insert or update of status on wa_messages
  for each row execute function pipeline_trg();
create trigger outreach_log_pipeline after insert on outreach_log
  for each row execute function pipeline_trg();
create trigger research_runs_pipeline after insert on research_runs
  for each row execute function pipeline_trg();
create trigger suppression_list_pipeline after insert on suppression_list
  for each row execute function pipeline_trg();

-- Leads que já existem: posiciona cada um na etapa que os fatos indicam e abre a jornada.
insert into lead_stage_history (lead_id, de, para, origem, motivo)
select id, null, pipeline_stage, 'sistema', 'início do histórico (lead já existente)' from leads;
select pipeline_sync(id, 'posição inicial pelos dados existentes') from leads where mesclado_em is null;
