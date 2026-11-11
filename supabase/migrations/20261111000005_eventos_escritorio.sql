-- =====================================================================
-- Eventos dos agentes (INPI AI Office): gravados pelo próprio banco.
-- Todo worker, em qualquer máquina, gera eventos sem mudar código.
-- =====================================================================

create table agent_events (
  id         bigserial primary key,
  tipo       text not null,          -- agent.started, task.completed, rpi.processed, lead.discovered...
  agente     text not null,          -- tipo de job (ex.: inpi.verify) ou 'sistema'
  job_id     bigint,
  referencia text,                   -- job:123, rpi:2914, lead:45, processo:9123...
  descricao  text not null,
  resultado  jsonb,
  criado_em  timestamptz not null default now()
);
create index agent_events_em_idx on agent_events (criado_em desc);
create index agent_events_agente_idx on agent_events (agente, id desc);
alter table agent_events enable row level security;

create or replace function office_emit(p_tipo text, p_agente text, p_job bigint, p_ref text, p_desc text, p_res jsonb)
returns void language plpgsql as $$
declare v_id bigint;
begin
  insert into agent_events (tipo, agente, job_id, referencia, descricao, resultado)
  values (p_tipo, p_agente, p_job, p_ref, left(p_desc, 500), p_res) returning id into v_id;
  perform pg_notify('agent_events', v_id::text);
end $$;

-- agentes que usam modelo de IA: em execução aparecem como "pensando"
create or replace function office_job_ref(j jobs) returns text language sql immutable as $$
  select coalesce(
    case when j.payload ? 'numero' then
           case when j.tipo like 'rpi.%' then 'rpi:' else 'processo:' end || (j.payload->>'numero') end,
    case when j.payload ? 'holder_id' then 'titular:' || (j.payload->>'holder_id') end,
    case when j.payload ? 'lead_id' then 'lead:' || (j.payload->>'lead_id') end,
    'job:' || j.id)
$$;

create or replace function office_jobs_trigger() returns trigger language plpgsql as $$
declare
  ref text := office_job_ref(new);
  ia  boolean := new.tipo in ('research.holder', 'sales.summarize_batch');
begin
  if tg_op = 'INSERT' then
    perform office_emit('task.created', new.tipo, new.id, ref, 'Tarefa criada', null);
    return new;
  end if;
  if new.status is not distinct from old.status then
    return new;
  end if;
  if new.status = 'running' then
    perform office_emit('task.started', new.tipo, new.id, ref, 'Tarefa iniciada (tentativa ' || new.tentativas || ')', null);
    perform office_emit(case when ia then 'agent.thinking' else 'agent.started' end, new.tipo, new.id, ref,
                        case when ia then 'Consultando o modelo de IA' else 'Trabalhando' end, null);
  elsif new.status = 'succeeded' then
    perform office_emit('task.completed', new.tipo, new.id, ref, 'Tarefa concluída', new.resultado);
    perform office_emit('agent.completed', new.tipo, new.id, ref, 'Concluiu a tarefa', null);
  elsif new.status = 'queued' and old.status = 'running' then
    perform office_emit('task.failed', new.tipo, new.id, ref, 'Falhou; nova tentativa agendada',
                        jsonb_build_object('erro', split_part(coalesce(new.ultimo_erro, ''), E'\n', 1)));
    perform office_emit('agent.waiting', new.tipo, new.id, ref, 'Aguardando nova tentativa', null);
  elsif new.status = 'dead' then
    perform office_emit('task.failed', new.tipo, new.id, ref, 'Falha definitiva (precisa de revisão)',
                        jsonb_build_object('erro', split_part(coalesce(new.ultimo_erro, ''), E'\n', 1)));
    perform office_emit('agent.error', new.tipo, new.id, ref, 'Ocorreu uma falha', null);
  end if;
  return new;
end $$;
create trigger jobs_office_events after insert or update of status on jobs
  for each row execute function office_jobs_trigger();

create or replace function office_rpi_trigger() returns trigger language plpgsql as $$
begin
  if new.status is distinct from old.status then
    if new.status = 'downloaded' then
      perform office_emit('rpi.imported', 'rpi.collect', null, 'rpi:' || new.numero,
                          'Revista ' || new.numero || ' importada', null);
    elsif new.status = 'parsed' then
      perform office_emit('rpi.processed', 'rpi.parse', null, 'rpi:' || new.numero,
        'Revista ' || new.numero || ': ' || coalesce(new.stats->>'processos_no_xml', '?') || ' processos, '
          || coalesce(new.stats->>'oportunidades_elegiveis', '?') || ' elegíveis',
        jsonb_build_object('processos', new.stats->'processos_no_xml', 'elegiveis', new.stats->'oportunidades_elegiveis'));
    end if;
  end if;
  return new;
end $$;
create trigger rpi_editions_office_events after update of status on rpi_editions
  for each row execute function office_rpi_trigger();

create or replace function office_leads_trigger() returns trigger language plpgsql as $$
declare nome text;
begin
  select nome_original into nome from holders where id = new.holder_id;
  if tg_op = 'INSERT' then
    perform office_emit('lead.discovered', 'leads.build', null, 'lead:' || new.id, 'Lead identificado: ' || coalesce(nome, '?'), null);
  elsif new.status = 'qualificado' and old.status is distinct from 'qualificado' then
    perform office_emit('lead.qualified', 'leads.build', null, 'lead:' || new.id,
                        'Lead qualificado: ' || coalesce(nome, '?') || ' (prioridade ' || coalesce(new.prioridade, '?') || ')', null);
  end if;
  return new;
end $$;
create trigger leads_office_events after insert or update of status on leads
  for each row execute function office_leads_trigger();

create or replace function office_contacts_trigger() returns trigger language plpgsql as $$
declare lead_id bigint;
begin
  if new.verificacao in ('dominio_ok', 'verificado_humano') and old.verificacao is distinct from new.verificacao then
    select id into lead_id from leads where holder_id = new.holder_id;
    perform office_emit('lead.validated', 'lead.validate_contacts', null, 'lead:' || coalesce(lead_id::text, '?'),
                        initcap(new.tipo) || ' comercial validado', jsonb_build_object('tipo', new.tipo));
  end if;
  return new;
end $$;
create trigger contacts_office_events after update of verificacao on contacts
  for each row execute function office_contacts_trigger();

-- limpeza: eventos ficam 30 dias (feita pelo agendamento de relatório)
