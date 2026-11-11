-- V2.0 · Fase 7 — WhatsApp Business Platform (Cloud API oficial): mensagens e webhooks.
-- Incremental: só cria tabelas. Status de entrega/leitura NUNCA é inventado:
-- 'aceita' vem da resposta da API; 'enviada', 'entregue', 'lida' e 'falhou' só vêm do webhook da Meta.

create table wa_messages (
  id               bigserial primary key,
  direcao          text not null check (direcao in ('saida','entrada')),
  modo             text not null default 'simulacao' check (modo in ('simulacao','real')),
  contact_id       bigint references contacts(id),
  lead_id          bigint references leads(id),
  numero_processo  text references processes(numero_processo),
  numero           text not null,                 -- E.164 do outro lado da conversa
  tipo             text not null default 'template' check (tipo in ('template','texto','outro')),
  template_nome    text,
  template_idioma  text,
  template_params  jsonb not null default '[]',
  corpo            text,                          -- texto recebido (entrada) ou prévia (saída)
  -- uma mensagem por contato + processo + template + regra: impede repetição
  idempotency_key  text unique,
  wa_message_id    text unique,                   -- id devolvido pela Meta
  status           text not null check (status in
                     ('simulada','na_fila','aceita','enviada','entregue','lida','falhou','bloqueada','cancelada','recebida')),
  motivo           text,                          -- por que foi bloqueada/cancelada/falhou
  erro_codigo      text,
  tentativas       int not null default 0,
  aceita_em        timestamptz,
  enviada_em       timestamptz,
  entregue_em      timestamptz,
  lida_em          timestamptz,
  falhou_em        timestamptz,
  recebida_em      timestamptz,
  criado_por       text not null default app_actor(),
  criado_em        timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);
create index wa_messages_lead_idx on wa_messages (lead_id, criado_em desc);
create index wa_messages_numero_idx on wa_messages (numero, criado_em desc);
create index wa_messages_status_idx on wa_messages (status) where status in ('na_fila','aceita');
create trigger wa_messages_updated before update on wa_messages
  for each row execute function set_updated_at();
create trigger wa_messages_audit after insert or update or delete on wa_messages
  for each row execute function audit_row('id');
alter table wa_messages enable row level security;

-- Tudo o que a Meta envia fica guardado como chegou (prova), sem alteração.
create table wa_webhook_events (
  id            bigserial primary key,
  recebido_em   timestamptz not null default now(),
  event_key     text not null unique,            -- dedupe: a Meta reenvia eventos
  tipo          text not null check (tipo in ('status','mensagem','outro')),
  wa_message_id text,
  payload       jsonb not null
);
create index wa_webhook_events_msg_idx on wa_webhook_events (wa_message_id);
create trigger wa_webhook_events_immutable before update or delete on wa_webhook_events
  for each row execute function forbid_mutation();
alter table wa_webhook_events enable row level security;

-- opt-out pode chegar pelo WhatsApp
alter table suppression_list add column origem text;
