-- V2.3 · Mapa de oportunidades, monitoramento semanal da RPI, prioridade territorial e temperatura dos leads.
-- Incremental: acrescenta colunas, tabelas e agendamentos. Nada é apagado; dados existentes são preservados.

-- ---------------------------------------------------------------------
-- 1. Oposição apresentada (categoria A) × pedido publicado para oposição (categoria B)
-- ---------------------------------------------------------------------
alter table despacho_types drop constraint despacho_types_categoria_comercial_check;
alter table despacho_types add constraint despacho_types_categoria_comercial_check check (categoria_comercial in
  ('oposicao_apresentada','oposicao','exigencia','indeferimento','extincao_prorrogacao','arquivamento','outro'));

-- IPAS423 "Notificação de oposição": um terceiro apresentou oposição e o titular é notificado para se manifestar.
-- Só é reclassificado se ninguém mudou a configuração original (respeita decisões do usuário).
update despacho_types
   set categoria_comercial = 'oposicao_apresentada', ativo_para_leads = true,
       fonte = fonte || ' · V2.3: oposição apresentada (categoria A)'
 where codigo = 'IPAS423' and categoria_comercial = 'outro' and not ativo_para_leads and confirmado_por is null;

-- Data e número do protocolo da oposição, extraídos do XML oficial (petição citada no despacho)
create or replace function publicacao_protocolo_data(p jsonb) returns date language sql immutable as $$
  select case when (p -> 0 ->> 'data') ~ '^\d{2}/\d{2}/\d{4}$' then to_date(p -> 0 ->> 'data', 'DD/MM/YYYY') end
$$;

-- ---------------------------------------------------------------------
-- 2. Localização do titular: confirmada (Receita) > estimada (declarada na RPI) > pendente
-- ---------------------------------------------------------------------
alter table holders
  add column geo_uf        char(2),
  add column geo_municipio text,
  add column geo_fonte     text check (geo_fonte in ('receita','rpi','manual')),
  add column geo_status    text not null default 'pendente' check (geo_status in ('confirmada','estimada','pendente')),
  add column geo_atualizado_em timestamptz;
create index holders_geo_idx on holders (geo_uf, geo_status);

create table cnpj_municipios (
  codigo text primary key,         -- código da Receita (tabela de municípios do dump aberto)
  nome   text not null
);
alter table cnpj_municipios enable row level security;

-- Atualiza a localização de todos os titulares (ou de um). A escolha manual nunca é sobrescrita.
create or replace function geo_atualizar(p_holder bigint default null) returns int language plpgsql as $$
declare n int;
begin
  update holders h set
         geo_uf = x.uf, geo_municipio = x.municipio, geo_fonte = x.fonte, geo_status = x.status, geo_atualizado_em = now()
    from (
      select h2.id,
             case when e.uf is not null then e.uf
                  when h2.pais = 'BR' and h2.uf ~ '^[A-Z]{2}$' then h2.uf end as uf,
             case when e.uf is not null then m.nome end as municipio,
             case when e.uf is not null then 'receita' when h2.pais = 'BR' and h2.uf ~ '^[A-Z]{2}$' then 'rpi' end as fonte,
             case when e.uf is not null then 'confirmada'
                  when h2.pais = 'BR' and h2.uf ~ '^[A-Z]{2}$' then 'estimada' else 'pendente' end as status
        from holders h2
        left join cnpj_estabelecimentos e on e.cnpj = h2.cnpj and h2.cnpj_status in ('encontrado','manual')
        left join cnpj_municipios m on m.codigo = e.municipio_codigo
       where (p_holder is null or h2.id = p_holder) and h2.geo_fonte is distinct from 'manual'
    ) x
   where h.id = x.id
     and (h.geo_uf, h.geo_municipio, h.geo_fonte, h.geo_status) is distinct from (x.uf, x.municipio, x.fonte, x.status);
  get diagnostics n = row_count;
  return n;
end $$;

-- ---------------------------------------------------------------------
-- 3. Prioridade territorial (configurável): SC, RS, PR e depois os demais
-- ---------------------------------------------------------------------
create table uf_prioridade (
  uf     char(2) primary key,
  nome   text not null,
  regiao text not null,
  ordem  smallint not null,
  ativo  boolean not null default true
);
insert into uf_prioridade (uf, nome, regiao, ordem) values
  ('SC','Santa Catarina','Sul',1), ('RS','Rio Grande do Sul','Sul',2), ('PR','Paraná','Sul',3),
  ('SP','São Paulo','Sudeste',4), ('RJ','Rio de Janeiro','Sudeste',5), ('MG','Minas Gerais','Sudeste',6),
  ('ES','Espírito Santo','Sudeste',7), ('DF','Distrito Federal','Centro-Oeste',8), ('GO','Goiás','Centro-Oeste',9),
  ('MS','Mato Grosso do Sul','Centro-Oeste',10), ('MT','Mato Grosso','Centro-Oeste',11), ('BA','Bahia','Nordeste',12),
  ('PE','Pernambuco','Nordeste',13), ('CE','Ceará','Nordeste',14), ('RN','Rio Grande do Norte','Nordeste',15),
  ('PB','Paraíba','Nordeste',16), ('AL','Alagoas','Nordeste',17), ('SE','Sergipe','Nordeste',18), ('PI','Piauí','Nordeste',19),
  ('MA','Maranhão','Nordeste',20), ('PA','Pará','Norte',21), ('AM','Amazonas','Norte',22), ('TO','Tocantins','Norte',23),
  ('RO','Rondônia','Norte',24), ('AC','Acre','Norte',25), ('AP','Amapá','Norte',26), ('RR','Roraima','Norte',27);
create trigger uf_prioridade_audit after insert or update or delete on uf_prioridade
  for each row execute function audit_row('uf');
alter table uf_prioridade enable row level security;

-- Prioridade de fila para trabalho de um titular: SC=15, RS=20, PR=25, demais 30+, localização pendente por último.
create or replace function prioridade_fila_uf(p_uf text) returns int language sql stable as $$
  select coalesce((select 10 + 5 * least(ordem, 6) + greatest(ordem - 6, 0) from uf_prioridade where uf = p_uf and ativo), 120)
$$;

-- ---------------------------------------------------------------------
-- 4. Temperatura comercial do lead (quente / morno / em pesquisa), com os motivos
-- ---------------------------------------------------------------------
alter table leads
  add column temperatura text check (temperatura in ('quente','morno','em_pesquisa')),
  add column temperatura_motivos jsonb not null default '[]';
create index leads_temperatura_idx on leads (temperatura) where mesclado_em is null;

-- ---------------------------------------------------------------------
-- 5. Operação semanal da RPI (marcos registrados com data e hora)
-- ---------------------------------------------------------------------
create table rpi_operacoes (
  edition_id               bigint primary key references rpi_editions(id),
  iniciada_em              timestamptz not null default now(),
  priorizada_em            timestamptz,
  sc_primeiros_quentes_em  timestamptz,
  concluida_em             timestamptz,
  ultima_verificacao_em    timestamptz,
  execucoes                int not null default 0,
  detalhes                 jsonb not null default '{}'
);
create trigger rpi_operacoes_audit after insert or update or delete on rpi_operacoes
  for each row execute function audit_row('edition_id');
alter table rpi_operacoes enable row level security;

-- ---------------------------------------------------------------------
-- 6. Agenda com janela de dias e horário (fuso America/Sao_Paulo)
-- ---------------------------------------------------------------------
alter table schedules
  add column dias_semana smallint[],             -- ISO: 1 = segunda ... 7 = domingo; nulo = todos os dias
  add column hora_inicio time,
  add column hora_fim    time,
  add column fuso        text not null default 'America/Sao_Paulo';

-- Terça (e quarta, para atrasos e feriados): verifica a RPI a cada 10 min das 05h às 23h59.
insert into schedules (nome, tipo, intervalo_minutos, dias_semana, hora_inicio, hora_fim, proximo_em)
values ('rpi-terca', 'rpi.discover', 10, '{2,3}', '05:00', '23:59', now())
on conflict (nome) do nothing;
-- Acompanha a operação da semana (marcos, alerta dos primeiros leads quentes de SC) a cada 10 min.
insert into schedules (nome, tipo, intervalo_minutos, proximo_em)
values ('operacao-semanal', 'rpi.semana_check', 10, now())
on conflict (nome) do nothing;

-- ---------------------------------------------------------------------
-- 7. Recaptura da última edição para incluir as oposições apresentadas (IPAS423) que antes não eram gravadas.
--    Reprocessar é idempotente: publicações e oportunidades não se duplicam.
-- ---------------------------------------------------------------------
insert into jobs (tipo, payload, dedupe_key, prioridade)
select 'rpi.parse', jsonb_build_object('numero', e.numero), 'rpi.parse:' || e.numero, 30
  from rpi_editions e
 where e.status = 'parsed'
   and exists (select 1 from despacho_types where codigo = 'IPAS423' and categoria_comercial = 'oposicao_apresentada')
 order by e.numero desc limit 1
on conflict do nothing;

select geo_atualizar();
