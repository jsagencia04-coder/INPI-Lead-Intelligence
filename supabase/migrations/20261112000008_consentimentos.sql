-- V2.0 · Fase 8 (estrutura) — Consentimentos, e a view da Central de contatos (Fase 1).
-- Encontrar um número público NÃO é consentimento: só existe permissão quando há uma linha 'ativo' aqui,
-- registrada com método, fonte da evidência e texto da autorização.

create table consents (
  id                   bigserial primary key,
  contact_id           bigint not null references contacts(id),
  canal                text   not null check (canal in ('whatsapp','email','telefone')),
  finalidade           text   not null,
  empresa_identificada text   not null,          -- quem se apresentou ao pedir a autorização
  obtido_em            timestamptz not null,
  metodo               text   not null check (metodo in
                         ('resposta_whatsapp','email','formulario','telefone','presencial','contrato','outro')),
  fonte_evidencia      text   not null,          -- URL, id da mensagem, protocolo...
  texto_autorizacao    text   not null,
  versao_aviso         text   not null,
  status               text   not null default 'ativo' check (status in ('ativo','revogado','expirado')),
  revogado_em          timestamptz,
  revogacao_origem     text,
  registrado_por       text   not null default app_actor(),
  criado_em            timestamptz not null default now(),
  check ((status = 'revogado') = (revogado_em is not null))
);
create unique index consents_ativo_idx on consents (contact_id, canal, finalidade) where status = 'ativo';
create index consents_contact_idx on consents (contact_id);

-- Consentimento nunca é apagado: revoga-se (status + data), preservando a prova.
create or replace function consents_no_delete() returns trigger language plpgsql as $$
begin
  raise exception 'consents: registros não podem ser apagados (revogue em vez de apagar)';
end $$;
create trigger consents_no_delete before delete on consents
  for each row execute function consents_no_delete();
create trigger consents_audit after insert or update or delete on consents
  for each row execute function audit_row('id');
alter table consents enable row level security;

-- ---------------------------------------------------------------------
-- Central de contatos: uma linha por titular, com todos os contatos e a origem de cada um.
-- ---------------------------------------------------------------------
create view v_contact_central with (security_invoker = true) as
with c as (
  select c.id, c.holder_id, c.tipo, c.valor, c.valor_normalizado, c.verificacao, c.confianca, c.fonte_tipo,
         c.observacao, c.checado_em, c.ultima_vez_visto, c.created_at,
         c.eh_celular, c.wa_nivel, c.wa_conta, c.wa_comercial,
         e.url as fonte_url, e.titulo as fonte_titulo, e.trecho as fonte_trecho, e.obtido_em as fonte_obtida_em,
         exists (select 1 from suppression_list s
                  where s.valor_hash = encode(sha256(convert_to(c.valor_normalizado, 'UTF8')), 'hex')) as bloqueado,
         -- permissão = consentimento ativo E contato válido E fora do opt-out (o opt-out sempre prevalece)
         (c.verificacao <> 'invalido'
          and exists (select 1 from consents k where k.contact_id = c.id and k.status = 'ativo')
          and not exists (select 1 from suppression_list s
                           where s.valor_hash = encode(sha256(convert_to(c.valor_normalizado, 'UTF8')), 'hex'))) as com_permissao,
         case c.verificacao when 'verificado_humano' then 1 when 'dominio_ok' then 2 when 'formato_ok' then 3
                            when 'encontrado' then 4 else 5 end as ordem
    from contacts c join evidences e on e.id = c.evidence_id
), agg as (
  select holder_id,
         jsonb_agg(to_jsonb(c) - 'holder_id' - 'ordem' order by ordem, confianca desc nulls last, id) as contatos,
         count(*) filter (where verificacao <> 'invalido')                              as n_contatos,
         count(*) filter (where tipo = 'whatsapp' and verificacao <> 'invalido')        as n_whatsapp,
         count(*) filter (where tipo = 'telefone' and verificacao <> 'invalido')        as n_telefone,
         count(*) filter (where tipo = 'email' and verificacao <> 'invalido')           as n_email,
         count(*) filter (where verificacao in ('encontrado','formato_ok'))             as n_pendentes,
         count(*) filter (where verificacao = 'invalido')                               as n_invalidos,
         count(*) filter (where bloqueado)                                              as n_bloqueados,
         count(*) filter (where com_permissao)                                          as n_com_permissao,
         bool_or(wa_nivel in ('found','candidate'))                                     as tem_wa_candidato,
         bool_or(wa_nivel = 'company_evidence')                                         as tem_wa_empresa,
         bool_or(wa_nivel = 'human_confirmed')                                          as tem_wa_humano,
         max(confianca) filter (where verificacao <> 'invalido')                        as confianca_max,
         max(created_at)                                                                as contato_mais_recente
    from c group by holder_id
)
select h.id as holder_id, h.nome_original as titular, h.tipo_provavel, h.uf, h.cnpj, h.cnpj_status,
       emp.razao_social, est.nome_fantasia,
       l.id as lead_id, l.status as lead_status, l.prioridade, l.score,
       pr.marcas, pr.processos,
       coalesce(agg.contatos, '[]'::jsonb) as contatos,
       coalesce(agg.n_contatos, 0) as n_contatos, coalesce(agg.n_whatsapp, 0) as n_whatsapp,
       coalesce(agg.n_telefone, 0) as n_telefone, coalesce(agg.n_email, 0) as n_email,
       coalesce(agg.n_pendentes, 0) as n_pendentes, coalesce(agg.n_invalidos, 0) as n_invalidos,
       coalesce(agg.n_bloqueados, 0) as n_bloqueados, coalesce(agg.n_com_permissao, 0) as n_com_permissao,
       coalesce(agg.tem_wa_candidato, false) as tem_wa_candidato,
       coalesce(agg.tem_wa_empresa, false) as tem_wa_empresa,
       coalesce(agg.tem_wa_humano, false) as tem_wa_humano,
       agg.confianca_max,
       exists (select 1 from suppression_list s
                where s.tipo = 'titular'
                  and s.valor_hash = encode(sha256(convert_to(h.holder_key, 'UTF8')), 'hex')) as titular_bloqueado,
       greatest(l.pesquisado_em, rr.ultima, agg.contato_mais_recente) as pesquisado_em
  from holders h
  left join leads l on l.holder_id = h.id and l.mesclado_em is null
  left join agg on agg.holder_id = h.id
  left join cnpj_estabelecimentos est on est.cnpj = h.cnpj
  left join cnpj_empresas emp on emp.cnpj_basico = left(h.cnpj, 8)
  left join lateral (
    select string_agg(distinct p.marca_nome, ', ') as marcas, string_agg(distinct p.numero_processo, ', ') as processos
      from process_holders ph join processes p on p.numero_processo = ph.numero_processo
     where ph.holder_id = h.id) pr on true
  left join lateral (
    select max(coalesce(r.finalizado_em, r.iniciado_em)) as ultima from research_runs r where r.holder_id = h.id) rr on true
 where l.id is not null or agg.holder_id is not null;
