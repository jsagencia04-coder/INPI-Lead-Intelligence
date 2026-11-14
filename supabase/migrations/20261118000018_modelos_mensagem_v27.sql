-- V2.7 · Três modelos de primeira mensagem (editáveis no banco) e envio direto pelo backend (Evolution).
-- Incremental: cria tabelas, colunas e configurações. Nada é apagado. Os textos ficam no banco, não no código.

-- ---------------------------------------------------------------------
-- 1. Modelos
-- ---------------------------------------------------------------------
create table wa_modelos (
  id                 bigserial primary key,
  codigo             text not null unique check (codigo in ('MODELO_01','MODELO_02','MODELO_03')),
  nome               text not null,
  descricao          text not null,
  tipo_oportunidade  text not null check (tipo_oportunidade in ('oposicao','indeferimento','institucional')),
  finalidade         text not null,
  texto              text not null check (length(texto) between 20 and 1500),
  ativo              boolean not null default true,
  versao             int not null default 1,
  atualizado_em      timestamptz not null default now(),
  atualizado_por     text not null default app_actor()
);
create trigger wa_modelos_audit after insert or update or delete on wa_modelos for each row execute function audit_row('codigo');
alter table wa_modelos enable row level security;

-- cada versão salva fica guardada (imutável)
create table wa_modelos_historico (
  id          bigserial primary key,
  modelo_id   bigint not null references wa_modelos(id),
  versao      int not null,
  nome        text not null,
  texto       text not null,
  ativo       boolean not null,
  alterado_por text not null,
  alterado_em timestamptz not null default now(),
  unique (modelo_id, versao)
);
create trigger wa_modelos_historico_immutable before update or delete on wa_modelos_historico
  for each row execute function forbid_mutation();
alter table wa_modelos_historico enable row level security;

insert into wa_modelos (codigo, nome, descricao, tipo_oportunidade, finalidade, texto, atualizado_por) values
('MODELO_01', 'Oposição apresentada',
 'Para titulares cujo pedido recebeu oposição de terceiro (despacho IPAS423). Oferece manifestação à oposição.',
 'oposicao', 'Manifestação à oposição',
 E'Olá, {{nome_titular}}! Aqui é {{nome_atendente}}, da {{empresa}}.\n\nNa Revista da Propriedade Industrial nº {{edicao_rpi}} foi publicada uma oposição de terceiro contra o pedido da marca {{marca}} (processo {{numero_processo}}). Existe um prazo legal para apresentar manifestação, que vale confirmar no próprio processo.\n\nTrabalhamos com manifestações à oposição e posso explicar como funciona, sem compromisso. Podemos conversar?\n\nSe preferir não receber mensagens, responda SAIR.',
 'sistema:migration'),
('MODELO_02', 'Pedido indeferido',
 'Para titulares cujo pedido foi indeferido (ou parcialmente). Oferece avaliação e eventual recurso administrativo.',
 'indeferimento', 'Avaliação e eventual recurso',
 E'Olá, {{nome_titular}}! Aqui é {{nome_atendente}}, da {{empresa}}.\n\nNa Revista da Propriedade Industrial nº {{edicao_rpi}} foi publicado o {{tipo_despacho}} do pedido da marca {{marca}} (processo {{numero_processo}}). Em muitos casos cabe recurso administrativo dentro do prazo legal, que vale confirmar no próprio processo.\n\nPosso avaliar o caso e explicar as possibilidades, sem compromisso. Podemos conversar?\n\nSe preferir não receber mensagens, responda SAIR.',
 'sistema:migration'),
('MODELO_03', 'Abordagem institucional',
 'Para outros casos comerciais elegíveis. Apresentação do serviço a partir de uma publicação real do processo.',
 'institucional', 'Apresentação institucional',
 E'Olá, {{nome_titular}}! Aqui é {{nome_atendente}}, da {{empresa}}.\n\nAcompanhamos as publicações do INPI e vimos uma movimentação no processo {{numero_processo}}, da marca {{marca}}, na Revista da Propriedade Industrial nº {{edicao_rpi}}.\n\nTrabalhamos com registro e acompanhamento de marcas. Posso explicar o que essa publicação significa, sem compromisso?\n\nSe preferir não receber mensagens, responda SAIR.',
 'sistema:migration');
insert into wa_modelos_historico (modelo_id, versao, nome, texto, ativo, alterado_por)
select id, versao, nome, texto, ativo, atualizado_por from wa_modelos;

-- dados do remetente usados nas variáveis {{nome_atendente}} e {{empresa}} (editáveis na tela, sem publicar versão)
insert into app_config (chave, valor) values ('primeiro_contato_atendente', ''), ('primeiro_contato_empresa', ''),
  ('whatsapp_limite_diario', '20') on conflict (chave) do nothing;

-- ---------------------------------------------------------------------
-- 2. Rascunho personalizado = versão independente do modelo, presa ao modelo e à finalidade
-- ---------------------------------------------------------------------
alter table wa_rascunhos
  add column modelo_id      bigint references wa_modelos(id),
  add column modelo_versao  int,
  add column modelo_texto   text,            -- texto do modelo no momento da personalização (o modelo pode mudar depois)
  add column finalidade     text,
  add column variaveis      jsonb not null default '{}',
  add column alertas        jsonb not null default '[]';

-- ---------------------------------------------------------------------
-- 3. Envio: modelo usado, chave de idempotência do clique e aviso de resposta ao operador
-- ---------------------------------------------------------------------
alter table wa_messages
  add column modelo_id bigint references wa_modelos(id),
  add column visto_em  timestamptz;          -- resposta recebida já vista por uma pessoa (notificação na tela)
