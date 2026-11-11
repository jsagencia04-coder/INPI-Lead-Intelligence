-- V2.0 · Fase 12 — Segurança: ambientes, usuários com papéis, bloqueio de dados fictícios, auditoria completa.
-- Incremental: só cria. Nenhum dado existente é alterado ou apagado.

-- Ambiente do BANCO (demo | homologacao | producao). A API confere ao iniciar e recusa
-- apontar um ambiente inferior para um banco de ambiente superior. O ambiente só sobe, nunca desce.
create table app_config (
  chave text primary key,
  valor text not null,
  atualizado_em timestamptz not null default now()
);
insert into app_config (chave, valor) values ('ambiente', 'demo');
create trigger app_config_audit after insert or update or delete on app_config
  for each row execute function audit_row('chave');
alter table app_config enable row level security;

-- Usuários do login próprio e papéis (valem também para o login via Supabase, pelo e-mail).
--   leitor   vê tudo, não altera nada
--   operador importa RPI, dispara pesquisas, registra contatos e prospecções, exporta
--   revisor  aprova leads, confirma contatos, prepara mensagens
--   admin    usuários, agenda, classificação de despachos, jobs avulsos
create table app_users (
  id            bigserial primary key,
  email         text not null unique check (email = lower(email)),
  nome          text,
  papel         text not null check (papel in ('admin','revisor','operador','leitor')),
  senha_hash    text,                      -- scrypt; nulo = só entra via Supabase
  ativo         boolean not null default true,
  falhas        int not null default 0,
  bloqueado_ate timestamptz,
  ultimo_login  timestamptz,
  criado_por    text not null default app_actor(),
  criado_em     timestamptz not null default now()
);
alter table app_users enable row level security;

-- Auditoria própria: registra tudo, MENOS o hash da senha e os contadores de login.
create or replace function app_users_audit() returns trigger language plpgsql as $$
declare
  antes  jsonb := case when tg_op in ('UPDATE','DELETE') then to_jsonb(old) - 'senha_hash' - 'falhas' - 'ultimo_login' - 'bloqueado_ate' end;
  depois jsonb := case when tg_op in ('INSERT','UPDATE') then to_jsonb(new) - 'senha_hash' - 'falhas' - 'ultimo_login' - 'bloqueado_ate' end;
begin
  if tg_op = 'UPDATE' then
    if old.senha_hash is distinct from new.senha_hash then
      depois := depois || '{"senha_alterada": true}';
    elsif antes = depois then
      return new;
    end if;
  end if;
  insert into audit_log (tabela, registro_id, acao, antes, depois)
  values ('app_users', coalesce(new.id, old.id)::text, tg_op, antes, depois);
  return coalesce(new, old);
end $$;
create trigger app_users_audit after insert or update or delete on app_users
  for each row execute function app_users_audit();

-- Domínios reservados para exemplos e testes (RFC 2606 / RFC 6761) e endereços internos.
create or replace function dominio_reservado(host text) returns boolean language sql immutable as $$
  select lower(coalesce(host, '')) ~
    '(^|\.)(example\.(com|net|org)|exemplo\.com(\.br)?|localhost)$|\.(invalid|test|example|localhost|local|internal|lan)$|^[0-9.]+$|^\[?[0-9a-f:]+\]?$'
$$;

create or replace function host_de(valor text) returns text language sql immutable as $$
  select split_part(split_part(split_part(regexp_replace(lower(valor), '^[a-z][a-z0-9+.-]*://', ''), '/', 1), '@', -1), ':', 1)
$$;

-- Fora do ambiente demo, contatos e evidências com domínio fictício são recusados pelo próprio banco.
create or replace function bloqueia_dado_ficticio() returns trigger language plpgsql as $$
declare
  h text;
begin
  if (select valor from app_config where chave = 'ambiente') = 'demo' then
    return new;
  end if;
  if tg_table_name = 'contacts' then
    if new.tipo not in ('email','site') then return new; end if;
    h := host_de(new.valor_normalizado);
  else
    if new.url !~* '^https?://' then return new; end if;
    h := host_de(new.url);
  end if;
  if dominio_reservado(h) then
    raise exception 'Dado fictício recusado fora do ambiente demo: domínio reservado (%)', h using errcode = '23514';
  end if;
  return new;
end $$;
create trigger contacts_sem_ficticio before insert or update of valor_normalizado on contacts
  for each row execute function bloqueia_dado_ficticio();
create trigger evidences_sem_ficticio before insert on evidences
  for each row execute function bloqueia_dado_ficticio();

-- Auditoria nas tabelas que ainda não tinham.
create trigger publications_audit after insert or update or delete on publications
  for each row execute function audit_row('id');
create trigger lead_processes_audit after insert or update or delete on lead_processes
  for each row execute function audit_row('lead_id');
create trigger research_runs_audit after insert or update or delete on research_runs
  for each row execute function audit_row('id');
create trigger reports_audit after insert or update or delete on reports
  for each row execute function audit_row('id');
create trigger exports_log_audit after insert or update or delete on exports_log
  for each row execute function audit_row('id');
