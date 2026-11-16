-- V2.9 · Extração paralela PDF + XML da RPI de marcas.
--
-- O INPI publica o PDF (Volume I: pedidos, oposições, indeferimentos; Volume II: concessões) e o XML de marcas em
-- horários diferentes. Cada arquivo passa a ser monitorado e processado de forma independente:
--   · o PDF do Volume I começa a ser lido assim que aparece, sem esperar o XML, e já gera leads (SC primeiro);
--   · o XML, quando chega, complementa e valida (dados estruturados, marca, classes) e é conciliado com o PDF.
-- Nada é apagado: o texto lido do PDF fica guardado, as divergências ficam registradas para revisão e toda
-- publicação guarda a origem (pdf ou xml). Migration incremental, sem alteração destrutiva.

-- 1. Monitoramento por arquivo (horário de detecção, download, processamento, registros, erro)
create table if not exists rpi_fontes (
  id                    bigserial primary key,
  edition_id            bigint      not null references rpi_editions(id),
  fonte                 text        not null check (fonte in ('pdf_i', 'pdf_ii', 'xml')),
  url                   text,
  status                text        not null default 'detectado'
                        check (status in ('detectado', 'baixando', 'baixado', 'processando', 'processado', 'erro',
                                          'ignorado')),
  detectado_em          timestamptz not null default now(),
  baixado_em            timestamptz,
  processamento_inicio  timestamptz,
  processado_em         timestamptz,
  tempo_download_s      numeric,
  tempo_processamento_s numeric,
  rpi_file_id           bigint      references rpi_files(id),
  paginas               int,
  registros             int,         -- entradas lidas no arquivo
  registros_alvo        int,         -- oposições, indeferimentos, deferimentos parciais...
  tentativas            int         not null default 0,
  ultimo_erro           text,
  etapa                 text,        -- texto curto do que está acontecendo agora
  uf_em_processamento   text,        -- estado sendo qualificado agora (SC → RS → PR → demais)
  detalhes              jsonb       not null default '{}',
  atualizado_em         timestamptz not null default now(),
  unique (edition_id, fonte)
);
create index if not exists rpi_fontes_status_idx on rpi_fontes (status, fonte);
alter table rpi_fontes enable row level security;

-- 2. Registros lidos do PDF (texto original preservado, com página)
create table if not exists rpi_pdf_registros (
  id               bigserial primary key,
  edition_id       bigint      not null references rpi_editions(id),
  rpi_file_id      bigint      references rpi_files(id),
  numero_processo  text        not null,
  despacho_nome    text        not null,
  despacho_codigo  text,        -- pelo nome no catálogo oficial (despacho_types); nulo quando o nome não é conhecido
  categoria        text,
  secao            text,
  titulares        jsonb       not null default '[]',
  uf               text,        -- UF do primeiro titular brasileiro
  procurador       text,
  pagina           int,
  texto            text        not null,   -- trecho original, como saiu do PDF
  campos           jsonb       not null default '{}',
  lote_uf          text,        -- lote de qualificação (SC, RS, PR, DEMAIS)
  importado_em     timestamptz,
  criado_em        timestamptz not null default now(),
  unique (edition_id, numero_processo, despacho_nome)
);
create index if not exists rpi_pdf_registros_lote_idx on rpi_pdf_registros (edition_id, lote_uf, importado_em);
alter table rpi_pdf_registros enable row level security;

-- 3. Conciliação PDF × XML (uma linha por processo e despacho de interesse comercial)
create table if not exists rpi_reconciliacao (
  id               bigserial primary key,
  edition_id       bigint      not null references rpi_editions(id),
  numero_processo  text        not null,
  despacho_codigo  text        not null,
  situacao         text        not null check (situacao in ('confere', 'so_pdf', 'so_xml', 'divergente')),
  diferencas       jsonb       not null default '{}',
  pdf_registro_id  bigint      references rpi_pdf_registros(id),
  criado_em        timestamptz not null default now(),
  atualizado_em    timestamptz not null default now(),
  revisado_em      timestamptz,
  revisado_por     text,
  unique (edition_id, numero_processo, despacho_codigo)
);
create index if not exists rpi_reconciliacao_situacao_idx on rpi_reconciliacao (edition_id, situacao);
alter table rpi_reconciliacao enable row level security;

-- 4. Origem de cada publicação. O XML oficial substitui o texto vindo do PDF (o original do PDF continua em
--    rpi_pdf_registros); o contrário nunca acontece.
alter table publications add column if not exists fonte text not null default 'xml';
do $$ begin
  alter table publications add constraint publications_fonte_check check (fonte in ('xml', 'pdf'));
exception when duplicate_object then null; end $$;

-- 5. Liga a leitura antecipada do PDF (pode ser desligada sem deploy)
insert into app_config (chave, valor) values ('rpi_pdf_primeiro', 'true') on conflict (chave) do nothing;
