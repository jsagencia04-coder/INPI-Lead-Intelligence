-- V2.6 · Correção da coleta da RPI e organização comercial (oposição → indeferimento; SC → RS → PR; mapa → pipeline).
-- Incremental e reversível: só cria tabelas, colunas, funções e registros de configuração. Nada é apagado.
-- Registros de edições anteriores ao corte NÃO são excluídos: saem da operação e o estado anterior fica guardado em
-- corte_rpi_backup, de onde volta automaticamente se a edição mínima for reduzida.

-- ---------------------------------------------------------------------
-- 1. Edição mínima operacional da RPI (fonte única em tempo de execução: app_config 'rpi_edicao_minima',
--    sincronizada na subida da API e do worker a partir de RPI_EDICAO_MINIMA / MIN_RPI_EDITION)
-- ---------------------------------------------------------------------
insert into app_config (chave, valor) values ('rpi_edicao_minima', '2914') on conflict (chave) do nothing;

create or replace function rpi_edicao_minima() returns int language sql stable as $$
  select valor::int from app_config where chave = 'rpi_edicao_minima'
$$;

create table corte_rpi_backup (
  tabela            text   not null check (tabela in ('opportunities','oportunidades_servico')),
  registro_id       bigint not null,
  status_anterior   text,
  motivo_anterior   text,
  elegivel_anterior boolean,
  edicao            int    not null,
  aplicado_em       timestamptz not null default now(),
  primary key (tabela, registro_id)
);
alter table corte_rpi_backup enable row level security;

-- Aplica o corte (idempotente): tira da operação o que é de edição anterior à mínima e devolve o que voltou a valer.
create or replace function aplicar_corte_rpi() returns jsonb language plpgsql as $$
declare
  minimo int := rpi_edicao_minima();
  motivo text := 'fora do corte: RPI anterior à edição mínima operacional (' || minimo || ')';
  a int; b int; c int; d int;
begin
  -- devolve o que agora está dentro do corte
  update opportunities o set status = k.status_anterior, motivo_descarte = k.motivo_anterior
    from corte_rpi_backup k, rpi_editions e
   where k.tabela = 'opportunities' and k.registro_id = o.id and e.id = o.edition_id and e.numero >= minimo;
  get diagnostics c = row_count;
  delete from corte_rpi_backup k using opportunities o, rpi_editions e
   where k.tabela = 'opportunities' and k.registro_id = o.id and e.id = o.edition_id and e.numero >= minimo;
  update oportunidades_servico s set elegivel = k.elegivel_anterior, motivo_descarte = k.motivo_anterior
    from corte_rpi_backup k
   where k.tabela = 'oportunidades_servico' and k.registro_id = s.id and s.rpi_numero >= minimo;
  get diagnostics d = row_count;
  delete from corte_rpi_backup k using oportunidades_servico s
   where k.tabela = 'oportunidades_servico' and k.registro_id = s.id and s.rpi_numero >= minimo;

  -- guarda e retira o que está abaixo do corte
  insert into corte_rpi_backup (tabela, registro_id, status_anterior, motivo_anterior, edicao)
  select 'opportunities', o.id, o.status, o.motivo_descarte, e.numero
    from opportunities o join rpi_editions e on e.id = o.edition_id
   where e.numero < minimo and o.status = 'elegivel'
  on conflict do nothing;
  update opportunities o set status = 'descartada', motivo_descarte = motivo
    from rpi_editions e where e.id = o.edition_id and e.numero < minimo and o.status = 'elegivel';
  get diagnostics a = row_count;
  insert into corte_rpi_backup (tabela, registro_id, elegivel_anterior, motivo_anterior, edicao)
  select 'oportunidades_servico', s.id, s.elegivel, s.motivo_descarte, s.rpi_numero
    from oportunidades_servico s where s.rpi_numero < minimo and s.elegivel
  on conflict do nothing;
  update oportunidades_servico set elegivel = false, motivo_descarte = motivo where rpi_numero < minimo and elegivel;
  get diagnostics b = row_count;
  return jsonb_build_object('edicao_minima', minimo, 'oportunidades_retiradas', a, 'servicos_retirados', b,
                            'oportunidades_devolvidas', c, 'servicos_devolvidos', d);
end $$;

select aplicar_corte_rpi();

-- ---------------------------------------------------------------------
-- 2. Catálogo de despachos: prioridade e finalidade comercial, com a fonte da validação
-- ---------------------------------------------------------------------
alter table despacho_types
  add column prioridade_comercial smallint check (prioridade_comercial in (1, 2)),
  add column finalidade_comercial text,
  add column vigencia             text,
  add column fonte_validacao      text;

update despacho_types set prioridade_comercial = 1, finalidade_comercial = 'Manifestação à oposição',
       fonte_validacao = 'XML oficial da RPI 2914 (revistas.inpi.gov.br/rpi), 481 ocorrências; nome oficial "Notificação de oposição"'
 where codigo = 'IPAS423';
update despacho_types set prioridade_comercial = 2, finalidade_comercial = 'Avaliação e eventual recurso administrativo',
       fonte_validacao = 'XML oficial da RPI 2914 (revistas.inpi.gov.br/rpi); nome oficial "' || nome || '"'
 where codigo in ('IPAS024', 'IPAS658', 'IPAS774', 'IPAS781');
update despacho_types set finalidade_comercial = 'Não é oposição apresentada (pedido apenas publicado para oposição)',
       fonte_validacao = 'XML oficial da RPI 2914: "' || nome || '"'
 where codigo in ('IPAS009', 'IPAS756');

-- Prioridade comercial de uma oportunidade de serviço: 1 = oposição apresentada, 2 = indeferimento (e parcial)
create or replace function prioridade_servico(p_servico text) returns int language sql immutable as $$
  select case p_servico when 'manifestacao_oposicao' then 1 when 'recurso_indeferimento' then 2 end
$$;
create or replace function prioridade_categoria(p_categoria text) returns int language sql immutable as $$
  select case p_categoria when 'oposicao_apresentada' then 1 when 'indeferimento' then 2 when 'deferimento_parcial' then 2 end
$$;

-- Versão do catálogo ativo: se mudar depois que uma edição foi lida, a edição precisa ser relida.
create or replace function catalogo_versao() returns text language sql stable as $$
  select md5(coalesce(string_agg(codigo || ':' || categoria_comercial, ',' order by codigo), ''))
    from despacho_types where ativo_para_leads
$$;

-- ---------------------------------------------------------------------
-- 3. Auditoria por edição
-- ---------------------------------------------------------------------
alter table rpi_editions
  add column catalogo_versao text,
  add column auditoria       jsonb not null default '{}';

-- ---------------------------------------------------------------------
-- 4. Representação (procurador): estados distintos; só SEM_PROCURADOR_CONFIRMADO entra na prospecção
--    (decisão do usuário: ausência de <procurador> no XML oficial lido por inteiro conta como confirmação)
-- ---------------------------------------------------------------------
alter table processes drop constraint processes_procurador_status_check;
alter table processes add constraint processes_procurador_status_check
  check (procurador_status in ('com_procurador','sem_confirmado','sem_na_rpi','desconhecido','erro_identificacao'));

create or replace function procurador_situacao(p_status text) returns text language sql immutable as $$
  select case p_status
           when 'com_procurador' then 'COM_PROCURADOR'
           when 'sem_confirmado' then 'SEM_PROCURADOR_CONFIRMADO'
           when 'sem_na_rpi' then 'SEM_PROCURADOR_CONFIRMADO'
           when 'erro_identificacao' then 'ERRO_NA_IDENTIFICACAO'
           else 'PROCURADOR_DESCONHECIDO' end
$$;

-- ---------------------------------------------------------------------
-- 5. Pipeline: etapas descritas (fases do funil) e vínculo explícito processo → lead
-- ---------------------------------------------------------------------
create table pipeline_etapas (
  id        text primary key,
  nome      text not null,
  ordem     smallint not null unique,
  fase      text not null,
  cor       text not null,
  descricao text not null,
  automatica boolean not null,
  regra     text not null
);
insert into pipeline_etapas (id, nome, ordem, fase, cor, automatica, descricao, regra) values
  ('lead_novo','Lead novo',1,'Identificação','#64748b',true,'Titular identificado na RPI, ainda sem pesquisa.','Entrada'),
  ('investigando','Investigando',2,'Identificação','#6366f1',true,'Pesquisa de dados e contatos em andamento.','Automática: pesquisa iniciada'),
  ('contato_identificado','Contato identificado',3,'Identificação','#0ea5e9',true,'Há contato encontrado, ainda não validado.','Automática: contato registrado'),
  ('contato_validado','Contato validado',4,'Identificação','#0891b2',true,'Contato confirmado por domínio ou por uma pessoa.','Automática: contato validado'),
  ('aguardando_autorizacao','Aguardando autorização',5,'Elegibilidade','#f59e0b',true,'Lead aprovado com WhatsApp, sem autorização registrada.','Automática: lead aprovado e WhatsApp com evidência'),
  ('elegivel_primeiro_contato','Elegível para primeiro contato',6,'Elegibilidade','#84cc16',true,'Autorização do destinatário registrada.','Automática: autorização ativa e número fornecido pelo titular'),
  ('mensagem_programada','Mensagem programada',7,'Primeiro contato','#a855f7',true,'Mensagem aprovada e na fila de envio.','Automática: envio real na fila'),
  ('mensagem_enviada','Mensagem enviada',8,'Primeiro contato','#8b5cf6',true,'Envio confirmado pelo provedor ou contato registrado por pessoa.','Automática: só com confirmação de envio'),
  ('mensagem_entregue','Mensagem entregue',9,'Primeiro contato','#7c3aed',true,'Entrega confirmada pelo WhatsApp (não basta o aceite do provedor).','Automática: confirmação de entrega/leitura'),
  ('resposta_recebida','Resposta recebida',10,'Primeiro contato','#16a34a',true,'O titular respondeu. Resposta não é autorização para novos contatos.','Automática: mensagem recebida'),
  ('interessado','Interessado',11,'Negociação','#22c55e',false,'Interesse declarado pelo titular.','Manual, com evidência de resposta ou contato registrado'),
  ('reuniao','Reunião',12,'Negociação','#10b981',false,'Reunião marcada ou realizada.','Manual, com evidência de resposta ou contato registrado'),
  ('proposta_enviada','Proposta enviada',13,'Negociação','#14b8a6',false,'Proposta comercial enviada.','Manual, com evidência de resposta ou contato registrado'),
  ('negociacao','Negociação',14,'Negociação','#0d9488',false,'Condições em negociação.','Manual, com evidência de resposta ou contato registrado'),
  ('fechado','Fechado',15,'Resultado','#15803d',false,'Serviço contratado.','Manual'),
  ('perdido','Perdido',16,'Resultado','#b91c1c',false,'Oportunidade encerrada sem contratação.','Manual'),
  ('opt_out','Opt-out',17,'Resultado','#991b1b',true,'Pediu para não ser contatado: bloqueia novos contatos.','Automática e definitiva: sempre prevalece');
alter table pipeline_etapas enable row level security;

alter table leads
  add column pipeline_incluido_em  timestamptz,
  add column pipeline_incluido_por text;

create table pipeline_processos (
  id                      bigserial primary key,
  lead_id                 bigint not null references leads(id),
  numero_processo         text   not null unique references processes(numero_processo),
  oportunidade_servico_id bigint references oportunidades_servico(id),
  servico                 text check (servico in ('manifestacao_oposicao','recurso_indeferimento')),
  rpi_numero              int,
  etapa_inicial           text not null references pipeline_etapas(id),
  adicionado_por          text not null default app_actor(),
  adicionado_em           timestamptz not null default now()
);
create index pipeline_processos_lead_idx on pipeline_processos (lead_id);
create trigger pipeline_processos_audit after insert or update or delete on pipeline_processos
  for each row execute function audit_row('id');
alter table pipeline_processos enable row level security;

-- ---------------------------------------------------------------------
-- 6. Fila: tarefas da RPI nunca mais ficam atrás de pesquisas e verificações em massa
-- ---------------------------------------------------------------------
update jobs set prioridade = least(prioridade, 10) where status = 'queued' and tipo in ('rpi.discover','rpi.collect','rpi.parse');
update jobs set prioridade = least(prioridade, 20) where status = 'queued' and tipo in ('leads.build','servicos.analisar');
