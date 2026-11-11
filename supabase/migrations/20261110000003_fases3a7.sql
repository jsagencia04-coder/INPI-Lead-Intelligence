-- =====================================================================
-- Fases 3 a 7: verificação no INPI, CNPJ, pesquisa, qualificação e relatórios
-- =====================================================================

-- ---------------------------------------------------------------------
-- Fase 3: verificação no INPI (pePI)
-- ---------------------------------------------------------------------
alter table processes
  add column inpi_cod_pedido     text,
  add column verificado_inpi_em  timestamptz;
create index processes_verif_idx on processes (verificado_inpi_em nulls first);

alter table inpi_verifications
  add column titulares jsonb not null default '[]',
  add column publicacoes jsonb not null default '[]',
  add column cod_pedido text;

-- ---------------------------------------------------------------------
-- Fase 4: base CNPJ (Receita Federal, dados abertos) — só o necessário
-- ---------------------------------------------------------------------
create table cnpj_empresas (
  cnpj_basico        char(8) primary key,
  razao_social       text not null,
  nome_normalizado   text not null,
  natureza_juridica  text,
  capital_social     numeric(18,2),
  porte              text,
  mes_referencia     text not null,
  updated_at         timestamptz not null default now()
);
create index cnpj_empresas_nome_idx on cnpj_empresas (nome_normalizado);

create table cnpj_estabelecimentos (
  cnpj               char(14) primary key,
  cnpj_basico        char(8) not null references cnpj_empresas(cnpj_basico),
  matriz             boolean not null,
  nome_fantasia      text,
  situacao_cadastral text,         -- 01 nula, 02 ativa, 03 suspensa, 04 inapta, 08 baixada
  data_situacao      date,
  data_inicio        date,
  cnae_principal     text,
  logradouro         text,
  numero             text,
  bairro             text,
  cep                text,
  uf                 text,
  municipio_codigo   text,
  telefone1          text,
  telefone2          text,
  email              text,
  mes_referencia     text not null,
  updated_at         timestamptz not null default now()
);
create index cnpj_estab_basico_idx on cnpj_estabelecimentos (cnpj_basico);

alter table holders
  add column cnpj_status text not null default 'pendente'
    check (cnpj_status in ('pendente','encontrado','ambiguo','nao_encontrado','nao_aplicavel','manual')),
  add column cnpj_mes_verificado text,
  add column cnpj_candidatos jsonb not null default '[]';

-- ---------------------------------------------------------------------
-- Fase 4: pesquisa, evidências e custo
-- ---------------------------------------------------------------------
alter table evidences add column fonte_tipo text not null default 'web'
  check (fonte_tipo in ('web','receita','inpi','manual'));

alter table contacts
  add column fonte_tipo text not null default 'web' check (fonte_tipo in ('web','receita','manual')),
  add column observacao text,
  add column checado_em timestamptz,
  add column checagem jsonb not null default '{}';
alter table contacts drop constraint contacts_tipo_check;
alter table contacts add constraint contacts_tipo_check check (tipo in
  ('email','telefone','site','whatsapp','instagram','linkedin','facebook','tiktok','youtube','outro'));

create table llm_calls (
  id          bigserial primary key,
  proposito   text not null,            -- research | summary
  modelo      text not null,
  job_id      bigint references jobs(id) on delete set null,
  holder_id   bigint references holders(id),
  tokens_in   int not null default 0,
  tokens_out  int not null default 0,
  buscas_web  int not null default 0,
  custo_usd   numeric(10,5) not null default 0,
  criado_em   timestamptz not null default now()
);
create index llm_calls_em_idx on llm_calls (criado_em);

-- ---------------------------------------------------------------------
-- Fase 5: leads
-- ---------------------------------------------------------------------
alter table leads
  add column score_detalhes     jsonb not null default '{}',
  add column categoria_principal text,
  add column prazo_ate          date,
  add column procurador_confirmado boolean not null default false,
  add column motivo_descarte    text,
  add column mesclado_em        bigint references leads(id),
  add column pesquisado_em      timestamptz,
  add column resumo_gerado_por  text;

create table lead_notes (
  id      bigserial primary key,
  lead_id bigint not null references leads(id) on delete cascade,
  texto   text not null,
  autor   text not null default app_actor(),
  em      timestamptz not null default now()
);
create trigger lead_notes_audit after insert or update or delete on lead_notes
  for each row execute function audit_row('id');

-- ---------------------------------------------------------------------
-- Fase 6: relatórios e exportações
-- ---------------------------------------------------------------------
create table reports (
  id         bigserial primary key,
  tipo       text not null,             -- semanal
  referencia text not null,             -- ex.: 'RPI 2914'
  dados      jsonb not null,
  criado_por text not null default app_actor(),
  criado_em  timestamptz not null default now(),
  unique (tipo, referencia)
);

create table exports_log (
  id         bigserial primary key,
  formato    text not null,
  filtros    jsonb not null default '{}',
  linhas     int not null,
  criado_por text not null default app_actor(),
  criado_em  timestamptz not null default now()
);

do $$
declare t text;
begin
  foreach t in array array['cnpj_empresas','cnpj_estabelecimentos','llm_calls','lead_notes','reports','exports_log']
  loop
    execute format('alter table %I enable row level security', t);
  end loop;
end $$;

-- ---------------------------------------------------------------------
-- Agendamentos das novas etapas
-- ---------------------------------------------------------------------
insert into schedules (nome, tipo, intervalo_minutos, ativo) values
  ('inpi-verificacao',  'inpi.verify_pending',  60,    true),
  ('leads-montagem',    'leads.build',          60,    true),
  ('pesquisa-web',      'research.batch',       60,    true),   -- não faz nada sem ANTHROPIC_API_KEY
  ('resumos-comerciais','sales.summarize_batch',120,   true),
  ('cnpj-receita',      'cnpj.sync',            10080, false),  -- baixa ~8 GB: ligar conscientemente
  ('relatorio-semanal', 'reports.weekly',       1440,  true);

-- ---------------------------------------------------------------------
-- Dashboard
-- ---------------------------------------------------------------------
create or replace view v_dashboard_summary with (security_invoker = true) as
select
  (select count(*) from processes)                                                   as processos_importados,
  (select count(distinct o.numero_processo) from opportunities o
     join processes p using (numero_processo)
    where o.status = 'elegivel' and not p.descartado
      and p.procurador_status in ('sem_confirmado','sem_na_rpi'))                    as processos_sem_procurador,
  (select count(*) from processes p where p.descartado
      or (exists (select 1 from opportunities o where o.numero_processo = p.numero_processo)
          and not exists (select 1 from opportunities o where o.numero_processo = p.numero_processo
                                                         and o.status = 'elegivel'))) as processos_descartados,
  (select count(*) from leads where status <> 'descartado')                          as leads_encontrados,
  (select count(*) from contacts where verificacao in ('dominio_ok','verificado_humano')) as contatos_validados,
  (select count(*) from leads where status = 'sem_contato')                          as leads_sem_contato,
  (select count(*) from jobs where status in ('queued','running') and tipo like 'research.%') as pesquisas_pendentes,
  (select count(*) from jobs where status = 'running')                               as agentes_em_execucao,
  (select count(*) from review_tasks where status = 'aberta')                        as revisoes_abertas,
  (select count(*) from processes where procurador_status = 'sem_confirmado')         as procurador_ausente_confirmado,
  (select coalesce(sum(custo_usd), 0) from llm_calls
    where criado_em >= date_trunc('week', now()))                                    as custo_ia_semana_usd;
