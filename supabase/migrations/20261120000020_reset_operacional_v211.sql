-- V2.11 · Rotina de limpeza dos dados operacionais (reset) e espera pela próxima Revista.
--
-- Esta migration SÓ CRIA a rotina; nada é apagado ao aplicá-la. A limpeza roda apenas quando alguém chama
-- reset_operational_data('RESET_INPI', ...) — na prática pelo comando `python -m app.reset`, que exige a
-- variável de ambiente CONFIRM_RESET=RESET_INPI.
--
-- Preservados (nunca truncados aqui): usuários, configurações, catálogos, agendamentos, modelos de mensagem,
-- conta do WhatsApp, lista de descadastro (opt-out), trilha de auditoria, base pública da Receita e o histórico
-- das próprias limpezas.

create table if not exists system_resets (
  id            bigserial primary key,
  executado_em  timestamptz not null default now(),
  executado_por text        not null,
  relatorio     jsonb       not null
);
alter table system_resets enable row level security;

insert into app_config (chave, valor) values
  ('importacao_bloqueada', 'false'),
  ('system_status', 'operational'),
  ('last_publication_id', ''),
  ('last_successful_import', ''),
  ('last_import_status', ''),
  ('next_scheduled_run', ''),
  ('timezone', 'America/Sao_Paulo')
on conflict (chave) do nothing;

-- Tabelas operacionais, na ordem das dependências (filhas antes das mães). Todas vão num único TRUNCATE sem
-- CASCADE: se alguma tabela preservada apontar para uma delas, o PostgreSQL recusa e nada é apagado.
create or replace function reset_tabelas_operacionais() returns text[] language sql immutable as $$
  select array[
    'rpi_reconciliacao', 'rpi_pdf_registros', 'rpi_fontes', 'rpi_operacoes',
    'wa_messages', 'wa_rascunhos', 'wa_auditoria',
    'consent_requests', 'consents', 'outreach_log',
    'pipeline_processos', 'lead_stage_history', 'lead_notes', 'lead_processes', 'leads',
    'process_peticoes', 'inpi_verifications', 'oportunidades_servico', 'opportunities', 'publications',
    'process_holders', 'contacts', 'evidences', 'research_runs', 'llm_calls',
    'processes', 'holders', 'rpi_files', 'rpi_editions',
    'corte_rpi_backup', 'review_tasks', 'reports', 'exports_log', 'agent_events', 'wa_webhook_events',
    'jobs'
  ]
$$;

create or replace function reset_operational_data(
  p_confirm        text,
  p_ator           text,
  p_proxima        timestamptz,
  p_edicao_minima  int
) returns jsonb language plpgsql as $$
declare
  t        text;
  antes    jsonb := '{}';
  restante jsonb := '{}';
  n        bigint;
  rel      jsonb;
begin
  if p_confirm is distinct from 'RESET_INPI' then
    raise exception 'Limpeza recusada: confirmação ausente ou incorreta (CONFIRM_RESET=RESET_INPI)';
  end if;
  -- uma limpeza por vez, mesmo com vários processos
  if not pg_try_advisory_xact_lock(hashtext('inpi:reset_operational_data')) then
    raise exception 'Já existe uma limpeza em andamento';
  end if;
  -- bloqueio de novas importações enquanto a transação existir (os agentes da RPI consultam esta chave)
  update app_config set valor = 'true', atualizado_em = now() where chave = 'importacao_bloqueada';

  foreach t in array reset_tabelas_operacionais() loop
    execute format('select count(*) from public.%I', t) into n;
    antes := antes || jsonb_build_object(t, n);
  end loop;

  -- jobs é referenciada por schedules (preservada): sai com DELETE depois de soltar a referência, e a sequência
  -- volta a 1. As demais saem num único TRUNCATE sem CASCADE.
  update schedules set ultimo_job_id = null;
  execute 'truncate ' || (select string_agg(format('public.%I', x), ', ')
                            from unnest(reset_tabelas_operacionais()) x where x <> 'jobs') || ' restart identity';
  delete from jobs;
  perform setval(pg_get_serial_sequence('public.jobs', 'id'), 1, false);

  -- validação: tudo vazio
  foreach t in array reset_tabelas_operacionais() loop
    execute format('select count(*) from public.%I', t) into n;
    if n <> 0 then
      restante := restante || jsonb_build_object(t, n);
    end if;
  end loop;
  if restante <> '{}' then
    raise exception 'Validação falhou, nada foi apagado: %', restante;
  end if;

  -- estado de espera pela próxima Revista (horários no fuso IANA America/Sao_Paulo, com o deslocamento do dia)
  set local timezone = 'America/Sao_Paulo';
  insert into app_config (chave, valor) values
    ('system_status', 'waiting_for_next_issue'),
    ('last_publication_id', ''),
    ('last_successful_import', ''),
    ('last_import_status', ''),
    ('next_scheduled_run', to_char(p_proxima, 'YYYY-MM-DD"T"HH24:MI:SSTZH:TZM')),
    ('timezone', 'America/Sao_Paulo'),
    ('rpi_edicao_minima', p_edicao_minima::text),
    ('importacao_bloqueada', 'false')
  on conflict (chave) do update set valor = excluded.valor, atualizado_em = now();

  -- primeira execução: verificação da RPI às terças e quartas desde 00:00:01 (fuso America/Sao_Paulo)
  update schedules set hora_inicio = '00:00:01', proximo_em = p_proxima where nome = 'rpi-terca';
  update schedules set proximo_em = greatest(proximo_em, p_proxima) where nome = 'rpi-descoberta';

  rel := jsonb_build_object(
    'executado_em', now(), 'executado_por', p_ator,
    'linhas_removidas', antes, 'tabelas_limpas', to_jsonb(reset_tabelas_operacionais()),
    'proxima_execucao', p_proxima, 'fuso', 'America/Sao_Paulo', 'edicao_minima', p_edicao_minima
  );
  insert into system_resets (executado_por, relatorio) values (p_ator, rel);
  return rel;
end $$;
