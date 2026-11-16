# V2.11: limpeza dos dados operacionais e nova operação a partir da RPI de 17/11/2026

Estado em 16/11/2026: implementado e validado em ambiente de teste. **Ainda não foi executado em produção.**

## 1. Como executar a limpeza com segurança

```sh
# 1. Simulação: só conta, não apaga nada
python -m app.reset --simular

# 2. Limpeza: exige a variável de confirmação
CONFIRM_RESET=RESET_INPI python -m app.reset --proxima "2026-11-17 00:00:01" --edicao-minima 2915
```

- **Tudo numa única transação, com rollback total.** A limpeza é desfeita inteira se:
  - alguma tabela não estiver classificada;
  - alguma tabela preservada depender de uma operacional (o TRUNCATE é feito sem CASCADE);
  - a validação final encontrar uma linha restante.
- **Uma limpeza por vez.** Um bloqueio no banco (`pg_try_advisory_xact_lock`) impede duas execuções juntas.
- **Importações bloqueadas.** Durante a limpeza, a chave `importacao_bloqueada` faz os agentes da RPI esperarem 2 minutos e tentarem de novo.
- **Sequências reiniciadas.** As tabelas limpas voltam a contar os IDs do 1.
- **Registro.** Cada limpeza gera uma linha em `system_resets`, com data e hora, autor e quantas linhas saíram de cada tabela.
- **Variáveis de ambiente:**
  - `CONFIRM_RESET=RESET_INPI`: só no comando, nunca fixa no `.env`;
  - `RPI_EDICAO_MINIMA=2915`: no `.env`, para a operação começar na próxima Revista.

## 2. Estado gravado após a limpeza (`app_config`, em `GET /api/sistema/status`)

| Chave | Valor |
|---|---|
| `system_status` | `waiting_for_next_issue`. Vira `operational` na primeira importação concluída |
| `last_publication_id`, `last_successful_import`, `last_import_status` | nulos. São preenchidos a cada importação (`success` ou `failed`) |
| `next_scheduled_run` | `2026-11-17T00:00:01-03:00` (03:00:01 UTC) |
| `timezone` | `America/Sao_Paulo` |

## 3. Agendamento

O agendador já existente (tabela `schedules`) usa o fuso IANA `America/Sao_Paulo`. Para disparar uma vez só com vários workers, ele usa `FOR UPDATE SKIP LOCKED` e a chave `dedupe_key` dos jobs.

A limpeza ajusta o agendamento `rpi-terca` (verificação da RPI a cada 10 minutos, às terças e quartas):

- a janela passa a começar às **00:00:01**;
- o primeiro disparo fica em **17/11/2026 00:00:01** no horário de São Paulo.

**Novas tentativas:**

- **XML ou PDF ainda não publicados:** o arquivo é procurado de novo a cada 10 minutos, e o download com erro é repetido com espera crescente.
- **Falha definitiva:** o sistema marca `last_import_status=failed`, registra o evento `rpi.failed` e abre uma tarefa de revisão (`review_tasks`).

## 4. Serviços pedidos e onde estão

| Serviço | Implementação |
|---|---|
| `resetOperationalData()` | `app.reset.reset_operational_data` e a função SQL `reset_operational_data` |
| `detectNewInpiPublication()` | job `rpi.discover`, que registra cada arquivo em `rpi_fontes` |
| `downloadPublicationFiles()` | `rpi.collect` (XML) e `rpi.pdf` (PDF). Cada original fica guardado com sha256 e o mesmo hash não é gravado duas vezes |
| `processPublicationPdf()` | `rpi.pdf` e `rpi.pdf_importar` (SC, RS, PR e demais) |
| `processPublicationXml()` | `rpi.parse` |
| `mergePdfAndXmlData()` | `rpi_pdf.conciliar`: o XML oficial substitui o texto do PDF e as divergências viram revisão |
| `classifyTrademarkOpportunity()` | importador + `servicos.sincronizar`. Classes: manifestação contra oposição, recurso contra indeferimento, oposição apresentada |
| `generateLeads()` | `rpi.semana` → `leads.build`. A busca de contato é automática: Receita (CNPJ, endereço, cidade, UF), sites e pePI. Um lead sem contato fica como "contato ainda não localizado" |
| `updateStateDashboard()` | mapa, filtros por estado e indicadores, calculados direto do banco |
| `registerImportRun()` / `sendFailureAlert()` | `app.reset.registrar_importacao` |
| `retryPendingXml()` | `rpi-terca` + repetição dos jobs (`rpi_fontes.status`) |

**Regras contra duplicidade:**

- edição única (`rpi_editions.numero`);
- arquivo único pelo hash (`rpi_files.sha256`);
- processo único (`processes.numero_processo`);
- publicação única por processo, edição e despacho;
- titular único pela chave nome normalizado + UF + país;
- oportunidade única por processo, edição e despacho.

## 5. Tabelas

O relatório completo de cada execução fica em `system_resets.relatorio`.

**Limpas, 36 tabelas:**

| Grupo | Tabelas |
|---|---|
| RPI | `rpi_editions`, `rpi_files`, `rpi_fontes`, `rpi_pdf_registros`, `rpi_reconciliacao`, `rpi_operacoes`, `publications`, `corte_rpi_backup` |
| Processos e oportunidades | `processes`, `process_holders`, `process_peticoes`, `inpi_verifications`, `opportunities`, `oportunidades_servico` |
| Titulares, contatos e pesquisa | `holders`, `contacts`, `evidences`, `research_runs`, `llm_calls` |
| Leads e pipeline | `leads`, `lead_processes`, `lead_notes`, `lead_stage_history`, `pipeline_processos`, `outreach_log` |
| WhatsApp e autorizações | `wa_messages`, `wa_rascunhos`, `wa_auditoria`, `consents`, `consent_requests` |
| Execução e painel | `jobs`, `agent_events`, `review_tasks`, `reports`, `exports_log`, `wa_webhook_events` |

**Preservadas:**

- `app_users`;
- `app_config`;
- `schema_migrations`;
- `schedules`;
- `despacho_types`;
- `pipeline_etapas`;
- `uf_prioridade`;
- `feriados`;
- `wa_modelos` e `wa_modelos_historico`;
- `wa_contas`;
- `suppression_list`: quem pediu para sair continua bloqueado;
- `audit_log`;
- a base pública da Receita: `cnpj_empresas`, `cnpj_estabelecimentos` e `cnpj_municipios`;
- `system_resets`.

**Arquivos em disco:** os PDFs e XMLs originais continuam no volume de dados como cópia de segurança. Só as referências no banco são removidas.

## 6. Testes

`tests/test_reset_v211.py`:

- toda tabela está classificada;
- a limpeza é recusada sem confirmação;
- a limpeza completa preserva usuários, modelos, opt-out e agendamentos;
- as sequências reiniciam;
- o status e a próxima execução ficam corretos (`2026-11-17T00:00:01-03:00` = 03:00:01 UTC);
- o painel fica zerado;
- a reimportação após a limpeza não cria duplicidade;
- o bloqueio de importação funciona;
- falhas geram alerta.

PDF e XML em momentos diferentes: `tests/test_extracao_v29.py`.
