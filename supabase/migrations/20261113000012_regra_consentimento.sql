-- V2.0 · Fase 8 — Regra de consentimento completa.
-- Incremental: uma coluna e uma tabela. Nada é apagado.

-- O destinatário forneceu ele mesmo o número? (número achado em página pública = false)
alter table consents add column numero_fornecido boolean not null default false;

-- Pedidos de autorização feitos por OUTRO canal (ex.: e-mail). O envio do pedido é manual; aqui fica o registro.
create table consent_requests (
  id              bigserial primary key,
  contact_id      bigint not null references contacts(id),   -- contato para o qual se quer autorização (o WhatsApp)
  via_contact_id  bigint references contacts(id),            -- contato usado para pedir (ex.: e-mail da empresa)
  canal_pedido    text   not null check (canal_pedido in ('email','telefone','presencial','outro')),
  finalidade      text   not null,
  texto           text   not null,
  versao_aviso    text   not null,
  status          text   not null default 'enviado' check (status in ('enviado','autorizado','recusado','sem_resposta')),
  consent_id      bigint references consents(id),
  criado_por      text   not null default app_actor(),
  criado_em       timestamptz not null default now(),
  respondido_em   timestamptz
);
create index consent_requests_contact_idx on consent_requests (contact_id, criado_em desc);
create trigger consent_requests_audit after insert or update or delete on consent_requests
  for each row execute function audit_row('id');
alter table consent_requests enable row level security;
