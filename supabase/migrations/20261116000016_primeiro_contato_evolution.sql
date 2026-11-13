-- V2.5 · Primeiro contato supervisionado (Evolution API, instância exclusiva "inpi-agent").
-- Incremental e reversível: só cria tabelas/colunas novas e amplia listas de valores. Nada é apagado.
-- Reaproveita: consents (autorização), suppression_list (opt-out), wa_messages (envio), wa_webhook_events (eventos).

-- ---------------------------------------------------------------------
-- 1. Conta/instância de envio (sem credenciais: chaves ficam só nas variáveis do backend)
-- ---------------------------------------------------------------------
create table wa_contas (
  id                bigserial primary key,
  provedor          text not null check (provedor in ('evolution','meta','manual')),
  instancia         text not null,
  segmento          text not null default 'INPI Agent',
  numero            text,                       -- número conectado, informado pela própria Evolution
  status_conexao    text not null default 'desconhecido',
  verificado_em     timestamptz,
  detalhes          jsonb not null default '{}', -- sem segredos
  criado_em         timestamptz not null default now(),
  unique (provedor, instancia)
);
create trigger wa_contas_audit after insert or update or delete on wa_contas for each row execute function audit_row('id');
alter table wa_contas enable row level security;

-- ---------------------------------------------------------------------
-- 2. Rascunhos de primeira mensagem, com aprovação presa ao conteúdo, ao número e ao canal
-- ---------------------------------------------------------------------
create table wa_rascunhos (
  id              bigserial primary key,
  lead_id         bigint not null references leads(id),
  contact_id      bigint not null references contacts(id),
  numero_processo text references processes(numero_processo),
  numero          text not null,                 -- E.164 do destinatário
  canal           text not null default 'evolution' check (canal in ('evolution','manual','meta')),
  conteudo        text not null check (length(conteudo) between 1 and 1500),
  conteudo_hash   char(64) not null,
  versao          int not null default 1,
  status          text not null default 'rascunho'
                  check (status in ('rascunho','aprovado','rejeitado','enviado','cancelado')),
  gerado_por      text not null,                 -- 'ia:<modelo>', 'modelo-padrao' ou o usuário que escreveu
  criado_por      text not null default app_actor(),
  aprovado_por    text,
  aprovado_em     timestamptz,
  aprovacao_hash  char(64),                      -- sha256(conteúdo | número | canal | versão) no momento da aprovação
  rejeitado_por   text,
  rejeitado_em    timestamptz,
  motivo          text,
  criado_em       timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  check ((status = 'aprovado') <= (aprovado_por is not null and aprovacao_hash is not null))
);
-- no máximo um rascunho em aberto por lead + contato
create unique index wa_rascunhos_aberto_idx on wa_rascunhos (lead_id, contact_id) where status in ('rascunho','aprovado');
create index wa_rascunhos_status_idx on wa_rascunhos (status, updated_at desc);
create trigger wa_rascunhos_updated before update on wa_rascunhos for each row execute function set_updated_at();
create trigger wa_rascunhos_audit after insert or update or delete on wa_rascunhos for each row execute function audit_row('id');
alter table wa_rascunhos enable row level security;

-- ---------------------------------------------------------------------
-- 3. Envio: wa_messages ganha provedor/instância/rascunho e o estado "reconciliar" (resultado desconhecido)
-- ---------------------------------------------------------------------
alter table wa_messages
  add column provedor   text not null default 'meta' check (provedor in ('meta','evolution','manual')),
  add column instancia  text,
  add column rascunho_id bigint references wa_rascunhos(id);
alter table wa_messages drop constraint wa_messages_status_check;
alter table wa_messages add constraint wa_messages_status_check check (status in
  ('simulada','na_fila','aceita','enviada','entregue','lida','falhou','bloqueada','cancelada','recebida','reconciliar'));
-- um único envio por rascunho aprovado (além da chave de idempotência por contato + processo)
create unique index wa_messages_rascunho_idx on wa_messages (rascunho_id)
  where rascunho_id is not null and status not in ('falhou','simulada','bloqueada','cancelada');

alter table wa_webhook_events add column provedor text not null default 'meta' check (provedor in ('meta','evolution'));

-- ---------------------------------------------------------------------
-- 4. Registro das ações humanas do primeiro contato (além da auditoria automática por tabela)
-- ---------------------------------------------------------------------
create table wa_auditoria (
  id        bigserial primary key,
  ator      text not null default app_actor(),
  lead_id   bigint references leads(id),
  acao      text not null,
  detalhes  jsonb not null default '{}',
  em        timestamptz not null default now()
);
create index wa_auditoria_lead_idx on wa_auditoria (lead_id, em desc);
create trigger wa_auditoria_immutable before update or delete on wa_auditoria for each row execute function forbid_mutation();
alter table wa_auditoria enable row level security;

-- ---------------------------------------------------------------------
-- 5. Botão de emergência: bloqueia novos envios no backend e no worker, sem redeploy
-- ---------------------------------------------------------------------
insert into app_config (chave, valor) values ('whatsapp_envio_bloqueado', 'false') on conflict (chave) do nothing;
