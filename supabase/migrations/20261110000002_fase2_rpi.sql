-- =====================================================================
-- Fase 2: importação e interpretação da RPI (Agentes 01 e 02)
-- =====================================================================

-- ---------------------------------------------------------------------
-- Edições e arquivos
-- ---------------------------------------------------------------------
alter table rpi_editions
  add column fonte_url text,
  add column links     jsonb not null default '{}',   -- links de marcas encontrados no índice
  add column stats     jsonb not null default '{}';   -- contagens do parser (conferência)

alter table rpi_files add column nome_arquivo text;

-- ---------------------------------------------------------------------
-- Processos: campos que o XML real traz
-- ---------------------------------------------------------------------
alter table processes
  add column data_concessao  date,
  add column data_vigencia   date,
  add column classes_vienna  text[] not null default '{}',
  add column nice_detalhes   jsonb  not null default '[]',  -- [{codigo, especificacao, status}]
  add column apostila        text,
  add column madri           boolean not null default false,
  add column numero_inscricao_internacional text;

alter table publications rename column complemento to texto_complementar;
alter table publications
  add column protocolos jsonb not null default '[]';  -- petições: numero, data, servico, requerente, procurador...

-- Titularidade muda (transferências): process_holders é reescrito a cada
-- publicação com titulares, então passa a ser auditado.
create trigger process_holders_audit after insert or update or delete on process_holders
  for each row execute function audit_row('numero_processo');

-- ---------------------------------------------------------------------
-- Catálogo de despachos
-- ---------------------------------------------------------------------
alter table despacho_types drop constraint despacho_types_categoria_comercial_check;
alter table despacho_types
  add constraint despacho_types_categoria_comercial_check check (categoria_comercial in
    ('oposicao','exigencia','indeferimento','extincao_prorrogacao','arquivamento','outro')),
  add column fonte          text,
  add column revisar        boolean not null default false,  -- código novo visto pelo parser
  add column confirmado_por text,
  add column confirmado_em  timestamptz;

-- Códigos e nomes copiados literalmente do XML oficial da RPI 2914 (10/11/2026).
-- Ativos para leads: o escopo aprovado (oposição, exigências, indeferimento e
-- extinção por expiração da vigência sem prorrogação). Os demais ficam
-- registrados como 'outro'; a classificação pode ser alterada na tela Despachos.
insert into despacho_types (codigo, nome, categoria_comercial, ativo_para_leads, fonte) values
  ('IPAS009','Publicação de pedido de registro para oposição (exame formal concluído)','oposicao',true,'RPI 2914'),
  ('IPAS136','Exigência de mérito','exigencia',true,'RPI 2914'),
  ('IPAS267','Exigência de mérito (em petição)','exigencia',true,'RPI 2914'),
  ('IPAS005','Exigência formal','exigencia',true,'RPI 2914'),
  ('IPAS192','Exigência de conformidade','exigencia',true,'RPI 2914'),
  ('IPAS024','Indeferimento do pedido','indeferimento',true,'RPI 2914'),
  ('IPAS161','Extinção de registro pela expiração do prazo de vigência','extincao_prorrogacao',true,'RPI 2914'),
  ('IPAS139','Arquivamento definitivo de pedido de registro por falta de cumprimento de exigência de mérito','arquivamento',false,'RPI 2914'),
  ('IPAS157','Arquivamento definitivo de pedido de registro por falta de pagamento da concessão','arquivamento',false,'RPI 2914'),
  ('IPAS106','Arquivamento definitivo de pedido de registro por falta de procuração','arquivamento',false,'RPI 2914'),
  ('IPAS289','Arquivamento definitivo de pedido de registro por falta de documentos de marca de certificação','arquivamento',false,'RPI 2914'),
  ('IPAS404','Arquivamento de ofício de pedido de registro de marca','arquivamento',false,'RPI 2914'),
  ('IPAS158','Concessão de registro','outro',false,'RPI 2914'),
  ('IPAS029','Deferimento do pedido','outro',false,'RPI 2914'),
  ('IPAS270','Deferimento da petição','outro',false,'RPI 2914'),
  ('IPAS360','Notificação de recurso','outro',false,'RPI 2914'),
  ('IPAS756','Publicação de pedido de registro para oposição (exame formal de designação concluído)','outro',false,'RPI 2914'),
  ('IPAS235','Recurso não provido (decisão mantida)','outro',false,'RPI 2914'),
  ('IPAS423','Notificação de oposição','outro',false,'RPI 2914'),
  ('IPAS770','Concessão de registro em designação','outro',false,'RPI 2914'),
  ('IPAS400','Notificação de instauração de processo de nulidade a requerimento','outro',false,'RPI 2914'),
  ('IPAS768','Deferimento de designação','outro',false,'RPI 2914'),
  ('IPAS428','Decisão de não conhecer da petição','outro',false,'RPI 2914'),
  ('IPAS699','Ato de prejudicar petição','outro',false,'RPI 2914'),
  ('IPAS1054','Petição de trâmite prioritário atendida','outro',false,'RPI 2914'),
  ('IPAS142','Sobrestamento do exame de mérito','outro',false,'RPI 2914'),
  ('IPAS532','Requerimento não provido (mantida a concessão)','outro',false,'RPI 2914'),
  ('IPAS338','Notificação de caducidade','outro',false,'RPI 2914'),
  ('IPAS1069','Petição de trâmite prioritário apta (aguardando término de prazo legal)','outro',false,'RPI 2914'),
  ('IPAS462','Notificação de procedimento judicial','outro',false,'RPI 2914'),
  ('IPAS499','Sobrestamento da instrução técnica','outro',false,'RPI 2914'),
  ('IPAS579','Emissão de segunda via de certificado de registro','outro',false,'RPI 2914'),
  ('IPAS901','Anotação de transferência de titularidade em designação','outro',false,'RPI 2914'),
  ('IPAS403','Anulação de despacho (em petição)','outro',false,'RPI 2914'),
  ('IPAS900','Anotação de alteração de nome e/ou endereço em designação','outro',false,'RPI 2914'),
  ('IPAS271','Indeferimento da petição','outro',false,'RPI 2914'),
  ('IPAS089','Exigência de pagamento (em petição)','outro',false,'RPI 2914'),
  ('IPAS774','Indeferimento de designação','outro',false,'RPI 2914'),
  ('IPAS1055','Petição de trâmite prioritário não atendida','outro',false,'RPI 2914'),
  ('IPAS227','Sobrestamento do exame de mérito (em petição)','outro',false,'RPI 2914'),
  ('IPAS639','Publicação de decisão judicial transitada em julgado','outro',false,'RPI 2914'),
  ('IPAS772','Exigência de mérito em designação','outro',false,'RPI 2914'),
  ('IPAS781','Deferimento parcial de designação','outro',false,'RPI 2914'),
  ('IPAS402','Anulação de despacho (em processo)','outro',false,'RPI 2914'),
  ('IPAS771','Sobrestamento do exame de mérito de designação','outro',false,'RPI 2914'),
  ('IPAS185','Arquivamento de petição por falta de procuração','outro',false,'RPI 2914'),
  ('IPAS669','Deferimento da petição de caducidade','outro',false,'RPI 2914'),
  ('IPAS409','Cancelamento de ofício de registro de marca','outro',false,'RPI 2914'),
  ('IPAS421','Republicação de pedido','outro',false,'RPI 2914'),
  ('IPAS337','Indeferimento da petição por falta de legítimo interesse','outro',false,'RPI 2914'),
  ('IPAS566','Petição de retificação atendida','outro',false,'RPI 2914'),
  ('IPAS237','Recurso provido (decisão reformada para: Deferimento)','outro',false,'RPI 2914'),
  ('IPAS971','Emissão de segunda via de certificado de registro em designação','outro',false,'RPI 2914'),
  ('IPAS773','Arquivamento definitivo de designação por falta de cumprimento de exigência de mérito','outro',false,'RPI 2914'),
  ('IPAS437','Notificação de instauração de processo de nulidade de ofício','outro',false,'RPI 2914'),
  ('IPAS304','Extinção de registro pela caducidade','outro',false,'RPI 2914'),
  ('IPAS135','Republicação de pedido (por perda da prioridade)','outro',false,'RPI 2914'),
  ('IPAS902','Anotação de cancelamento parcial de especificação em designação','outro',false,'RPI 2914'),
  ('IPAS395','Exigência de pagamento','outro',false,'RPI 2914'),
  ('IPAS658','Indeferimento do pedido (em retificação)','outro',false,'RPI 2914'),
  ('IPAS1028','Notificação de processo decorrente de transferência parcial (Madri) da inscrição internacional','outro',false,'RPI 2914'),
  ('IPAS654','Deferimento do pedido (em retificação)','outro',false,'RPI 2914'),
  ('IPAS349','Deferimento parcial da petição','outro',false,'RPI 2914'),
  ('IPAS567','Petição de retificação não atendida','outro',false,'RPI 2914'),
  ('IPAS973','Ato de prejudicar comunicação de Madri','outro',false,'RPI 2914'),
  ('IPAS790','Decisão de considerar Pedido Internacional inexistente por não cumprir requisitos de certificação','outro',false,'RPI 2914');

-- ---------------------------------------------------------------------
-- Oportunidades: cada publicação de despacho-alvo gera uma linha
-- ---------------------------------------------------------------------
create table opportunities (
  id              bigserial primary key,
  numero_processo text   not null references processes(numero_processo),
  edition_id      bigint not null references rpi_editions(id),
  despacho_codigo text   not null references despacho_types(codigo),
  categoria       text   not null,
  status          text   not null default 'elegivel'
                  check (status in ('elegivel','descartada')),
  motivo_descarte text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  unique (numero_processo, edition_id, despacho_codigo)
);
create index opportunities_status_idx on opportunities (status, categoria);
create index opportunities_edition_idx on opportunities (edition_id);
create trigger opportunities_updated before update on opportunities
  for each row execute function set_updated_at();
create trigger opportunities_audit after insert or update or delete on opportunities
  for each row execute function audit_row('id');
alter table opportunities enable row level security;

-- ---------------------------------------------------------------------
-- Agendamentos (portável: funciona no Postgres local e no Supabase)
-- ---------------------------------------------------------------------
create table schedules (
  nome              text primary key,
  tipo              text  not null,
  payload           jsonb not null default '{}',
  intervalo_minutos int   not null check (intervalo_minutos >= 5),
  ativo             boolean not null default true,
  proximo_em        timestamptz not null default now(),
  ultimo_job_id     bigint references jobs(id),
  updated_at        timestamptz not null default now()
);
create trigger schedules_updated before update on schedules
  for each row execute function set_updated_at();
create trigger schedules_audit after insert or update or delete on schedules
  for each row execute function audit_row('nome');
alter table schedules enable row level security;

-- A RPI sai às terças; a verificação a cada 3 h é barata (1 página) e
-- garante a captura mesmo com atraso de publicação.
insert into schedules (nome, tipo, intervalo_minutos) values ('rpi-descoberta', 'rpi.discover', 180);

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
  (select count(*) from jobs where status = 'queued' and tipo like 'research.%')     as pesquisas_pendentes,
  (select count(*) from jobs where status = 'running')                               as agentes_em_execucao,
  (select count(*) from review_tasks where status = 'aberta')                        as revisoes_abertas;
