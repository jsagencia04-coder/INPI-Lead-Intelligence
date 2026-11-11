-- =====================================================================
-- INPI Lead Intelligence — schema inicial (Fase 1)
--
-- Convenções:
--   * Número do processo INPI (texto, só dígitos) é a chave natural.
--   * Status usam TEXT + CHECK (mais fácil de evoluir que ENUM).
--   * Arquivos da RPI e evidências são IMUTÁVEIS (trigger bloqueia UPDATE/DELETE).
--   * Tabelas de negócio têm trilha de auditoria (audit_log) via trigger.
--   * O "ator" de cada alteração vem de set_config('app.actor', ..., true),
--     definido pelo backend em cada transação.
--   * RLS habilitado em todas as tabelas sem policies: nada fica exposto pela
--     API pública do Supabase (anon/authenticated). Só o backend acessa.
-- =====================================================================

create extension if not exists pg_trgm;
create extension if not exists unaccent;

-- ---------------------------------------------------------------------
-- Funções utilitárias
-- ---------------------------------------------------------------------
create or replace function app_actor() returns text
language sql stable as $$
  select coalesce(nullif(current_setting('app.actor', true), ''), current_user::text)
$$;

create or replace function set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end $$;

create or replace function forbid_mutation() returns trigger
language plpgsql as $$
begin
  raise exception 'Tabela % é imutável (operação % bloqueada)', tg_table_name, tg_op
    using errcode = 'P0001';
end $$;

-- ---------------------------------------------------------------------
-- Auditoria (regra 7: manter histórico de alterações)
-- ---------------------------------------------------------------------
create table audit_log (
  id          bigserial primary key,
  tabela      text        not null,
  registro_id text        not null,
  acao        text        not null check (acao in ('INSERT','UPDATE','DELETE')),
  antes       jsonb,
  depois      jsonb,
  ator        text        not null default app_actor(),
  em          timestamptz not null default now()
);
create index audit_log_registro_idx on audit_log (tabela, registro_id, em desc);
create index audit_log_em_idx on audit_log (em desc);

-- Identifica o registro pela coluna informada no argumento do trigger.
create or replace function audit_row() returns trigger
language plpgsql as $$
declare
  pk_col text := tg_argv[0];
  rec    jsonb;
begin
  rec := case when tg_op = 'DELETE' then to_jsonb(old) else to_jsonb(new) end;
  if tg_op = 'UPDATE' and to_jsonb(old) - 'updated_at' = to_jsonb(new) - 'updated_at' then
    return new;  -- nada mudou de fato
  end if;
  insert into audit_log (tabela, registro_id, acao, antes, depois)
  values (
    tg_table_name,
    rec ->> pk_col,
    tg_op,
    case when tg_op in ('UPDATE','DELETE') then to_jsonb(old) end,
    case when tg_op in ('INSERT','UPDATE') then to_jsonb(new) end
  );
  return coalesce(new, old);
end $$;

-- ---------------------------------------------------------------------
-- Fila de jobs (agentes) — Postgres + SELECT ... FOR UPDATE SKIP LOCKED
-- ---------------------------------------------------------------------
create table jobs (
  id            bigserial primary key,
  tipo          text        not null,              -- ex.: 'rpi.collect', 'rpi.parse'
  payload       jsonb       not null default '{}',
  status        text        not null default 'queued'
                check (status in ('queued','running','succeeded','failed','dead','cancelled')),
  prioridade    int         not null default 100,   -- menor = mais urgente
  tentativas    int         not null default 0,
  max_tentativas int        not null default 5,
  run_after     timestamptz not null default now(),
  dedupe_key    text,                               -- idempotência: 1 job ativo por chave
  locked_by     text,
  locked_at     timestamptz,
  iniciado_em   timestamptz,
  finalizado_em timestamptz,
  resultado     jsonb,
  ultimo_erro   text,
  criado_por    text        not null default app_actor(),
  criado_em     timestamptz not null default now(),
  parent_id     bigint references jobs(id)
);
create index jobs_fetch_idx on jobs (prioridade, run_after, id) where status = 'queued';
create index jobs_status_idx on jobs (status, criado_em desc);
create index jobs_tipo_idx on jobs (tipo, criado_em desc);
create unique index jobs_dedupe_active_idx on jobs (dedupe_key)
  where dedupe_key is not null and status in ('queued','running');

-- ---------------------------------------------------------------------
-- RPI: edições e arquivos originais (regra 6: preservar originais)
-- ---------------------------------------------------------------------
create table rpi_editions (
  id              bigserial primary key,
  numero          int         not null unique,
  data_publicacao date,
  status          text        not null default 'detected'
                  check (status in ('detected','downloading','downloaded','parsing','parsed','error')),
  detectada_em    timestamptz not null default now(),
  coletada_em     timestamptz,
  processada_em   timestamptz,
  observacoes     text,
  updated_at      timestamptz not null default now()
);
create trigger rpi_editions_updated before update on rpi_editions
  for each row execute function set_updated_at();
create trigger rpi_editions_audit after insert or update or delete on rpi_editions
  for each row execute function audit_row('numero');

create table rpi_files (
  id           bigserial primary key,
  edition_id   bigint      not null references rpi_editions(id),
  secao        text        not null default 'marcas',
  volume       text,
  formato      text        not null check (formato in ('xml','pdf','txt','zip')),
  source_url   text        not null,
  storage_path text        not null unique,
  sha256       char(64)    not null unique,
  bytes        bigint      not null,
  baixado_em   timestamptz not null default now()
);
create index rpi_files_edition_idx on rpi_files (edition_id);
create trigger rpi_files_immutable before update or delete on rpi_files
  for each row execute function forbid_mutation();

-- Catálogo de despachos e sua relevância comercial (populado na Fase 2,
-- após conferência com a tabela oficial de despachos do INPI).
create table despacho_types (
  codigo               text primary key,
  nome                 text not null,
  categoria_comercial  text not null default 'outro'
                       check (categoria_comercial in
                         ('oposicao','exigencia','indeferimento','extincao_prorrogacao','outro')),
  ativo_para_leads     boolean not null default false,
  updated_at           timestamptz not null default now()
);
create trigger despacho_types_updated before update on despacho_types
  for each row execute function set_updated_at();
create trigger despacho_types_audit after insert or update or delete on despacho_types
  for each row execute function audit_row('codigo');

-- ---------------------------------------------------------------------
-- Processos, publicações e titulares
-- ---------------------------------------------------------------------
create table processes (
  numero_processo   text primary key check (numero_processo ~ '^[0-9]{6,12}$'),
  marca_nome        text,
  apresentacao      text,               -- nominativa, mista, figurativa...
  natureza          text,               -- produto, serviço, coletiva...
  classes_nice      text[] not null default '{}',
  data_deposito     date,
  situacao_atual    text,
  -- Regra: ausência de procurador só é "confirmada" após verificação no INPI.
  procurador_status text not null default 'desconhecido'
                    check (procurador_status in ('com_procurador','sem_confirmado','sem_na_rpi','desconhecido')),
  procurador_nome   text,
  procurador_fonte  text,               -- 'rpi:<edição>' ou 'inpi:<verification_id>'
  first_seen_edition_id bigint references rpi_editions(id),
  last_seen_edition_id  bigint references rpi_editions(id),
  descartado        boolean not null default false,
  motivo_descarte   text,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);
create index processes_procurador_idx on processes (procurador_status) where not descartado;
create index processes_marca_trgm on processes using gin (marca_nome gin_trgm_ops);
create trigger processes_updated before update on processes
  for each row execute function set_updated_at();
create trigger processes_audit after insert or update or delete on processes
  for each row execute function audit_row('numero_processo');

create table publications (
  id              bigserial primary key,
  numero_processo text   not null references processes(numero_processo),
  edition_id      bigint not null references rpi_editions(id),
  rpi_file_id     bigint references rpi_files(id),
  despacho_codigo text   not null,
  despacho_nome   text,
  complemento     text,
  procurador_na_publicacao text,
  raw_hash        char(64),             -- hash do fragmento original (rastreabilidade)
  criado_em       timestamptz not null default now(),
  unique (numero_processo, edition_id, despacho_codigo)
);
create index publications_edition_idx on publications (edition_id);
create index publications_despacho_idx on publications (despacho_codigo);

create table holders (
  id               bigserial primary key,
  nome_original    text not null,
  nome_normalizado text not null,       -- sem acentos, maiúsculo, espaços colapsados
  uf               text,
  pais             text,
  tipo_provavel    text not null default 'indefinido'
                   check (tipo_provavel in ('PF','PJ','indefinido')),
  cnpj             char(14),
  cnpj_confianca   numeric(4,3) check (cnpj_confianca between 0 and 1),
  cnpj_fonte       text,
  holder_key       text generated always as
                   (nome_normalizado || '|' || coalesce(uf,'') || '|' || coalesce(pais,'')) stored,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  unique (holder_key)
);
create index holders_nome_trgm on holders using gin (nome_normalizado gin_trgm_ops);
create index holders_cnpj_idx on holders (cnpj) where cnpj is not null;
create trigger holders_updated before update on holders
  for each row execute function set_updated_at();
create trigger holders_audit after insert or update or delete on holders
  for each row execute function audit_row('id');

create table process_holders (
  numero_processo text   not null references processes(numero_processo),
  holder_id       bigint not null references holders(id),
  ordem           smallint not null default 1,
  primary key (numero_processo, holder_id)
);
create index process_holders_holder_idx on process_holders (holder_id);

-- ---------------------------------------------------------------------
-- Verificação na base do INPI (Agente 03)
-- ---------------------------------------------------------------------
create table inpi_verifications (
  id              bigserial primary key,
  numero_processo text        not null references processes(numero_processo),
  consultado_em   timestamptz not null default now(),
  fonte_url       text        not null,
  resultado       text        not null check (resultado in ('ok','indisponivel','nao_encontrado','erro')),
  titular         text,
  marca           text,
  situacao        text,
  procurador      text,
  procurador_status text check (procurador_status in ('com_procurador','sem_confirmado','desconhecido')),
  snapshot_path   text,
  snapshot_sha256 char(64),
  job_id          bigint references jobs(id),
  observacoes     text
);
create index inpi_verifications_proc_idx on inpi_verifications (numero_processo, consultado_em desc);
create trigger inpi_verifications_immutable before update or delete on inpi_verifications
  for each row execute function forbid_mutation();

-- ---------------------------------------------------------------------
-- Pesquisa externa e evidências (Agente 04) — regra 3: toda info tem fonte
-- ---------------------------------------------------------------------
create table research_runs (
  id            bigserial primary key,
  holder_id     bigint not null references holders(id),
  agente        text   not null,
  modelo        text,
  status        text   not null default 'running'
                check (status in ('running','succeeded','failed','needs_review')),
  consultas     jsonb  not null default '[]',   -- termos pesquisados
  tokens_in     int    not null default 0,
  tokens_out    int    not null default 0,
  buscas_web    int    not null default 0,
  custo_usd     numeric(10,5) not null default 0,
  job_id        bigint references jobs(id),
  iniciado_em   timestamptz not null default now(),
  finalizado_em timestamptz,
  erro          text
);
create index research_runs_holder_idx on research_runs (holder_id, iniciado_em desc);

create table evidences (
  id              bigserial primary key,
  research_run_id bigint references research_runs(id),
  url             text        not null,
  titulo          text,
  trecho          text,                 -- trecho literal que sustenta o dado
  obtido_em       timestamptz not null default now(),
  snapshot_path   text,
  content_sha256  char(64)
);
create index evidences_run_idx on evidences (research_run_id);
create trigger evidences_immutable before update or delete on evidences
  for each row execute function forbid_mutation();

-- Regra 4: contato encontrado ≠ contato verificado.
create table contacts (
  id            bigserial primary key,
  holder_id     bigint not null references holders(id),
  tipo          text   not null check (tipo in ('email','telefone','site','whatsapp','instagram','linkedin','facebook','outro')),
  valor         text   not null,
  valor_normalizado text not null,
  evidence_id   bigint not null references evidences(id),
  verificacao   text   not null default 'encontrado'
                check (verificacao in ('encontrado','formato_ok','dominio_ok','verificado_humano','invalido')),
  confianca     numeric(4,3) check (confianca between 0 and 1),
  ultima_vez_visto timestamptz not null default now(),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (holder_id, tipo, valor_normalizado)
);
create trigger contacts_updated before update on contacts
  for each row execute function set_updated_at();
create trigger contacts_audit after insert or update or delete on contacts
  for each row execute function audit_row('id');

-- ---------------------------------------------------------------------
-- Leads (1 lead por titular) e prospecção
-- ---------------------------------------------------------------------
create table leads (
  id              bigserial primary key,
  holder_id       bigint not null unique references holders(id),
  status          text   not null default 'novo'
                  check (status in ('novo','pesquisando','sem_contato','qualificado','em_revisao',
                                    'aprovado','contatado','convertido','descartado')),
  score           numeric(5,2),
  prioridade      text check (prioridade in ('alta','media','baixa')),
  segmento        text,
  resumo          text,
  sugestao_abordagem text,
  precisa_revisao boolean not null default true,  -- regra 10: revisão humana por padrão
  revisado_por    text,
  revisado_em     timestamptz,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);
create index leads_status_idx on leads (status, prioridade);
create trigger leads_updated before update on leads
  for each row execute function set_updated_at();
create trigger leads_audit after insert or update or delete on leads
  for each row execute function audit_row('id');

create table lead_processes (
  lead_id         bigint not null references leads(id) on delete cascade,
  numero_processo text   not null references processes(numero_processo),
  primary key (lead_id, numero_processo)
);

-- Regra 8: nenhum disparo sem aprovação explícita.
create table outreach_log (
  id           bigserial primary key,
  lead_id      bigint not null references leads(id),
  canal        text   not null,
  contact_id   bigint references contacts(id),
  aprovado_por text   not null,
  executado_por text  not null default app_actor(),
  executado_em timestamptz not null default now(),
  resultado    text,
  observacoes  text
);
create trigger outreach_log_audit after insert or update or delete on outreach_log
  for each row execute function audit_row('id');

-- Regra 9 (LGPD): opt-out. Guardamos apenas o hash do valor normalizado.
create table suppression_list (
  id         bigserial primary key,
  tipo       text not null check (tipo in ('email','telefone','titular')),
  valor_hash char(64) not null,
  motivo     text,
  criado_por text not null default app_actor(),
  criado_em  timestamptz not null default now(),
  unique (tipo, valor_hash)
);
create trigger suppression_list_audit after insert or update or delete on suppression_list
  for each row execute function audit_row('id');

-- Revisão humana em qualquer etapa (regra 10)
create table review_tasks (
  id           bigserial primary key,
  entidade     text not null,          -- 'process','holder','contact','lead'
  entidade_id  text not null,
  motivo       text not null,
  status       text not null default 'aberta' check (status in ('aberta','resolvida','descartada')),
  atribuido_a  text,
  resolucao    text,
  criado_em    timestamptz not null default now(),
  resolvido_em timestamptz,
  updated_at   timestamptz not null default now()
);
create index review_tasks_aberta_idx on review_tasks (status, criado_em) where status = 'aberta';
create trigger review_tasks_updated before update on review_tasks
  for each row execute function set_updated_at();
create trigger review_tasks_audit after insert or update or delete on review_tasks
  for each row execute function audit_row('id');

-- ---------------------------------------------------------------------
-- Visão do dashboard
-- ---------------------------------------------------------------------
-- security_invoker: a view respeita o RLS de quem consulta (não vaza via API pública)
create or replace view v_dashboard_summary with (security_invoker = true) as
select
  (select count(*) from processes)                                                   as processos_importados,
  (select count(*) from processes where procurador_status in ('sem_confirmado','sem_na_rpi')
                                    and not descartado)                              as processos_sem_procurador,
  (select count(*) from processes where descartado)                                  as processos_descartados,
  (select count(*) from leads where status <> 'descartado')                          as leads_encontrados,
  (select count(*) from contacts where verificacao in ('dominio_ok','verificado_humano')) as contatos_validados,
  (select count(*) from leads where status = 'sem_contato')                          as leads_sem_contato,
  (select count(*) from jobs where status = 'queued' and tipo like 'research.%')     as pesquisas_pendentes,
  (select count(*) from jobs where status = 'running')                               as agentes_em_execucao,
  (select count(*) from review_tasks where status = 'aberta')                        as revisoes_abertas;

-- ---------------------------------------------------------------------
-- Segurança Supabase: RLS ligado, sem policies => sem acesso via anon/authenticated
-- ---------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array[
    'audit_log','jobs','rpi_editions','rpi_files','despacho_types','processes','publications',
    'holders','process_holders','inpi_verifications','research_runs','evidences','contacts',
    'leads','lead_processes','outreach_log','suppression_list','review_tasks']
  loop
    execute format('alter table %I enable row level security', t);
  end loop;
end $$;
