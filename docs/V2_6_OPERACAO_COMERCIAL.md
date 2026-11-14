# V2.6: correção da coleta da RPI e organização comercial

Estado em 14/11/2026.

| Item | Situação |
|---|---|
| Código | Implementado e testado: backend com 191 testes aprovados (16 novos); frontend com 34 testes, lint, tipos e build sem problemas |
| Produção | **Somente a correção emergencial** (releitura da RPI 2914, autorizada). A V2.6 **não foi publicada** |
| Evolution API | Não foi tocada |

## 1. Diagnóstico (Fase A)

### Causa das oposições perdidas

A RPI **2914** (10/11/2026) traz **481** despachos IPAS423 ("Notificação de oposição"). Nenhum deles estava no banco.

- A edição foi lida em 12/11, às 00:14, quando o IPAS423 ainda não gerava oportunidade.
- A releitura automática (tarefa nº 6201) ficou na fila desde 12/11, às 22:31, atrás destas tarefas mais prioritárias:
  - 9.400 pesquisas gratuitas;
  - 4.402 verificações no INPI;
  - 294 verificações já mortas por tempo esgotado.
- Nenhum erro foi registrado: foi uma **falha silenciosa da fila**, não do parser.
- **Correção emergencial em 14/11:** a prioridade da tarefa foi elevada, com a sua autorização. As 481 oposições foram gravadas, e 157 ficaram elegíveis. O número bate com a contagem feita direto no XML oficial.

### Outros achados

- **Edições no banco:** 2908 a 2914. Com o corte na 2914, as oportunidades da 2908 à 2913 saem da operação, mas não são apagadas.
- **Procurador:** já havia 4 situações internas. Faltava a separação "erro de identificação" e o uso de um único critério em todas as telas.
- **Prioridade dos estados:** a tabela `uf_prioridade` já fixava SC, RS e PR nas três primeiras posições. Faltava aplicar a ordem nas listas, com o tipo de despacho antes do estado.
- **Pipeline:** as 17 etapas já existiam. O lead é por titular, todos entravam automaticamente no funil e não existia vínculo com o processo nem o botão no mapa.

## 2. Códigos oficiais validados (XML da RPI 2914)

| Código | Descrição oficial | Ocorrências | Prioridade | Finalidade |
|---|---|---|---|---|
| IPAS423 | Notificação de oposição | 481 | **1** | Manifestação à oposição |
| IPAS024 | Indeferimento do pedido | 1.769 | **2** | Avaliação e recurso |
| IPAS658 | Indeferimento do pedido (em retificação) | 1 | 2 | Avaliação e recurso |
| IPAS774 | Indeferimento de designação | 31 | 2 | Avaliação e recurso (todos estrangeiros/Madri) |
| IPAS781 | Deferimento parcial de designação | — | 2 | Avaliação e recurso |
| IPAS009 | Publicação de pedido de registro para oposição | 10.290 | — | **Não é oposição apresentada** |
| IPAS756 | Publicação para oposição (designação) | 773 | — | **Não é oposição apresentada** |

O catálogo (`despacho_types`) ganhou quatro campos:

- `prioridade_comercial`;
- `finalidade_comercial`;
- `vigencia`;
- `fonte_validacao`.

## 3. Comparativo da RPI 2914 (XML oficial × sistema)

| | No XML | Gravados | Com procurador | Estrangeiro | **Elegíveis** | SC | RS | PR |
|---|---|---|---|---|---|---|---|---|
| Oposições (IPAS423) | 481 | 481 | 323 | 21 | **157** | 12 | 11 | 10 |
| Indeferimentos (IPAS024) | 1.769 | 1.769 | 1.162 | 38 | **607** | 36 | 25 | 44 |

- **Descartados por procurador:** 323 oposições e 1.162 indeferimentos.
- **Representação desconhecida ou com erro:** 0 nesta edição.

## 4. O que mudou

### Banco

Migration `20261117000017_operacao_comercial_v26.sql`, incremental e reversível:

- **Edição mínima:**
  - `app_config.rpi_edicao_minima` e a função `rpi_edicao_minima()`;
  - `aplicar_corte_rpi()`, idempotente: guarda o estado anterior em `corte_rpi_backup` e devolve tudo se o mínimo baixar.
- **Catálogo:**
  - prioridade e fonte por código;
  - `prioridade_servico()` e `prioridade_categoria()`;
  - `catalogo_versao()`.
- **Edições:** `rpi_editions.catalogo_versao` e `rpi_editions.auditoria` (relatório de cada edição).
- **Procurador:** novo estado `erro_identificacao` e a função `procurador_situacao()`, que devolve um destes 4 estados:
  - `SEM_PROCURADOR_CONFIRMADO`;
  - `COM_PROCURADOR`;
  - `PROCURADOR_DESCONHECIDO`;
  - `ERRO_NA_IDENTIFICACAO`.
- **Pipeline:**
  - `pipeline_etapas`: 17 etapas em 5 fases, cada uma com cor, descrição e regra de transição;
  - `pipeline_processos`: vínculo processo → lead, um único por processo;
  - `leads.pipeline_incluido_em`.
- **Fila:** as tarefas da RPI e da montagem de leads que estavam esperando foram promovidas.

### Backend

- **`app/comercial.py`** (novo): regras centralizadas.
  - edição mínima (`RPI_EDICAO_MINIMA` ou `MIN_RPI_EDITION`, padrão 2914);
  - prioridade dos despachos;
  - SC=1, RS=2, PR=3;
  - os estados do procurador.
- **`app/config.py`:** `rpi_edicao_minima`, sincronizada no banco na subida da API e do worker.
- **`app/jobs/queue.py`:**
  - teto de prioridade para `rpi.*`, `leads.build` e `servicos.analisar`;
  - uma tarefa repetida passa a herdar a prioridade mais alta.
- **`app/agents/rpi.py`:**
  - corte aplicado na descoberta, no download, na leitura e no histórico;
  - releitura automática quando o catálogo muda;
  - relatório de auditoria por edição: processos lidos, oposições e indeferimentos (encontrados × gravados), representação, duplicidades, tempo e divergências.
- **`app/rpi/xml_parser.py` e `app/rpi/importer.py`:**
  - `<procurador>` vazio vira erro de identificação;
  - representação desconhecida ou com erro não entra;
  - contagens de auditoria.
- **`app/api/rpi_routes.py`:** envio manual e reprocessamento recusam edição abaixo do mínimo.
- **`app/api/servicos_routes.py`:**
  - entram só oportunidades elegíveis, de edição ≥ mínima e sem procurador confirmado;
  - ordem: prioridade do despacho → estado (sem UF por último) → publicação → edição → número.
- **`app/api/lead_routes.py`:** `operacional=true` e `ordem=comercial`, usados pelo mapa.
- **`app/api/mapa_routes.py`:**
  - edições operacionais;
  - leads prioritários com a oposição primeiro;
  - SC, RS e PR a partir da regra central.
- **`app/api/pipeline_routes.py`:**
  - `GET` e `POST /api/pipeline/processo/{numero}`: ficha e inclusão idempotente;
  - filtros `lead_id` e `adicionados`;
  - etapas com fase, cor e regra;
  - "Interessado", "Reunião", "Proposta" e "Negociação" exigem evidência de conversa (resposta recebida ou contato registrado).
- **`app/api/comercial_routes.py`** (novo): `/api/comercial/indicadores` e `/api/rpi/{n}/auditoria`.

### Frontend

- **Mapa:**
  - indicadores da coleta, com alertas de edição incompleta;
  - comparativo SC × RS × PR;
  - **Oportunidades priorizadas por processo**, com filtros Todos, SC, RS e PR combinados com o tipo de despacho;
  - botão **+ Pipeline** em cada processo e em cada lead.
- **Janela Gestão comercial** (`components/adicionar-pipeline.tsx`):
  - mostra titular, marca, processo, estado, despacho, RPI, procurador, contato, consentimento e etapa;
  - permite escolher a etapa inicial;
  - avisa "Lead adicionado ao Pipeline com sucesso" ou "Este processo já está cadastrado no Pipeline";
  - links **Abrir no Pipeline** e **Visualizar lead existente**.
- **Detalhe do lead:** botão **+ Adicionar ao Pipeline** em cada processo.
- **Pipeline:**
  - fases numeradas e cores por etapa;
  - filtro "Somente adicionados ao Pipeline";
  - `?lead=ID` abre o lead direto na etapa.
- **RPI:** tabela **Auditoria da coleta** por edição.

## 5. Testes (`backend/tests/test_operacao_v26.py`)

| Área | Casos |
|---|---|
| RPI | 2913 recusada (envio, leitura, coleta e reprocessamento); 2914, 2915 e 2916 aceitas; a descoberta ignora as anteriores; o histórico sai do mapa e dos indicadores sem ser apagado; o corte é reversível |
| Oposição | Código oficial e fonte; 40 de 40 oposições capturadas; nenhum IPAS009 vira oposição; auditoria "completa"; catálogo alterado → alerta e releitura, que passa na frente de 50 pesquisas na fila |
| Procurador | Campo ausente → elegível; procurador presente → excluído; elemento vazio → erro (não vira "sem"); desconhecido → excluído |
| Geografia | Oposição SC, RS, PR, SP e sem UF; depois indeferimento SC, RS, PR; filtro por estado combinado com o despacho; comparativo SC × RS × PR; lista de leads do mapa na ordem comercial |
| Pipeline | Inclusão; duplicidade detectada; segundo processo do mesmo titular sem duplicar o lead; notas e histórico preservados; abre no lead certo; etapa manual bloqueada sem evidência e liberada com ela; etapa atual preservada; opt-out bloqueado; 17 etapas em 5 fases |
| Fila | Teto de prioridade e promoção de tarefa repetida |
| Regressão | Toda a suíte anterior: 175 testes |

## 6. Rollback

| Situação | O que fazer |
|---|---|
| Voltar a mostrar as edições anteriores | `RPI_EDICAO_MINIMA=<edição>` e redeploy. O corte devolve sozinho o que estava em `corte_rpi_backup` |
| Retirar a V2.6 | Redeploy do commit anterior (85307641). A migration só acrescenta tabelas, colunas e funções; o código antigo ignora tudo isso |
| Desfazer o vínculo com o pipeline | `pipeline_processos` e `pipeline_incluido_em` são acréscimos; a etapa do lead não é alterada ao incluir |

## 7. Pendências

- Publicar a V2.6, depois da sua autorização.
- **Fila de verificações no INPI:** são 4.402 na fila e 294 mortas por tempo esgotado. Não impede a operação, mas a confirmação pelo site do INPI segue lenta. Recomendo revisar o volume de pesquisas em massa (9.400 na fila).
- **Primeira releitura após o deploy:** a 2914 será relida uma vez (catálogo sem versão registrada) para gerar o relatório de auditoria. A releitura é idempotente.
