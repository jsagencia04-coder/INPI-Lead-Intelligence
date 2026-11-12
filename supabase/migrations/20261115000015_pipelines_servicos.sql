-- V2.4 · Foco comercial: (1) marcas que SOFRERAM oposição → manifestação à oposição;
--                       (2) marcas indeferidas (e deferimentos parciais) → recurso administrativo.
-- Incremental: acrescenta tabelas e colunas. Nada é apagado; registros existentes são preservados.

-- ---------------------------------------------------------------------
-- 1. Catálogo de despachos
-- ---------------------------------------------------------------------
alter table despacho_types drop constraint despacho_types_categoria_comercial_check;
alter table despacho_types add constraint despacho_types_categoria_comercial_check check (categoria_comercial in
  ('oposicao_apresentada','oposicao','exigencia','indeferimento','deferimento_parcial','extincao_prorrogacao','arquivamento','outro'));

-- Só altera códigos que ninguém reconfigurou (respeita decisões do usuário).
update despacho_types set categoria_comercial = 'indeferimento', ativo_para_leads = true,
       fonte = fonte || ' · V2.4: indeferimento republicado (recurso)'
 where codigo = 'IPAS658' and categoria_comercial = 'outro' and not ativo_para_leads and confirmado_por is null;
update despacho_types set categoria_comercial = 'indeferimento', ativo_para_leads = true,
       fonte = fonte || ' · V2.4: indeferimento de designação (Madri; registrado, normalmente descartado por titular estrangeiro)'
 where codigo = 'IPAS774' and categoria_comercial = 'outro' and not ativo_para_leads and confirmado_por is null;
update despacho_types set categoria_comercial = 'deferimento_parcial', ativo_para_leads = true,
       fonte = fonte || ' · V2.4: deferimento parcial (recurso)'
 where codigo = 'IPAS781' and categoria_comercial = 'outro' and not ativo_para_leads and confirmado_por is null;
-- "Publicado para oposição" (IPAS009) NÃO é oposição apresentada: deixa de gerar leads novos.
-- Os registros e leads já existentes ficam preservados como histórico. Reversível na tela Despachos.
update despacho_types set ativo_para_leads = false,
       fonte = fonte || ' · V2.4: fora do foco comercial (publicação para oposição não é oposição apresentada)'
 where codigo = 'IPAS009' and ativo_para_leads and confirmado_por is null;

-- ---------------------------------------------------------------------
-- 2. Calendário para contagem de prazos (dias sem expediente)
-- ---------------------------------------------------------------------
create table feriados (
  data       date primary key,
  nome       text not null,
  tipo       text not null check (tipo in ('nacional','ponto_facultativo','inpi')),
  considerar boolean not null default true,  -- conta como dia sem expediente na prorrogação do vencimento
  fonte      text not null default 'Lei 662/1949, Lei 6.802/1980, Lei 14.759/2023 (feriados nacionais)'
);
create trigger feriados_audit after insert or update or delete on feriados for each row execute function audit_row('data');
alter table feriados enable row level security;
-- Pontos facultativos entram desligados (contagem conservadora); ligue-os se o INPI confirmar que não houve expediente.
insert into feriados (data, nome, tipo, considerar) values
  ('2025-01-01','Confraternização Universal','nacional',true),
  ('2025-03-03','Carnaval (segunda-feira)','ponto_facultativo',false),
  ('2025-03-04','Carnaval (terça-feira)','ponto_facultativo',false),
  ('2025-04-18','Paixão de Cristo (Sexta-feira Santa)','nacional',true),
  ('2025-04-21','Tiradentes','nacional',true),
  ('2025-05-01','Dia do Trabalho','nacional',true),
  ('2025-06-19','Corpus Christi','ponto_facultativo',false),
  ('2025-09-07','Independência do Brasil','nacional',true),
  ('2025-10-12','Nossa Senhora Aparecida','nacional',true),
  ('2025-11-02','Finados','nacional',true),
  ('2025-11-15','Proclamação da República','nacional',true),
  ('2025-11-20','Dia Nacional de Zumbi e da Consciência Negra','nacional',true),
  ('2025-12-25','Natal','nacional',true),
  ('2026-01-01','Confraternização Universal','nacional',true),
  ('2026-02-16','Carnaval (segunda-feira)','ponto_facultativo',false),
  ('2026-02-17','Carnaval (terça-feira)','ponto_facultativo',false),
  ('2026-04-03','Paixão de Cristo (Sexta-feira Santa)','nacional',true),
  ('2026-04-21','Tiradentes','nacional',true),
  ('2026-05-01','Dia do Trabalho','nacional',true),
  ('2026-06-04','Corpus Christi','ponto_facultativo',false),
  ('2026-09-07','Independência do Brasil','nacional',true),
  ('2026-10-12','Nossa Senhora Aparecida','nacional',true),
  ('2026-11-02','Finados','nacional',true),
  ('2026-11-15','Proclamação da República','nacional',true),
  ('2026-11-20','Dia Nacional de Zumbi e da Consciência Negra','nacional',true),
  ('2026-12-25','Natal','nacional',true),
  ('2027-01-01','Confraternização Universal','nacional',true),
  ('2027-02-08','Carnaval (segunda-feira)','ponto_facultativo',false),
  ('2027-02-09','Carnaval (terça-feira)','ponto_facultativo',false),
  ('2027-03-26','Paixão de Cristo (Sexta-feira Santa)','nacional',true),
  ('2027-04-21','Tiradentes','nacional',true),
  ('2027-05-01','Dia do Trabalho','nacional',true),
  ('2027-05-27','Corpus Christi','ponto_facultativo',false),
  ('2027-09-07','Independência do Brasil','nacional',true),
  ('2027-10-12','Nossa Senhora Aparecida','nacional',true),
  ('2027-11-02','Finados','nacional',true),
  ('2027-11-15','Proclamação da República','nacional',true),
  ('2027-11-20','Dia Nacional de Zumbi e da Consciência Negra','nacional',true),
  ('2027-12-25','Natal','nacional',true),
  ('2028-01-01','Confraternização Universal','nacional',true),
  ('2028-02-28','Carnaval (segunda-feira)','ponto_facultativo',false),
  ('2028-02-29','Carnaval (terça-feira)','ponto_facultativo',false),
  ('2028-04-14','Paixão de Cristo (Sexta-feira Santa)','nacional',true),
  ('2028-04-21','Tiradentes','nacional',true),
  ('2028-05-01','Dia do Trabalho','nacional',true),
  ('2028-06-15','Corpus Christi','ponto_facultativo',false),
  ('2028-09-07','Independência do Brasil','nacional',true),
  ('2028-10-12','Nossa Senhora Aparecida','nacional',true),
  ('2028-11-02','Finados','nacional',true),
  ('2028-11-15','Proclamação da República','nacional',true),
  ('2028-11-20','Dia Nacional de Zumbi e da Consciência Negra','nacional',true),
  ('2028-12-25','Natal','nacional',true);

-- ---------------------------------------------------------------------
-- 3. Petições do processo (pePI): manifestação, recurso, oposição (quem se opôs)
--    Histórico preservado: cada protocolo visto fica gravado com a fonte.
-- ---------------------------------------------------------------------
create table process_peticoes (
  protocolo       text primary key,
  numero_processo text not null references processes(numero_processo),
  data            date,
  servico         text,
  descricao       text,
  cliente         text,
  fonte_url       text not null,
  verification_id bigint references inpi_verifications(id),
  visto_em        timestamptz not null default now()
);
create index process_peticoes_proc_idx on process_peticoes (numero_processo, data);
create trigger process_peticoes_audit after insert or update or delete on process_peticoes
  for each row execute function audit_row('protocolo');
alter table process_peticoes enable row level security;

-- ---------------------------------------------------------------------
-- 4. Oportunidades de serviço (uma por processo + serviço + edição que a originou)
-- ---------------------------------------------------------------------
create table oportunidades_servico (
  id                  bigserial primary key,
  numero_processo     text not null references processes(numero_processo),
  servico             text not null check (servico in ('manifestacao_oposicao','recurso_indeferimento')),
  tipo_decisao        text not null check (tipo_decisao in ('oposicao','indeferimento','deferimento_parcial')),
  edition_id          bigint not null references rpi_editions(id),
  rpi_numero          int not null,
  despacho_codigo     text not null,
  data_publicacao     date,
  elegivel            boolean not null default true,
  motivo_descarte     text,
  fundamentacao       text,
  -- oposição sofrida (o lead é o TITULAR; quem se opôs é só informação complementar)
  oposicao_protocolo  text,
  oposicao_data       date,
  opositor_nome       text,
  opositor_fonte      text,
  -- prazo
  prazo_inicio        date,
  prazo_fim           date,
  prazo_status        text not null default 'validar'
                      check (prazo_status in ('em_andamento','proximo_fim','encerrado','validar')),
  prazo_fonte         text,
  validacao_juridica  boolean not null default false,
  validacao_motivo    text,
  -- medida já apresentada (manifestação ou recurso)
  medida_status       text not null default 'nao_verificada'
                      check (medida_status in ('nao_verificada','nao_identificada','protocolada')),
  medida_protocolo    text,
  medida_data         date,
  medida_fonte        text,
  decisao_posterior   text,          -- despacho posterior que encerra a oportunidade (ex.: deferimento, arquivamento)
  situacao_processual text not null default 'pendente'
                      check (situacao_processual in ('aberta','historico','pendente')),
  classificacao       text check (classificacao in ('quente','morno','historico','pendente')),
  classificacao_motivos jsonb not null default '[]',
  analisado_em        timestamptz,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  unique (numero_processo, servico, edition_id)
);
create index oportunidades_servico_idx on oportunidades_servico (servico, situacao_processual, classificacao);
create index oportunidades_servico_prazo_idx on oportunidades_servico (prazo_fim) where situacao_processual = 'aberta';
create trigger oportunidades_servico_updated before update on oportunidades_servico
  for each row execute function set_updated_at();
create trigger oportunidades_servico_audit after insert or update or delete on oportunidades_servico
  for each row execute function audit_row('id');
alter table oportunidades_servico enable row level security;

-- ---------------------------------------------------------------------
-- 5. Classificação comercial do lead por pipeline
-- ---------------------------------------------------------------------
alter table leads
  add column servico_principal      text check (servico_principal in ('manifestacao_oposicao','recurso_indeferimento')),
  add column classificacao_oposicao text check (classificacao_oposicao in ('quente','morno','historico','pendente')),
  add column classificacao_recurso  text check (classificacao_recurso in ('quente','morno','historico','pendente'));
alter table leads drop constraint leads_temperatura_check;
alter table leads add constraint leads_temperatura_check check (temperatura in ('quente','morno','em_pesquisa','historico'));
create index leads_servico_idx on leads (servico_principal) where mesclado_em is null;

-- ---------------------------------------------------------------------
-- 6. Agendamentos: prazos mudam com o calendário → reanálise diária; histórico das últimas edições
-- ---------------------------------------------------------------------
insert into schedules (nome, tipo, intervalo_minutos, proximo_em)
values ('prazos-servicos', 'servicos.analisar', 360, now())
on conflict (nome) do nothing;

-- Recaptura da última edição (deferimentos parciais, recursos e decisões dos processos acompanhados)
-- e busca das 9 edições anteriores (~60 dias), para cruzar oposições e indeferimentos ainda dentro do prazo.
insert into jobs (tipo, payload, dedupe_key, prioridade)
select 'rpi.parse', jsonb_build_object('numero', e.numero), 'rpi.parse:' || e.numero, 30
  from rpi_editions e where e.status = 'parsed' order by e.numero desc limit 1
on conflict do nothing;
insert into jobs (tipo, payload, dedupe_key, prioridade)
select 'rpi.historico', jsonb_build_object('edicoes', 9), 'rpi.historico', 40
 where exists (select 1 from rpi_editions where status = 'parsed')
on conflict do nothing;
