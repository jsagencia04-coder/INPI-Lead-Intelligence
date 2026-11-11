-- WhatsApp comercial como canal principal do primeiro contato.
alter table leads
  add column whatsapp        text,
  add column whatsapp_status text check (whatsapp_status in ('confirmado', 'validado', 'candidato'));
create index leads_whatsapp_idx on leads (whatsapp_status) where whatsapp_status is not null;

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
  (select count(*) from jobs where status in ('queued','running') and tipo like 'research.%') as pesquisas_pendentes,
  (select count(*) from jobs where status = 'running')                               as agentes_em_execucao,
  (select count(*) from review_tasks where status = 'aberta')                        as revisoes_abertas,
  (select count(*) from processes where procurador_status = 'sem_confirmado')         as procurador_ausente_confirmado,
  (select coalesce(sum(custo_usd), 0) from llm_calls
    where criado_em >= date_trunc('week', now()))                                    as custo_ia_semana_usd,
  (select count(*) from leads where status <> 'descartado' and mesclado_em is null
      and whatsapp_status in ('confirmado', 'validado'))                             as leads_whatsapp_validado;
