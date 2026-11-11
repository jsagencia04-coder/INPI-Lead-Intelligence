# Arquitetura e decisões

## Decisões aprovadas (10/11/2026)

| Tema | Decisão |
|---|---|
| Prestador | Pessoa autônoma, não advogada (sem restrições da OAB sobre captação) |
| Titulares | PF e PJ (PF com salvaguardas LGPD, ver abaixo) |
| Base de CNPJ | Dump aberto da Receita Federal, ingerido localmente (Fase 4) |
| Busca web | Ferramenta de web search nativa da Claude API (sem scraping do Google) |
| Despachos de interesse | Publicação para oposição, exigências, indeferimentos e extinção por falta de pagamento da prorrogação |

## Fluxo

```
pg_cron (terça) ─▶ jobs ─▶ worker
  rpi.collect   (01) baixa a RPI de marcas, guarda o original + SHA-256      [determinístico]
  rpi.parse     (02) extrai processos, titulares, despachos, procurador     [determinístico]
  inpi.verify   (03) confirma situação e procurador de leads priorizados    [determinístico]
  research.*    (04) Claude + web search; todo dado precisa de evidência    [LLM]
  lead.validate (05) homônimos, CNPJ, deduplicação, confiança               [regras + LLM]
  sales.*       (06) segmento, prioridade, resumo, abordagem, relatório     [LLM]
```

O funil é o principal controle de custo: só chega à pesquisa web quem passou pelos
filtros de despacho, ausência de procurador e deduplicação por titular.

## Princípios implementados no schema

- **Chave do processo**: `processes.numero_processo` (texto numérico com CHECK).
- **Procurador em 4 estados**: `com_procurador`, `sem_na_rpi` (ausente na publicação, ainda
  não confirmado), `sem_confirmado` (confirmado no INPI) e `desconhecido`. Ausência
  só é considerada confirmada depois da verificação, que registra data e fonte.
- **Originais imutáveis**: `rpi_files`, `evidences` e `inpi_verifications` bloqueiam
  UPDATE/DELETE por trigger. O storage recusa sobrescrever um arquivo com conteúdo diferente.
- **Toda informação externa tem fonte**: `contacts.evidence_id` é NOT NULL.
- **Encontrado ≠ verificado**: `contacts.verificacao` vai de `encontrado` até `verificado_humano`.
- **Histórico**: `audit_log` registra antes/depois e o ator (usuário ou agente#job) de cada mudança.
- **Revisão humana**: `leads.precisa_revisao` é `true` por padrão; `review_tasks` serve a qualquer etapa.
- **Sem disparo automático**: `outreach_log.aprovado_por` é obrigatório.
- **LGPD**: `suppression_list` (opt-out, guarda só o hash), RLS em todas as tabelas.

## LGPD (titulares PF), a formalizar antes da Fase 4

- Base legal: legítimo interesse (art. 7º, IX), com LIA documentado.
- Coletar apenas dados profissionais públicos (sem CPF, endereço residencial ou dados sensíveis).
- Toda abordagem identifica a fonte do dado (RPI) e oferece opt-out.
- Política de retenção: leads sem conversão são anonimizados após um prazo a definir.

## Fase 2: importação da RPI (implementada)

**Fonte.** Índice em https://revistas.inpi.gov.br/rpi/. Para marcas, cada edição tem o
XML `txt/RM<N>.zip` (~10 MB, cerca de 38 mil processos) e o PDF em volumes
`pdf/Marcas<N>_I.pdf` e `_II.pdf` (~150 MB). O XML é a fonte estruturada. O PDF é baixado
e guardado como original apenas com `RPI_DOWNLOAD_PDF=true`, e não é interpretado: ele traz
o mesmo conteúdo do XML. Marcas não têm versão TXT.

**Estrutura real do XML.** Foi conferida na RPI 2914 e difere do manual v1.03 do INPI em
alguns pontos: `lista-classe-nice` envolve as classes, `dados-de-madri` marca os processos
do Protocolo de Madri, e petições trazem `protocolo/requerente/procurador`.

**Procurador.** Só o `<procurador>` filho direto de `<processo>` conta. O procurador
dentro de `<protocolo>` é de quem peticionou (pode ser um oponente) e é guardado em
`publications.protocolos`, sem afetar o status do titular. Na RPI 2914, 65% dos processos
tinham procurador.

**Marca ausente.** Despachos de indeferimento, exigência e extinção normalmente não trazem
o nome da marca. Ele é preenchido quando o processo aparece em outra edição, ou na
Fase 3 (consulta ao INPI).

**Catálogo de despachos.** Os 66 códigos e nomes vieram literalmente do XML da RPI 2914.
Os ativos para leads são:

| Código | Despacho | Categoria |
|---|---|---|
| IPAS009 | Publicação de pedido de registro para oposição (exame formal concluído) | oposição |
| IPAS136, IPAS267, IPAS005, IPAS192 | Exigências de mérito, formal e de conformidade | exigência |
| IPAS024 | Indeferimento do pedido | indeferimento |
| IPAS161 | Extinção de registro pela expiração do prazo de vigência | extinção (prorrogação) |

Os arquivamentos (IPAS139, 157, 106, 289, 404) ficaram catalogados, mas desligados. Você
pode ligá-los na tela Despachos. Códigos novos entram automaticamente como "outro", com
tarefa de revisão.

**Oportunidade.** É gerada por publicação de despacho ativo. Fica `elegivel` quando não há
procurador e o titular é brasileiro e não vem do Protocolo de Madri. Caso contrário, fica
`descartada` com o motivo. Se uma edição posterior revelar procurador, as oportunidades
anteriores do processo são descartadas, com registro no histórico.

**Economia.** O escopo padrão `alvo` grava só os processos com despacho ativo (~17% da
edição). O zip original fica guardado, e "Reprocessar" com escopo `todos` reconstrói tudo.
No teste de carga, uma edição de 38 mil processos levou ~10 s em Postgres local, com
~190 MB de memória.

**Agendamento.** A tabela `schedules` é lida pelo worker (portável: funciona no Postgres
local e no Supabase, sem precisar de pg_cron). Padrão: `rpi.discover` a cada 3 h.

**Requisito de rede.** O worker precisa acessar `revistas.inpi.gov.br`. Se ele rodar num
servidor que o INPI bloqueie, use o upload manual.

## Fase 3: verificação no INPI (Agente 03)

- **Fonte:** pePI, com consulta anônima por número de processo. O fluxo (login anônimo,
  pesquisa e detalhe) e a estrutura HTML foram conferidos em 10/11/2026.
- **Confirmação de ausência de procurador:** só vale quando a seção "Representante Legal"
  existe e está vazia (`sem_confirmado`). Página incompleta resulta em `desconhecido`.
- **Captcha e bloqueio:** nunca são contornados. A consulta pausa a fila por 2 h e abre uma
  revisão em *Sistema*.
- **Divergências não são resolvidas sozinhas:** procurador na RPI sem representante no
  INPI, ou titular diferente (possível transferência), viram revisão humana.
- **Guarda:** HTML original com SHA-256, URL e data em `inpi_verifications`. A marca
  ausente na RPI é completada pelo INPI.

## Fase 4: CNPJ e pesquisa web (Agente 04)

- **Receita:** WebDAV público, com pastas mensais de `Empresas*.zip` e
  `Estabelecimentos*.zip`. A varredura guarda só as empresas cujo nome normalizado
  coincide com titulares pendentes. Remove o prefixo de CNPJ dos MEIs.
- **Vínculo:** nome idêntico + mesma UF, com exatamente 1 matriz ativa. Mais de uma vira
  `ambiguo` + revisão, e uma pessoa escolhe.
- **Contatos da Receita:** telefone e e-mail cadastrais entram como contatos `receita`.
  O e-mail cadastral não sobe sozinho para validado, porque pode ser do contador.
- **Pesquisa:** feita com Claude (`claude-sonnet-5-5`) + `web_search` (US$ 10 por 1.000
  buscas), com um máximo de 4 buscas por titular. Claude precisa registrar URL e trecho
  literal; contato cujo valor não aparece no trecho é descartado. O prompt proíbe dados
  pessoais (LGPD).
- **Economia:** só pesquisa leads de prioridade alta ou média com ausência de procurador
  confirmada, sem pesquisa nos últimos 60 dias. Há orçamento semanal
  (`IA_ORCAMENTO_SEMANAL_USD`), e o custo de cada chamada fica em `llm_calls`.

## Pesquisa gratuita (Agente 04 sem IA)

- **Agente `research.free`:** encontra o site oficial sem buscador e sem IA. Usa o domínio
  do e-mail da Receita (exceto provedores gratuitos), os sites já cadastrados e endereços
  prováveis a partir do nome fantasia e das marcas (`marca.com.br`, `marca.com`).
- **Vínculo obrigatório:** alguma página precisa citar o CNPJ (confiança 0,85), a razão
  social (0,7) ou o nome fantasia (0,65). Em domínio "adivinhado", citar só a marca não
  basta, porque pode ser outra empresa com nome parecido.
- **Extração:** `mailto:`, `tel:`, links de WhatsApp e redes sociais, e e-mails e telefones
  no texto, sempre com URL e trecho de origem.
- **Educação com os sites:** segue o `robots.txt`, pausa 1 s entre requisições, lê no
  máximo 6 páginas por site e revisita cada titular só a cada 60 dias.
- **Revalidação:** um site fora do ar (4xx/5xx) não invalida o contato. Só invalida quando
  a página abre e o valor sumiu.

## Fase 5: validação e qualificação (Agentes 05 e 06)

- **Níveis do contato:** `encontrado` → `formato_ok` → `dominio_ok` (valor reencontrado
  na página citada e, para e-mail, domínio com MX) → `verificado_humano`, ou `invalido`.
- **Lead:** 1 por titular. Titulares com o mesmo CNPJ são mesclados (`mesclado_em`).
- **Score explicável** (`score_detalhes`), somando pontos:

  | Critério | Pontos |
  |---|---|
  | Categoria | indeferimento 40, exigência 35, extinção 30, oposição 20 |
  | Urgência do prazo estimado | até +20, ou −15 se vencido |
  | Contatos | validados 20, só encontrados 8 |
  | Mais de um processo | até +15 |
  | Pessoa jurídica | +5 |
  | Ausência de procurador confirmada | +10 (sem confirmação: −10) |
  | CNPJ ambíguo | −10 |

  Prioridade: alta a partir de 60 pontos, média a partir de 40.
- **Prazos:** estimativa de 60 dias corridos da publicação (LPI), sempre identificada como
  estimativa.
- **Resumo e abordagem:** Claude Haiku usa só os fatos do banco. Sem chave, usa um texto fixo.
- **Prospecção:** só depois de aprovação humana, e só registro. O sistema nunca envia nada.
  O opt-out guarda apenas o hash e bloqueia contato e exportação.

## Fase 6: relatórios e exportação

- O relatório semanal por edição é salvo na tabela `reports`.
- A exportação em Excel ou CSV inclui só contatos validados, com as URLs de origem, e
  registra quem exportou em `exports_log`.

## Fase 7: testes e implantação

- 46 testes. `test_fases3a7.py` roda o pipeline inteiro com INPI, Receita, Claude e sites
  simulados.
- Docker (API e worker na mesma imagem), `docker-compose.prod.yml`, `render.yaml`, CI com
  build das imagens.
- **Operação:** a tela Operação (`/api/metrics`) mostra fila, falhas, custo de IA e liga ou
  desliga os agendamentos.

## Limites conhecidos

- As mudanças de layout do pePI e da RPI são detectadas (revisão ou erro), mas exigem
  ajuste no parser.
- O layout de colunas do CNPJ segue o dicionário de dados da Receita. Confira na primeira
  carga real.
- Os preços dos modelos estão na configuração e precisam ser conferidos em anthropic.com/pricing.
