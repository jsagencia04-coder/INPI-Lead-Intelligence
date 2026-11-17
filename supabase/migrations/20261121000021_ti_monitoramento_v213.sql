-- V2.13 · Setor de TI (Julio): monitoramento contínuo do sistema, de terça a terça.
-- Cada verificação grava um retrato da saúde do sistema; transições de estado viram eventos (alerta no painel).
create table if not exists system_health (
  id         bigserial primary key,
  status     text        not null check (status in ('ok', 'atencao', 'falha')),
  checks     jsonb       not null,
  acoes      jsonb       not null default '[]',   -- correções automáticas feitas nesta verificação
  criado_em  timestamptz not null default now()
);
create index if not exists system_health_em_idx on system_health (criado_em desc);
alter table system_health enable row level security;

insert into schedules (nome, tipo, intervalo_minutos, proximo_em)
values ('ti-monitor', 'sistema.saude', 5, now())
on conflict (nome) do nothing;
